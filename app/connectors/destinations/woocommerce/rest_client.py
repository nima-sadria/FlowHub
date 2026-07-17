"""WooCommerce REST API client for the WooCommerce destination connector.

THIS IS THE ONLY MODULE PERMITTED TO MAKE WooCommerce REST API CALLS.
No other FlowHub module may call wp-json/wc/v3/ endpoints directly.

FlowHub 1.0.0 permits one explicit write path through the generic Write
Pipeline: WooCommerce price update only. No stock, scheduler, or generic
connector write API is implemented.

Supported operations:
  - list_products()      - paginated GET /wp-json/wc/v3/products (connector ABC)
  - get_product()        - GET /wp-json/wc/v3/products/{id}
  - get_variation()      - GET /wp-json/wc/v3/products/{id}/variations/{variation_id}
  - list_variations()    - GET /wp-json/wc/v3/products/{id}/variations
  - ping()               - lightweight connectivity probe
  - list_products_paged()- paginated product fetch returning (products, total, total_pages)
  - list_all_products()  - all pages of products
  - list_categories_all()- all product categories
  - list_orders_paged()  - paginated read-only order fetch
  - get_order()          - read one order
  - count_products()     - total product count from X-WP-Total header
  - update_product_price()- PUT /wp-json/wc/v3/products/{id} price fields only
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
from app.connectors.destinations.woocommerce.auth import WooCommerceCredentials
from app.flowhub.rate_limit import acquire_connector_rate_limit

_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
_TIMEOUT_QUICK = httpx.Timeout(connect=10.0, read=15.0, write=10.0, pool=5.0)
_TIMEOUT_PAGE = httpx.Timeout(connect=10.0, read=45.0, write=10.0, pool=5.0)
_TIMEOUT_FULL = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=5.0)
_WC_API = "/wp-json/wc/v3"

# Field selectors used by the integration layer
_PRODUCT_FIELDS = (
    "id,name,type,sku,regular_price,sale_price,price,"
    "stock_quantity,stock_status,manage_stock,backorders,"
    "categories,images,attributes,status,date_modified_gmt"
)
_CATEGORY_FIELDS = "id,name,parent,count"
_ORDER_FIELDS = (
    "id,number,status,currency,total,date_created_gmt,date_modified_gmt,"
    "date_paid_gmt,payment_method_title,billing,shipping,line_items"
)

# Retry constants (adapted from the original connector prototype)
_RETRY_STATUSES: frozenset[int] = frozenset({429, 500, 502, 503, 504})
_MAX_RETRIES = 3
_MAX_RETRY_SLEEP = 30.0
_MAX_TOTAL_RETRY_SLEEP = 90.0


def _auth(creds: WooCommerceCredentials) -> tuple[str, str]:
    return (creds.key, creds.secret)


def _map_http_error(status: int, provider: str = "woocommerce") -> ConnectorError:
    if status == 401:
        return ConnectorError(
            code=ConnectorErrorCode.AUTH_FAILED,
            message="WooCommerce authentication failed - check consumer key and secret",
            provider=provider,
            http_status=status,
        )
    if status == 403:
        return ConnectorError(
            code=ConnectorErrorCode.PERMISSION,
            message="WooCommerce access denied - ensure the API key has read permissions",
            provider=provider,
            http_status=status,
        )
    if status == 404:
        return ConnectorError(
            code=ConnectorErrorCode.NOT_FOUND,
            message="WooCommerce REST API not found - verify the store URL",
            provider=provider,
            http_status=status,
        )
    if status == 429:
        return ConnectorError(
            code=ConnectorErrorCode.RATE_LIMITED,
            message="WooCommerce rate limited",
            provider=provider,
            http_status=status,
            retryable=True,
        )
    return ConnectorError(
        code=ConnectorErrorCode.PROVIDER_ERROR,
        message=f"Unexpected WooCommerce status: HTTP {status}",
        provider=provider,
        http_status=status,
    )


async def _get(
    creds: WooCommerceCredentials,
    path: str,
    params: dict[str, Any] | None = None,
) -> Any:
    """Internal GET helper. Returns parsed JSON."""
    url = creds.url + _WC_API + path
    try:
        await acquire_connector_rate_limit("woocommerce:primary", "read")
        async with httpx.AsyncClient(
            auth=_auth(creds),
            follow_redirects=True,
        ) as client:
            r = await client.get(url, params=params or {}, timeout=_TIMEOUT)
    except httpx.TimeoutException as exc:
        raise ConnectorError(
            code=ConnectorErrorCode.TIMEOUT,
            message="WooCommerce request timed out",
            provider="woocommerce",
            retryable=True,
        ) from exc
    except httpx.ConnectError as exc:
        raise ConnectorError(
            code=ConnectorErrorCode.NETWORK,
            message="WooCommerce connection failed.",
            provider="woocommerce",
            retryable=True,
        ) from exc

    if r.status_code != 200:
        raise _map_http_error(r.status_code)

    try:
        return r.json()
    except Exception as exc:
        raise ConnectorError(
            code=ConnectorErrorCode.PROVIDER_ERROR,
            message="WooCommerce returned an invalid response.",
            provider="woocommerce",
        ) from exc


async def _get_raw(
    creds: WooCommerceCredentials,
    path: str,
    params: dict[str, Any] | None = None,
    timeout: httpx.Timeout | None = None,
) -> httpx.Response:
    """GET with exponential back-off retry on transient errors.

    Returns httpx.Response on HTTP 200. Raises ConnectorError on all failures
    including exhausted retries.
    """
    url = creds.url + _WC_API + path
    effective_timeout = timeout or _TIMEOUT
    total_slept = 0.0

    for attempt in range(_MAX_RETRIES + 1):
        try:
            await acquire_connector_rate_limit("woocommerce:primary", "read")
            async with httpx.AsyncClient(
                auth=_auth(creds),
                follow_redirects=True,
            ) as client:
                r = await client.get(url, params=params or {}, timeout=effective_timeout)
        except httpx.TimeoutException as exc:
            if attempt >= _MAX_RETRIES:
                raise ConnectorError(
                    code=ConnectorErrorCode.TIMEOUT,
                    message="WooCommerce request timed out",
                    provider="woocommerce",
                    retryable=True,
                ) from exc
            sleep_for = min(2.0 ** attempt, _MAX_RETRY_SLEEP)
            if total_slept + sleep_for > _MAX_TOTAL_RETRY_SLEEP:
                raise ConnectorError(
                    code=ConnectorErrorCode.TIMEOUT,
                    message="WooCommerce request timed out - retry budget exhausted",
                    provider="woocommerce",
                    retryable=True,
                ) from exc
            await asyncio.sleep(sleep_for)
            total_slept += sleep_for
            continue
        except httpx.ConnectError as exc:
            if attempt >= _MAX_RETRIES:
                raise ConnectorError(
                    code=ConnectorErrorCode.NETWORK,
                    message="WooCommerce connection failed.",
                    provider="woocommerce",
                    retryable=True,
                ) from exc
            sleep_for = min(2.0 ** attempt, _MAX_RETRY_SLEEP)
            if total_slept + sleep_for > _MAX_TOTAL_RETRY_SLEEP:
                raise ConnectorError(
                    code=ConnectorErrorCode.NETWORK,
                    message="WooCommerce connection failed - retry budget exhausted",
                    provider="woocommerce",
                    retryable=True,
                ) from exc
            await asyncio.sleep(sleep_for)
            total_slept += sleep_for
            continue

        if r.status_code not in _RETRY_STATUSES:
            if r.status_code != 200:
                raise _map_http_error(r.status_code)
            return r

        if attempt >= _MAX_RETRIES:
            raise _map_http_error(r.status_code)

        retry_after_str = r.headers.get("Retry-After", "")
        try:
            raw_wait = float(retry_after_str) if retry_after_str else 2.0 ** attempt
        except (ValueError, TypeError):
            raw_wait = 2.0 ** attempt
        sleep_for = min(raw_wait, _MAX_RETRY_SLEEP)

        if total_slept + sleep_for > _MAX_TOTAL_RETRY_SLEEP:
            raise _map_http_error(r.status_code)

        await asyncio.sleep(sleep_for)
        total_slept += sleep_for

    raise ConnectorError(
        code=ConnectorErrorCode.UNKNOWN,
        message="Unexpected exit from retry loop",
        provider="woocommerce",
    )


async def _put(
    creds: WooCommerceCredentials,
    path: str,
    payload: dict[str, Any],
) -> Any:
    """Internal PUT helper for the approved Write Pipeline price adapter."""
    url = creds.url + _WC_API + path
    try:
        async with httpx.AsyncClient(
            auth=_auth(creds),
            follow_redirects=True,
        ) as client:
            r = await client.put(url, json=payload, timeout=_TIMEOUT)
    except httpx.TimeoutException as exc:
        raise ConnectorError(
            code=ConnectorErrorCode.TIMEOUT,
            message="WooCommerce price update timed out",
            provider="woocommerce",
            retryable=True,
        ) from exc
    except httpx.ConnectError as exc:
        raise ConnectorError(
            code=ConnectorErrorCode.NETWORK,
            message="WooCommerce connection failed.",
            provider="woocommerce",
            retryable=True,
        ) from exc

    if r.status_code not in {200, 201}:
        raise _map_http_error(r.status_code)

    try:
        return r.json()
    except Exception as exc:
        raise ConnectorError(
            code=ConnectorErrorCode.PROVIDER_ERROR,
            message="WooCommerce returned an invalid response.",
            provider="woocommerce",
        ) from exc


async def list_products(
    creds: WooCommerceCredentials,
    page: int = 1,
    per_page: int = 100,
    status: str = "publish",
) -> list[dict]:
    """Return a page of WooCommerce products (read-only)."""
    return await _get(creds, "/products", params={
        "page": page,
        "per_page": per_page,
        "status": status,
    })


async def get_product(creds: WooCommerceCredentials, product_id: int) -> dict:
    """Return a single WooCommerce product by ID (read-only)."""
    return await _get(creds, f"/products/{product_id}")


async def list_variations(
    creds: WooCommerceCredentials,
    product_id: int,
    page: int = 1,
    per_page: int = 100,
) -> list[dict]:
    """Return variations of a variable product (read-only)."""
    r = await _get_raw(
        creds,
        f"/products/{product_id}/variations",
        params={
            "page": page,
            "per_page": per_page,
        },
        timeout=_TIMEOUT_PAGE,
    )
    try:
        return r.json()
    except Exception as exc:
        raise ConnectorError(
            code=ConnectorErrorCode.PROVIDER_ERROR,
            message="WooCommerce returned an invalid response.",
            provider="woocommerce",
        ) from exc


async def ping(creds: WooCommerceCredentials) -> dict:
    """Lightweight connectivity probe - fetch one product to verify API access."""
    result = await _get_raw(creds, "/products", params={"per_page": 1, "_fields": "id"}, timeout=_TIMEOUT_QUICK)
    try:
        data = result.json()
    except Exception as exc:
        raise ConnectorError(
            code=ConnectorErrorCode.PROVIDER_ERROR,
            message="WooCommerce returned an invalid response.",
            provider="woocommerce",
        ) from exc
    return {
        "reachable": True,
        "records_checked": len(data) if isinstance(data, list) else 0,
        "http_status": result.status_code,
    }


async def list_products_paged(
    creds: WooCommerceCredentials,
    page: int = 1,
    per_page: int = 20,
    search: str = "",
    category_id: int | None = None,
    product_type: str | None = None,
    fields: str = _PRODUCT_FIELDS,
    status: str = "publish",
    product_ids: list[int] | None = None,
    modified_since: Any | None = None,
) -> tuple[list[dict], int, int]:
    """Return (products, total_count, total_pages) for one page.

    Includes retry logic and respects the Retry-After header.
    """
    params: dict[str, Any] = {
        "status": status,
        "page": page,
        "per_page": per_page,
        "_fields": fields,
    }
    if search:
        params["search"] = search
    if category_id is not None:
        params["category"] = category_id
    if product_type in ("simple", "variable"):
        params["type"] = product_type
    if product_ids:
        params["include"] = ",".join(str(item) for item in product_ids)
    if modified_since is not None:
        if hasattr(modified_since, "isoformat"):
            params["modified_after"] = modified_since.isoformat()
        else:
            params["modified_after"] = str(modified_since)

    r = await _get_raw(creds, "/products", params=params, timeout=_TIMEOUT_PAGE)
    total = int(r.headers.get("X-WP-Total", "0"))
    total_pages = int(r.headers.get("X-WP-TotalPages", "1"))
    try:
        data = r.json()
    except Exception as exc:
        raise ConnectorError(
            code=ConnectorErrorCode.PROVIDER_ERROR,
            message="WooCommerce returned an invalid response.",
            provider="woocommerce",
        ) from exc
    return data, total, total_pages


async def list_orders_paged(
    creds: WooCommerceCredentials,
    *,
    page: int = 1,
    per_page: int = 50,
    status: str = "any",
    fields: str = _ORDER_FIELDS,
) -> tuple[list[dict], int, int]:
    """Return one read-only WooCommerce order page."""
    response = await _get_raw(
        creds,
        "/orders",
        params={
            "page": max(1, page),
            "per_page": min(100, max(1, per_page)),
            "status": status,
            "_fields": fields,
        },
        timeout=_TIMEOUT_PAGE,
    )
    try:
        data = response.json()
    except Exception as exc:
        raise ConnectorError(
            code=ConnectorErrorCode.PROVIDER_ERROR,
            message="WooCommerce returned an invalid order response.",
            provider="woocommerce",
        ) from exc
    if not isinstance(data, list):
        raise ConnectorError(
            code=ConnectorErrorCode.PROVIDER_ERROR,
            message="WooCommerce returned an invalid order response.",
            provider="woocommerce",
        )
    return (
        data,
        int(response.headers.get("X-WP-Total", len(data))),
        int(response.headers.get("X-WP-TotalPages", "1")),
    )


async def get_order(
    creds: WooCommerceCredentials,
    order_id: str,
    *,
    fields: str = _ORDER_FIELDS,
) -> dict:
    """Read one WooCommerce order without mutating provider state."""
    data = await _get(creds, f"/orders/{order_id}", params={"_fields": fields})
    if not isinstance(data, dict):
        raise ConnectorError(
            code=ConnectorErrorCode.PROVIDER_ERROR,
            message="WooCommerce returned an invalid order response.",
            provider="woocommerce",
        )
    return data


async def list_all_products(
    creds: WooCommerceCredentials,
    fields: str = _PRODUCT_FIELDS,
    status: str = "publish",
) -> list[dict]:
    """Fetch ALL products across all pages (100 per page) with retry."""
    all_products: list[dict] = []
    page = 1
    while True:
        r = await _get_raw(creds, "/products", params={
            "status": status,
            "page": page,
            "per_page": 100,
            "_fields": fields,
        }, timeout=_TIMEOUT_FULL)
        try:
            raw_list = r.json()
        except Exception as exc:
            raise ConnectorError(
                code=ConnectorErrorCode.PROVIDER_ERROR,
                message="WooCommerce returned an invalid response.",
                provider="woocommerce",
            ) from exc
        if not raw_list:
            break
        all_products.extend(raw_list)
        total_pages = int(r.headers.get("X-WP-TotalPages", "1"))
        if page >= total_pages:
            break
        page += 1
    return all_products


async def list_categories_all(
    creds: WooCommerceCredentials,
    fields: str = _CATEGORY_FIELDS,
) -> list[dict]:
    """Fetch all product categories across all pages."""
    all_categories: list[dict] = []
    page = 1
    while True:
        r = await _get_raw(creds, "/products/categories", params={
            "per_page": 100,
            "page": page,
            "_fields": fields,
            "hide_empty": "false",
        }, timeout=_TIMEOUT_PAGE)
        try:
            raw_list = r.json()
        except Exception as exc:
            raise ConnectorError(
                code=ConnectorErrorCode.PROVIDER_ERROR,
                message="WooCommerce returned an invalid response.",
                provider="woocommerce",
            ) from exc
        if not raw_list:
            break
        all_categories.extend(raw_list)
        total_pages = int(r.headers.get("X-WP-TotalPages", "1"))
        if page >= total_pages:
            break
        page += 1
    return all_categories


async def count_products(
    creds: WooCommerceCredentials,
    status: str = "publish",
) -> int:
    """Return total product count from the X-WP-Total response header."""
    r = await _get_raw(creds, "/products", params={
        "status": status,
        "per_page": "1",
        "_fields": "id",
    }, timeout=_TIMEOUT_QUICK)
    return int(r.headers.get("X-WP-Total", "0"))


async def get_variation(creds: WooCommerceCredentials, product_id: int, variation_id: int) -> dict:
    """Return one variation by parent product ID and variation ID."""
    data = await _get(creds, f"/products/{product_id}/variations/{variation_id}")
    return data if isinstance(data, dict) else {}


async def update_product_price(
    creds: WooCommerceCredentials,
    product_id: int,
    price: float,
    *,
    parent_product_id: int | None = None,
) -> dict:
    """Update only regular_price for a WooCommerce product or variation.

    Stock and inventory fields are intentionally not accepted by this adapter.
    """
    normalized = f"{price:.2f}"
    path = (
        f"/products/{parent_product_id}/variations/{product_id}"
        if parent_product_id is not None
        else f"/products/{product_id}"
    )
    result = await _put(
        creds,
        path,
        {"regular_price": normalized},
    )
    return {
        "provider": "woocommerce",
        "product_id": result.get("id", product_id) if isinstance(result, dict) else product_id,
        "parent_product_id": parent_product_id,
        "variation_id": product_id if parent_product_id is not None else None,
        "regular_price": result.get("regular_price", normalized) if isinstance(result, dict) else normalized,
        "stock_update": False,
    }
