"""WooCommerce product read adapter for the IncrementalReadEngine."""

from __future__ import annotations

import time
from datetime import datetime

from app.connectors.destinations.woocommerce.auth import WooCommerceCredentials
from app.connectors.destinations.woocommerce.rest_client import list_products_paged, list_variations
from app.flowhub.read_engine.contracts import ConnectorReadCapabilities, ReadPage


class WooCommerceProductReadAdapter:
    connector_id = "woocommerce:primary"
    connector_type = "woocommerce"
    uses_http_boundary_limiter = True
    capabilities = ConnectorReadCapabilities(
        supports_modified_since=True,
        supports_delta_sync=True,
        supports_updated_after=True,
        supports_pagination=True,
        supports_batch_read=True,
    )

    def __init__(self, *, url: str, key: str, secret: str, per_page: int = 100) -> None:
        self._creds = WooCommerceCredentials(url=url.rstrip("/"), key=key, secret=secret)
        self._per_page = per_page
        self.products_read = 0
        self.variable_products_read = 0
        self.variations_read = 0
        self.warnings: list[str] = []

    async def fetch_products(
        self,
        *,
        modified_since: datetime | None = None,
        cursor: str | None = None,
        product_ids: list[str] | None = None,
    ) -> ReadPage:
        ids = _numeric_product_ids(product_ids)
        if product_ids is not None and not ids:
            return ReadPage(items=[], next_cursor=None, latency_ms=0.0)

        page = _cursor_to_page(cursor)
        started = time.monotonic()
        items, _total, total_pages = await list_products_paged(
            self._creds,
            page=page,
            per_page=self._per_page,
            product_ids=ids or None,
            modified_since=modified_since,
        )
        expanded: list[dict] = []
        for raw in items:
            product = _normalize_product(raw)
            if product is None:
                self.warnings.append("WooCommerce returned a product without an ID; the row was skipped.")
                continue
            expanded.append(product)
            self.products_read += 1
            if product["product_type"] != "variable":
                continue
            self.variable_products_read += 1
            variations = await self._fetch_all_variations(product)
            expanded.extend(variations)

        latency_ms = (time.monotonic() - started) * 1000
        next_cursor = str(page + 1) if page < total_pages else None
        return ReadPage(items=expanded, next_cursor=next_cursor, latency_ms=latency_ms)

    async def fetch_metadata(self, *, cursor: str | None = None) -> ReadPage:
        page = _cursor_to_page(cursor)
        started = time.monotonic()
        items, _total, total_pages = await list_products_paged(
            self._creds,
            page=page,
            per_page=self._per_page,
            fields="id,date_modified_gmt,regular_price,price,status",
        )
        latency_ms = (time.monotonic() - started) * 1000
        next_cursor = str(page + 1) if page < total_pages else None
        metadata = [
            {
                "product_id": str(item.get("id")),
                "last_modified": item.get("date_modified_gmt"),
                "price": item.get("regular_price") or item.get("price"),
            }
            for item in items
            if item.get("id")
        ]
        return ReadPage(items=metadata, next_cursor=next_cursor, latency_ms=latency_ms, metadata_only=True)

    async def _fetch_all_variations(self, parent: dict) -> list[dict]:
        parent_id = int(parent["product_id"])
        page = 1
        variations: list[dict] = []
        seen: set[str] = set()
        while True:
            raw_items = await list_variations(self._creds, parent_id, page=page, per_page=self._per_page)
            added = 0
            for raw in raw_items:
                variation = _normalize_variation(raw, parent)
                if variation is None:
                    self.warnings.append(
                        f"WooCommerce returned a variation without an ID for parent {parent_id}; the row was skipped."
                    )
                    continue
                variation_id = variation["product_id"]
                if variation_id in seen:
                    continue
                seen.add(variation_id)
                variations.append(variation)
                self.variations_read += 1
                added += 1
            if len(raw_items) < self._per_page:
                break
            if added == 0:
                self.warnings.append(
                    f"WooCommerce variation pagination repeated rows for parent {parent_id}; reading stopped safely."
                )
                break
            page += 1
        return variations


def _cursor_to_page(cursor: str | None) -> int:
    try:
        return max(1, int(cursor or "1"))
    except ValueError:
        return 1


def _numeric_product_ids(product_ids: list[str] | None) -> list[int]:
    if product_ids is None:
        return []
    return [int(item) for item in product_ids if str(item).isdigit()]


def _normalize_product(raw: dict) -> dict | None:
    product_id = str(raw.get("id") or raw.get("product_id") or "").strip()
    if not product_id.isdigit():
        return None
    product_type = str(raw.get("type") or raw.get("product_type") or "simple").strip().lower()
    return {
        **raw,
        "id": product_id,
        "product_id": product_id,
        "product_type": product_type,
        "parent_id": None,
    }


def _normalize_variation(raw: dict, parent: dict) -> dict | None:
    variation_id = str(raw.get("id") or raw.get("product_id") or "").strip()
    parent_id = str(parent.get("product_id") or "").strip()
    if not variation_id.isdigit() or not parent_id.isdigit():
        return None
    images = raw.get("images")
    if not isinstance(images, list):
        image = raw.get("image")
        images = [image] if isinstance(image, dict) and image else []
    return {
        **raw,
        "id": variation_id,
        "product_id": variation_id,
        "type": "variation",
        "product_type": "variation",
        "parent_id": parent_id,
        "parent_name": parent.get("name"),
        "categories": raw.get("categories") or parent.get("categories") or [],
        "images": images,
        "date_modified_gmt": raw.get("date_modified_gmt") or parent.get("date_modified_gmt"),
    }
