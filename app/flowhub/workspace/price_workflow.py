"""Source-driven Workspace preview for WooCommerce price management.

This service imports the configured Nextcloud spreadsheet, validates source
rows against cached WooCommerce products, and returns preview rows. It never
executes marketplace writes; valid rows are handed to the existing Write
Pipeline dry-run endpoint.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.data_layer.models import DlProductCache, DlRefreshJob, DlSourceSnapshot, DlWorkspacePreview
from app.flowhub.integration_platform.contracts import WorkspacePreviewResponse
from app.flowhub.integration_platform.service import IntegrationPlatformService
from app.flowhub.integration_platform.models import IntegrationConnectorInstance
from app.flowhub.product_media import primary_image_url
from app.flowhub.sources.spreadsheet_source import SpreadsheetSourceReadService
from app.flowhub.source_workspace.models import SourceProfile
from app.flowhub.setup.service import AppConfigService
from app.flowhub.workspace.preview_store import WorkspacePreviewStore

SOURCE_ID = "nextcloud:primary"
SOURCE_TYPE = "nextcloud_spreadsheet"
CHANNEL_ID = "woocommerce:primary"
MAX_DRY_RUN_DELTA_PERCENT = 50.0
LARGE_CHANGE_WARNING_PERCENT = 30.0
SUSPICIOUS_LOW_PRICE = 1.0
SUSPICIOUS_HIGH_PRICE = 100_000.0
SUPPORTED_WRITE_PRODUCT_TYPES = frozenset({"simple", "variation"})
_LOCAL_PREVIEW_LOCKS: dict[str, asyncio.Lock] = {}


@dataclass(frozen=True)
class ProductMatch:
    row: DlProductCache
    current_price: float
    category_names: list[str]
    image_url: str | None
    parent_row: DlProductCache | None
    variation_attributes: list[dict]


class WorkspacePriceWorkflowService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.config = AppConfigService(db)
        self.source_reader = SpreadsheetSourceReadService(db)
        self.integration = IntegrationPlatformService(db)
        self.workspace_source_id = SOURCE_ID
        self.workspace_connector_id = SOURCE_ID

    async def preview_from_nextcloud(
        self, user: FlowHubUser, source_profile_id: str | None = None
    ) -> WorkspacePreviewResponse:
        source = self._resolve_workspace_source(user, source_profile_id)
        if source is not None:
            self.workspace_source_id = source.id
            self.workspace_connector_id = str(source.external_source_id)
            self.source_reader = SpreadsheetSourceReadService(
                self.db, connector_id=self.workspace_connector_id
            )
        lock_key = self.workspace_source_id
        async with _preview_execution_lock(self.db, lock_key):
            worksheet_scope = self.source_reader.worksheet_scope(
                source_profile_id=self.workspace_source_id if source is not None else None
            )
            source_config_hash = self._source_config_hash(
                self.workspace_source_id,
                worksheet_scope=worksheet_scope,
            )
            self._require_channel_config()
            latest_refresh = self._latest_cache_refresh()
            self._ensure_cache_refresh_ready(latest_refresh)
            if not self._load_products():
                raise HTTPException(status.HTTP_409_CONFLICT, "WooCommerce product cache is empty. Run a manual read first.")
            reusable = WorkspacePreviewStore(self.db).latest_reusable(
                source_id=self.workspace_source_id,
                owner=user,
                source_config_hash=source_config_hash,
            )
            if reusable is not None:
                if int(reusable.owner_user_id) != int(user.id):
                    reusable = self._clone_reusable_preview(reusable, user)
                return self._reused_preview_response(reusable, user)
            return await self._create_preview_from_nextcloud(
                user,
                source_config_hash=source_config_hash,
                worksheet_scope=worksheet_scope,
            )

    def _resolve_workspace_source(
        self, user: FlowHubUser, source_profile_id: str | None
    ) -> SourceProfile | None:
        """Resolve an explicit active Source; never choose an archived profile."""
        requested = str(source_profile_id or self.config.get("nextcloud.workspace_source_id") or "").strip()
        if requested:
            source = self.db.get(SourceProfile, requested)
            if source is None or (source.owner_user_id != user.id and user.role != "admin"):
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace Source binding not found.")
            if source.status != "active":
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    {
                        "code": "SOURCE_WORKSPACE_REBIND_REQUIRED",
                        "message": "Workspace is bound to an inactive Source. Bind an active Source before Preview.",
                        "sourceId": source.id,
                        "sourceStatus": source.status,
                    },
                )
            connector = self.db.get(IntegrationConnectorInstance, source.external_source_id)
            if connector is None or connector.connector_type != "nextcloud":
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    {
                        "code": "SOURCE_WORKSPACE_BINDING_INVALID",
                        "message": "Workspace Source binding is not an active Nextcloud connector.",
                    },
                )
            return source

        profiles = (
            self.db.query(SourceProfile)
            .join(
                IntegrationConnectorInstance,
                IntegrationConnectorInstance.id == SourceProfile.external_source_id,
            )
            .filter(SourceProfile.owner_user_id == user.id)
            .filter(IntegrationConnectorInstance.connector_type == "nextcloud")
            .all()
        )
        if not profiles:
            # Compatibility mode applies only when the v2 Source registry has
            # never been established; it does not select among Source rows.
            return None
        legacy = next((item for item in profiles if item.external_source_id == SOURCE_ID), None)
        candidates = [item for item in profiles if item.status == "active"]
        if legacy is not None and legacy.status != "active":
            bound_id = legacy.id
        else:
            bound_id = legacy.id if legacy is not None else None
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "code": "SOURCE_WORKSPACE_REBIND_REQUIRED",
                "message": "Select and bind the active Nextcloud Source before starting Preview.",
                "boundSourceId": bound_id,
                "boundSourceStatus": legacy.status if legacy is not None else None,
                "candidates": [
                    {"sourceId": item.id, "sourceName": item.name, "status": item.status}
                    for item in candidates
                ],
            },
        )

    def bind_workspace_source(self, *, source_id: str, user: FlowHubUser) -> dict[str, Any]:
        source = self.db.get(SourceProfile, source_id)
        if source is None or (source.owner_user_id != user.id and user.role != "admin"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Source not found.")
        connector = self.db.get(IntegrationConnectorInstance, source.external_source_id)
        if source.status != "active" or connector is None or connector.connector_type != "nextcloud":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {"code": "SOURCE_WORKSPACE_BINDING_INVALID", "message": "Only an active Nextcloud Source can be bound."},
            )
        self.config.set("nextcloud.workspace_source_id", source.id, updated_by=user.username)
        return {"sourceId": source.id, "sourceName": source.name, "status": source.status}

    def workspace_source_binding(self, user: FlowHubUser) -> dict[str, Any]:
        bound_id = self.config.get("nextcloud.workspace_source_id")
        bound = self.db.get(SourceProfile, bound_id) if bound_id else None
        candidates = (
            self.db.query(SourceProfile)
            .join(IntegrationConnectorInstance, IntegrationConnectorInstance.id == SourceProfile.external_source_id)
            .filter(SourceProfile.owner_user_id == user.id)
            .filter(SourceProfile.status == "active")
            .filter(IntegrationConnectorInstance.connector_type == "nextcloud")
            .order_by(SourceProfile.name, SourceProfile.id)
            .all()
        )
        return {
            "boundSource": (
                {"sourceId": bound.id, "sourceName": bound.name, "status": bound.status}
                if bound is not None and bound.status != "deleted"
                else None
            ),
            "candidates": [
                {"sourceId": item.id, "sourceName": item.name, "status": item.status}
                for item in candidates
            ],
        }

    async def _create_preview_from_nextcloud(
        self,
        user: FlowHubUser,
        *,
        source_config_hash: str | None = None,
        worksheet_scope: dict[str, object] | None = None,
    ) -> WorkspacePreviewResponse:
        started = datetime.now(timezone.utc).replace(tzinfo=None)
        preview_id = f"wp_{uuid.uuid4().hex[:16]}"
        self._required_config("nextcloud.spreadsheet_path")
        self._require_channel_config()
        latest_refresh = self._latest_cache_refresh()
        self._ensure_cache_refresh_ready(latest_refresh)
        products = self._load_products()
        if not products:
            raise HTTPException(status.HTTP_409_CONFLICT, "WooCommerce product cache is empty. Run a manual read first.")

        worksheet_scope = worksheet_scope or self.source_reader.worksheet_scope(
            source_profile_id=self.workspace_source_id
        )
        imported = await self.source_reader.read_nextcloud_spreadsheet(
            triggered_by=user.username,
            triggered_by_id=user.id,
            manual=False,
            source_profile_id=self.workspace_source_id,
            worksheet_scope=worksheet_scope,
        )
        rows = self._build_preview_rows(
            imported.rows,
            imported.duplicate_info,
            products,
            preview_id,
            imported.snapshot,
            source_config_hash or self._source_config_hash(self.workspace_source_id),
            mapping_revision=worksheet_scope.get("mapping_revision"),
        )
        summary = _summary(rows)
        eligible_changes = [row["dry_run_change"] for row in rows if row["eligible_for_dry_run"]]
        duplicate_warnings = _duplicate_warnings(imported.duplicate_info)
        if latest_refresh is not None and latest_refresh.status == "completed_with_warnings":
            duplicate_warnings.append(
                "WooCommerce cache refresh completed with warnings"
                f" ({self._refresh_timestamp(latest_refresh)}). Review Commerce Hub -> Channels if preview results look incomplete."
            )
        preview_snapshot = WorkspacePreviewStore(self.db).create(
            preview_id=preview_id,
            source_id=self.workspace_source_id,
            source_snapshot=imported.snapshot,
            owner=user,
            rows=rows,
            summary=summary,
        )
        self.integration.record_event(
            connector_id=self.workspace_connector_id,
            event_name="preview_created",
            message="Immutable Workspace preview created from source rows.",
            metadata={
                "preview_id": preview_id,
                "preview_hash": preview_snapshot.preview_hash,
                "source_id": self.workspace_source_id,
                "source_type": SOURCE_TYPE,
                "source_file_path": imported.spreadsheet_path,
                "row_count": summary["total_rows"],
                "selected_count": len(eligible_changes),
                "changed_count": summary["changed_prices"],
                "blocked_count": summary["blocked_rows"],
                "stock_write": False,
            },
        )
        return WorkspacePreviewResponse(
            id=preview_id,
            sourceId=self.workspace_source_id,
            sourceName=f"Nextcloud Spreadsheet: {imported.spreadsheet_path}",
            state="preview_ready",
            totalChanges=len(eligible_changes),
            changes=eligible_changes,
            rows=rows,
            summary=summary,
            startedAt=started.isoformat(),
            duplicateWarnings=duplicate_warnings,
            sourceContext={
                "filePath": imported.spreadsheet_path,
                "worksheet": worksheet_scope.get("name") or None,
                "rowsRead": summary["total_rows"],
                "mappingRevision": worksheet_scope.get("mapping_revision"),
            },
            runtime_write_blocked=True,
            external_call_performed=True,
        )

    def _clone_reusable_preview(self, preview: DlWorkspacePreview, user: FlowHubUser) -> DlWorkspacePreview:
        source_snapshot = self.db.get(DlSourceSnapshot, preview.source_snapshot_id)
        if source_snapshot is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Cached source snapshot is no longer available.")
        preview_id = f"wp_{uuid.uuid4().hex[:16]}"
        rows = json.loads(_canonical_json(preview.rows_json if isinstance(preview.rows_json, list) else []))
        for row in rows:
            source = row.get("source")
            if isinstance(source, dict):
                source["previewId"] = preview_id
            change = row.get("dry_run_change")
            if isinstance(change, dict) and isinstance(change.get("source"), dict):
                change["source"]["previewId"] = preview_id
        return WorkspacePreviewStore(self.db).create(
            preview_id=preview_id,
            source_id=preview.source_id,
            source_snapshot=source_snapshot,
            owner=user,
            rows=rows,
            summary=preview.summary_json if isinstance(preview.summary_json, dict) else {},
        )

    def _reused_preview_response(self, preview: DlWorkspacePreview, user: FlowHubUser) -> WorkspacePreviewResponse:
        rows = preview.rows_json if isinstance(preview.rows_json, list) else []
        summary = preview.summary_json if isinstance(preview.summary_json, dict) else {}
        mapping_revision = (
            rows[0].get("source", {}).get("mappingRevision")
            if rows and isinstance(rows[0].get("source"), dict)
            else None
        )
        changes = [
            row["dry_run_change"]
            for row in rows
            if row.get("eligible_for_dry_run") is True and isinstance(row.get("dry_run_change"), dict)
        ]
        source_path = ""
        if rows and isinstance(rows[0].get("source"), dict):
            source_path = str(rows[0]["source"].get("sourceFilePath") or "")
        self.integration.record_event(
            connector_id=self.workspace_connector_id,
            event_name="preview_reused",
            message="Recent immutable Workspace preview reused without another source read.",
            metadata={
                "preview_id": preview.id,
                "source_id": self.workspace_source_id,
                "actor": user.username,
                "source_read_performed": False,
            },
        )
        return WorkspacePreviewResponse(
            id=preview.id,
            sourceId=self.workspace_source_id,
            sourceName=f"Nextcloud Spreadsheet: {source_path}" if source_path else "Nextcloud Spreadsheet",
            state="preview_ready",
            totalChanges=len(changes),
            changes=changes,
            rows=rows,
            summary=summary,
            startedAt=preview.created_at.isoformat(),
            duplicateWarnings=[],
            sourceContext={
                "filePath": source_path or None,
                "worksheet": rows[0].get("source", {}).get("worksheet") if rows else None,
                "rowsRead": summary.get("total_rows", len(rows)),
                "mappingRevision": mapping_revision,
            },
            runtime_write_blocked=True,
            external_call_performed=False,
        )

    def _required_config(self, key: str) -> str:
        value = self.config.get(key)
        if not value:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Missing required setting: {key}")
        return value

    def _source_config_hash(
        self,
        source_profile_id: str | None = None,
        *,
        worksheet_scope: dict[str, object] | None = None,
    ) -> str:
        worksheet_scope = worksheet_scope or self.source_reader.worksheet_scope(
            source_profile_id=source_profile_id
        )
        payload = {
            "spreadsheet_path": self._required_config("nextcloud.spreadsheet_path"),
            "mapping": self.source_reader.mapping(),
            "worksheet": worksheet_scope,
        }
        return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()

    def _require_channel_config(self) -> None:
        for key in ("woocommerce.url", "woocommerce.key", "woocommerce.secret"):
            self._required_config(key)

    def _load_products(self) -> list[DlProductCache]:
        return (
            self.db.query(DlProductCache)
            .filter(DlProductCache.connector_id == CHANNEL_ID)
            .filter(DlProductCache.exists.is_(True))
            .all()
        )

    def _latest_cache_refresh(self) -> DlRefreshJob | None:
        return (
            self.db.query(DlRefreshJob)
            .filter(DlRefreshJob.connector_id == CHANNEL_ID, DlRefreshJob.entity_type == "products")
            .order_by(DlRefreshJob.created_at.desc(), DlRefreshJob.id.desc())
            .first()
        )

    def _ensure_cache_refresh_ready(self, latest_refresh: DlRefreshJob | None) -> None:
        if latest_refresh is None:
            return
        if latest_refresh.status not in {"failed", "partial_failed"}:
            return
        timestamp = self._refresh_timestamp(latest_refresh)
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "CACHE_REFRESH_INCOMPLETE: WooCommerce product cache refresh status is "
            f"'{latest_refresh.status}' as of {timestamp}. Refresh product cache again in Commerce Hub -> Channels.",
        )

    def _refresh_timestamp(self, latest_refresh: DlRefreshJob) -> str:
        return (
            (latest_refresh.completed_at or latest_refresh.started_at or latest_refresh.created_at).isoformat()
            if (latest_refresh.completed_at or latest_refresh.started_at or latest_refresh.created_at)
            else "unknown"
        )

    def _build_preview_rows(
        self,
        source_rows: list[dict],
        duplicate_info: dict,
        products: list[DlProductCache],
        preview_id: str,
        snapshot: DlSourceSnapshot,
        source_config_hash: str,
        mapping_revision: object | None = None,
    ) -> list[dict]:
        by_product_id = {row.product_id: row for row in products if row.product_id}
        by_sku: dict[str, list[DlProductCache]] = {}
        for product in products:
            if product.sku:
                by_sku.setdefault(product.sku.strip().lower(), []).append(product)

        duplicate_product_ids = set(duplicate_info["duplicate_product_ids"])
        duplicate_skus = set(duplicate_info["duplicate_skus"])
        preview_rows: list[dict] = []
        for row_index, source_row in enumerate(source_rows):
            errors: list[str] = []
            warnings: list[str] = []
            status_value = "valid_change"
            errors.extend(str(item) for item in source_row.get("row_errors") or [])
            warnings.extend(str(item) for item in source_row.get("row_warnings") or [])
            matched = self._match_product(source_row, by_product_id, by_sku, errors)
            proposed_price = source_row.get("proposed_price")
            product_id = source_row.get("product_id")
            sku = str(source_row.get("sku") or "")
            price_enabled = source_row.get("price_enabled") is not False
            stock_enabled = source_row.get("stock_enabled") is True
            source_stock = source_row.get("source_stock")

            if not product_id and not sku.strip():
                errors.append("missing_product_identifier")
            if source_row.get("product_id_error"):
                errors.append("invalid_product_id")
            if product_id and product_id in duplicate_product_ids:
                errors.append("duplicate_product_id")
            if sku and sku.strip().lower() in duplicate_skus:
                errors.append("duplicate_sku")
            if price_enabled:
                if source_row.get("price_parse_error") or source_row.get("raw_price") == "":
                    errors.append("invalid_or_missing_price")
                elif proposed_price is None:
                    errors.append("missing_price")
                elif not isinstance(proposed_price, int | float) or not math.isfinite(float(proposed_price)):
                    errors.append("invalid_price")
                elif float(proposed_price) <= 0:
                    errors.append("zero_or_negative_price")

            if matched is not None:
                product_type = (matched.row.product_type or "simple").lower()
                if product_type not in SUPPORTED_WRITE_PRODUCT_TYPES:
                    errors.append("unsupported_product_type")
                if product_type == "variation" and not str(matched.row.parent_id or "").strip():
                    errors.append("missing_variation_parent_id")
                if matched.row.freshness == "stale":
                    warnings.append("stale_product_cache")
                if _parse_float(matched.row.sale_price) is not None:
                    warnings.append("active_sale_price_not_modified")
                if stock_enabled and source_stock is not None and matched.row.manage_stock is False:
                    warnings.append("manage_stock_false_stock_update_requested")

            current_price = matched.current_price if matched is not None else None
            current_stock = matched.row.stock_qty if matched is not None else None
            proposed = float(proposed_price) if price_enabled and isinstance(proposed_price, int | float) else None
            difference = None
            change_pct = None
            price_changed = False
            if current_price is not None and proposed is not None:
                difference = proposed - current_price
                change_pct = ((proposed - current_price) / current_price) * 100 if current_price else 0.0
                if proposed == current_price:
                    status_value = "unchanged"
                else:
                    price_changed = True
                    if abs(change_pct) > MAX_DRY_RUN_DELTA_PERCENT:
                        errors.append("large_price_change_blocked")
                    elif abs(change_pct) > LARGE_CHANGE_WARNING_PERCENT:
                        warnings.append("large_price_change")
                if proposed < SUSPICIOUS_LOW_PRICE:
                    warnings.append("suspiciously_low_price")
                if proposed > SUSPICIOUS_HIGH_PRICE:
                    warnings.append("suspiciously_high_price")

            stock_difference = None
            stock_changed = False
            if stock_enabled and isinstance(source_stock, int) and current_stock is not None:
                stock_difference = source_stock - int(current_stock)
                stock_changed = stock_difference != 0
                if source_stock < 0:
                    errors.append("stock_below_zero")
                if abs(stock_difference) > 1000:
                    warnings.append("large_stock_change")

            if price_enabled is False and stock_changed:
                status_value = "stock_changed"
            elif price_changed and stock_changed:
                status_value = "price_and_stock_changed"
            elif price_changed:
                status_value = "valid_change"
            elif stock_changed:
                status_value = "stock_changed"
            elif not errors:
                status_value = "unchanged"

            if errors:
                status_value = "error"
            elif status_value != "unchanged" and warnings:
                status_value = "warning"

            eligible = (
                status_value in {"valid_change", "warning", "price_and_stock_changed"}
                and matched is not None
                and proposed is not None
                and price_changed
            )
            dry_run_change = None
            if eligible:
                dry_run_change = {
                    "productId": matched.row.product_id,
                    "productName": matched.row.name or source_row.get("product_name") or "",
                    "sku": matched.row.sku or sku,
                    "currentPrice": current_price,
                    "proposedPrice": proposed,
                    "currency": self.config.get("server.currency") or "EUR",
                    "changePct": round(change_pct or 0.0, 4),
                    "difference": round(difference or 0.0, 4),
                    "warning": "; ".join(warnings) if warnings else None,
                    "validationStatus": status_value,
                    "status": status_value,
                    "eligible_for_dry_run": True,
                    "itemType": _item_type(matched.row),
                    "parentProductId": matched.row.parent_id,
                    "parentProductName": matched.parent_row.name if matched.parent_row is not None else None,
                    "variationId": matched.row.product_id if _item_type(matched.row) == "variation" else None,
                    "variationAttributes": matched.variation_attributes,
                    "source": _source_payload(
                        source_row, preview_id, snapshot, row_index, source_config_hash,
                        source_id=self.workspace_source_id,
                        mapping_revision=mapping_revision,
                    ),
                    "validationWarnings": warnings,
                }

            errors = list(dict.fromkeys(errors))
            warnings = list(dict.fromkeys(warnings))
            source_payload = _source_payload(
                source_row, preview_id, snapshot, row_index, source_config_hash,
                source_id=self.workspace_source_id,
                mapping_revision=mapping_revision,
            )
            preview_rows.append({
                "id": _preview_row_id(source_row, snapshot, row_index, source_id=self.workspace_source_id),
                "source": source_payload,
                "matchedProduct": _matched_payload(matched),
                "currentPrice": current_price,
                "proposedPrice": proposed,
                "currentStock": current_stock,
                "sourceStock": source_stock,
                "stockDifference": stock_difference,
                "difference": round(difference, 4) if difference is not None else None,
                "changePct": round(change_pct, 4) if change_pct is not None else None,
                "status": status_value,
                "changeType": _change_type(price_changed, stock_changed),
                "errors": errors,
                "errorDetails": source_row.get("row_error_details") or [],
                "warnings": warnings,
                "eligible_for_dry_run": eligible,
                "dry_run_change": dry_run_change,
            })
        invalid_count = sum(1 for row in preview_rows if row["errors"])
        snapshot.invalid_row_count = invalid_count
        self.db.commit()
        return preview_rows

    def _match_product(
        self,
        source_row: dict,
        by_product_id: dict[str, DlProductCache],
        by_sku: dict[str, list[DlProductCache]],
        errors: list[str],
    ) -> ProductMatch | None:
        candidates: list[DlProductCache] = []
        product_id = source_row.get("product_id")
        if product_id and source_row.get("id_enabled") is not False:
            product = by_product_id.get(str(product_id))
            if product is not None:
                candidates = [product]
        if not candidates and source_row.get("sku"):
            candidates = by_sku.get(str(source_row["sku"]).strip().lower(), [])

        if not candidates:
            errors.append("missing_product")
            return None
        if len(candidates) > 1:
            errors.append("ambiguous_product_match")
            return None
        current_price = _current_price(candidates[0])
        if current_price is None:
            errors.append("missing_current_price")
            return None
        return ProductMatch(
            row=candidates[0],
            current_price=current_price,
            category_names=_category_names(candidates[0].categories),
            image_url=_resolved_image_url(candidates[0], by_product_id),
            parent_row=by_product_id.get(str(candidates[0].parent_id)) if candidates[0].parent_id else None,
            variation_attributes=_variation_attributes(candidates[0].raw_data),
        )


def _current_price(product: DlProductCache) -> float | None:
    for raw in (product.sale_price, product.regular_price, product.price, product.last_price):
        parsed = _parse_float(raw)
        if parsed is not None and parsed >= 0:
            return parsed
    return None


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        text = str(value).replace(",", "").strip()
        if text == "":
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def _category_names(categories: Any) -> list[str]:
    if not isinstance(categories, list):
        return []
    names: list[str] = []
    for item in categories:
        if isinstance(item, dict) and item.get("name"):
            names.append(str(item["name"]))
        elif isinstance(item, str):
            names.append(item)
    return names


def _image_url(images: Any) -> str | None:
    return primary_image_url(images)


def _resolved_image_url(product: DlProductCache, by_product_id: dict[str, DlProductCache]) -> str | None:
    image_url = _image_url(product.images)
    if image_url:
        return image_url
    if (product.product_type or "").lower() != "variation" or not product.parent_id:
        return None
    parent = by_product_id.get(str(product.parent_id))
    return _image_url(parent.images) if parent is not None else None


def _variation_attributes(raw_data: Any) -> list[dict]:
    if not isinstance(raw_data, dict):
        return []
    raw_attributes = raw_data.get("attributes") or raw_data.get("variation_attributes") or []
    if not isinstance(raw_attributes, list):
        return []
    attributes: list[dict] = []
    for item in raw_attributes:
        if isinstance(item, dict):
            name = item.get("name") or item.get("attribute") or item.get("slug")
            value = item.get("option") or item.get("value")
            if name or value:
                attributes.append({"name": str(name or ""), "value": str(value or "")})
    return attributes


def _item_type(row: DlProductCache) -> str:
    return "variation" if (row.product_type or "").lower() == "variation" else "simple"


@asynccontextmanager
async def _preview_execution_lock(db: Session, key: str):
    if db.get_bind().dialect.name != "postgresql":
        lock = _LOCAL_PREVIEW_LOCKS.setdefault(key, asyncio.Lock())
        async with lock:
            yield
        return

    connection = db.get_bind().connect()
    acquired = False
    deadline = monotonic() + 120.0
    try:
        while monotonic() < deadline:
            acquired = bool(
                connection.execute(
                    text("SELECT pg_try_advisory_lock(hashtextextended(:lock_key, 0))"),
                    {"lock_key": key},
                ).scalar()
            )
            if acquired:
                break
            await asyncio.sleep(0.1)
        if not acquired:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                {"code": "PREVIEW_IN_PROGRESS", "message": "A preview is already being prepared. Try again shortly."},
                headers={"Retry-After": "2"},
            )
        yield
    finally:
        if acquired:
            connection.execute(
                text("SELECT pg_advisory_unlock(hashtextextended(:lock_key, 0))"),
                {"lock_key": key},
            )
        connection.close()


def _source_payload(
    source_row: dict,
    preview_id: str,
    snapshot: DlSourceSnapshot,
    row_index: int | None = None,
    source_config_hash: str = "",
    *,
    source_id: str = SOURCE_ID,
    mapping_revision: object | None = None,
) -> dict:
    return {
        "previewId": preview_id,
        "sourceId": source_id,
        "sourceType": SOURCE_TYPE,
        "sourceSnapshotId": snapshot.id,
        "sourceSnapshotVersion": snapshot.version_seq,
        "sourceConfigHash": source_config_hash,
        "mappingRevision": mapping_revision,
        "sourceFilePath": snapshot.file_path,
        "worksheet": source_row.get("worksheet"),
        "rowNumber": source_row.get("row_number"),
        "sourceRowIndex": row_index,
        "productId": source_row.get("product_id"),
        "sourceDisplayName": source_row.get("product_name") or "",
        "sourceProductKey": source_row.get("product_id"),
        "sourceRowNumber": source_row.get("row_number"),
        "sourceLocation": f"{source_row.get('worksheet')}:{source_row.get('row_number')}" if source_row.get("worksheet") and source_row.get("row_number") else None,
        "sku": source_row.get("sku") or "",
        "productName": source_row.get("product_name") or "",
        "rawPrice": source_row.get("raw_price") or "",
        "rawStock": source_row.get("raw_stock") or "",
        "sourceStock": source_row.get("source_stock"),
        "rawValues": source_row.get("raw_values") or {},
        "raw": source_row.get("raw") or {},
    }


def _preview_row_id(
    source_row: dict,
    snapshot: DlSourceSnapshot,
    row_index: int,
    *,
    source_id: str = SOURCE_ID,
) -> str:
    sheet = str(source_row.get("worksheet") or source_row.get("sheet_name") or "").strip()
    row_number = _positive_int(source_row.get("row_number"))
    if sheet and row_number is not None:
        location = {"sheet": sheet, "row_number": row_number, "fallback": False}
    elif sheet:
        location = {"sheet": sheet, "source_row_index": row_index, "fallback": True}
    else:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {
                "code": "WORKSPACE_PREVIEW_ROW_ID_INVALID",
                "message": "Source row location is missing.",
                "row": {"source_row_index": row_index},
            },
        )
    payload = {
        "source_id": source_id,
        "source_type": SOURCE_TYPE,
        "source_snapshot_id": snapshot.id,
        "source_snapshot_version": snapshot.version_seq,
        "source_integrity_hash": snapshot.integrity_hash,
        "location": location,
    }
    digest = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return f"wpr_{digest[:32]}"


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _matched_payload(match: ProductMatch | None) -> dict | None:
    if match is None:
        return None
    row = match.row
    return {
        "channelId": CHANNEL_ID,
        "productId": row.product_id,
        "externalId": row.external_id,
        "productType": row.product_type or "simple",
        "parentId": row.parent_id,
        "parentProductId": row.parent_id,
        "parentProductName": match.parent_row.name if match.parent_row is not None else None,
        "variationId": row.product_id if _item_type(row) == "variation" else None,
        "variationAttributes": match.variation_attributes,
        "itemType": _item_type(row),
        "sku": row.sku or "",
        "name": row.name or "",
        "currentPrice": match.current_price,
        "regularPrice": _parse_float(row.regular_price),
        "salePrice": _parse_float(row.sale_price),
        "effectivePrice": match.current_price,
        "stockQuantity": row.stock_qty,
        "stockStatus": row.stock_status,
        "manageStock": row.manage_stock,
        "imageUrl": match.image_url,
        "categoryNames": match.category_names,
        "lastFetchedAt": row.last_fetched_at.isoformat() if row.last_fetched_at else None,
        "freshness": row.freshness,
    }


def _summary(rows: list[dict]) -> dict:
    changed_prices = sum(1 for row in rows if row.get("difference") not in (None, 0) and row["status"] != "error")
    changed_stock = sum(1 for row in rows if row.get("stockDifference") not in (None, 0) and row["status"] != "error")
    return {
        "total_rows": len(rows),
        "valid_changes": sum(1 for row in rows if row["status"] == "valid_change"),
        "unchanged_rows": sum(1 for row in rows if row["status"] == "unchanged"),
        "warning_rows": sum(1 for row in rows if row["warnings"]),
        "error_rows": sum(1 for row in rows if row["errors"]),
        "blocked_rows": sum(1 for row in rows if row["errors"]),
        "duplicate_rows": sum(
            1 for row in rows if "duplicate_product_id" in row["errors"] or "duplicate_sku" in row["errors"]
        ),
        "missing_products": sum(1 for row in rows if "missing_product" in row["errors"]),
        "large_changes": sum(
            1 for row in rows if "large_price_change" in row["warnings"] or "large_price_change_blocked" in row["errors"]
        ),
        "matched_products": sum(
            1 for row in rows if row.get("matchedProduct") and row["matchedProduct"].get("itemType") == "simple"
        ),
        "matched_variations": sum(
            1 for row in rows if row.get("matchedProduct") and row["matchedProduct"].get("itemType") == "variation"
        ),
        "unmatched_rows": sum(1 for row in rows if row.get("matchedProduct") is None),
        "changed_prices": changed_prices,
        "changed_stock": changed_stock,
        "estimated_woocommerce_updates": sum(1 for row in rows if row.get("eligible_for_dry_run")),
    }


def _change_type(price_changed: bool, stock_changed: bool) -> str:
    if price_changed and stock_changed:
        return "price_and_stock_changed"
    if price_changed:
        return "price_changed"
    if stock_changed:
        return "stock_changed"
    return "unchanged"


def _duplicate_warnings(duplicate_info: dict) -> list[str]:
    warnings: list[str] = []
    for product_id in duplicate_info["duplicate_product_ids"]:
        warnings.append(f"Duplicate product ID in spreadsheet: {product_id}")
    for sku in duplicate_info["duplicate_skus"]:
        warnings.append(f"Duplicate SKU in spreadsheet: {sku}")
    return warnings
