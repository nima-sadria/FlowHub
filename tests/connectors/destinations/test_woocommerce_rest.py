"""Tests for the WooCommerce REST client (rest_client.py).

All HTTP calls are mocked — no real WooCommerce store required.
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
from app.connectors.destinations.woocommerce.auth import WooCommerceCredentials
from app.connectors.destinations.woocommerce.rest_client import (
    get_product,
    list_products,
    ping,
)

_CREDS = WooCommerceCredentials(
    url="https://shop.example.com",
    key="ck_abc123",
    secret="cs_xyz789",
)


def _mock_json_response(status: int, data: object) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.json = MagicMock(return_value=data)
    return r


_SAMPLE_PRODUCT = {
    "id": 42,
    "name": "Test Widget",
    "sku": "TW-001",
    "price": "9.99",
    "regular_price": "9.99",
    "sale_price": "",
    "stock_quantity": 100,
    "stock_status": "instock",
    "manage_stock": True,
    "backorders": "no",
}


# ── list_products ─────────────────────────────────────────────────────────────

def test_list_products_returns_list():
    mock_resp = _mock_json_response(200, [_SAMPLE_PRODUCT])

    async def _run():
        with patch("httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
            instance.get = AsyncMock(return_value=mock_resp)
            return await list_products(_CREDS, page=1, per_page=10)

    products = asyncio.run(_run())
    assert isinstance(products, list)
    assert products[0]["id"] == 42
    assert products[0]["name"] == "Test Widget"


def test_list_products_401_raises_auth_error():
    mock_resp = _mock_json_response(401, {"code": "woocommerce_rest_cannot_list"})

    async def _run():
        with patch("httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
            instance.get = AsyncMock(return_value=mock_resp)
            return await list_products(_CREDS)

    with pytest.raises(ConnectorError) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.code == ConnectorErrorCode.AUTH_FAILED
    assert exc_info.value.http_status == 401


def test_list_products_404_raises_not_found():
    mock_resp = _mock_json_response(404, {})

    async def _run():
        with patch("httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
            instance.get = AsyncMock(return_value=mock_resp)
            return await list_products(_CREDS)

    with pytest.raises(ConnectorError) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.code == ConnectorErrorCode.NOT_FOUND


def test_list_products_timeout_raises_retryable():
    async def _run():
        with patch("httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
            instance.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            return await list_products(_CREDS)

    with pytest.raises(ConnectorError) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.code == ConnectorErrorCode.TIMEOUT
    assert exc_info.value.retryable is True


def test_list_products_connect_error_raises_network():
    async def _run():
        with patch("httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
            instance.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
            return await list_products(_CREDS)

    with pytest.raises(ConnectorError) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.code == ConnectorErrorCode.NETWORK
    assert exc_info.value.retryable is True


# ── get_product ───────────────────────────────────────────────────────────────

def test_get_product_returns_dict():
    mock_resp = _mock_json_response(200, _SAMPLE_PRODUCT)

    async def _run():
        with patch("httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
            instance.get = AsyncMock(return_value=mock_resp)
            return await get_product(_CREDS, 42)

    product = asyncio.run(_run())
    assert product["id"] == 42
    assert product["stock_status"] == "instock"


def test_get_product_404_raises_not_found():
    mock_resp = _mock_json_response(404, {})

    async def _run():
        with patch("httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
            instance.get = AsyncMock(return_value=mock_resp)
            return await get_product(_CREDS, 99999)

    with pytest.raises(ConnectorError) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.code == ConnectorErrorCode.NOT_FOUND


# ── ping ──────────────────────────────────────────────────────────────────────

def test_ping_returns_reachable():
    mock_resp = _mock_json_response(200, [_SAMPLE_PRODUCT])

    async def _run():
        with patch("httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
            instance.get = AsyncMock(return_value=mock_resp)
            return await ping(_CREDS)

    result = asyncio.run(_run())
    assert result["reachable"] is True
    assert result["sample_count"] == 1


def test_ping_403_raises_permission():
    mock_resp = _mock_json_response(403, {})

    async def _run():
        with patch("httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
            instance.get = AsyncMock(return_value=mock_resp)
            return await ping(_CREDS)

    with pytest.raises(ConnectorError) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.code == ConnectorErrorCode.PERMISSION
