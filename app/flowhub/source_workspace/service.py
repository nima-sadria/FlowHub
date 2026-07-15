"""Application services for source mappings and internal FlowHub Sheets."""

from __future__ import annotations

import base64
import csv
import io
import json
import re
import uuid
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any

import openpyxl
from fastapi import HTTPException, status
from sqlalchemy import tuple_
from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.setup.service import AppConfigService
from app.flowhub.source_workspace.formula import (
    FORMULA_ENGINE_VERSION,
    FormulaResult,
    calculate_sheet,
    column_name,
)
from app.flowhub.source_workspace.models import (
    FlowHubSheet,
    SheetCell,
    SheetColumn,
    SheetImportJob,
    SheetRevision,
    SheetRow,
    SourceChannelFieldMapping,
    SourceChannelMapping,
    SourceDataQualityIssue,
    SourceDataQualityScan,
    SourceDataQualityScanSource,
    SourceFieldMapping,
    SourceMappingRevision,
    SourceProfile,
    SourceWorksheetChannelFieldMapping,
    SourceWorksheetChannelMapping,
    SourceWorksheetFieldMapping,
    SourceWorksheetRule,
    SourceWorksheetRuleSet,
)
from app.flowhub.source_workspace.repositories import (
    DataQualityRepository,
    SheetRepository,
    SourceRepository,
)
from app.flowhub.sources.spreadsheet_source import (
    SOURCE_ID as LEGACY_EXTERNAL_SOURCE_ID,
)
from app.flowhub.sources.spreadsheet_source import (
    SourceImportResult,
    SpreadsheetSourceReadService,
    normalize_source_mapping,
)
from app.flowhub.unified_workspace.domain import ApplyState, ReviewState, checksum, utcnow
from app.flowhub.unified_workspace.events import (
    DomainEvent,
    DomainEventBus,
    PersistenceAuditSubscriber,
)
from app.flowhub.unified_workspace.models import (
    ApplyJob,
    CanonicalProduct,
    ChannelCache,
    Listing,
    Review,
    UnifiedWorkspace,
    WorkspaceChannel,
    WorkspaceSnapshot,
)

MAX_SHEET_ROWS = 10_000
MAX_SHEET_COLUMNS = 200
MAX_IMPORT_BYTES = 20 * 1024 * 1024
SOURCE_FIELDS = {"name", "source_key", "category", "brand", "cost"}
CHANNEL_FIELDS = {"external_id", "price", "stock", "status"}
REFERENCE_TYPES = {"column_letter", "header_name", "column_id", "disabled"}
DEFAULT_VALUE_POLICY = {
    "blank": "no_change",
    "x": "unavailable",
    "dash": "no_change",
    "zero": "explicit_zero",
    "formula": "calculated_value",
    "invalid": "blocked",
}


def _id() -> str:
    return str(uuid.uuid4())


def _clean_name(value: object, fallback: str) -> str:
    text = " ".join(str(value or "").strip().split())
    return text[:240] or fallback


def _unprocessable(code: str, message: str, details: dict[str, Any] | None = None) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        {"code": code, "message": message, "details": details or {}},
    )


class SourceWorkspaceService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.sources = SourceRepository(db)
        self.sheets = SheetRepository(db)
        self.issues = DataQualityRepository(db)

    # -- Source and Mapping -------------------------------------------------

    def list_sources(self, user: FlowHubUser) -> dict[str, Any]:
        return {"items": [self._source_shape(item) for item in self.sources.list_for_user(user.id)]}

    def available_channels(self) -> dict[str, Any]:
        self._ensure_channels()
        channels = (
            self.db.query(WorkspaceChannel)
            .order_by(WorkspaceChannel.name, WorkspaceChannel.id)
            .all()
        )
        return {
            "items": [
                {
                    "channelId": item.id,
                    "name": item.name,
                    "connectorType": item.connector_type,
                    "capabilityVersion": item.capability_version,
                    "capabilities": item.capabilities_json,
                    "enabled": item.enabled,
                    "implementationState": item.implementation_state,
                    "available": item.enabled and item.implementation_state == "implemented",
                }
                for item in channels
            ]
        }

    def create_source(
        self,
        *,
        name: str,
        source_kind: str,
        external_source_id: str | None,
        worksheet_mode: str,
        worksheet_name: str | None,
        data_start_row: int,
        user: FlowHubUser,
    ) -> dict[str, Any]:
        if source_kind not in {"flowhub_sheet", "imported_sheet", "external"}:
            raise _unprocessable("SOURCE_KIND_INVALID", "Unsupported Source kind.")
        if source_kind == "external" and not external_source_id:
            raise _unprocessable(
                "EXTERNAL_SOURCE_REQUIRED", "External Sources require an existing Source identity."
            )
        self._validate_worksheet(worksheet_mode, worksheet_name, data_start_row)
        source = SourceProfile(
            id=_id(),
            name=_clean_name(name, "FlowHub Source"),
            source_kind=source_kind,
            external_source_id=external_source_id,
            worksheet_mode=worksheet_mode,
            worksheet_name=worksheet_name,
            data_start_row=data_start_row,
            owner_user_id=user.id,
            status="active",
            version=1,
        )
        self.db.add(source)
        self.db.flush()
        if source_kind in {"flowhub_sheet", "imported_sheet"}:
            self.db.add(
                FlowHubSheet(
                    id=_id(),
                    source_id=source.id,
                    name=source.name,
                    owner_user_id=user.id,
                    current_version=0,
                )
            )
        self.db.commit()
        return self._source_shape(source)

    def get_source(self, source_id: str, user: FlowHubUser) -> dict[str, Any]:
        source = self._owned_source(source_id, user)
        result = self._source_shape(source)
        mapping = self.sources.latest_mapping(source.id)
        result["mapping"] = self._mapping_shape(mapping) if mapping else None
        result["legacyMapping"] = self._legacy_mapping_shape(source) if mapping is None else None
        sheet = self.sheets.for_source(source.id)
        result["sheetId"] = sheet.id if sheet else None
        if mapping is not None:
            _, _, rules = self._worksheet_rule_configs(mapping)
            result["configuredWorksheets"] = sorted(
                item["worksheetName"]
                for item in rules
                if item["worksheetName"] != "*"
            )
        else:
            result["configuredWorksheets"] = []
        return result

    def source_lifecycle(self, source_id: str, user: FlowHubUser) -> dict[str, Any]:
        """Describe the safe lifecycle action without mutating the Source."""
        source = self._owned_source(source_id, user)
        return self._source_lifecycle_impact(source)

    def delete_or_archive_source(
        self,
        *,
        source_id: str,
        expected_source_version: int,
        confirmation_name: str,
        user: FlowHubUser,
    ) -> dict[str, Any]:
        """Delete a genuinely unused Source or archive it while preserving history.

        The Source row is locked before the optimistic checks and stays locked
        through the history decision, mutation, Audit append, and commit.
        """
        source = self._owned_source(source_id, user, lock=True)
        if source.version != expected_source_version:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {
                    "code": "SOURCE_VERSION_CONFLICT",
                    "message": "Source configuration changed before confirmation.",
                },
            )
        if confirmation_name.strip() != source.name:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {
                    "code": "SOURCE_CONFIRMATION_MISMATCH",
                    "message": "Enter the current Source name to confirm this action.",
                },
            )
        if source.status != "active":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {
                    "code": "SOURCE_ALREADY_ARCHIVED",
                    "message": "This Source is already archived.",
                },
            )

        impact = self._source_lifecycle_impact(source)
        if impact["action"] == "blocked":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {
                    "code": "SOURCE_ACTIVE_WORKSPACE",
                    "message": "Archive the active Workspace before removing this Source.",
                    "details": impact,
                },
            )

        source_metadata = {
            "sourceId": source.id,
            "sourceName": source.name,
            "sourceKind": source.source_kind,
            "sourceVersion": source.version,
            "protectedHistory": impact["protectedHistory"],
        }
        if impact["action"] == "archive":
            source.status = "disabled"
            source.version += 1
            source.updated_at = utcnow()
            self._append_source_lifecycle_audit(
                event_type="source_archived",
                user=user,
                reason="protected_source_history_preserved",
                metadata=source_metadata,
            )
            self.db.commit()
            return {
                "outcome": "archived",
                "sourceId": source.id,
                "sourceName": source.name,
                "source": self._source_shape(source),
                "impact": impact,
            }

        sheet = self.sheets.for_source(source.id)
        if sheet is not None:
            self.db.delete(sheet)
            self.db.flush()
        deleted_id = source.id
        deleted_name = source.name
        self.db.delete(source)
        self._append_source_lifecycle_audit(
            event_type="source_deleted",
            user=user,
            reason="unused_source_deleted",
            metadata=source_metadata,
        )
        self.db.commit()
        return {
            "outcome": "deleted",
            "sourceId": deleted_id,
            "sourceName": deleted_name,
            "source": None,
            "impact": impact,
        }

    def lock_source_for_workspace(
        self,
        source_id: str,
        user: FlowHubUser,
        *,
        expected_source_version: int,
    ) -> SourceProfile:
        """Fence Source lifecycle changes while a Workspace Snapshot is committed."""
        source = self._owned_source(source_id, user, require_active=True, lock=True)
        if source.version != expected_source_version:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {
                    "code": "SOURCE_VERSION_CONFLICT",
                    "message": "Source configuration changed during Workspace preparation.",
                },
            )
        return source

    async def list_source_worksheets(
        self, source_id: str, user: FlowHubUser
    ) -> dict[str, Any]:
        """Acquire a workbook once and return its worksheet identities."""
        source = self._owned_source(source_id, user, require_active=True)
        sheet = self.sheets.for_source(source.id)
        if sheet is not None:
            revision = self.sheets.latest_revision(sheet.id)
            return {
                "sourceId": source.id,
                "items": [
                    {
                        "name": "Sheet1",
                        "rowCount": revision.row_count if revision else 0,
                    }
                ],
                "sourceRevisionId": revision.id if revision else None,
            }
        imported = await self._read_external_source(source, user, manual=True)
        worksheets = imported.worksheets or {}
        return {
            "sourceId": source.id,
            "items": [
                {"name": name, "rowCount": len(rows)}
                for name, rows in worksheets.items()
            ],
            "sourceRevisionId": (
                f"external:{imported.snapshot.id}:{imported.snapshot.version_seq}"
            ),
        }

    def save_mapping(
        self,
        *,
        source_id: str,
        expected_source_version: int,
        worksheet_mode: str,
        worksheet_name: str | None,
        data_start_row: int,
        source_fields: list[dict[str, Any]],
        channel_mappings: list[dict[str, Any]],
        value_policy: dict[str, str],
        worksheet_rule_mode: str = "shared",
        selected_worksheet_names: list[str] | None = None,
        duplicate_product_policy: str = "block",
        worksheet_rules: list[dict[str, Any]] | None = None,
        user: FlowHubUser,
    ) -> dict[str, Any]:
        self._ensure_channels()
        source = self._owned_source(source_id, user, require_active=True, lock=True)
        if source.version != expected_source_version:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {"code": "SOURCE_VERSION_CONFLICT", "message": "Source configuration changed."},
            )
        if worksheet_rule_mode not in {"shared", "per_worksheet"}:
            raise _unprocessable(
                "WORKSHEET_RULE_MODE_INVALID",
                "Use shared or per-worksheet Source rules.",
            )
        normalized_selected_worksheets = self._normalize_selected_worksheet_names(
            selected_worksheet_names or []
        )
        if worksheet_rule_mode == "shared":
            if worksheet_mode == "all":
                if normalized_selected_worksheets:
                    raise _unprocessable(
                        "WORKSHEET_SELECTION_INVALID",
                        "Selected worksheet names require selected worksheet mode.",
                    )
                self._validate_worksheet("all", None, data_start_row)
                effective_worksheet_name = None
            else:
                if not normalized_selected_worksheets and str(worksheet_name or "").strip():
                    normalized_selected_worksheets = [str(worksheet_name).strip()]
                if not normalized_selected_worksheets:
                    raise _unprocessable(
                        "WORKSHEET_REQUIRED",
                        "Select at least one worksheet for the shared rules.",
                    )
                if (
                    worksheet_name
                    and str(worksheet_name).strip() not in normalized_selected_worksheets
                ):
                    raise _unprocessable(
                        "WORKSHEET_SELECTION_INVALID",
                        "The compatibility worksheet must be one of the selected worksheets.",
                    )
                for selected_name in normalized_selected_worksheets:
                    self._validate_worksheet("selected", selected_name, data_start_row)
                effective_worksheet_name = (
                    normalized_selected_worksheets[0]
                    if len(normalized_selected_worksheets) == 1
                    else None
                )
        else:
            if normalized_selected_worksheets:
                raise _unprocessable(
                    "WORKSHEET_SELECTION_INVALID",
                    "Per-worksheet rules define their worksheet selection directly.",
                )
            self._validate_worksheet(worksheet_mode, worksheet_name, data_start_row)
            effective_worksheet_name = worksheet_name
        if duplicate_product_policy not in {"block", "last_sheet_wins"}:
            raise _unprocessable(
                "DUPLICATE_PRODUCT_POLICY_INVALID",
                "Choose block or last-sheet-wins duplicate handling.",
            )
        normalized_source_fields = self._normalize_field_mappings(
            source_fields,
            SOURCE_FIELDS,
            required_fields={"name"} if worksheet_rule_mode == "shared" else set(),
        )
        normalized_channels = self._normalize_channel_mappings(
            channel_mappings,
            require_enabled=worksheet_rule_mode == "shared",
        )
        normalized_policy = self._normalize_value_policy(value_policy)
        normalized_worksheet_rules: list[dict[str, Any]]
        if worksheet_rule_mode == "shared":
            shared_rule_names = normalized_selected_worksheets or ["*"]
            normalized_worksheet_rules = [
                {
                    "worksheetName": shared_rule_name,
                    "enabled": True,
                    "dataStartRow": data_start_row,
                    "sourceFields": normalized_source_fields,
                    "channels": normalized_channels,
                    "valuePolicy": normalized_policy,
                }
                for shared_rule_name in shared_rule_names
            ]
        else:
            normalized_worksheet_rules = self._normalize_worksheet_rules(
                worksheet_rules or []
            )
        if source.source_kind == "external":
            external_references = [
                *[
                    field
                    for rule in normalized_worksheet_rules
                    for field in rule["sourceFields"]
                ],
                *[
                    field
                    for rule in normalized_worksheet_rules
                    for channel in rule["channels"]
                    for field in channel["fields"]
                ],
            ]
            if any(item["referenceType"] == "column_id" for item in external_references):
                raise _unprocessable(
                    "COLUMN_REFERENCE_UNAVAILABLE",
                    "Internal FlowHub column IDs cannot be used for an external Source.",
                )
        latest = self.sources.latest_mapping(source.id)
        version = (latest.version if latest else 0) + 1
        document = {
            "sourceId": source.id,
            "version": version,
            "worksheetMode": worksheet_mode,
            "worksheetName": effective_worksheet_name,
            "selectedWorksheetNames": normalized_selected_worksheets,
            "dataStartRow": data_start_row,
            "sourceFields": normalized_source_fields,
            "channels": normalized_channels,
            "valuePolicy": normalized_policy,
            "worksheetRuleMode": worksheet_rule_mode,
            "duplicateProductPolicy": duplicate_product_policy,
            "worksheetRules": normalized_worksheet_rules,
        }
        revision = SourceMappingRevision(
            id=_id(),
            source_id=source.id,
            version=version,
            checksum=checksum(document),
            worksheet_mode=worksheet_mode,
            worksheet_name=effective_worksheet_name,
            data_start_row=data_start_row,
            value_policy_json=normalized_policy,
            created_by_user_id=user.id,
        )
        self.db.add(revision)
        self.db.flush()
        for item in normalized_source_fields:
            self.db.add(
                SourceFieldMapping(
                    id=_id(),
                    mapping_revision_id=revision.id,
                    field=item["field"],
                    reference_type=item["referenceType"],
                    reference_value=item["referenceValue"],
                    required=bool(item["required"]),
                )
            )
        for channel in normalized_channels:
            channel_mapping = SourceChannelMapping(
                id=_id(),
                mapping_revision_id=revision.id,
                channel_id=channel["channelId"],
                worksheet_name=channel["worksheetName"],
                enabled=bool(channel["enabled"]),
            )
            self.db.add(channel_mapping)
            self.db.flush()
            for field in channel["fields"]:
                self.db.add(
                    SourceChannelFieldMapping(
                        id=_id(),
                        channel_mapping_id=channel_mapping.id,
                        field=field["field"],
                        reference_type=field["referenceType"],
                        reference_value=field["referenceValue"],
                    )
                )
        self._persist_worksheet_rule_set(
            revision=revision,
            mode=worksheet_rule_mode,
            duplicate_product_policy=duplicate_product_policy,
            rules=normalized_worksheet_rules,
        )
        source.version += 1
        source.worksheet_mode = worksheet_mode
        source.worksheet_name = effective_worksheet_name
        source.data_start_row = data_start_row
        source.updated_at = utcnow()
        self._invalidate_source_reviews(source.id)
        self.db.commit()
        shape = self._mapping_shape(revision)
        if shape is None:
            raise RuntimeError("Mapping revision persistence failed")
        return shape

    async def source_preview(
        self, source_id: str, user: FlowHubUser, *, page: int, page_size: int
    ) -> dict[str, Any]:
        source = self._owned_source(source_id, user, require_active=True)
        mapping = self.sources.latest_mapping(source.id)
        if mapping is None:
            raise _unprocessable("SOURCE_MAPPING_REQUIRED", "Configure Source mappings first.")
        sheet = self.sheets.for_source(source.id)
        revision_id: str
        if sheet is None:
            imported = await self._read_external_source(source, user, manual=True)
            records = self._mapped_external_records(imported.worksheets or {}, mapping)
            revision_id = f"external:{imported.snapshot.id}:{imported.snapshot.version_seq}"
        else:
            revision = self.sheets.latest_revision(sheet.id)
            if revision is None:
                return {
                    "items": [],
                    "total": 0,
                    "recognized": 0,
                    "ignored": 0,
                    "issues": [],
                    "businessSummary": self._preview_business_summary([], mapping),
                }
            records = self._mapped_sheet_records(revision, mapping)
            revision_id = revision.id
        start = (max(page, 1) - 1) * page_size
        page_records: list[dict[str, Any]] = []
        for record in records[start : start + min(max(page_size, 1), 500)]:
            shaped = dict(record)
            shaped["hasIssues"] = bool(record.get("issues"))
            shaped["ready"] = bool(record.get("recognized")) and not shaped["hasIssues"]
            page_records.append(shaped)
        return {
            "items": page_records,
            "total": len(records),
            "recognized": sum(1 for item in records if item["recognized"]),
            "ignored": sum(1 for item in records if not item["recognized"]),
            "issues": self._preview_issue_summary(records),
            "businessSummary": self._preview_business_summary(records, mapping),
            "sheetRevisionId": revision_id,
            "mappingRevisionId": mapping.id,
        }

    async def snapshot_candidates(self, source_id: str, user: FlowHubUser) -> dict[str, Any]:
        """Read a Source once and resolve independent Listing-scoped Channel targets."""
        source = self._owned_source(source_id, user, require_active=True)
        mapping = self.sources.latest_mapping(source.id)
        sheet = self.sheets.for_source(source.id)
        if mapping is None:
            raise _unprocessable("SOURCE_MAPPING_REQUIRED", "Configure Source mappings first.")
        if sheet is None:
            imported = await self._read_external_source(source, user, manual=False)
            records = self._mapped_external_records(imported.worksheets or {}, mapping)
            revision_shape = {
                "id": f"external:{imported.snapshot.id}:{imported.snapshot.version_seq}",
                "version": int(imported.snapshot.version_seq or 1),
                "checksum": str(imported.snapshot.integrity_hash or ""),
                "formulaEngineVersion": "provider-evaluated-v1",
            }
        else:
            revision = self.sheets.latest_revision(sheet.id)
            if revision is None:
                raise _unprocessable("SHEET_REVISION_REQUIRED", "Save the FlowHub Sheet first.")
            records = self._mapped_sheet_records(revision, mapping)
            revision_shape = {
                "id": revision.id,
                "version": revision.version,
                "checksum": revision.checksum,
                "formulaEngineVersion": revision.formula_engine_version,
            }
        identities = {
            (channel["channelId"], str(channel["fields"]["external_id"]).strip())
            for record in records
            if record["recognized"]
            for channel in record["channels"]
        }
        listings = {
            (item.channel_id, item.external_primary_id): item
            for item in self.db.query(Listing)
            .filter(
                tuple_(Listing.channel_id, Listing.external_primary_id).in_(sorted(identities))
            )
            .all()
        } if identities else {}
        listing_ids = [item.id for item in listings.values()]
        caches = {
            item.listing_id: item
            for item in self.db.query(ChannelCache)
            .filter(ChannelCache.listing_id.in_(listing_ids))
            .all()
        } if listing_ids else {}
        product_ids = {item.canonical_product_id for item in listings.values()}
        products = {
            item.id: item
            for item in self.db.query(CanonicalProduct)
            .filter(CanonicalProduct.id.in_(product_ids))
            .all()
        } if product_ids else {}
        candidates: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        product_identity: dict[str, str] = {}
        source_channel_listings: dict[tuple[str, str], set[str]] = defaultdict(set)
        seen_listing_ids: set[str] = set()
        for record in records:
            source_product = record["sourceProduct"]
            group_key = str(source_product.get("source_key") or source_product.get("name") or "").strip().casefold()
            blocked_channels: set[str] = set()
            global_block = False
            for row_issue in record.get("issues", []):
                issue_channel = row_issue.get("channelId")
                if issue_channel:
                    blocked_channels.add(str(issue_channel))
                else:
                    global_block = True
                issues.append(
                    self._candidate_issue(
                        record,
                        str(issue_channel) if issue_channel else None,
                        str(row_issue["category"]),
                        str(row_issue["category"]).upper(),
                        str(row_issue["message"]),
                        "Correct the Source row or its explicit Mapping policy.",
                        {},
                    )
                )
            if global_block:
                continue
            if not record["recognized"]:
                continue
            policy = dict(DEFAULT_VALUE_POLICY) | dict(
                record.get("valuePolicy") or mapping.value_policy_json
            )
            for channel in record["channels"]:
                channel_id = channel["channelId"]
                if channel_id in blocked_channels:
                    continue
                fields = channel["fields"]
                external_id = str(fields.get("external_id") or "").strip()
                listing = listings.get((channel_id, external_id))
                if listing is None:
                    issues.append(
                        self._candidate_issue(
                            record,
                            channel_id,
                            "missing_mapping",
                            "LISTING_NOT_MAPPED",
                            "No Channel Listing matches this External Listing ID.",
                            "Map the listing explicitly before Review.",
                            {"external_id": external_id},
                        )
                    )
                    continue
                if listing.id in seen_listing_ids:
                    issues.append(
                        self._candidate_issue(
                            record,
                            channel_id,
                            "duplicate_rows",
                            "DUPLICATE_LISTING_ROW",
                            "The same Listing appears more than once in this Source revision.",
                            "Keep one authoritative row for each Listing.",
                            {"listing_id": listing.id},
                        )
                    )
                    continue
                previous_product = product_identity.get(group_key)
                if previous_product and previous_product != listing.canonical_product_id:
                    issues.append(
                        self._candidate_issue(
                            record,
                            channel_id,
                            "mapping_conflict",
                            "SOURCE_PRODUCT_MAPPING_CONFLICT",
                            "Channel Listings under this Source Product resolve to different products.",
                            "Approve the intended Mapping before continuing.",
                            {
                                "previous_product_id": previous_product,
                                "conflicting_product_id": listing.canonical_product_id,
                            },
                        )
                    )
                    continue
                channel_group = (group_key, channel_id)
                if (
                    channel_id.startswith("woocommerce:")
                    and source_channel_listings[channel_group]
                    and listing.id not in source_channel_listings[channel_group]
                ):
                    issues.append(
                        self._candidate_issue(
                            record,
                            channel_id,
                            "mapping_conflict",
                            "WOOCOMMERCE_LISTING_CARDINALITY",
                            "A Source Product can map to at most one WooCommerce Listing.",
                            "Keep one WooCommerce Listing or separate the Source Products.",
                            {"listing_id": listing.id},
                        )
                    )
                    continue
                product_identity[group_key] = listing.canonical_product_id
                source_channel_listings[channel_group].add(listing.id)
                product = products.get(listing.canonical_product_id)
                cache = caches.get(listing.id)
                if product is None or cache is None:
                    issues.append(
                        self._candidate_issue(
                            record,
                            channel_id,
                            "unavailable_cache",
                            "LISTING_CACHE_UNAVAILABLE",
                            "The mapped Listing or its Channel Cache is unavailable.",
                            "Refresh the Channel Cache before creating a Workspace.",
                            {"listing_id": listing.id},
                        )
                    )
                    continue
                targets: dict[str, str] = {}
                blocked = False
                for field in ("price", "stock", "status"):
                    interpreted = self._interpret_target(fields.get(field), field, policy)
                    if interpreted["issue"]:
                        blocked = True
                        issues.append(
                            self._candidate_issue(
                                record,
                                channel_id,
                                "invalid_value",
                                interpreted["issue"],
                                str(interpreted["message"]),
                                "Correct the mapped value or change the explicit value policy.",
                                {"field": field, "raw": fields.get(field)},
                            )
                        )
                    elif interpreted["target"] is not None:
                        targets[field] = interpreted["target"]
                if blocked:
                    continue
                seen_listing_ids.add(listing.id)
                candidates.append(
                    {
                        "sourceRowKey": record["rowKey"],
                        "sourceRowNumber": record["rowNumber"],
                        "sourceProduct": source_product,
                        "canonicalProductId": product.id,
                        "listingId": listing.id,
                        "channelId": listing.channel_id,
                        "mappingVersion": listing.mapping_version,
                        "cacheVersion": cache.cache_version,
                        "targets": targets,
                    }
                )
        return {
            "source": self._source_shape(source),
            "mapping": self._mapping_shape(mapping),
            "sheetRevision": revision_shape,
            "candidates": candidates,
            "issues": issues,
            "summary": {
                "sourceProducts": len({str(item["sourceProduct"].get("source_key") or item["sourceProduct"].get("name")) for item in candidates}),
                "listings": len(candidates),
                "blocked": len(issues),
            },
        }

    # -- FlowHub Sheet ------------------------------------------------------

    def create_sheet(
        self, *, name: str, columns: list[dict[str, Any]], user: FlowHubUser
    ) -> dict[str, Any]:
        source_shape = self.create_source(
            name=name,
            source_kind="flowhub_sheet",
            external_source_id=None,
            worksheet_mode="selected",
            worksheet_name="Sheet1",
            data_start_row=1,
            user=user,
        )
        sheet = self.sheets.for_source(source_shape["id"])
        if sheet is None:
            raise RuntimeError("Sheet persistence failed")
        if columns:
            self.save_sheet_revision(
                sheet_id=sheet.id,
                expected_version=0,
                columns=columns,
                rows=[],
                user=user,
            )
        return self.get_sheet(sheet.id, user, page=1, page_size=200)

    def get_sheet(
        self,
        sheet_id: str,
        user: FlowHubUser,
        *,
        page: int,
        page_size: int,
        search: str | None = None,
        sort_column: str | None = None,
        sort_direction: str = "asc",
    ) -> dict[str, Any]:
        sheet = self._owned_sheet(sheet_id, user)
        revision = self.sheets.latest_revision(sheet.id)
        if revision is None:
            return {
                "id": sheet.id,
                "sourceId": sheet.source_id,
                "name": sheet.name,
                "version": 0,
                "revisionId": None,
                "columns": [],
                "rows": [],
                "total": 0,
                "page": page,
                "pageSize": page_size,
            }
        page_size = min(max(page_size, 1), 500)
        columns = self.sheets.columns(revision.id)
        column_keys = {item.column_key for item in columns}
        if sort_column and sort_column not in column_keys:
            raise _unprocessable("SHEET_SORT_COLUMN_INVALID", "Sort requires a persisted Column identity.")
        if sort_direction not in {"asc", "desc"}:
            raise _unprocessable("SHEET_SORT_DIRECTION_INVALID", "Sort direction must be asc or desc.")
        rows, total = self.sheets.rows(
            revision.id,
            offset=(max(page, 1) - 1) * page_size,
            limit=page_size,
            search=(search or "").strip()[:240] or None,
            sort_column=sort_column,
            sort_direction=sort_direction,
        )
        cells = self.sheets.cells(revision.id, [row.id for row in rows])
        by_row: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        for cell in cells:
            by_row[cell.row_id][cell.column_key] = {
                "raw": cell.raw_value,
                "value": cell.calculated_value,
                "formula": cell.formula_expression,
                "error": cell.calculation_error,
            }
        return {
            "id": sheet.id,
            "sourceId": sheet.source_id,
            "name": sheet.name,
            "version": sheet.current_version,
            "revisionId": revision.id,
            "revisionChecksum": revision.checksum,
            "formulaEngineVersion": revision.formula_engine_version,
            "columns": [self._column_shape(item) for item in columns],
            "rows": [
                {
                    "rowKey": row.row_key,
                    "position": row.position,
                    "cells": by_row.get(row.id, {}),
                }
                for row in rows
            ],
            "total": total,
            "page": page,
            "pageSize": page_size,
        }

    def save_sheet_revision(
        self,
        *,
        sheet_id: str,
        expected_version: int,
        columns: list[dict[str, Any]],
        rows: list[dict[str, Any]],
        user: FlowHubUser,
    ) -> dict[str, Any]:
        sheet = self._owned_sheet(sheet_id, user)
        self._owned_source(sheet.source_id, user, require_active=True, lock=True)
        if sheet.current_version != expected_version:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {"code": "SHEET_VERSION_CONFLICT", "message": "Sheet was changed elsewhere."},
            )
        normalized_columns = self._normalize_columns(columns)
        normalized_rows = self._normalize_rows(rows, normalized_columns)
        formula_results = self._calculate(normalized_columns, normalized_rows)
        version = sheet.current_version + 1
        document = {
            "sheetId": sheet.id,
            "version": version,
            "columns": normalized_columns,
            "rows": normalized_rows,
            "formulaEngine": FORMULA_ENGINE_VERSION,
        }
        revision = SheetRevision(
            id=_id(),
            sheet_id=sheet.id,
            version=version,
            checksum=checksum(document),
            formula_engine_version=FORMULA_ENGINE_VERSION,
            row_count=len(normalized_rows),
            column_count=len(normalized_columns),
            created_by_user_id=user.id,
        )
        self.db.add(revision)
        self.db.flush()
        column_models = [
            SheetColumn(
                id=_id(),
                revision_id=revision.id,
                column_key=item["columnKey"],
                name=item["name"],
                position=item["position"],
                data_type=item["dataType"],
            )
            for item in normalized_columns
        ]
        self.db.add_all(column_models)
        self.db.flush()
        row_models: list[SheetRow] = []
        cell_models: list[SheetCell] = []
        column_position = {item["columnKey"]: item["position"] for item in normalized_columns}
        for item in normalized_rows:
            row_model = SheetRow(
                id=_id(),
                revision_id=revision.id,
                row_key=item["rowKey"],
                position=item["position"],
            )
            row_models.append(row_model)
            for column_key, raw in item["values"].items():
                reference = f"{column_name(column_position[column_key])}{item['position']}"
                result = formula_results.get(reference)
                formula = str(raw) if raw is not None and str(raw).lstrip().startswith("=") else None
                cell_models.append(
                    SheetCell(
                        id=_id(),
                        revision_id=revision.id,
                        row_id=row_model.id,
                        column_key=column_key,
                        raw_value=None if raw is None else str(raw),
                        calculated_value=result.value if result else None if raw is None else str(raw),
                        formula_expression=formula,
                        formula_dependencies_json=list(result.dependencies) if result else [],
                        calculation_error=result.error if result else None,
                    )
                )
        # One flush/commit for the full bulk revision, never one transaction per cell.
        self.db.add_all(row_models)
        self.db.add_all(cell_models)
        sheet.current_version = version
        sheet.updated_at = utcnow()
        self.db.commit()
        return self.get_sheet(sheet.id, user, page=1, page_size=200)

    def patch_sheet_revision(
        self,
        *,
        sheet_id: str,
        expected_version: int,
        changes: list[dict[str, Any]],
        column_names: dict[str, str] | None = None,
        user: FlowHubUser,
    ) -> dict[str, Any]:
        """Create a full immutable revision from a bounded, identity-based cell patch."""
        sheet = self._owned_sheet(sheet_id, user)
        if sheet.current_version != expected_version:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {"code": "SHEET_VERSION_CONFLICT", "message": "Sheet was changed elsewhere."},
            )
        revision = self.sheets.latest_revision(sheet.id)
        if revision is None:
            raise _unprocessable("SHEET_REVISION_REQUIRED", "Create the first Sheet revision first.")
        columns = [self._column_shape(item) for item in self.sheets.columns(revision.id)]
        column_names = column_names or {}
        column_keys = {item["columnKey"] for item in columns}
        if set(column_names) - column_keys:
            raise _unprocessable(
                "SHEET_COLUMN_IDENTITY_INVALID",
                "Column name changes require persisted Column identities.",
            )
        for column in columns:
            replacement = column_names.get(column["columnKey"])
            if replacement is not None:
                column["name"] = _clean_name(replacement, column["name"])
        row_models = self.sheets.all_rows(revision.id)
        cells = self.sheets.cells(revision.id, [item.id for item in row_models])
        values_by_row: dict[str, dict[str, str | None]] = defaultdict(dict)
        row_key_by_id = {item.id: item.row_key for item in row_models}
        for cell in cells:
            values_by_row[row_key_by_id[cell.row_id]][cell.column_key] = cell.raw_value
        row_keys = {item.row_key for item in row_models}
        seen: set[tuple[str, str]] = set()
        for change in changes:
            row_key = str(change.get("row_key") or change.get("rowKey") or "")
            column_key = str(change.get("column_key") or change.get("columnKey") or "")
            identity = (row_key, column_key)
            if row_key not in row_keys or column_key not in column_keys or identity in seen:
                raise _unprocessable(
                    "SHEET_PATCH_IDENTITY_INVALID",
                    "Cell patches require unique persisted Row and Column identities.",
                )
            seen.add(identity)
            value = change.get("value")
            values_by_row[row_key][column_key] = None if value is None else str(value)
        rows = [
            {
                "rowKey": item.row_key,
                "position": item.position,
                "values": values_by_row[item.row_key],
            }
            for item in row_models
        ]
        return self.save_sheet_revision(
            sheet_id=sheet.id,
            expected_version=expected_version,
            columns=columns,
            rows=rows,
            user=user,
        )

    def append_sheet_rows(
        self,
        *,
        sheet_id: str,
        expected_version: int,
        count: int,
        user: FlowHubUser,
    ) -> dict[str, Any]:
        sheet = self._owned_sheet(sheet_id, user)
        if sheet.current_version != expected_version:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {"code": "SHEET_VERSION_CONFLICT", "message": "Sheet was changed elsewhere."},
            )
        revision = self.sheets.latest_revision(sheet.id)
        if revision is None:
            raise _unprocessable("SHEET_REVISION_REQUIRED", "Create the first Sheet revision first.")
        if count < 1 or revision.row_count + count > MAX_SHEET_ROWS:
            raise _unprocessable("SHEET_ROW_LIMIT", f"A Sheet supports at most {MAX_SHEET_ROWS} rows.")
        columns = [self._column_shape(item) for item in self.sheets.columns(revision.id)]
        row_models = self.sheets.all_rows(revision.id)
        cells = self.sheets.cells(revision.id, [item.id for item in row_models])
        row_key_by_id = {item.id: item.row_key for item in row_models}
        values_by_row: dict[str, dict[str, str | None]] = defaultdict(dict)
        for cell in cells:
            values_by_row[row_key_by_id[cell.row_id]][cell.column_key] = cell.raw_value
        rows = [
            {"rowKey": item.row_key, "position": item.position, "values": values_by_row[item.row_key]}
            for item in row_models
        ]
        last_position = max((item.position for item in row_models), default=0)
        rows.extend(
            {"rowKey": _id(), "position": last_position + offset, "values": {}}
            for offset in range(1, count + 1)
        )
        return self.save_sheet_revision(
            sheet_id=sheet.id,
            expected_version=expected_version,
            columns=columns,
            rows=rows,
            user=user,
        )

    def calculate(
        self, *, columns: list[dict[str, Any]], rows: list[dict[str, Any]]
    ) -> dict[str, Any]:
        normalized_columns = self._normalize_columns(columns)
        normalized_rows = self._normalize_rows(rows, normalized_columns)
        results = self._calculate(normalized_columns, normalized_rows)
        return {
            "engineVersion": FORMULA_ENGINE_VERSION,
            "cells": {
                reference: {
                    "value": result.value,
                    "dependencies": list(result.dependencies),
                    "error": result.error,
                }
                for reference, result in results.items()
            },
        }

    # -- Import -------------------------------------------------------------

    def preview_import(
        self, *, filename: str, content_base64: str, worksheet_name: str | None
    ) -> dict[str, Any]:
        content = self._decode_import(content_base64)
        sheets = self._read_import(filename, content)
        selected = worksheet_name or next(iter(sheets), None)
        if selected is None or selected not in sheets:
            raise _unprocessable("WORKSHEET_NOT_FOUND", "Select an available worksheet.")
        rows = sheets[selected]
        width = max((len(row) for row in rows), default=0)
        headers = [str(value or f"Column {column_name(index)}") for index, value in enumerate(rows[0] if rows else [], start=1)]
        return {
            "filename": filename,
            "sourceChecksum": checksum(content.hex()),
            "worksheets": list(sheets),
            "selectedWorksheet": selected,
            "rowCount": len(rows),
            "columnCount": width,
            "headers": headers,
            "previewRows": rows[:50],
            "truncated": len(rows) > 50,
        }

    def import_sheet(
        self,
        *,
        name: str,
        filename: str,
        content_base64: str,
        worksheet_name: str,
        expected_checksum: str,
        data_start_row: int,
        user: FlowHubUser,
    ) -> dict[str, Any]:
        content = self._decode_import(content_base64)
        source_checksum = checksum(content.hex())
        if source_checksum != expected_checksum:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {"code": "IMPORT_CONTENT_CHANGED", "message": "Import file changed after preview."},
            )
        sheets = self._read_import(filename, content)
        if worksheet_name not in sheets:
            raise _unprocessable("WORKSHEET_NOT_FOUND", "Selected worksheet does not exist.")
        source = self.create_source(
            name=name,
            source_kind="imported_sheet",
            external_source_id=None,
            worksheet_mode="selected",
            worksheet_name=worksheet_name,
            data_start_row=data_start_row,
            user=user,
        )
        sheet = self.sheets.for_source(source["id"])
        if sheet is None:
            raise RuntimeError("Imported sheet persistence failed")
        imported_rows = sheets[worksheet_name]
        width = max((len(row) for row in imported_rows), default=0)
        columns = [
            {
                "columnKey": f"col-{column_name(index).lower()}",
                "name": _clean_name(
                    imported_rows[0][index - 1] if imported_rows and len(imported_rows[0]) >= index else None,
                    f"Column {column_name(index)}",
                ),
                "position": index,
                "dataType": "text",
            }
            for index in range(1, width + 1)
        ]
        rows = [
            {
                "rowKey": _id(),
                "position": index,
                "values": {
                    columns[column_index]["columnKey"]: value
                    for column_index, value in enumerate(row)
                    if column_index < len(columns) and value is not None
                },
            }
            for index, row in enumerate(imported_rows, start=1)
        ]
        result = self.save_sheet_revision(
            sheet_id=sheet.id,
            expected_version=0,
            columns=columns,
            rows=rows,
            user=user,
        )
        self.db.add(
            SheetImportJob(
                id=_id(),
                sheet_id=sheet.id,
                source_type="xlsx" if filename.lower().endswith(".xlsx") else "csv",
                source_filename=filename[:500],
                worksheet_name=worksheet_name,
                imported_row_count=len(rows),
                mapping_version=0,
                source_checksum=source_checksum,
                status="completed",
                metadata_json={"original_unchanged": True, "available_worksheets": list(sheets)},
                created_by_user_id=user.id,
            )
        )
        self.db.commit()
        return result

    # -- Data Quality -------------------------------------------------------

    async def scan_data_quality(
        self,
        *,
        user: FlowHubUser,
        source_id: str | None,
    ) -> dict[str, Any]:
        """Evaluate each selected Source once and persist an explicit scan result."""
        if source_id:
            sources = [self._owned_source(source_id, user, require_active=True)]
        else:
            sources = [
                source
                for source in self.sources.list_for_user(user.id)
                if source.status == "active"
            ]
        source_ids = [source.id for source in sources]
        scan = SourceDataQualityScan(
            id=_id(),
            owner_user_id=user.id,
            source_id=source_id,
            source_ids_json=source_ids,
            source_results_json={},
            status="checking",
            sources_checked=0,
            products_checked=0,
            issue_count=0,
            blocking_issue_count=0,
            warning_count=0,
            affected_product_count=0,
            affected_channel_count=0,
            affected_source_count=0,
            previous_issue_count=None,
            resolved_since_previous=0,
            error_code=None,
            created_at=utcnow(),
            checked_at=None,
        )
        self.db.add(scan)
        self.db.add_all(
            SourceDataQualityScanSource(scan_id=scan.id, source_id=item)
            for item in source_ids
        )
        self.db.commit()

        try:
            pending_issues: list[SourceDataQualityIssue] = []
            all_product_rows: set[tuple[str, str]] = set()
            affected_products: set[tuple[str, str]] = set()
            affected_channels: set[str] = set()
            affected_sources: set[str] = set()
            source_results: dict[str, dict[str, int]] = {}
            blocking_count = 0
            warning_count = 0

            for source in sources:
                # snapshot_candidates owns the single acquisition and the shared
                # normalization/validation path.  No scan-specific Source read exists.
                try:
                    analysis = await self.snapshot_candidates(source.id, user)
                except HTTPException as exc:
                    detail: dict[str, Any] = (
                        exc.detail if isinstance(exc.detail, dict) else {}
                    )
                    code = str(detail.get("code") or "")
                    configuration_issues = {
                        "SOURCE_MAPPING_REQUIRED": (
                            "mapping_not_configured",
                            "Source columns have not been configured.",
                            "Choose the Source Product and Channel columns before running the check.",
                        ),
                        "SHEET_REVISION_REQUIRED": (
                            "source_not_saved",
                            "The FlowHub Sheet has not been saved yet.",
                            "Save the Sheet, then run the Data Quality check again.",
                        ),
                    }
                    if code not in configuration_issues:
                        raise
                    category, summary, action = configuration_issues[code]
                    analysis = {
                        "candidates": [],
                        "issues": [
                            {
                                "sourceRowKey": None,
                                "sourceRowNumber": None,
                                "worksheetName": source.worksheet_name,
                                "channelId": None,
                                "sourceProductName": None,
                                "mappingState": "unmapped",
                                "category": category,
                                "severity": "blocked",
                                "code": code,
                                "summary": summary,
                                "recommendedAction": action,
                                "technicalDetails": {},
                            }
                        ],
                    }
                analysis_issues = [dict(item) for item in analysis.get("issues", [])]
                source_product_rows: set[str] = {
                    str(item.get("sourceRowKey") or "")
                    for item in analysis.get("candidates", [])
                    if item.get("sourceRowKey")
                }
                source_product_rows.update(
                    str(item.get("sourceRowKey") or "")
                    for item in analysis_issues
                    if item.get("sourceRowKey")
                )
                all_product_rows.update((source.id, row_key) for row_key in source_product_rows)

                source_blocking = 0
                source_warnings = 0
                source_affected_products: set[str] = set()
                source_affected_channels: set[str] = set()
                for issue in analysis_issues:
                    severity = str(issue.get("severity") or "blocked")
                    if severity not in {"warning", "error", "blocked"}:
                        severity = "blocked"
                    if severity == "warning":
                        source_warnings += 1
                        warning_count += 1
                    else:
                        source_blocking += 1
                        blocking_count += 1
                    row_key = str(issue.get("sourceRowKey") or "")
                    if row_key:
                        source_affected_products.add(row_key)
                        affected_products.add((source.id, row_key))
                    channel_id = str(issue.get("channelId") or "").strip() or None
                    if channel_id:
                        source_affected_channels.add(channel_id)
                        affected_channels.add(channel_id)
                    affected_sources.add(source.id)
                    technical_details = dict(issue.get("technicalDetails") or {})
                    listing_id = str(technical_details.get("listing_id") or "").strip()
                    listing = self.db.get(Listing, listing_id) if listing_id else None
                    pending_issues.append(
                        SourceDataQualityIssue(
                            id=_id(),
                            scan_id=scan.id,
                            source_id=source.id,
                            snapshot_id=None,
                            worksheet_name=(
                                str(issue.get("worksheetName"))[:240]
                                if issue.get("worksheetName") is not None
                                else None
                            ),
                            source_row_key=self._data_quality_source_row_key(
                                issue.get("sourceRowKey")
                            ),
                            source_product_name=(
                                str(issue.get("sourceProductName"))[:240]
                                if issue.get("sourceProductName") is not None
                                else None
                            ),
                            mapping_state=(
                                str(issue.get("mappingState"))[:40]
                                if issue.get("mappingState") is not None
                                else None
                            ),
                            channel_id=channel_id,
                            canonical_product_id=(
                                listing.canonical_product_id if listing is not None else None
                            ),
                            category=str(issue.get("category") or "validation")[:80],
                            severity=severity,
                            code=str(issue.get("code") or "SOURCE_VALIDATION_FAILED")[:120],
                            summary=str(issue.get("summary") or "Source validation failed.")[:500],
                            recommended_action=str(
                                issue.get("recommendedAction")
                                or "Review the Source row and its configured columns."
                            )[:1000],
                            technical_details_json=technical_details,
                            created_at=utcnow(),
                        )
                    )
                source_results[source.id] = {
                    "productsChecked": len(source_product_rows),
                    "issueCount": len(analysis_issues),
                    "blockingIssues": source_blocking,
                    "warnings": source_warnings,
                    "affectedProducts": len(source_affected_products),
                    "affectedChannels": len(source_affected_channels),
                    "affectedSources": 1 if analysis_issues else 0,
                }

            previous = self.issues.previous_completed_scan(
                user_id=user.id,
                source_id=source_id,
                exclude_scan_id=scan.id,
            )
            previous_issue_count: int | None = None
            previous_issue_identities: set[
                tuple[str, str, str, str, str, str, str, str]
            ] = set()
            if previous is not None:
                if source_id is not None and previous.source_id is None:
                    previous_source_result = dict(
                        previous.source_results_json.get(source_id) or {}
                    )
                    previous_issue_count = int(
                        previous_source_result.get("issueCount", 0)
                    )
                else:
                    previous_issue_count = previous.issue_count
                previous_issue_identities = self.issues.issue_identity_keys(
                    previous.id,
                    source_id=source_id,
                )
            current_issue_identities = {
                self._data_quality_issue_identity(item) for item in pending_issues
            }
            persisted_scan = self.db.get(SourceDataQualityScan, scan.id)
            if persisted_scan is None:
                raise RuntimeError("Data Quality scan persistence was lost")
            scan = persisted_scan
            scan.sources_checked = len(sources)
            scan.products_checked = len(all_product_rows)
            scan.issue_count = len(pending_issues)
            scan.blocking_issue_count = blocking_count
            scan.warning_count = warning_count
            scan.affected_product_count = len(affected_products)
            scan.affected_channel_count = len(affected_channels)
            scan.affected_source_count = len(affected_sources)
            scan.previous_issue_count = previous_issue_count
            scan.resolved_since_previous = len(
                previous_issue_identities - current_issue_identities
            )
            scan.source_results_json = source_results
            self.db.add_all(pending_issues)
            # Issue rows must be persisted while the durable scan is still in
            # its only mutable state.  The database seals terminal scans and
            # rejects any issue appended after this flush.
            self.db.flush()
            scan.status = "completed"
            scan.checked_at = utcnow()
            self.db.commit()
            return {"summary": self._data_quality_summary(scan, source_id=source_id)}
        except Exception as exc:
            self.db.rollback()
            persisted = self.db.get(SourceDataQualityScan, scan.id)
            if persisted is not None:
                persisted.status = "failed"
                persisted.sources_checked = len(sources)
                persisted.error_code = self._data_quality_error_code(exc)
                persisted.checked_at = utcnow()
                self.db.commit()
            raise

    def data_quality(
        self,
        *,
        user: FlowHubUser,
        source_id: str | None,
        channel_id: str | None,
        worksheet: str | None,
        category: str | None,
        severity: str | None,
        product: str | None,
        mapping_state: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        normalized_source = self._data_quality_filter(source_id)
        normalized_channel = self._data_quality_filter(channel_id)
        normalized_worksheet = self._data_quality_filter(worksheet)
        normalized_category = self._data_quality_filter(category)
        normalized_severity = self._data_quality_filter(severity)
        normalized_product = self._data_quality_filter(product)
        normalized_mapping_state = self._data_quality_filter(mapping_state)
        scan = self.issues.latest_scan(user_id=user.id, source_id=normalized_source)
        if scan is None:
            return {
                "items": [],
                "counts": {},
                "total": 0,
                "page": page,
                "pageSize": page_size,
                "summary": self._data_quality_summary(None, source_id=normalized_source),
            }
        items, total, counts = self.issues.list(
            user_id=user.id,
            scan_id=scan.id,
            source_id=normalized_source,
            channel_id=normalized_channel,
            worksheet=normalized_worksheet,
            category=normalized_category,
            severity=normalized_severity,
            product=normalized_product,
            mapping_state=normalized_mapping_state,
            page=max(page, 1),
            page_size=min(max(page_size, 1), 200),
        )
        return {
            "items": [
                {
                    "id": item.id,
                    "scanId": item.scan_id,
                    "sourceId": item.source_id,
                    "sourceRowKey": item.source_row_key,
                    "worksheet": item.worksheet_name,
                    "sourceProductName": item.source_product_name,
                    "mappingState": item.mapping_state,
                    "channelId": item.channel_id,
                    "category": item.category,
                    "severity": item.severity,
                    "code": item.code,
                    "summary": item.summary,
                    "recommendedAction": item.recommended_action,
                    "technicalDetails": item.technical_details_json,
                }
                for item in items
            ],
            "counts": dict(counts),
            "total": total,
            "page": page,
            "pageSize": page_size,
            "summary": self._data_quality_summary(scan, source_id=normalized_source),
        }

    def _data_quality_summary(
        self,
        scan: SourceDataQualityScan | None,
        *,
        source_id: str | None,
    ) -> dict[str, Any]:
        if scan is None:
            return {
                "state": "never_checked",
                "totalIssues": 0,
                "blockingIssues": 0,
                "warnings": 0,
                "affectedProducts": 0,
                "affectedChannels": 0,
                "affectedSources": 0,
                "resolvedSinceLastRead": 0,
                "trendSinceLastRead": None,
                "productsChecked": 0,
                "sourcesChecked": 0,
                "checkedAt": None,
                "scanId": None,
                "errorCode": None,
                "categories": [],
            }
        scoped = (
            dict(scan.source_results_json.get(source_id) or {})
            if source_id is not None and scan.source_id is None
            else {}
        )
        total_issues = int(scoped.get("issueCount", scan.issue_count))
        if scan.status == "checking":
            state = "checking"
        elif scan.status == "failed":
            state = "failed"
        else:
            state = "issues_found" if total_issues else "healthy"
        scoped_to_global_scan = bool(scoped)
        categories = self.issues.categories(scan.id, source_id=source_id)
        return {
            "state": state,
            "totalIssues": total_issues,
            "blockingIssues": int(scoped.get("blockingIssues", scan.blocking_issue_count)),
            "warnings": int(scoped.get("warnings", scan.warning_count)),
            "affectedProducts": int(
                scoped.get("affectedProducts", scan.affected_product_count)
            ),
            "affectedChannels": int(
                scoped.get("affectedChannels", scan.affected_channel_count)
            ),
            "affectedSources": int(
                scoped.get("affectedSources", scan.affected_source_count)
            ),
            "resolvedSinceLastRead": (
                0 if scoped_to_global_scan else scan.resolved_since_previous
            ),
            "trendSinceLastRead": (
                None
                if scoped_to_global_scan or scan.previous_issue_count is None
                else scan.issue_count - scan.previous_issue_count
            ),
            "productsChecked": int(scoped.get("productsChecked", scan.products_checked)),
            "sourcesChecked": 1 if scoped_to_global_scan else scan.sources_checked,
            "checkedAt": scan.checked_at,
            "scanId": scan.id,
            "errorCode": scan.error_code,
            "categories": [
                {"category": category, "count": count}
                for category, count in sorted(
                    categories.items(), key=lambda item: (-item[1], item[0])
                )
            ],
        }

    @staticmethod
    def _data_quality_filter(value: str | None) -> str | None:
        normalized = str(value or "").strip()
        return None if not normalized or normalized.casefold() == "all" else normalized

    @staticmethod
    def _data_quality_source_row_key(value: object) -> str | None:
        """Return a complete bounded Source-row identity without truncation."""
        normalized = str(value or "").strip()
        if not normalized:
            return None
        if len(normalized) > 512:
            raise _unprocessable(
                "SOURCE_ROW_IDENTITY_TOO_LONG",
                "The Source row identity exceeds the supported length.",
            )
        return normalized

    @staticmethod
    def _data_quality_issue_identity(
        issue: SourceDataQualityIssue,
    ) -> tuple[str, str, str, str, str, str, str, str]:
        return (
            str(issue.source_id or ""),
            str(issue.worksheet_name or ""),
            str(issue.source_row_key or ""),
            str(issue.source_product_name or ""),
            str(issue.channel_id or ""),
            str(issue.mapping_state or ""),
            str(issue.category or ""),
            str(issue.code or ""),
        )

    @staticmethod
    def _data_quality_error_code(exc: Exception) -> str:
        if isinstance(exc, HTTPException) and isinstance(exc.detail, dict):
            return str(exc.detail.get("code") or "DATA_QUALITY_SCAN_FAILED")[:120]
        return type(exc).__name__.upper()[:120] or "DATA_QUALITY_SCAN_FAILED"

    # -- Helpers ------------------------------------------------------------

    def _owned_source(
        self,
        source_id: str,
        user: FlowHubUser,
        *,
        require_active: bool = False,
        lock: bool = False,
    ) -> SourceProfile:
        query = self.db.query(SourceProfile).filter(SourceProfile.id == source_id)
        if lock:
            query = query.with_for_update()
        source = query.populate_existing().one_or_none()
        if source is None or (source.owner_user_id != user.id and user.role != "admin"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found.")
        if require_active and source.status != "active":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {
                    "code": "SOURCE_ARCHIVED",
                    "message": "Archived Sources are read-only and cannot start new processing.",
                },
            )
        return source

    def _source_lifecycle_impact(self, source: SourceProfile) -> dict[str, Any]:
        sheet = self.sheets.for_source(source.id)
        sheet_revision_count = (
            self.db.query(SheetRevision).filter(SheetRevision.sheet_id == sheet.id).count()
            if sheet is not None
            else 0
        )
        import_count = (
            self.db.query(SheetImportJob).filter(SheetImportJob.sheet_id == sheet.id).count()
            if sheet is not None
            else 0
        )
        workspace_rows = (
            self.db.query(WorkspaceSnapshot, UnifiedWorkspace)
            .join(UnifiedWorkspace, UnifiedWorkspace.id == WorkspaceSnapshot.workspace_id)
            .filter(WorkspaceSnapshot.entry_point == "source")
            .all()
        )
        matching_workspaces = [
            (snapshot, workspace)
            for snapshot, workspace in workspace_rows
            if str((snapshot.source_metadata_json or {}).get("source_id") or "") == source.id
        ]
        active_workspace_count = sum(
            1 for _, workspace in matching_workspaces if workspace.status == "active"
        )
        protected_counts = {
            "mappingRevisions": self.db.query(SourceMappingRevision)
            .filter(SourceMappingRevision.source_id == source.id)
            .count(),
            "sheetRevisions": sheet_revision_count,
            "importJobs": import_count,
            "dataQualityIssues": self.db.query(SourceDataQualityIssue)
            .filter(SourceDataQualityIssue.source_id == source.id)
            .count(),
            "dataQualityScans": sum(
                1
                for scan in self.db.query(SourceDataQualityScan)
                .filter(SourceDataQualityScan.owner_user_id == source.owner_user_id)
                .all()
                if scan.source_id == source.id or source.id in scan.source_ids_json
            ),
            "workspaceSnapshots": len(matching_workspaces),
        }
        protected_history = {
            key: count for key, count in protected_counts.items() if count > 0
        }
        blockers = (
            {"activeWorkspaces": active_workspace_count}
            if active_workspace_count > 0
            else {}
        )
        action = (
            "none"
            if source.status != "active"
            else "blocked"
            if blockers
            else "archive"
            if protected_history
            else "delete"
        )
        return {
            "sourceId": source.id,
            "sourceName": source.name,
            "sourceVersion": source.version,
            "sourceStatus": source.status,
            "action": action,
            "blockers": blockers,
            "protectedHistory": protected_history,
        }

    def _append_source_lifecycle_audit(
        self,
        *,
        event_type: str,
        user: FlowHubUser,
        reason: str,
        metadata: dict[str, Any],
    ) -> None:
        bus = DomainEventBus()
        bus.subscribe(PersistenceAuditSubscriber(self.db, _id))
        bus.publish(
            DomainEvent(
                event_type=event_type,
                correlation_id=f"source-lifecycle:{_id()}",
                user_id=user.id,
                attributes={"reason": reason, "metadata": metadata},
            )
        )

    def _ensure_channels(self) -> None:
        # Reuse the v1.2 connector capability registry.  The local import keeps
        # the Source module independent from the Workspace service at import time.
        from app.flowhub.unified_workspace.services import UnifiedWorkspaceService

        UnifiedWorkspaceService(self.db)._seed_channels()

    def _owned_sheet(self, sheet_id: str, user: FlowHubUser) -> FlowHubSheet:
        sheet = self.sheets.get(sheet_id)
        if sheet is None or (sheet.owner_user_id != user.id and user.role != "admin"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Sheet not found.")
        return sheet

    def _source_shape(self, source: SourceProfile) -> dict[str, Any]:
        mapping = self.sources.latest_mapping(source.id)
        sheet = self.sheets.for_source(source.id)
        return {
            "id": source.id,
            "name": source.name,
            "sourceKind": source.source_kind,
            "externalSourceId": source.external_source_id,
            "worksheetMode": source.worksheet_mode,
            "worksheetName": source.worksheet_name,
            "dataStartRow": source.data_start_row,
            "status": source.status,
            "version": source.version,
            "mappingVersion": mapping.version if mapping else 0,
            "sheetId": sheet.id if sheet else None,
            "createdAt": source.created_at,
            "updatedAt": source.updated_at,
        }

    def _mapping_shape(self, revision: SourceMappingRevision | None) -> dict[str, Any] | None:
        if revision is None:
            return None
        source_fields = self.sources.source_fields(revision.id)
        channels = self.sources.channel_mappings(revision.id)
        channel_fields = self.sources.channel_fields([channel.id for channel in channels])
        by_channel: dict[str, list[SourceChannelFieldMapping]] = defaultdict(list)
        for channel_field in channel_fields:
            by_channel[channel_field.channel_mapping_id].append(channel_field)
        rule_set = self.sources.worksheet_rule_set(revision.id)
        worksheet_rules: list[dict[str, Any]] = []
        if rule_set is not None:
            stored_rules = self.sources.worksheet_rules(rule_set.id)
            stored_fields = self.sources.worksheet_fields([rule.id for rule in stored_rules])
            stored_channels = self.sources.worksheet_channels([rule.id for rule in stored_rules])
            stored_channel_fields = self.sources.worksheet_channel_fields(
                [channel.id for channel in stored_channels]
            )
            fields_by_rule: dict[str, list[SourceWorksheetFieldMapping]] = defaultdict(list)
            channels_by_rule: dict[str, list[SourceWorksheetChannelMapping]] = defaultdict(list)
            fields_by_stored_channel: dict[
                str, list[SourceWorksheetChannelFieldMapping]
            ] = defaultdict(list)
            for stored_field in stored_fields:
                fields_by_rule[stored_field.worksheet_rule_id].append(stored_field)
            for stored_channel in stored_channels:
                channels_by_rule[stored_channel.worksheet_rule_id].append(stored_channel)
            for stored_channel_field in stored_channel_fields:
                fields_by_stored_channel[
                    stored_channel_field.worksheet_channel_mapping_id
                ].append(stored_channel_field)
            worksheet_rules = [
                {
                    "worksheetName": stored_rule.worksheet_name,
                    "enabled": stored_rule.enabled,
                    "dataStartRow": stored_rule.data_start_row,
                    "valuePolicy": stored_rule.value_policy_json,
                    "sourceFields": [
                        {
                            "field": field.field,
                            "referenceType": field.reference_type,
                            "referenceValue": field.reference_value,
                            "required": field.required,
                        }
                        for field in fields_by_rule[stored_rule.id]
                    ],
                    "channels": [
                        {
                            "channelId": channel.channel_id,
                            "worksheetName": channel.worksheet_name,
                            "enabled": channel.enabled,
                            "fields": [
                                {
                                    "field": field.field,
                                    "referenceType": field.reference_type,
                                    "referenceValue": field.reference_value,
                                }
                                for field in fields_by_stored_channel[channel.id]
                            ],
                        }
                        for channel in channels_by_rule[stored_rule.id]
                    ],
                }
                for stored_rule in stored_rules
            ]
        return {
            "id": revision.id,
            "sourceId": revision.source_id,
            "version": revision.version,
            "checksum": revision.checksum,
            "worksheetMode": revision.worksheet_mode,
            "worksheetName": revision.worksheet_name,
            "dataStartRow": revision.data_start_row,
            "valuePolicy": revision.value_policy_json,
            "worksheetRuleMode": rule_set.mode if rule_set else "shared",
            "selectedWorksheetNames": (
                sorted(
                    rule["worksheetName"]
                    for rule in worksheet_rules
                    if rule["worksheetName"] != "*" and rule["enabled"]
                )
                if rule_set is not None and rule_set.mode == "shared"
                else []
            ),
            "duplicateProductPolicy": (
                rule_set.duplicate_product_policy if rule_set else "block"
            ),
            "worksheetRules": worksheet_rules,
            "sourceFields": [
                {
                    "field": source_field.field,
                    "referenceType": source_field.reference_type,
                    "referenceValue": source_field.reference_value,
                    "required": source_field.required,
                }
                for source_field in source_fields
            ],
            "channels": [
                {
                    "channelId": channel_mapping.channel_id,
                    "worksheetName": channel_mapping.worksheet_name,
                    "enabled": channel_mapping.enabled,
                    "fields": [
                        {
                            "field": field.field,
                            "referenceType": field.reference_type,
                            "referenceValue": field.reference_value,
                        }
                        for field in by_channel[channel_mapping.id]
                    ],
                }
                for channel_mapping in channels
            ],
            "createdAt": revision.created_at,
        }

    def _legacy_mapping_shape(self, source: SourceProfile) -> dict[str, Any] | None:
        """Expose the historical global mapping as WooCommerce-only compatibility data.

        It is never persisted into the revisioned Source mapping automatically. The
        user must review and save the prefilled mapping explicitly.
        """
        if source.source_kind != "external" or source.external_source_id != LEGACY_EXTERNAL_SOURCE_ID:
            return None
        raw = AppConfigService(self.db).get("nextcloud.source_mapping")
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return None
        legacy = normalize_source_mapping(parsed)
        field_names = {"id": "external_id", "price": "price", "stock": "stock"}
        fields: list[dict[str, Any]] = []
        for legacy_field, target_field in field_names.items():
            item = legacy[legacy_field]
            value = str(item.get("column") or "").strip()
            fields.append(
                {
                    "field": target_field,
                    "referenceType": (
                        "disabled"
                        if not item.get("enabled")
                        else "column_letter"
                        if re.fullmatch(r"[A-Za-z]{1,3}", value)
                        else "header_name"
                    ),
                    "referenceValue": value or None,
                    "required": False,
                }
            )
        fields.append(
            {
                "field": "status",
                "referenceType": "disabled",
                "referenceValue": None,
                "required": False,
            }
        )
        return {
            "primaryChannelId": "woocommerce:primary",
            "fields": fields,
            "requiresConfirmation": True,
        }

    def _invalidate_source_reviews(self, source_id: str) -> None:
        """Invalidate prepared state tied to an older active Source mapping."""
        snapshots = (
            self.db.query(WorkspaceSnapshot)
            .filter(WorkspaceSnapshot.entry_point == "source")
            .all()
        )
        snapshot_ids = [
            item.id
            for item in snapshots
            if str((item.source_metadata_json or {}).get("source_id") or "") == source_id
        ]
        if not snapshot_ids:
            return
        now = utcnow()
        reviews = (
            self.db.query(Review)
            .filter(Review.snapshot_id.in_(snapshot_ids), Review.status != ReviewState.STALE)
            .all()
        )
        review_ids: list[str] = []
        for review in reviews:
            review.status = ReviewState.STALE
            review.invalidated_at = now
            review.stale_reason = "source_mapping_revision_changed"
            review.selection_checksum = None
            review_ids.append(review.id)
        if review_ids:
            for job in (
                self.db.query(ApplyJob)
                .filter(
                    ApplyJob.review_id.in_(review_ids),
                    ApplyJob.status == ApplyState.PENDING,
                )
                .all()
            ):
                job.status = ApplyState.STALE
                job.completed_at = now

    async def _read_external_source(
        self, source: SourceProfile, user: FlowHubUser, *, manual: bool
    ) -> SourceImportResult:
        if source.external_source_id != LEGACY_EXTERNAL_SOURCE_ID:
            raise _unprocessable(
                "EXTERNAL_SOURCE_UNSUPPORTED",
                "This external Source connector does not support read-once Workspace acquisition.",
            )
        return await SpreadsheetSourceReadService(self.db).read_nextcloud_spreadsheet(
            triggered_by="source_workspace",
            triggered_by_id=user.id,
            manual=manual,
            capture_raw_worksheets=True,
        )

    @staticmethod
    def _validate_worksheet(mode: str, name: str | None, data_start_row: int) -> None:
        if mode not in {"all", "selected"}:
            raise _unprocessable("WORKSHEET_MODE_INVALID", "Use all or selected worksheet mode.")
        if mode == "selected" and not str(name or "").strip():
            raise _unprocessable("WORKSHEET_REQUIRED", "Select a worksheet.")
        if data_start_row < 1 or data_start_row > 1_000_000:
            raise _unprocessable("DATA_START_ROW_INVALID", "Data start row is outside the valid range.")

    @staticmethod
    def _normalize_selected_worksheet_names(names: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_name in names:
            name = str(raw_name or "").strip()
            if not name or name == "*" or len(name) > 240 or name in seen:
                raise _unprocessable(
                    "WORKSHEET_SELECTION_INVALID",
                    "Selected worksheet names must be explicit, unique, and at most 240 characters.",
                )
            normalized.append(name)
            seen.add(name)
        return normalized

    def _normalize_field_mappings(
        self,
        mappings: list[dict[str, Any]],
        allowed_fields: set[str],
        *,
        required_fields: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        seen: set[str] = set()
        normalized: list[dict[str, Any]] = []
        for raw in mappings:
            field = str(raw.get("field") or "").strip()
            reference_type = str(raw.get("reference_type") or raw.get("referenceType") or "disabled")
            reference_value = str(raw.get("reference_value") or raw.get("referenceValue") or "").strip() or None
            if field not in allowed_fields or field in seen:
                raise _unprocessable("FIELD_MAPPING_INVALID", "Field mappings must be unique and supported.")
            if reference_type not in REFERENCE_TYPES:
                raise _unprocessable("REFERENCE_TYPE_INVALID", "Unsupported column reference type.")
            if reference_type != "disabled" and not reference_value:
                raise _unprocessable("REFERENCE_VALUE_REQUIRED", "Configured fields require a column reference.")
            if reference_type == "column_letter" and reference_value and not re.fullmatch(r"[A-Za-z]{1,3}", reference_value):
                raise _unprocessable("COLUMN_LETTER_INVALID", "Column letter is invalid.")
            seen.add(field)
            normalized.append(
                {
                    "field": field,
                    "referenceType": reference_type,
                    "referenceValue": reference_value.upper() if reference_type == "column_letter" and reference_value else reference_value,
                    "required": bool(raw.get("required") or field in (required_fields or set())),
                }
            )
        for required in required_fields or set():
            configured = next((item for item in normalized if item["field"] == required), None)
            if configured is None or configured["referenceType"] == "disabled":
                raise _unprocessable("SOURCE_IDENTITY_REQUIRED", f"Source Product {required} must be mapped.")
        return sorted(normalized, key=lambda item: item["field"])

    def _normalize_channel_mappings(
        self,
        mappings: list[dict[str, Any]],
        *,
        require_enabled: bool = True,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        enabled_count = 0
        for raw in mappings:
            channel_id = str(raw.get("channel_id") or raw.get("channelId") or "").strip()
            if not channel_id or channel_id in seen:
                raise _unprocessable("CHANNEL_MAPPING_INVALID", "Channel mappings must be unique.")
            channel = self.db.get(WorkspaceChannel, channel_id)
            enabled = bool(raw.get("enabled", True))
            if channel is None:
                raise _unprocessable("CHANNEL_UNKNOWN", "The Channel mapping identity is unknown.")
            if enabled and (not channel.enabled or channel.implementation_state != "implemented"):
                raise _unprocessable(
                    "CHANNEL_UNAVAILABLE", "Only enabled Channels with official connectors may be mapped."
                )
            fields = self._normalize_field_mappings(list(raw.get("fields") or []), CHANNEL_FIELDS)
            external = next((item for item in fields if item["field"] == "external_id"), None)
            if enabled and (external is None or external["referenceType"] == "disabled"):
                raise _unprocessable(
                    "CHANNEL_EXTERNAL_ID_REQUIRED", "Every enabled Channel requires an External Listing ID mapping."
                )
            result.append(
                {
                    "channelId": channel_id,
                    "worksheetName": str(raw.get("worksheet_name") or raw.get("worksheetName") or "").strip() or None,
                    "enabled": enabled,
                    "fields": fields,
                }
            )
            enabled_count += int(enabled)
            seen.add(channel_id)
        if require_enabled and (not result or enabled_count == 0):
            raise _unprocessable("CHANNEL_MAPPING_REQUIRED", "Select at least one enabled Channel.")
        return sorted(result, key=lambda item: item["channelId"])

    def _normalize_worksheet_rules(
        self, rules: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not rules:
            raise _unprocessable(
                "WORKSHEET_RULE_REQUIRED",
                "Configure at least one worksheet or use shared rules.",
            )
        seen: set[str] = set()
        normalized: list[dict[str, Any]] = []
        enabled_count = 0
        for raw in rules:
            worksheet_name = str(
                raw.get("worksheet_name") or raw.get("worksheetName") or ""
            ).strip()
            enabled = bool(raw.get("enabled", True))
            data_start_row = int(
                raw.get("data_start_row") or raw.get("dataStartRow") or 1
            )
            if not worksheet_name or worksheet_name == "*" or worksheet_name in seen:
                raise _unprocessable(
                    "WORKSHEET_RULE_INVALID",
                    "Worksheet rule names must be explicit and unique.",
                )
            self._validate_worksheet("selected", worksheet_name, data_start_row)
            source_fields = self._normalize_field_mappings(
                list(raw.get("source_fields") or raw.get("sourceFields") or []),
                SOURCE_FIELDS,
                required_fields={"name"} if enabled else set(),
            )
            channels = self._normalize_channel_mappings(
                list(raw.get("channel_mappings") or raw.get("channels") or []),
                require_enabled=enabled,
            )
            normalized.append(
                {
                    "worksheetName": worksheet_name,
                    "enabled": enabled,
                    "dataStartRow": data_start_row,
                    "sourceFields": source_fields,
                    "channels": channels,
                    "valuePolicy": self._normalize_value_policy(
                        dict(raw.get("value_policy") or raw.get("valuePolicy") or {})
                    ),
                }
            )
            enabled_count += int(enabled)
            seen.add(worksheet_name)
        if enabled_count == 0:
            raise _unprocessable(
                "WORKSHEET_RULE_REQUIRED",
                "At least one worksheet must participate in Source processing.",
            )
        return normalized

    def _persist_worksheet_rule_set(
        self,
        *,
        revision: SourceMappingRevision,
        mode: str,
        duplicate_product_policy: str,
        rules: list[dict[str, Any]],
    ) -> None:
        rule_set = SourceWorksheetRuleSet(
            id=_id(),
            mapping_revision_id=revision.id,
            mode=mode,
            duplicate_product_policy=duplicate_product_policy,
            sealed=False,
        )
        self.db.add(rule_set)
        self.db.flush()
        for rule in rules:
            worksheet_rule = SourceWorksheetRule(
                id=_id(),
                rule_set_id=rule_set.id,
                worksheet_name=rule["worksheetName"],
                enabled=bool(rule["enabled"]),
                data_start_row=int(rule["dataStartRow"]),
                value_policy_json=dict(rule["valuePolicy"]),
            )
            self.db.add(worksheet_rule)
            self.db.flush()
            for field in rule["sourceFields"]:
                self.db.add(
                    SourceWorksheetFieldMapping(
                        id=_id(),
                        worksheet_rule_id=worksheet_rule.id,
                        field=field["field"],
                        reference_type=field["referenceType"],
                        reference_value=field["referenceValue"],
                        required=bool(field["required"]),
                    )
                )
            for channel in rule["channels"]:
                worksheet_channel = SourceWorksheetChannelMapping(
                    id=_id(),
                    worksheet_rule_id=worksheet_rule.id,
                    channel_id=channel["channelId"],
                    worksheet_name=channel.get("worksheetName"),
                    enabled=bool(channel["enabled"]),
                )
                self.db.add(worksheet_channel)
                self.db.flush()
                for field in channel["fields"]:
                    self.db.add(
                        SourceWorksheetChannelFieldMapping(
                            id=_id(),
                            worksheet_channel_mapping_id=worksheet_channel.id,
                            field=field["field"],
                            reference_type=field["referenceType"],
                            reference_value=field["referenceValue"],
                        )
                    )
        # Flush the complete aggregate while its construction window is open,
        # then perform the sole permitted parent update to seal it forever.
        self.db.flush()
        rule_set.sealed = True
        self.db.flush()

    @staticmethod
    def _normalize_value_policy(raw: dict[str, str]) -> dict[str, str]:
        allowed = {
            "blank": {"no_change", "blocked"},
            "x": {"unavailable", "no_change", "blocked"},
            "dash": {"no_change", "unavailable", "blocked"},
            "zero": {"explicit_zero", "no_change", "blocked"},
            "formula": {"calculated_value", "blocked"},
            "invalid": {"blocked"},
        }
        result = dict(DEFAULT_VALUE_POLICY)
        for key, value in raw.items():
            if key not in allowed or value not in allowed[key]:
                raise _unprocessable("VALUE_POLICY_INVALID", f"Invalid handling policy for {key}.")
            result[key] = value
        return result

    @staticmethod
    def _normalize_columns(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not columns or len(columns) > MAX_SHEET_COLUMNS:
            raise _unprocessable("SHEET_COLUMNS_INVALID", f"Use 1 to {MAX_SHEET_COLUMNS} columns.")
        keys: set[str] = set()
        positions: set[int] = set()
        normalized = []
        for index, item in enumerate(columns, start=1):
            key = str(item.get("column_key") or item.get("columnKey") or _id()).strip()
            position = int(item.get("position") or index)
            if not key or len(key) > 36 or key in keys or position in positions or position < 1:
                raise _unprocessable("SHEET_COLUMN_INVALID", "Column identities and positions must be unique.")
            keys.add(key)
            positions.add(position)
            normalized.append(
                {
                    "columnKey": key,
                    "name": _clean_name(item.get("name"), f"Column {column_name(position)}"),
                    "position": position,
                    "dataType": str(item.get("data_type") or item.get("dataType") or "text")[:30],
                }
            )
        return sorted(normalized, key=lambda item: item["position"])

    @staticmethod
    def _normalize_rows(
        rows: list[dict[str, Any]], columns: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if len(rows) > MAX_SHEET_ROWS:
            raise _unprocessable("SHEET_ROW_LIMIT", f"A Sheet supports at most {MAX_SHEET_ROWS} rows.")
        column_keys = {item["columnKey"] for item in columns}
        keys: set[str] = set()
        positions: set[int] = set()
        normalized = []
        for index, item in enumerate(rows, start=1):
            key = str(item.get("row_key") or item.get("rowKey") or _id()).strip()
            position = int(item.get("position") or index)
            values = dict(item.get("values") or {})
            if key in keys or position in positions or position < 1:
                raise _unprocessable("SHEET_ROW_INVALID", "Row identities and positions must be unique.")
            unknown = set(values) - column_keys
            if unknown:
                raise _unprocessable("SHEET_CELL_COLUMN_INVALID", "A cell references an unknown column.")
            keys.add(key)
            positions.add(position)
            normalized.append(
                {"rowKey": key, "position": position, "values": values}
            )
        return sorted(normalized, key=lambda item: item["position"])

    @staticmethod
    def _calculate(
        columns: list[dict[str, Any]], rows: list[dict[str, Any]]
    ) -> dict[str, FormulaResult]:
        positions = {item["columnKey"]: item["position"] for item in columns}
        values = {
            f"{column_name(positions[column_key])}{row['position']}": None if value is None else str(value)
            for row in rows
            for column_key, value in row["values"].items()
        }
        return calculate_sheet(values)

    @staticmethod
    def _column_shape(column: SheetColumn) -> dict[str, Any]:
        return {
            "columnKey": column.column_key,
            "name": column.name,
            "position": column.position,
            "dataType": column.data_type,
        }

    @staticmethod
    def _decode_import(content_base64: str) -> bytes:
        try:
            content = base64.b64decode(content_base64, validate=True)
        except ValueError as exc:
            raise _unprocessable("IMPORT_ENCODING_INVALID", "Import content is not valid base64.") from exc
        if not content or len(content) > MAX_IMPORT_BYTES:
            raise _unprocessable("IMPORT_SIZE_INVALID", "Import file is empty or exceeds 20 MB.")
        return content

    @staticmethod
    def _read_import(filename: str, content: bytes) -> dict[str, list[list[Any]]]:
        lowered = filename.lower()
        if lowered.endswith(".csv"):
            decoded = None
            for encoding in ("utf-8-sig", "utf-8", "cp1256"):
                try:
                    decoded = content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            if decoded is None:
                raise _unprocessable("CSV_ENCODING_INVALID", "CSV must use a supported text encoding.")
            return {"Sheet1": [list(row) for row in csv.reader(io.StringIO(decoded))]}
        if lowered.endswith(".xlsx"):
            try:
                workbook = openpyxl.load_workbook(io.BytesIO(content), data_only=False, read_only=True)
            except Exception as exc:
                raise _unprocessable("XLSX_INVALID", "XLSX file could not be read.") from exc
            return {
                worksheet.title: [list(row) for row in worksheet.iter_rows(values_only=True)]
                for worksheet in workbook.worksheets
            }
        raise _unprocessable("IMPORT_FORMAT_UNSUPPORTED", "Use an XLSX or CSV file.")

    def _worksheet_rule_configs(
        self, mapping: SourceMappingRevision
    ) -> tuple[str, str, list[dict[str, Any]]]:
        """Load normalized rules, synthesizing a shared rule for FLOWHUB_018 data."""
        rule_set = self.sources.worksheet_rule_set(mapping.id)
        if rule_set is None:
            legacy_source_fields = self.sources.source_fields(mapping.id)
            legacy_channels = self.sources.channel_mappings(mapping.id)
            legacy_channel_fields = self.sources.channel_fields(
                [channel.id for channel in legacy_channels]
            )
            by_channel: dict[str, list[SourceChannelFieldMapping]] = defaultdict(list)
            for channel_field in legacy_channel_fields:
                by_channel[channel_field.channel_mapping_id].append(channel_field)
            return (
                "shared",
                "block",
                [
                    {
                        "worksheetName": "*",
                        "enabled": True,
                        "dataStartRow": mapping.data_start_row,
                        "valuePolicy": dict(mapping.value_policy_json),
                        "sourceFields": legacy_source_fields,
                        "channels": [
                            {
                                "channelId": item.channel_id,
                                "worksheetName": item.worksheet_name,
                                "enabled": item.enabled,
                                "fields": by_channel[item.id],
                            }
                            for item in legacy_channels
                        ],
                    }
                ],
            )
        rules = self.sources.worksheet_rules(rule_set.id)
        worksheet_source_fields = self.sources.worksheet_fields([rule.id for rule in rules])
        worksheet_channels = self.sources.worksheet_channels([rule.id for rule in rules])
        worksheet_channel_fields = self.sources.worksheet_channel_fields(
            [channel.id for channel in worksheet_channels]
        )
        source_fields_by_rule: dict[str, list[SourceWorksheetFieldMapping]] = defaultdict(list)
        channels_by_rule: dict[str, list[SourceWorksheetChannelMapping]] = defaultdict(list)
        channel_fields_by_mapping: dict[
            str, list[SourceWorksheetChannelFieldMapping]
        ] = defaultdict(list)
        for worksheet_source_field in worksheet_source_fields:
            source_fields_by_rule[worksheet_source_field.worksheet_rule_id].append(
                worksheet_source_field
            )
        for worksheet_channel in worksheet_channels:
            channels_by_rule[worksheet_channel.worksheet_rule_id].append(
                worksheet_channel
            )
        for worksheet_channel_field in worksheet_channel_fields:
            channel_fields_by_mapping[
                worksheet_channel_field.worksheet_channel_mapping_id
            ].append(worksheet_channel_field)
        return (
            rule_set.mode,
            rule_set.duplicate_product_policy,
            [
                {
                    "worksheetName": rule.worksheet_name,
                    "enabled": rule.enabled,
                    "dataStartRow": rule.data_start_row,
                    "valuePolicy": dict(rule.value_policy_json),
                    "sourceFields": source_fields_by_rule[rule.id],
                    "channels": [
                        {
                            "channelId": channel.channel_id,
                            "worksheetName": channel.worksheet_name,
                            "enabled": channel.enabled,
                            "fields": channel_fields_by_mapping[channel.id],
                        }
                        for channel in channels_by_rule[rule.id]
                    ],
                }
                for rule in rules
            ],
        )

    @staticmethod
    def _apply_cross_worksheet_duplicate_policy(
        records: list[dict[str, Any]], policy: str
    ) -> None:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in records:
            if not record["recognized"]:
                continue
            source = record.get("sourceProduct") or {}
            identity = str(source.get("source_key") or source.get("name") or "").strip().casefold()
            if identity:
                grouped[identity].append(record)
        for matches in grouped.values():
            if len({str(item.get("worksheetName") or "") for item in matches}) < 2:
                continue
            if policy == "last_sheet_wins":
                affected = matches[:-1]
                category = "duplicate_source_product_superseded"
                severity = "warning"
                message = "A later participating worksheet explicitly replaces this Source Product."
            else:
                affected = matches
                category = "duplicate_source_product"
                severity = "blocked"
                message = "The same Source Product appears in more than one participating worksheet."
            for record in affected:
                record["recognized"] = False
                record["channels"] = []
                record["issues"].append(
                    {
                        "category": category,
                        "severity": severity,
                        "channelId": None,
                        "message": message,
                    }
                )

    def _mapped_external_records(
        self,
        worksheets: dict[str, list[list[Any]]],
        mapping: SourceMappingRevision,
    ) -> list[dict[str, Any]]:
        """Resolve an acquired workbook once into independent Channel values."""
        if not worksheets:
            return []
        rule_mode, duplicate_policy, configured_rules = self._worksheet_rule_configs(mapping)
        rule_work: list[tuple[str, dict[str, Any]]] = []
        if rule_mode == "shared":
            explicit_rules = {
                item["worksheetName"]: item
                for item in configured_rules
                if item["worksheetName"] != "*"
            }
            if explicit_rules:
                missing = [
                    name
                    for name, rule in explicit_rules.items()
                    if rule["enabled"] and name not in worksheets
                ]
                if missing:
                    raise _unprocessable(
                        "WORKSHEET_NOT_FOUND",
                        "A selected worksheet is not present in the acquired workbook.",
                        {"worksheets": missing},
                    )
                rule_work = [
                    (name, explicit_rules[name])
                    for name in worksheets
                    if name in explicit_rules and explicit_rules[name]["enabled"]
                ]
            else:
                # FLOWHUB_018 and early FLOWHUB_019 shared mappings use a
                # wildcard rule plus the legacy all/single worksheet columns.
                worksheet_names = (
                    [str(mapping.worksheet_name or "")]
                    if mapping.worksheet_mode == "selected"
                    else list(worksheets)
                )
                missing = [name for name in worksheet_names if name not in worksheets]
                if missing:
                    raise _unprocessable(
                        "WORKSHEET_NOT_FOUND",
                        "The configured Source worksheet is not present in the acquired workbook.",
                        {"worksheets": missing},
                    )
                rule_work = [(name, configured_rules[0]) for name in worksheet_names]
        else:
            rules_by_name = {item["worksheetName"]: item for item in configured_rules}
            missing = [
                name
                for name, rule in rules_by_name.items()
                if rule["enabled"] and name not in worksheets
            ]
            if missing:
                raise _unprocessable(
                    "WORKSHEET_NOT_FOUND",
                    "A configured worksheet is not present in the acquired workbook.",
                    {"worksheets": missing},
                )
            rule_work = [
                (name, rules_by_name[name])
                for name in worksheets
                if name in rules_by_name and rules_by_name[name]["enabled"]
            ]
        channel_ids = {
            str(channel["channelId"])
            for _, rule in rule_work
            for channel in rule["channels"]
        }
        current_channels = {
            item.id: item
            for item in self.db.query(WorkspaceChannel)
            .filter(WorkspaceChannel.id.in_(channel_ids))
            .all()
        }
        header_cache: dict[tuple[str, int, str], int | None] = {}

        def column_index(
            worksheet: str,
            data_start_row: int,
            reference_type: str,
            reference_value: str | None,
        ) -> int | None:
            if reference_type == "column_letter":
                try:
                    return int(
                        openpyxl.utils.column_index_from_string(str(reference_value or ""))
                    ) - 1
                except ValueError:
                    return None
            if reference_type != "header_name":
                return None
            normalized = str(reference_value or "").strip().casefold()
            cache_key = (worksheet, data_start_row, normalized)
            if cache_key in header_cache:
                return header_cache[cache_key]
            found = None
            header_rows = worksheets.get(worksheet, [])[: max(data_start_row - 1, 0)]
            for header_row in reversed(header_rows):
                for index, value in enumerate(header_row):
                    if str(value or "").strip().casefold() == normalized:
                        found = index
                        break
                if found is not None:
                    break
            header_cache[cache_key] = found
            return found

        def read(
            worksheet: str,
            row_number: int,
            data_start_row: int,
            reference_type: str,
            reference_value: str | None,
        ) -> Any:
            index = column_index(
                worksheet, data_start_row, reference_type, reference_value
            )
            rows = worksheets.get(worksheet, [])
            if index is None or row_number < 1 or row_number > len(rows):
                return None
            row = rows[row_number - 1]
            return row[index] if index < len(row) else None

        records: list[dict[str, Any]] = []
        for worksheet_name, rule in rule_work:
            data_start_row = int(rule["dataStartRow"])
            policy = dict(DEFAULT_VALUE_POLICY) | dict(rule["valuePolicy"])
            for row_number in range(data_start_row, len(worksheets[worksheet_name]) + 1):
                row_issues: list[dict[str, str | None]] = []
                source_data = {
                    field.field: read(
                        worksheet_name,
                        row_number,
                        data_start_row,
                        field.reference_type,
                        field.reference_value,
                    )
                    for field in rule["sourceFields"]
                    if field.reference_type != "disabled"
                }
                name = str(source_data.get("name") or "").strip()
                channel_data: list[dict[str, Any]] = []
                for channel in rule["channels"]:
                    channel_id = str(channel["channelId"])
                    current = current_channels.get(channel_id)
                    if (
                        not channel["enabled"]
                        or current is None
                        or not current.enabled
                        or current.implementation_state != "implemented"
                    ):
                        continue
                    channel_worksheet = channel.get("worksheetName") or worksheet_name
                    if channel_worksheet not in worksheets:
                        row_issues.append(
                            {
                                "category": "missing_channel_worksheet",
                                "severity": "blocked",
                                "channelId": channel_id,
                                "message": "The worksheet selected for this Channel is unavailable.",
                            }
                        )
                        continue
                    fields = {
                        item.field: read(
                            channel_worksheet,
                            row_number,
                            data_start_row,
                            item.reference_type,
                            item.reference_value,
                        )
                        for item in channel["fields"]
                        if item.reference_type != "disabled"
                    }
                    external_id = str(fields.get("external_id") or "").strip()
                    marker = external_id.casefold()
                    if marker == "x" and policy["x"] in {"unavailable", "no_change"}:
                        continue
                    if marker in {"-", "–", "—"} and policy["dash"] in {
                        "unavailable",
                        "no_change",
                    }:
                        continue
                    if external_id:
                        channel_data.append({"channelId": channel_id, "fields": fields})
                    elif any(value not in {None, ""} for value in fields.values()):
                        row_issues.append(
                            {
                                "category": "missing_mapping_identity",
                                "severity": "blocked",
                                "channelId": channel_id,
                                "message": "Channel values exist but External Listing ID is missing.",
                            }
                        )
                recognized = bool(name and channel_data)
                if not name and channel_data:
                    row_issues.append(
                        {
                            "category": "missing_source_identity",
                            "severity": "blocked",
                            "channelId": None,
                            "message": "Source Product Name is required.",
                        }
                    )
                records.append(
                    {
                        "rowKey": f"external:{worksheet_name}:{row_number}",
                        "rowNumber": row_number,
                        "worksheetName": worksheet_name,
                        "recognized": recognized,
                        "sourceProduct": source_data,
                        "channels": channel_data,
                        "valuePolicy": policy,
                        "issues": row_issues,
                    }
                )
        self._apply_cross_worksheet_duplicate_policy(records, duplicate_policy)
        return records

    def _mapped_sheet_records(
        self, revision: SheetRevision, mapping: SourceMappingRevision
    ) -> list[dict[str, Any]]:
        columns = self.sheets.columns(revision.id)
        rows = self.sheets.all_rows(revision.id)
        cells = self.sheets.cells(revision.id, [item.id for item in rows])
        column_by_key = {item.column_key: item for item in columns}
        by_name = {item.name.casefold(): item.column_key for item in columns}
        by_letter = {column_name(item.position): item.column_key for item in columns}
        by_row: dict[str, dict[str, SheetCell]] = defaultdict(dict)
        for cell in cells:
            by_row[cell.row_id][cell.column_key] = cell

        def mapped_key(reference_type: str, reference_value: str | None) -> str | None:
            if reference_type == "column_id":
                return reference_value if reference_value in column_by_key else None
            if reference_type == "column_letter":
                return by_letter.get(str(reference_value or "").upper())
            if reference_type == "header_name":
                return by_name.get(str(reference_value or "").casefold())
            return None

        rule_mode, _, configured_rules = self._worksheet_rule_configs(mapping)
        selected_rule: dict[str, Any] | None = None
        if rule_mode == "shared":
            internal_name = str(mapping.worksheet_name or "Sheet1")
            selected_rule = next(
                (
                    configured_rule
                    for configured_rule in configured_rules
                    if configured_rule["worksheetName"] in {"*", internal_name}
                    and configured_rule["enabled"]
                ),
                None,
            )
        else:
            internal_name = str(mapping.worksheet_name or "Sheet1")
            for configured_rule in configured_rules:
                if (
                    configured_rule["worksheetName"] == internal_name
                    and configured_rule["enabled"]
                ):
                    selected_rule = configured_rule
                    break
        if selected_rule is None:
            return []
        rule = selected_rule
        source_fields = rule["sourceFields"]
        channels = rule["channels"]
        channel_ids = [str(item["channelId"]) for item in channels]
        current_channels = {
            item.id: item
            for item in self.db.query(WorkspaceChannel)
            .filter(WorkspaceChannel.id.in_(channel_ids))
            .all()
        }
        records: list[dict[str, Any]] = []
        policy = dict(DEFAULT_VALUE_POLICY) | dict(rule["valuePolicy"])
        for row in rows:
            if row.position < int(rule["dataStartRow"]):
                continue
            values = by_row.get(row.id, {})
            row_issues: list[dict[str, str | None]] = []

            def read(
                reference_type: str,
                reference_value: str | None,
                row_values: dict[str, SheetCell] = values,
                issues: list[dict[str, str | None]] = row_issues,
            ) -> Any:
                key = mapped_key(reference_type, reference_value)
                cell = row_values.get(key or "")
                if cell and cell.calculation_error:
                    issues.append(
                        {
                            "category": "formula_error",
                            "severity": "blocked",
                            "channelId": None,
                            "message": f"Formula calculation failed: {cell.calculation_error}.",
                        }
                    )
                elif cell and cell.formula_expression and policy["formula"] == "blocked":
                    issues.append(
                        {
                            "category": "formula_blocked",
                            "severity": "blocked",
                            "channelId": None,
                            "message": "Formula values are blocked by the Source policy.",
                        }
                    )
                return cell.calculated_value if cell else None

            source_data = {
                field.field: read(field.reference_type, field.reference_value)
                for field in source_fields
                if field.reference_type != "disabled"
            }
            name = str(source_data.get("name") or "").strip()
            channel_data = []
            for channel in channels:
                channel_id = str(channel["channelId"])
                current = current_channels.get(channel_id)
                if (
                    not channel["enabled"]
                    or current is None
                    or not current.enabled
                    or current.implementation_state != "implemented"
                ):
                    continue
                fields = {
                    item.field: read(item.reference_type, item.reference_value)
                    for item in channel["fields"]
                    if item.reference_type != "disabled"
                }
                external_id = str(fields.get("external_id") or "").strip()
                marker = external_id.casefold()
                if marker == "x" and policy["x"] in {"unavailable", "no_change"}:
                    continue
                if marker in {"-", "–", "—"} and policy["dash"] in {
                    "unavailable",
                    "no_change",
                }:
                    continue
                if external_id:
                    channel_data.append({"channelId": channel_id, "fields": fields})
                elif any(value not in {None, ""} for value in fields.values()):
                    row_issues.append(
                        {
                            "category": "missing_mapping_identity",
                            "severity": "blocked",
                            "channelId": channel_id,
                            "message": "Channel values exist but External Listing ID is missing.",
                        }
                    )
            recognized = bool(name and channel_data)
            if not name and channel_data:
                row_issues.append(
                    {
                        "category": "missing_source_identity",
                        "severity": "blocked",
                        "message": "Source Product Name is required.",
                    }
                )
            records.append(
                {
                    "rowKey": row.row_key,
                    "rowNumber": row.position,
                    "worksheetName": str(mapping.worksheet_name or "Sheet1"),
                    "recognized": recognized,
                    "sourceProduct": source_data,
                    "channels": channel_data,
                    "valuePolicy": policy,
                    "issues": row_issues,
                }
            )
        return records

    @staticmethod
    def _interpret_target(
        raw: Any, field: str, policy: dict[str, str]
    ) -> dict[str, str | None]:
        if raw is None or str(raw).strip() == "":
            if policy["blank"] == "blocked":
                return {
                    "target": None,
                    "issue": "BLANK_VALUE_BLOCKED",
                    "message": f"Blank {field} is blocked by the Source policy.",
                }
            return {"target": None, "issue": None, "message": None}
        text = str(raw).strip()
        lowered = text.casefold()
        if lowered == "x":
            behavior = policy["x"]
            if behavior == "blocked":
                return {
                    "target": None,
                    "issue": "X_MARKER_BLOCKED",
                    "message": f"The x marker is not valid for {field}.",
                }
            return {"target": None, "issue": None, "message": None}
        if lowered in {"-", "–", "—"}:
            behavior = policy["dash"]
            if behavior == "blocked":
                return {
                    "target": None,
                    "issue": "DASH_MARKER_BLOCKED",
                    "message": f"The dash marker is not valid for {field}.",
                }
            return {"target": None, "issue": None, "message": None}
        if field in {"price", "stock"}:
            try:
                number = Decimal(text.replace(",", ""))
            except InvalidOperation:
                return {
                    "target": None,
                    "issue": "INVALID_NUMERIC_VALUE",
                    "message": f"{field.title()} must be a valid numeric value.",
                }
            if number < 0:
                return {
                    "target": None,
                    "issue": "NEGATIVE_VALUE",
                    "message": f"{field.title()} cannot be negative.",
                }
            if number == 0 and policy["zero"] != "explicit_zero":
                if policy["zero"] == "blocked":
                    return {
                        "target": None,
                        "issue": "ZERO_VALUE_BLOCKED",
                        "message": f"Zero {field} is blocked by the Source policy.",
                    }
                return {"target": None, "issue": None, "message": None}
            text = format(number.normalize(), "f")
        return {"target": text, "issue": None, "message": None}

    @staticmethod
    def _candidate_issue(
        record: dict[str, Any],
        channel_id: str | None,
        category: str,
        code: str,
        summary: str,
        action: str,
        details: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "sourceRowKey": record["rowKey"],
            "sourceRowNumber": record["rowNumber"],
            "worksheetName": record.get("worksheetName"),
            "channelId": channel_id,
            "sourceProductName": str(
                record.get("sourceProduct", {}).get("name")
                or record.get("sourceProduct", {}).get("source_key")
                or ""
            )[:240]
            or None,
            "mappingState": (
                "unmapped"
                if category == "missing_mapping"
                else "conflict"
                if category == "mapping_conflict"
                else "resolved"
            ),
            "category": category,
            "severity": "blocked",
            "code": code,
            "summary": summary,
            "recommendedAction": action,
            "technicalDetails": details,
        }

    @staticmethod
    def _preview_issue_summary(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str, str | None], int] = defaultdict(int)
        for record in records:
            for issue in record["issues"]:
                grouped[(issue["category"], issue["severity"], issue.get("channelId"))] += 1
        return [
            {"category": key[0], "severity": key[1], "channelId": key[2], "count": count}
            for key, count in sorted(grouped.items())
        ]

    def _preview_business_summary(
        self,
        records: list[dict[str, Any]],
        mapping: SourceMappingRevision,
    ) -> dict[str, int | None]:
        """Return seller-facing counts without inventing Channel comparisons.

        A Source Product can produce several Listing rows, so product totals use
        the stable Source identity when present and fall back to the Source row
        identity.  Attention is intentionally row-scoped because one problematic
        row must remain independently actionable even when another row names the
        same product.
        """

        def product_identity(record: dict[str, Any]) -> str:
            source_product = dict(record.get("sourceProduct") or {})
            identity = str(
                source_product.get("source_key") or source_product.get("name") or ""
            ).strip()
            if identity:
                return f"product:{identity.casefold()}"
            return f"row:{record.get('rowKey') or record.get('rowNumber') or ''}"

        recognized_products = {
            product_identity(record) for record in records if record.get("recognized")
        }
        products_with_issues = {
            product_identity(record) for record in records if record.get("issues")
        }
        attention_rows = {
            str(
                record.get("rowKey")
                or f"{record.get('worksheetName') or ''}:{record.get('rowNumber') or ''}"
            )
            for record in records
            if record.get("issues")
        }

        _, _, configured_rules = self._worksheet_rule_configs(mapping)
        configured_channel_ids = {
            str(channel["channelId"])
            for rule in configured_rules
            if bool(rule.get("enabled", True))
            for channel in rule["channels"]
            if bool(channel["enabled"])
        }
        available_channel_ids = {
            str(channel_id)
            for (channel_id,) in self.db.query(WorkspaceChannel.id)
            .filter(
                WorkspaceChannel.enabled.is_(True),
                WorkspaceChannel.implementation_state == "implemented",
            )
            .all()
        }
        ready_channel_ids = configured_channel_ids & available_channel_ids

        return {
            "productsFound": len(recognized_products),
            "productsReady": len(recognized_products - products_with_issues),
            # Preview has not compared targets with each Channel cache.  Returning
            # zero here would falsely claim that no change exists.
            "priceChanges": None,
            "stockChanges": None,
            "unchanged": None,
            "needsAttention": len(attention_rows),
            "channelsReady": len(ready_channel_ids),
            "channelsNotConfigured": len(available_channel_ids - ready_channel_ids),
        }
