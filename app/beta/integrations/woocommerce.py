"""FlowHub Beta — WooCommerce client (BU5).

Adapted from production-proven WooPrice woocommerce.py.
Read-only: product listing + category listing only.
No price writes, no stock writes, no batch updates.

Retry strategy (adapted from WooPrice):
  - Retries on 429, 500, 502, 503, 504.
  - Respects Retry-After header.
  - Exponential back-off capped at _MAX_RETRY_SLEEP seconds.
  - Raises IntegrationError when total retry sleep budget exhausted.

Logging:
  - Every external request: provider, endpoint, duration_ms, status_code.
  - Every retry: attempt#, wait_s, reason.
  - Errors: readable message, no secrets.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

import httpx

from .errors import IntegrationError

if TYPE_CHECKING:
    from app.beta.setup.service import AppConfigService

logger = logging.getLogger(__name__)

# ── Retry constants (adapted from WooPrice) ───────────────────────────────────

_RETRY_STATUSES: frozenset[int] = frozenset({429, 500, 502, 503, 504})
_MAX_RETRIES = 3
_MAX_RETRY_SLEEP = 30.0
_MAX_TOTAL_RETRY_SLEEP = 90.0

# WooCommerce API field selectors
_PRODUCT_FIELDS = (
    "id,name,type,sku,regular_price,sale_price,price,"
    "stock_status,categories,images,status,date_modified_gmt"
)
_CATEGORY_FIELDS = "id,name,parent,count"

# Timeout policy
_TIMEOUT_QUICK = httpx.Timeout(connect=10.0, read=15.0, write=10.0, pool=5.0)
_TIMEOUT_PAGE = httpx.Timeout(connect=10.0, read=45.0, write=10.0, pool=5.0)
_TIMEOUT_FULL = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=5.0)

_PROVIDER = "WooCommerce"


# ── Retry helper (aligned with WooPrice _get_with_retry) ─────────────────────

async def _get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    params: dict,
    auth: tuple[str, str],
) -> httpx.Response:
    """GET with exponential back-off retry on transient errors.

    Logs every retry.  Raises IntegrationError when retry budget exhausted.
    """
    total_slept = 0.0

    for attempt in range(_MAX_RETRIES + 1):
        t0 = time.monotonic()
        try:
            r = await client.get(url, params=params, auth=auth)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.warning(
                "wc request error provider=%s endpoint=%s attempt=%d/%d "
                "duration_ms=%.0f error=%s",
                _PROVIDER, url, attempt + 1, _MAX_RETRIES + 1, elapsed_ms, exc,
            )
            if attempt >= _MAX_RETRIES:
                raise IntegrationError(
                    _PROVIDER, url,
                    "Could not connect to WooCommerce — check the store URL and network",
                ) from exc
            sleep_for = min(2.0 ** attempt, _MAX_RETRY_SLEEP)
            if total_slept + sleep_for > _MAX_TOTAL_RETRY_SLEEP:
                raise IntegrationError(
                    _PROVIDER, url,
                    "WooCommerce retry budget exhausted — store may be unavailable",
                ) from exc
            await asyncio.sleep(sleep_for)
            total_slept += sleep_for
            continue

        elapsed_ms = (time.monotonic() - t0) * 1000

        if r.status_code not in _RETRY_STATUSES:
            logger.info(
                "wc request provider=%s endpoint=%s status=%d duration_ms=%.0f success=true",
                _PROVIDER, url, r.status_code, elapsed_ms,
            )
            return r

        if attempt >= _MAX_RETRIES:
            logger.error(
                "wc request failed provider=%s endpoint=%s status=%d "
                "duration_ms=%.0f attempt=%d/%d — giving up",
                _PROVIDER, url, r.status_code, elapsed_ms, attempt + 1, _MAX_RETRIES + 1,
            )
            return r

        # Honour Retry-After if present
        retry_after_str = r.headers.get("Retry-After", "")
        try:
            raw_wait = float(retry_after_str) if retry_after_str else 2.0 ** attempt
        except (ValueError, TypeError):
            raw_wait = 2.0 ** attempt
        sleep_for = min(raw_wait, _MAX_RETRY_SLEEP)

        if total_slept + sleep_for > _MAX_TOTAL_RETRY_SLEEP:
            logger.error(
                "wc retry budget exhausted provider=%s endpoint=%s "
                "total_slept_s=%.0f — aborting",
                _PROVIDER, url, total_slept,
            )
            raise IntegrationError(
                _PROVIDER, url,
                "WooCommerce retry budget exhausted — store may be rate-limiting",
                status_code=r.status_code,
            )

        logger.warning(
            "wc retry provider=%s endpoint=%s status=%d attempt=%d/%d "
            "wait_s=%.0f retry_after=%s",
            _PROVIDER, url, r.status_code, attempt + 1, _MAX_RETRIES + 1,
            sleep_for, retry_after_str or "none",
        )
        await asyncio.sleep(sleep_for)
        total_slept += sleep_for

    # Unreachable — satisfies type checker
    raise IntegrationError(_PROVIDER, url, "Unexpected exit from retry loop")


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
    """Async read-only WooCommerce REST v3 client."""

    def __init__(self, url: str, key: str, secret: str) -> None:
        self._url = url.rstrip("/")
        self._auth = (key, secret)
        self._base = f"{self._url}/wp-json/wc/v3"

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
        params: dict[str, str | int] = {
            "status": "publish",
            "page": page,
            "per_page": per_page,
            "_fields": _PRODUCT_FIELDS,
        }
        if search:
            params["search"] = search
        if category_id:
            params["category"] = category_id
        if product_type in ("simple", "variable"):
            params["type"] = product_type

        endpoint = f"{self._base}/products"
        logger.info(
            "wc get_products_page provider=%s endpoint=%s page=%d per_page=%d",
            _PROVIDER, endpoint, page, per_page,
        )
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_PAGE, follow_redirects=True) as client:
                r = await _get_with_retry(client, endpoint, params, self._auth)
        except IntegrationError:
            raise
        except Exception as exc:
            raise IntegrationError(_PROVIDER, endpoint, str(exc)[:200]) from exc

        if not r.is_success:
            raise IntegrationError(
                _PROVIDER, endpoint,
                f"WooCommerce returned HTTP {r.status_code}",
                status_code=r.status_code,
            )

        total = int(r.headers.get("X-WP-Total", "0"))
        raw_list = r.json()
        products = [p for raw in raw_list if (p := _parse_wc_product(raw)) is not None]
        logger.info(
            "wc get_products_page provider=%s total=%d returned=%d",
            _PROVIDER, total, len(products),
        )
        return products, total

    async def get_all_products_for_preview(self) -> list[dict]:
        """Fetch ALL published products (all pages) for preview comparison.

        Iterates pages of 100 at a time.  Adapted from WooPrice fetch_all_products_fast().
        """
        all_products: list[dict] = []
        page = 1
        endpoint = f"{self._base}/products"

        logger.info("wc get_all_products_for_preview provider=%s started", _PROVIDER)
        t_start = time.monotonic()

        async with httpx.AsyncClient(timeout=_TIMEOUT_FULL, follow_redirects=True) as client:
            while True:
                params: dict[str, str | int] = {
                    "status": "publish",
                    "page": page,
                    "per_page": 100,
                    "_fields": _PRODUCT_FIELDS,
                }
                try:
                    r = await _get_with_retry(client, endpoint, params, self._auth)
                except IntegrationError:
                    raise
                except Exception as exc:
                    raise IntegrationError(_PROVIDER, endpoint, str(exc)[:200]) from exc

                if not r.is_success:
                    logger.warning(
                        "wc get_all_products_for_preview provider=%s page=%d status=%d — stopping",
                        _PROVIDER, page, r.status_code,
                    )
                    break

                raw_list = r.json()
                if not raw_list:
                    break

                for raw in raw_list:
                    p = _parse_wc_product(raw)
                    if p:
                        all_products.append(p)

                total_pages = int(r.headers.get("X-WP-TotalPages", "1"))
                if page >= total_pages:
                    break
                page += 1

        elapsed_ms = (time.monotonic() - t_start) * 1000
        logger.info(
            "wc get_all_products_for_preview provider=%s done "
            "products=%d pages=%d duration_ms=%.0f",
            _PROVIDER, len(all_products), page, elapsed_ms,
        )
        return all_products

    async def get_categories(self) -> list[dict]:
        """Fetch all product categories (paginated, 100 per page)."""
        all_categories: list[dict] = []
        page = 1
        endpoint = f"{self._base}/products/categories"

        logger.info("wc get_categories provider=%s started", _PROVIDER)

        async with httpx.AsyncClient(timeout=_TIMEOUT_PAGE, follow_redirects=True) as client:
            while True:
                params: dict[str, str | int] = {
                    "per_page": 100,
                    "page": page,
                    "_fields": _CATEGORY_FIELDS,
                    "hide_empty": "false",
                }
                try:
                    r = await _get_with_retry(client, endpoint, params, self._auth)
                except IntegrationError:
                    raise
                except Exception as exc:
                    raise IntegrationError(_PROVIDER, endpoint, str(exc)[:200]) from exc

                if not r.is_success:
                    break
                raw_list = r.json()
                if not raw_list:
                    break

                for cat in raw_list:
                    if cat.get("id") and cat.get("name"):
                        all_categories.append({
                            "id": cat["id"],
                            "name": cat["name"],
                            "parent": cat.get("parent", 0),
                            "count": cat.get("count", 0),
                        })

                total_pages = int(r.headers.get("X-WP-TotalPages", "1"))
                if page >= total_pages:
                    break
                page += 1

        logger.info("wc get_categories provider=%s total=%d", _PROVIDER, len(all_categories))
        return all_categories

    async def count_products(self) -> int:
        """Return total published product count from X-WP-Total header."""
        endpoint = f"{self._base}/products"
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_QUICK, follow_redirects=True) as client:
                r = await _get_with_retry(
                    client, endpoint,
                    {"status": "publish", "per_page": "1", "_fields": "id"},
                    self._auth,
                )
        except IntegrationError:
            raise
        except Exception as exc:
            raise IntegrationError(_PROVIDER, endpoint, str(exc)[:200]) from exc

        if not r.is_success:
            return 0
        return int(r.headers.get("X-WP-Total", "0"))

    async def test_connection(self) -> tuple[bool, str, float]:
        """Test connectivity.  Returns (ok, message, latency_ms)."""
        endpoint = f"{self._base}/products"
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_QUICK, follow_redirects=True) as client:
                r = await client.get(
                    endpoint,
                    params={"per_page": "1", "_fields": "id"},
                    auth=self._auth,
                )
            latency_ms = (time.monotonic() - t0) * 1000
            logger.info(
                "wc test_connection provider=%s status=%d latency_ms=%.0f",
                _PROVIDER, r.status_code, latency_ms,
            )
            if r.status_code == 200:
                total = int(r.headers.get("X-WP-Total", "0"))
                return True, f"Connected — {total} products", latency_ms
            if r.status_code == 401:
                return False, "Authentication failed — check consumer key and secret", latency_ms
            if r.status_code == 403:
                return False, "Access denied — ensure the API key has read permissions", latency_ms
            if r.status_code == 404:
                return False, "WooCommerce REST API not found — check store URL", latency_ms
            return False, f"Unexpected HTTP {r.status_code}", latency_ms
        except httpx.ConnectError:
            latency_ms = (time.monotonic() - t0) * 1000
            logger.warning("wc test_connection provider=%s error=ConnectError latency_ms=%.0f", _PROVIDER, latency_ms)
            return False, "Could not connect — check the store URL", latency_ms
        except httpx.TimeoutException:
            latency_ms = (time.monotonic() - t0) * 1000
            logger.warning("wc test_connection provider=%s error=Timeout latency_ms=%.0f", _PROVIDER, latency_ms)
            return False, "Connection timed out", latency_ms
        except Exception as exc:
            latency_ms = (time.monotonic() - t0) * 1000
            logger.warning("wc test_connection provider=%s error=%s latency_ms=%.0f", _PROVIDER, exc, latency_ms)
            return False, f"Error: {str(exc)[:200]}", latency_ms
