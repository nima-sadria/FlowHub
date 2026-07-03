"""Connector and route isolation tests."""

from __future__ import annotations

import ast
import asyncio
import pathlib
from unittest.mock import AsyncMock, patch

import pytest

from app.flowhub.integrations.errors import IntegrationError
from app.flowhub.integrations.nextcloud import NextcloudClient
from app.flowhub.integrations.woocommerce import WooCommerceClient
from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
from app.connectors.common.test_result import ConnectionTestResult


_REPO_ROOT = pathlib.Path(__file__).parents[2]


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
}


def _imports(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names if alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_wc_get_products_page_delegates_to_rest_client():
    async def _run():
        wc = _wc()
        with patch(
            "app.flowhub.integrations.woocommerce._list_products_paged",
            new=AsyncMock(return_value=([_RAW_PRODUCT], 1, 1)),
        ):
            return await wc.get_products_page(page=1, per_page=10)

    products, total = asyncio.run(_run())
    assert total == 1
    assert products[0]["wcId"] == 42
    assert products[0]["currentPrice"] == 9.99


def test_wc_connector_error_maps_to_integration_error():
    async def _run():
        wc = _wc()
        with patch(
            "app.flowhub.integrations.woocommerce._list_products_paged",
            new=AsyncMock(
                side_effect=ConnectorError(
                    code=ConnectorErrorCode.AUTH_FAILED,
                    message="WooCommerce authentication failed",
                    provider="woocommerce",
                    http_status=401,
                )
            ),
        ):
            await wc.get_products_page()

    with pytest.raises(IntegrationError):
        asyncio.run(_run())


def test_wc_test_connection_uses_connector_rest_client():
    async def _run():
        wc = _wc()
        with patch(
            "app.flowhub.integrations.woocommerce._ping",
            new=AsyncMock(return_value={"reachable": True, "records_checked": 5}),
        ):
            return await wc.test_connection()

    ok, message, latency = asyncio.run(_run())
    assert ok is True
    assert "5" in message
    assert latency >= 0


def test_nc_download_file_delegates_to_webdav():
    async def _run():
        nc = _nc()
        with patch(
            "app.flowhub.integrations.nextcloud.get_file",
            new=AsyncMock(return_value=(b"xlsx", {"etag": "abc"})),
        ):
            return await nc.download_file("/prices.xlsx")

    content, meta = asyncio.run(_run())
    assert content == b"xlsx"
    assert meta["etag"] == "abc"


def test_nc_test_connection_uses_connector():
    async def _run():
        nc = _nc()
        result = ConnectionTestResult(ok=True, message="Connected to Nextcloud 27", latency_ms=42)
        with patch(
            "app.flowhub.integrations.nextcloud.NextcloudConnector.test_connection",
            new=AsyncMock(return_value=result),
        ):
            return await nc.test_connection()

    ok, message, latency = asyncio.run(_run())
    assert ok is True
    assert "Nextcloud" in message
    assert latency == 42


def test_active_FLOWHUB_v2_routes_do_not_import_live_clients_or_httpx():
    forbidden = {
        "app.flowhub.integrations.woocommerce",
        "app.flowhub.integrations.nextcloud",
        "app.services.woocommerce",
        "app.services.nextcloud",
        "app.connectors.destinations.woocommerce",
        "app.connectors.sources.nextcloud",
        "httpx",
    }
    offenders: list[str] = []
    for path in (_REPO_ROOT / "app" / "flowhub" / "api" / "v2").glob("*.py"):
        imported = _imports(path)
        bad = sorted(imported & forbidden)
        if bad:
            offenders.append(f"{path.relative_to(_REPO_ROOT)} imports {bad}")
    assert offenders == []
