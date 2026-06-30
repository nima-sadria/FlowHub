"""Connector wiring tests.

Verify that:
1. WooCommerceClient delegates all HTTP to app/connectors/ (rest_client functions).
2. NextcloudClient delegates all HTTP to app/connectors/ (webdav / ocs functions).
3. ConnectorError is translated to IntegrationError.
4. All public method signatures are preserved.
5. settings_routes connection test helpers use connector objects.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.beta.integrations.errors import IntegrationError
from app.beta.integrations.nextcloud import NextcloudClient
from app.beta.integrations.woocommerce import WooCommerceClient
from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
from app.connectors.common.test_result import ConnectionTestResult


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _wc() -> WooCommerceClient:
    return WooCommerceClient("https://shop.example.com", "ck_abc", "cs_xyz")


def _nc() -> NextcloudClient:
    return NextcloudClient("https://cloud.example.com", "alice", "s3cr3t")


_RAW_PRODUCT = {
    "id": 42,
    "name": "Widget",
    "sku": "W-1",
    "type": "simple",
    "regular_price": "9.99",
    "sale_price": "",
    "price": "9.99",
    "stock_status": "instock",
    "categories": [{"id": 1, "name": "Gadgets"}],
    "images": [],
    "status": "publish",
    "date_modified_gmt": "2024-01-01T00:00:00",
}

_RAW_CATEGORY = {"id": 1, "name": "Gadgets", "parent": 0, "count": 5}


# ── WooCommerceClient.get_products_page ───────────────────────────────────────

def test_wc_get_products_page_delegates_to_rest_client():
    async def _run():
        wc = _wc()
        with patch(
            "app.beta.integrations.woocommerce._list_products_paged",
            new=AsyncMock(return_value=([_RAW_PRODUCT], 1, 1)),
        ):
            products, total = await wc.get_products_page(page=1, per_page=10)
        return products, total

    products, total = asyncio.run(_run())
    assert total == 1
    assert products[0]["wcId"] == 42
    assert products[0]["name"] == "Widget"
    assert products[0]["currentPrice"] == 9.99


def test_wc_get_products_page_connector_error_raises_integration_error():
    async def _run():
        wc = _wc()
        with patch(
            "app.beta.integrations.woocommerce._list_products_paged",
            new=AsyncMock(side_effect=ConnectorError(
                code=ConnectorErrorCode.AUTH_FAILED,
                message="WooCommerce authentication failed — check consumer key and secret",
                provider="woocommerce",
                http_status=401,
            )),
        ):
            await wc.get_products_page()

    with pytest.raises(IntegrationError) as exc_info:
        asyncio.run(_run())
    assert "Authentication failed" in exc_info.value.message


def test_wc_get_products_page_filters_non_published():
    raw_draft = dict(_RAW_PRODUCT, status="draft")

    async def _run():
        wc = _wc()
        with patch(
            "app.beta.integrations.woocommerce._list_products_paged",
            new=AsyncMock(return_value=([_RAW_PRODUCT, raw_draft], 2, 1)),
        ):
            products, total = await wc.get_products_page()
        return products

    products = asyncio.run(_run())
    assert len(products) == 1  # draft filtered out


# ── WooCommerceClient.get_all_products_for_preview ────────────────────────────

def test_wc_get_all_products_delegates_to_rest_client():
    async def _run():
        wc = _wc()
        with patch(
            "app.beta.integrations.woocommerce._list_all_products",
            new=AsyncMock(return_value=[_RAW_PRODUCT]),
        ):
            return await wc.get_all_products_for_preview()

    products = asyncio.run(_run())
    assert len(products) == 1
    assert products[0]["wcId"] == 42


def test_wc_get_all_products_connector_error_raises_integration_error():
    async def _run():
        wc = _wc()
        with patch(
            "app.beta.integrations.woocommerce._list_all_products",
            new=AsyncMock(side_effect=ConnectorError(
                code=ConnectorErrorCode.NETWORK,
                message="WooCommerce connection failed: refused",
                provider="woocommerce",
                retryable=True,
            )),
        ):
            await wc.get_all_products_for_preview()

    with pytest.raises(IntegrationError) as exc_info:
        asyncio.run(_run())
    assert "Could not connect" in exc_info.value.message


# ── WooCommerceClient.get_categories ─────────────────────────────────────────

def test_wc_get_categories_delegates_to_rest_client():
    async def _run():
        wc = _wc()
        with patch(
            "app.beta.integrations.woocommerce._list_categories_all",
            new=AsyncMock(return_value=[_RAW_CATEGORY]),
        ):
            return await wc.get_categories()

    cats = asyncio.run(_run())
    assert len(cats) == 1
    assert cats[0]["id"] == 1
    assert cats[0]["name"] == "Gadgets"
    assert cats[0]["count"] == 5


# ── WooCommerceClient.count_products ─────────────────────────────────────────

def test_wc_count_products_delegates_to_rest_client():
    async def _run():
        wc = _wc()
        with patch(
            "app.beta.integrations.woocommerce._count_products",
            new=AsyncMock(return_value=99),
        ):
            return await wc.count_products()

    assert asyncio.run(_run()) == 99


# ── WooCommerceClient.test_connection ────────────────────────────────────────

def test_wc_test_connection_ok_returns_tuple():
    async def _run():
        wc = _wc()
        with patch(
            "app.beta.integrations.woocommerce._ping",
            new=AsyncMock(return_value={"reachable": True, "sample_count": 5}),
        ):
            return await wc.test_connection()

    ok, msg, latency = asyncio.run(_run())
    assert ok is True
    assert "5" in msg
    assert latency >= 0.0


def test_wc_test_connection_failure_returns_tuple():
    async def _run():
        wc = _wc()
        with patch(
            "app.beta.integrations.woocommerce._ping",
            new=AsyncMock(side_effect=ConnectorError(
                code=ConnectorErrorCode.AUTH_FAILED,
                message="WooCommerce authentication failed — check consumer key and secret",
                provider="woocommerce",
            )),
        ):
            return await wc.test_connection()

    ok, msg, latency = asyncio.run(_run())
    assert ok is False
    assert "authentication failed" in msg.lower()
    assert latency >= 0.0


# ── NextcloudClient.download_file ─────────────────────────────────────────────

def test_nc_download_file_delegates_to_webdav():
    content = b"hello xlsx"
    raw_meta = {
        "etag": "abc123",
        "last_modified": "Mon, 01 Jan 2024 00:00:00 GMT",
        "content_type": "application/vnd.ms-excel",
        "content_length": "10",
    }

    async def _run():
        nc = _nc()
        with patch(
            "app.beta.integrations.nextcloud.get_file",
            new=AsyncMock(return_value=(content, raw_meta)),
        ):
            return await nc.download_file("/docs/prices.xlsx")

    data, meta = asyncio.run(_run())
    assert data == b"hello xlsx"
    assert meta["etag"] == "abc123"
    assert meta["last_modified"] == "Mon, 01 Jan 2024 00:00:00 GMT"
    assert meta["content_length"] == "10"


def test_nc_download_file_connector_error_raises_integration_error():
    async def _run():
        nc = _nc()
        with patch(
            "app.beta.integrations.nextcloud.get_file",
            new=AsyncMock(side_effect=ConnectorError(
                code=ConnectorErrorCode.AUTH_FAILED,
                message="WebDAV authentication failed (HTTP 401)",
                provider="nextcloud",
                http_status=401,
            )),
        ):
            await nc.download_file("/docs/prices.xlsx")

    with pytest.raises(IntegrationError) as exc_info:
        asyncio.run(_run())
    assert "Authentication failed" in exc_info.value.message


# ── NextcloudClient.get_file_meta ─────────────────────────────────────────────

def test_nc_get_file_meta_uses_head_first():
    head_result = {"etag": "etag1", "last_modified": "Mon, 01 Jan 2024", "content_length": "100"}

    async def _run():
        nc = _nc()
        with patch(
            "app.beta.integrations.nextcloud.head_file",
            new=AsyncMock(return_value=head_result),
        ) as mock_head:
            result = await nc.get_file_meta("/docs/prices.xlsx")
            assert mock_head.called
            return result

    meta = asyncio.run(_run())
    assert meta["etag"] == "etag1"


def test_nc_get_file_meta_falls_back_to_propfind_when_head_empty():
    propfind_result = {
        "etag": "pf_etag",
        "last_modified": "Tue, 02 Jan 2024",
        "is_collection": False,
        "content_length": 200,
        "content_type": "application/vnd.ms-excel",
    }

    async def _run():
        nc = _nc()
        with patch(
            "app.beta.integrations.nextcloud.head_file",
            new=AsyncMock(return_value={"etag": None, "last_modified": None, "content_length": None}),
        ):
            with patch(
                "app.beta.integrations.nextcloud.get_metadata",
                new=AsyncMock(return_value=propfind_result),
            ):
                return await nc.get_file_meta("/docs/prices.xlsx")

    meta = asyncio.run(_run())
    assert meta["etag"] == "pf_etag"
    assert meta["content_length"] == "200"


def test_nc_get_file_meta_never_raises():
    async def _run():
        nc = _nc()
        with patch(
            "app.beta.integrations.nextcloud.head_file",
            new=AsyncMock(return_value={"etag": None, "last_modified": None, "content_length": None}),
        ):
            with patch(
                "app.beta.integrations.nextcloud.get_metadata",
                new=AsyncMock(side_effect=ConnectorError(
                    code=ConnectorErrorCode.NOT_FOUND,
                    message="not found",
                    provider="nextcloud",
                )),
            ):
                return await nc.get_file_meta("/nonexistent.xlsx")

    meta = asyncio.run(_run())
    assert meta == {"etag": None, "last_modified": None, "content_length": None}


# ── NextcloudClient.test_connection ──────────────────────────────────────────

def test_nc_test_connection_uses_connector():
    async def _run():
        nc = _nc()
        mock_result = ConnectionTestResult(
            ok=True,
            message="Connected to Nextcloud 27.1.0",
            latency_ms=42.0,
        )
        with patch(
            "app.beta.integrations.nextcloud.NextcloudConnector.test_connection",
            new=AsyncMock(return_value=mock_result),
        ):
            return await nc.test_connection()

    ok, msg, latency = asyncio.run(_run())
    assert ok is True
    assert "Nextcloud" in msg
    assert latency == 42.0


def test_nc_test_connection_failure_returns_tuple():
    async def _run():
        nc = _nc()
        mock_result = ConnectionTestResult(
            ok=False,
            message="OCS authentication failed (HTTP 401)",
            latency_ms=10.0,
        )
        with patch(
            "app.beta.integrations.nextcloud.NextcloudConnector.test_connection",
            new=AsyncMock(return_value=mock_result),
        ):
            return await nc.test_connection()

    ok, msg, latency = asyncio.run(_run())
    assert ok is False
    assert "401" in msg


# ── settings_routes helpers ───────────────────────────────────────────────────

def test_settings_routes_wc_test_uses_connector():
    from app.beta.api.v2.settings_routes import _test_woocommerce_connection

    async def _run():
        with patch(
            "app.beta.api.v2.settings_routes.WooCommerceConnector.test_connection",
            new=AsyncMock(return_value=ConnectionTestResult(
                ok=True, message="Connected to WooCommerce store (3 product(s) found)", latency_ms=25.0,
            )),
        ):
            return await _test_woocommerce_connection(
                "https://shop.example.com", "ck_abc", "cs_xyz"
            )

    result = asyncio.run(_run())
    assert result["ok"] is True
    assert "Connected" in result["message"]


def test_settings_routes_wc_test_failure():
    from app.beta.api.v2.settings_routes import _test_woocommerce_connection

    async def _run():
        with patch(
            "app.beta.api.v2.settings_routes.WooCommerceConnector.test_connection",
            new=AsyncMock(return_value=ConnectionTestResult(
                ok=False,
                message="WooCommerce authentication failed — check consumer key and secret",
                latency_ms=5.0,
            )),
        ):
            return await _test_woocommerce_connection(
                "https://shop.example.com", "bad_key", "bad_secret"
            )

    result = asyncio.run(_run())
    assert result["ok"] is False
    assert "authentication failed" in result["message"].lower()


def test_settings_routes_nc_test_uses_connector():
    from app.beta.api.v2.settings_routes import _test_nextcloud_connection

    async def _run():
        with patch(
            "app.beta.api.v2.settings_routes.NextcloudConnector.test_connection",
            new=AsyncMock(return_value=ConnectionTestResult(
                ok=True, message="Connected to Nextcloud 27.1.0", latency_ms=30.0,
            )),
        ):
            return await _test_nextcloud_connection(
                "https://cloud.example.com", "alice", "secret"
            )

    result = asyncio.run(_run())
    assert result["ok"] is True
    assert "Nextcloud" in result["message"]


# ── ConnectorError → IntegrationError mapping ─────────────────────────────────

def test_wc_permission_error_maps_to_integration():
    async def _run():
        wc = _wc()
        with patch(
            "app.beta.integrations.woocommerce._list_products_paged",
            new=AsyncMock(side_effect=ConnectorError(
                code=ConnectorErrorCode.PERMISSION,
                message="WooCommerce access denied",
                provider="woocommerce",
                http_status=403,
            )),
        ):
            await wc.get_products_page()

    with pytest.raises(IntegrationError) as exc_info:
        asyncio.run(_run())
    assert "Access denied" in exc_info.value.message


def test_wc_timeout_error_maps_to_integration():
    async def _run():
        wc = _wc()
        with patch(
            "app.beta.integrations.woocommerce._list_products_paged",
            new=AsyncMock(side_effect=ConnectorError(
                code=ConnectorErrorCode.TIMEOUT,
                message="WooCommerce request timed out",
                provider="woocommerce",
                retryable=True,
            )),
        ):
            await wc.get_products_page()

    with pytest.raises(IntegrationError) as exc_info:
        asyncio.run(_run())
    assert "timed out" in exc_info.value.message.lower()


def test_nc_network_error_maps_to_integration():
    async def _run():
        nc = _nc()
        with patch(
            "app.beta.integrations.nextcloud.get_file",
            new=AsyncMock(side_effect=ConnectorError(
                code=ConnectorErrorCode.NETWORK,
                message="WebDAV connection failed: Connection refused",
                provider="nextcloud",
                retryable=True,
            )),
        ):
            await nc.download_file("/docs/prices.xlsx")

    with pytest.raises(IntegrationError) as exc_info:
        asyncio.run(_run())
    assert "Could not connect" in exc_info.value.message
