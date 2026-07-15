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
    SourceFieldMapping,
    SourceMappingRevision,
    SourceProfile,
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
from app.flowhub.unified_workspace.models import (
    ApplyJob,
    CanonicalProduct,
    ChannelCache,
    Listing,
    Review,
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
        return result

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
        user: FlowHubUser,
    ) -> dict[str, Any]:
        self._ensure_channels()
        source = self._owned_source(source_id, user)
        if source.version != expected_source_version:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {"code": "SOURCE_VERSION_CONFLICT", "message": "Source configuration changed."},
            )
        self._validate_worksheet(worksheet_mode, worksheet_name, data_start_row)
        normalized_source_fields = self._normalize_field_mappings(
            source_fields, SOURCE_FIELDS, required_fields={"name"}
        )
        normalized_channels = self._normalize_channel_mappings(channel_mappings)
        if source.source_kind == "external":
            external_references = [
                *normalized_source_fields,
                *[
                    field
                    for channel in normalized_channels
                    for field in channel["fields"]
                ],
            ]
            if any(item["referenceType"] == "column_id" for item in external_references):
                raise _unprocessable(
                    "COLUMN_REFERENCE_UNAVAILABLE",
                    "Internal FlowHub column IDs cannot be used for an external Source.",
                )
        normalized_policy = self._normalize_value_policy(value_policy)
        latest = self.sources.latest_mapping(source.id)
        version = (latest.version if latest else 0) + 1
        document = {
            "sourceId": source.id,
            "version": version,
            "worksheetMode": worksheet_mode,
            "worksheetName": worksheet_name,
            "dataStartRow": data_start_row,
            "sourceFields": normalized_source_fields,
            "channels": normalized_channels,
            "valuePolicy": normalized_policy,
        }
        revision = SourceMappingRevision(
            id=_id(),
            source_id=source.id,
            version=version,
            checksum=checksum(document),
            worksheet_mode=worksheet_mode,
            worksheet_name=worksheet_name,
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
        source.version += 1
        source.worksheet_mode = worksheet_mode
        source.worksheet_name = worksheet_name
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
        source = self._owned_source(source_id, user)
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
                return {"items": [], "total": 0, "recognized": 0, "ignored": 0, "issues": []}
            records = self._mapped_sheet_records(revision, mapping)
            revision_id = revision.id
        start = (max(page, 1) - 1) * page_size
        page_records = records[start : start + min(max(page_size, 1), 500)]
        return {
            "items": page_records,
            "total": len(records),
            "recognized": sum(1 for item in records if item["recognized"]),
            "ignored": sum(1 for item in records if not item["recognized"]),
            "issues": self._preview_issue_summary(records),
            "sheetRevisionId": revision_id,
            "mappingRevisionId": mapping.id,
        }

    async def snapshot_candidates(self, source_id: str, user: FlowHubUser) -> dict[str, Any]:
        """Read a Source once and resolve independent Listing-scoped Channel targets."""
        source = self._owned_source(source_id, user)
        mapping = self.sources.latest_mapping(source.id)
        sheet = self.sheets.for_source(source.id)
        if mapping is None:
            raise _unprocessable("SOURCE_MAPPING_REQUIRED", "Configure Source mappings first.")
        if sheet is None:
            imported = await self._read_external_source(source, user, manual=False)
            records = [
                item
                for item in self._mapped_external_records(imported.worksheets or {}, mapping)
                if item["recognized"]
            ]
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
            records = [
                item for item in self._mapped_sheet_records(revision, mapping) if item["recognized"]
            ]
            revision_shape = {
                "id": revision.id,
                "version": revision.version,
                "checksum": revision.checksum,
                "formulaEngineVersion": revision.formula_engine_version,
            }
        identities = {
            (channel["channelId"], str(channel["fields"]["external_id"]).strip())
            for record in records
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
        policy = dict(DEFAULT_VALUE_POLICY) | dict(mapping.value_policy_json)
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
        items, total = self.issues.list(
            user_id=user.id,
            source_id=source_id,
            channel_id=channel_id,
            worksheet=worksheet,
            category=category,
            severity=severity,
            product=product,
            mapping_state=mapping_state,
            page=max(page, 1),
            page_size=min(max(page_size, 1), 200),
        )
        counts: dict[str, int] = defaultdict(int)
        for item in items:
            counts[item.category] += 1
        return {
            "items": [
                {
                    "id": item.id,
                    "sourceId": item.source_id,
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
        }

    # -- Helpers ------------------------------------------------------------

    def _owned_source(self, source_id: str, user: FlowHubUser) -> SourceProfile:
        source = self.sources.get(source_id)
        if source is None or (source.owner_user_id != user.id and user.role != "admin"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found.")
        return source

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
        channel_fields = self.sources.channel_fields([item.id for item in channels])
        by_channel: dict[str, list[SourceChannelFieldMapping]] = defaultdict(list)
        for item in channel_fields:
            by_channel[item.channel_mapping_id].append(item)
        return {
            "id": revision.id,
            "sourceId": revision.source_id,
            "version": revision.version,
            "checksum": revision.checksum,
            "worksheetMode": revision.worksheet_mode,
            "worksheetName": revision.worksheet_name,
            "dataStartRow": revision.data_start_row,
            "valuePolicy": revision.value_policy_json,
            "sourceFields": [
                {
                    "field": item.field,
                    "referenceType": item.reference_type,
                    "referenceValue": item.reference_value,
                    "required": item.required,
                }
                for item in source_fields
            ],
            "channels": [
                {
                    "channelId": item.channel_id,
                    "worksheetName": item.worksheet_name,
                    "enabled": item.enabled,
                    "fields": [
                        {
                            "field": field.field,
                            "referenceType": field.reference_type,
                            "referenceValue": field.reference_value,
                        }
                        for field in by_channel[item.id]
                    ],
                }
                for item in channels
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

    def _normalize_channel_mappings(self, mappings: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
        if not result or enabled_count == 0:
            raise _unprocessable("CHANNEL_MAPPING_REQUIRED", "Select at least one enabled Channel.")
        return sorted(result, key=lambda item: item["channelId"])

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

    def _mapped_external_records(
        self,
        worksheets: dict[str, list[list[Any]]],
        mapping: SourceMappingRevision,
    ) -> list[dict[str, Any]]:
        """Resolve an acquired workbook once into independent Channel values."""
        if not worksheets:
            return []
        if mapping.worksheet_mode == "selected":
            worksheet_names = [str(mapping.worksheet_name or "")]
            if worksheet_names[0] not in worksheets:
                raise _unprocessable(
                    "WORKSHEET_NOT_FOUND",
                    "The configured Source worksheet is not present in the acquired workbook.",
                )
        else:
            worksheet_names = list(worksheets)

        source_fields = self.sources.source_fields(mapping.id)
        channels = self.sources.channel_mappings(mapping.id)
        channel_fields = self.sources.channel_fields([item.id for item in channels])
        fields_by_channel: dict[str, list[SourceChannelFieldMapping]] = defaultdict(list)
        for item in channel_fields:
            fields_by_channel[item.channel_mapping_id].append(item)
        current_channels = {
            item.id: item
            for item in self.db.query(WorkspaceChannel)
            .filter(WorkspaceChannel.id.in_([item.channel_id for item in channels]))
            .all()
        }
        header_cache: dict[tuple[str, str], int | None] = {}

        def column_index(
            worksheet: str, reference_type: str, reference_value: str | None
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
            cache_key = (worksheet, normalized)
            if cache_key in header_cache:
                return header_cache[cache_key]
            found = None
            header_rows = worksheets.get(worksheet, [])[: max(mapping.data_start_row - 1, 0)]
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
            reference_type: str,
            reference_value: str | None,
        ) -> Any:
            index = column_index(worksheet, reference_type, reference_value)
            rows = worksheets.get(worksheet, [])
            if index is None or row_number < 1 or row_number > len(rows):
                return None
            row = rows[row_number - 1]
            return row[index] if index < len(row) else None

        records: list[dict[str, Any]] = []
        policy = dict(DEFAULT_VALUE_POLICY) | dict(mapping.value_policy_json)
        for worksheet_name in worksheet_names:
            for row_number in range(mapping.data_start_row, len(worksheets[worksheet_name]) + 1):
                row_issues: list[dict[str, str | None]] = []
                source_data = {
                    field.field: read(
                        worksheet_name,
                        row_number,
                        field.reference_type,
                        field.reference_value,
                    )
                    for field in source_fields
                    if field.reference_type != "disabled"
                }
                name = str(source_data.get("name") or "").strip()
                channel_data: list[dict[str, Any]] = []
                for channel in channels:
                    current = current_channels.get(channel.channel_id)
                    if (
                        not channel.enabled
                        or current is None
                        or not current.enabled
                        or current.implementation_state != "implemented"
                    ):
                        continue
                    channel_worksheet = channel.worksheet_name or worksheet_name
                    fields = {
                        item.field: read(
                            channel_worksheet,
                            row_number,
                            item.reference_type,
                            item.reference_value,
                        )
                        for item in fields_by_channel[channel.id]
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
                        channel_data.append({"channelId": channel.channel_id, "fields": fields})
                    elif any(value not in {None, ""} for value in fields.values()):
                        row_issues.append(
                            {
                                "category": "missing_mapping_identity",
                                "severity": "blocked",
                                "channelId": channel.channel_id,
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
                        "issues": row_issues,
                    }
                )
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

        source_fields = self.sources.source_fields(mapping.id)
        channels = self.sources.channel_mappings(mapping.id)
        channel_fields = self.sources.channel_fields([item.id for item in channels])
        fields_by_channel: dict[str, list[SourceChannelFieldMapping]] = defaultdict(list)
        for item in channel_fields:
            fields_by_channel[item.channel_mapping_id].append(item)
        current_channels = {
            item.id: item
            for item in self.db.query(WorkspaceChannel)
            .filter(WorkspaceChannel.id.in_([item.channel_id for item in channels]))
            .all()
        }
        records: list[dict[str, Any]] = []
        policy = dict(DEFAULT_VALUE_POLICY) | dict(mapping.value_policy_json)
        for row in rows:
            if row.position < mapping.data_start_row:
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
                current = current_channels.get(channel.channel_id)
                if (
                    not channel.enabled
                    or current is None
                    or not current.enabled
                    or current.implementation_state != "implemented"
                ):
                    continue
                fields = {
                    item.field: read(item.reference_type, item.reference_value)
                    for item in fields_by_channel[channel.id]
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
                    channel_data.append({"channelId": channel.channel_id, "fields": fields})
                elif any(value not in {None, ""} for value in fields.values()):
                    row_issues.append(
                        {
                            "category": "missing_mapping_identity",
                            "severity": "blocked",
                            "channelId": channel.channel_id,
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
                    "recognized": recognized,
                    "sourceProduct": source_data,
                    "channels": channel_data,
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
