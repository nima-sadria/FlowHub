"""WooCommerce REST API client for the WooCommerce destination connector.

THIS IS THE ONLY MODULE PERMITTED TO MAKE WooCommerce REST API CALLS.
No other FlowHub module may call wp-json/wc/v3/ endpoints directly.

All operations are READ-ONLY. No write path (PUT/POST/PATCH/DELETE products)
is implemented. FlowHub Beta is a read-only system.

Supported operations:
  - list_products()   — paginated GET /wp-json/wc/v3/products
  - get_product()     — GET /wp-json/wc/v3/products/{id}
  - list_variations() — GET /wp-json/wc/v3/products/{id}/variations
"""
from __future__ import annotations

from typing import Any

import httpx

from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
from app.connectors.destinations.woocommerce.auth import WooCommerceCredentials

_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
_WC_API = "/wp-json/wc/v3"


def _auth(creds: WooCommerceCredentials) -> tuple[str, str]:
    return (creds.key, creds.secret)


def _map_http_error(status: int, provider: str = "woocommerce") -> ConnectorError:
    if status == 401:
        return ConnectorError(
            code=ConnectorErrorCode.AUTH_FAILED,
            message="WooCommerce authentication failed — check consumer key and secret",
            provider=provider,
            http_status=status,
        )
    if status == 403:
        return ConnectorError(
            code=ConnectorErrorCode.PERMISSION,
            message="WooCommerce access denied — ensure the API key has read permissions",
            provider=provider,
            http_status=status,
        )
    if status == 404:
        return ConnectorError(
            code=ConnectorErrorCode.NOT_FOUND,
            message="WooCommerce REST API not found — verify the store URL",
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
            message=f"WooCommerce connection failed: {exc}",
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
            message=f"Failed to parse WooCommerce JSON response: {exc}",
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
    return await _get(creds, f"/products/{product_id}/variations", params={
        "page": page,
        "per_page": per_page,
    })


async def ping(creds: WooCommerceCredentials) -> dict:
    """Lightweight connectivity probe — fetch one product to verify API access."""
    result = await _get(creds, "/products", params={"per_page": 1})
    return {"reachable": True, "sample_count": len(result) if isinstance(result, list) else 0}
