"""WooCommerce product read adapter for the IncrementalReadEngine."""

from __future__ import annotations

import time
from datetime import datetime

from app.connectors.destinations.woocommerce.auth import WooCommerceCredentials
from app.connectors.destinations.woocommerce.rest_client import list_products_paged
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
        latency_ms = (time.monotonic() - started) * 1000
        next_cursor = str(page + 1) if page < total_pages else None
        return ReadPage(items=items, next_cursor=next_cursor, latency_ms=latency_ms)

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


def _cursor_to_page(cursor: str | None) -> int:
    try:
        return max(1, int(cursor or "1"))
    except ValueError:
        return 1


def _numeric_product_ids(product_ids: list[str] | None) -> list[int]:
    if product_ids is None:
        return []
    return [int(item) for item in product_ids if str(item).isdigit()]
