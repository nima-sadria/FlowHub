"""Source-driven Workspace preview for WooCommerce price management.

This service imports the configured Nextcloud spreadsheet, validates source
rows against cached WooCommerce products, and returns preview rows. It never
executes marketplace writes; valid rows are handed to the existing Write
Pipeline dry-run endpoint.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.data_layer.models import DlProductCache, DlRefreshJob, DlSourceSnapshot
from app.flowhub.integration_platform.contracts import WorkspacePreviewResponse
from app.flowhub.integration_platform.service import IntegrationPlatformService
from app.flowhub.setup.service import AppConfigService
from app.flowhub.sources.spreadsheet_source import SpreadsheetSourceReadService
from app.flowhub.workspace.preview_store import WorkspacePreviewStore

SOURCE_ID = "nextcloud:primary"
SOURCE_TYPE = "nextcloud_spreadsheet"
CHANNEL_ID = "woocommerce:primary"
MAX_DRY_RUN_DELTA_PERCENT = 50.0
LARGE_CHANGE_WARNING_PERCENT = 30.0
SUSPICIOUS_LOW_PRICE = 1.0
SUSPICIOUS_HIGH_PRICE = 100_000.0
SUPPORTED_WRITE_PRODUCT_TYPES = frozenset({"simple", "variation"})


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

    async def preview_from_nextcloud(self, user: FlowHubUser) -> WorkspacePreviewResponse:
        started = datetime.utcnow()
        preview_id = f"wp_{uuid.uuid4().hex[:16]}"
        self._required_config("nextcloud.spreadsheet_path")
        self._require_channel_config()
        latest_refresh = self._latest_cache_refresh()
        self._ensure_cache_refresh_ready(latest_refresh)
        products = self._load_products()
        if not products:
            raise HTTPException(status.HTTP_409_CONFLICT, "WooCommerce product cache is empty. Run a manual read first.")

        imported = await self.source_reader.read_nextcloud_spreadsheet(
            triggered_by=user.username,
            triggered_by_id=user.id,
            manual=False,
        )
        rows = self._build_preview_rows(imported.rows, imported.duplicate_info, products, preview_id, imported.snapshot)
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
            source_id=SOURCE_ID,
            source_snapshot=imported.snapshot,
            owner=user,
            rows=rows,
            summary=summary,
        )
        self.integration.record_event(
            connector_id=SOURCE_ID,
            event_name="preview_created",
            message="Immutable Workspace preview created from source rows.",
            metadata={
                "preview_id": preview_id,
                "preview_hash": preview_snapshot.preview_hash,
                "source_id": SOURCE_ID,
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
            sourceId=SOURCE_ID,
            sourceName=f"Nextcloud Spreadsheet: {imported.spreadsheet_path}",
            state="preview_ready",
            totalChanges=len(eligible_changes),
            changes=eligible_changes,
            rows=rows,
            summary=summary,
            startedAt=started.isoformat(),
            duplicateWarnings=duplicate_warnings,
            runtime_write_blocked=True,
            external_call_performed=True,
        )

    def _required_config(self, key: str) -> str:
        value = self.config.get(key)
        if not value:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Missing required setting: {key}")
        return value

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
    ) -> list[dict]:
        by_product_id = {row.product_id: row for row in products if row.product_id}
        by_sku: dict[str, list[DlProductCache]] = {}
        for product in products:
            if product.sku:
                by_sku.setdefault(product.sku.strip().lower(), []).append(product)

        duplicate_product_ids = set(duplicate_info["duplicate_product_ids"])
        duplicate_skus = set(duplicate_info["duplicate_skus"])
        preview_rows: list[dict] = []
        for source_row in source_rows:
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
                source_name = str(source_row.get("product_name") or "").strip()
                cache_name = str(matched.row.name or "").strip()
                if source_name and cache_name and source_name.casefold() != cache_name.casefold():
                    errors.append("product_name_mismatch")
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
                    "source": _source_payload(source_row, preview_id, snapshot),
                    "validationWarnings": warnings,
                }

            errors = list(dict.fromkeys(errors))
            warnings = list(dict.fromkeys(warnings))
            preview_rows.append({
                "id": f"{preview_id}:{source_row.get('worksheet')}:{source_row.get('row_number')}",
                "source": _source_payload(source_row, preview_id, snapshot),
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
    if not isinstance(images, list):
        return None
    for item in images:
        if isinstance(item, dict):
            url = item.get("src") or item.get("url")
            if url:
                return str(url)
        elif isinstance(item, str) and item:
            return item
    return None


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


def _source_payload(source_row: dict, preview_id: str, snapshot: DlSourceSnapshot) -> dict:
    return {
        "previewId": preview_id,
        "sourceId": SOURCE_ID,
        "sourceType": SOURCE_TYPE,
        "sourceSnapshotId": snapshot.id,
        "sourceSnapshotVersion": snapshot.version_seq,
        "sourceFilePath": snapshot.file_path,
        "worksheet": source_row.get("worksheet"),
        "rowNumber": source_row.get("row_number"),
        "productId": source_row.get("product_id"),
        "sku": source_row.get("sku") or "",
        "productName": source_row.get("product_name") or "",
        "rawPrice": source_row.get("raw_price") or "",
        "rawStock": source_row.get("raw_stock") or "",
        "sourceStock": source_row.get("source_stock"),
        "rawValues": source_row.get("raw_values") or {},
        "raw": source_row.get("raw") or {},
    }


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
