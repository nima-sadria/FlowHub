"""FlowHub Beta — WooCommerce client (BU5).

All HTTP calls are delegated to app/connectors/destinations/woocommerce/.
No direct httpx usage in this module.

Read-only: product listing + category listing only.
No price writes, no stock writes, no batch updates.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
from app.connectors.destinations.woocommerce.auth import WooCommerceCredentials
from app.connectors.destinations.woocommerce.rest_client import (
    count_products as _count_products,
    list_all_products as _list_all_products,
    list_categories_all as _list_categories_all,
    list_products_paged as _list_products_paged,
    ping as _ping,
)

from .errors import IntegrationError

if TYPE_CHECKING:
    from app.beta.setup.service import AppConfigService

logger = logging.getLogger(__name__)

_PROVIDER = "WooCommerce"


# ── Error mapping ─────────────────────────────────────────────────────────────

def _to_integration_error(exc: ConnectorError, endpoint: str) -> IntegrationError:
    """Map ConnectorError to IntegrationError for the API layer."""
    code = exc.code
    if code == ConnectorErrorCode.AUTH_FAILED:
        msg = "Authentication failed — check consumer key and secret"
    elif code == ConnectorErrorCode.PERMISSION:
        msg = "Access denied — ensure the API key has read permissions"
    elif code == ConnectorErrorCode.NOT_FOUND:
        msg = "WooCommerce REST API not found — check store URL"
    elif code == ConnectorErrorCode.TIMEOUT:
        msg = "Connection timed out"
    elif code == ConnectorErrorCode.NETWORK:
        msg = "Could not connect to WooCommerce — check the store URL and network"
    elif code == ConnectorErrorCode.RATE_LIMITED:
        msg = "WooCommerce retry budget exhausted — store may be rate-limiting"
    else:
        msg = exc.message or f"WooCommerce error: {code.value}"
    return IntegrationError(_PROVIDER, endpoint, msg, status_code=exc.http_status)


# ── Product parser ────────────────────────────────────────────────────────────

def _parse_wc_product(raw: dict) -> dict | None:
    """Parse a raw WC product dict.  Returns None for non-published or invalid items."""
    wc_id = raw.get("id")
    if not wc_id:
        return None
    if raw.get("status") != "publish":
        return None

    # Price — prefer regular_price, fall back to price
    price_str = raw.get("regular_price") or raw.get("price") or "0"
    try:
        current_price = float(price_str) if price_str else 0.0
    except (ValueError, TypeError):
        current_price = 0.0

    categories = raw.get("categories") or []
    category_names = [c["name"] for c in categories if c.get("name")]
    category_ids = [c["id"] for c in categories if c.get("id")]

    images = raw.get("images") or []
    image_url: str | None = images[0]["src"] if images and images[0].get("src") else None

    product_type = raw.get("type", "simple")
    if product_type not in ("simple", "variable"):
        product_type = "simple"

    return {
        "id": str(wc_id),
        "wcId": wc_id,
        "name": raw.get("name", ""),
        "sku": raw.get("sku", ""),
        "currentPrice": current_price,
        "currency": None,       # caller fills from AppConfigService
        "categoryNames": category_names,
        "categoryIds": category_ids,
        "imageUrl": image_url,
        "productType": product_type,
        "status": "pending",    # BU5: no scheduler, always 'pending'
        "lastSynced": None,
    }


# ── Client ────────────────────────────────────────────────────────────────────

class WooCommerceClient:
    """Async read-only WooCommerce REST v3 client backed by the connector framework."""

    def __init__(self, url: str, key: str, secret: str) -> None:
        self._creds = WooCommerceCredentials(
            url=url.rstrip("/"),
            key=key,
            secret=secret,
        )

    @classmethod
    def from_config(cls, config: "AppConfigService") -> "WooCommerceClient | None":
        """Build from AppConfigService.  Returns None if not fully configured."""
        url = config.get("woocommerce.url")
        key = config.get("woocommerce.key")
        secret = config.get("woocommerce.secret")
        if not url or not key or not secret:
            return None
        return cls(url, key, secret)

    async def get_products_page(
        self,
        *,
        page: int = 1,
        per_page: int = 20,
        search: str = "",
        category_id: int | None = None,
        product_type: str | None = None,
    ) -> tuple[list[dict], int]:
        """Fetch one page of products.  Returns (parsed_products, total_count)."""
        endpoint = f"{self._creds.url}/wp-json/wc/v3/products"
        logger.info(
            "wc get_products_page provider=%s page=%d per_page=%d",
            _PROVIDER, page, per_page,
        )
        try:
            raw_list, total, _ = await _list_products_paged(
                self._creds,
                page=page,
                per_page=per_page,
                search=search,
                category_id=category_id,
                product_type=product_type,
            )
        except ConnectorError as exc:
            raise _to_integration_error(exc, endpoint) from exc
        except Exception as exc:
            raise IntegrationError(_PROVIDER, endpoint, str(exc)[:200]) from exc

        products = [p for raw in raw_list if (p := _parse_wc_product(raw)) is not None]
        logger.info(
            "wc get_products_page provider=%s total=%d returned=%d",
            _PROVIDER, total, len(products),
        )
        return products, total

    async def get_all_products_for_preview(self) -> list[dict]:
        """Fetch ALL published products (all pages) for preview comparison."""
        endpoint = f"{self._creds.url}/wp-json/wc/v3/products"
        logger.info("wc get_all_products_for_preview provider=%s started", _PROVIDER)
        t_start = time.monotonic()
        try:
            raw_list = await _list_all_products(self._creds)
        except ConnectorError as exc:
            raise _to_integration_error(exc, endpoint) from exc
        except Exception as exc:
            raise IntegrationError(_PROVIDER, endpoint, str(exc)[:200]) from exc

        all_products = [p for raw in raw_list if (p := _parse_wc_product(raw)) is not None]
        elapsed_ms = (time.monotonic() - t_start) * 1000
        logger.info(
            "wc get_all_products_for_preview provider=%s done products=%d duration_ms=%.0f",
            _PROVIDER, len(all_products), elapsed_ms,
        )
        return all_products

    async def get_categories(self) -> list[dict]:
        """Fetch all product categories (paginated, 100 per page)."""
        endpoint = f"{self._creds.url}/wp-json/wc/v3/products/categories"
        logger.info("wc get_categories provider=%s started", _PROVIDER)
        try:
            raw_list = await _list_categories_all(self._creds)
        except ConnectorError as exc:
            raise _to_integration_error(exc, endpoint) from exc
        except Exception as exc:
            raise IntegrationError(_PROVIDER, endpoint, str(exc)[:200]) from exc

        categories = [
            {
                "id": cat["id"],
                "name": cat["name"],
                "parent": cat.get("parent", 0),
                "count": cat.get("count", 0),
            }
            for cat in raw_list
            if cat.get("id") and cat.get("name")
        ]
        logger.info("wc get_categories provider=%s total=%d", _PROVIDER, len(categories))
        return categories

    async def count_products(self) -> int:
        """Return total published product count."""
        endpoint = f"{self._creds.url}/wp-json/wc/v3/products"
        try:
            return await _count_products(self._creds)
        except ConnectorError as exc:
            raise _to_integration_error(exc, endpoint) from exc
        except Exception as exc:
            raise IntegrationError(_PROVIDER, endpoint, str(exc)[:200]) from exc

    async def test_connection(self) -> tuple[bool, str, float]:
        """Test connectivity.  Returns (ok, message, latency_ms)."""
        t0 = time.monotonic()
        try:
            result = await _ping(self._creds)
            latency_ms = (time.monotonic() - t0) * 1000
            total = result.get("sample_count", 0)
            logger.info(
                "wc test_connection provider=%s ok=true latency_ms=%.0f", _PROVIDER, latency_ms,
            )
            return True, f"Connected — {total} products", latency_ms
        except ConnectorError as exc:
            latency_ms = (time.monotonic() - t0) * 1000
            logger.warning(
                "wc test_connection provider=%s ok=false error=%s latency_ms=%.0f",
                _PROVIDER, exc.message, latency_ms,
            )
            return False, exc.message, latency_ms
        except Exception as exc:
            latency_ms = (time.monotonic() - t0) * 1000
            logger.warning(
                "wc test_connection provider=%s ok=false error=%s latency_ms=%.0f",
                _PROVIDER, exc, latency_ms,
            )
            return False, f"Error: {str(exc)[:200]}", latency_ms
