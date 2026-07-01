"""Tests for WooCommerceConnector (connector.py + auth.py)."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.connectors.common.auth import AuthConfig
from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
from app.connectors.common.health import HealthStatus
from app.connectors.common.types import ConnectorType
from app.connectors.destinations.woocommerce.auth import extract_credentials
from app.connectors.destinations.woocommerce.connector import WooCommerceConnector

_AUTH = AuthConfig(
    auth_type="api_key",
    credentials={
        "url": "https://shop.example.com",
        "key": "ck_abc",
        "secret": "cs_xyz",
    },
)

_SAMPLE_PRODUCT = {
    "id": 10,
    "name": "Widget",
    "sku": "W-001",
    "price": "19.99",
    "regular_price": "19.99",
    "sale_price": "",
    "stock_quantity": 50,
    "stock_status": "instock",
    "manage_stock": True,
    "backorders": "no",
}

# -- auth.py tests -------------------------------------------------------------

def test_extract_credentials_api_key():
    creds = extract_credentials(_AUTH)
    assert creds.url == "https://shop.example.com"
    assert creds.key == "ck_abc"
    assert creds.secret == "cs_xyz"


def test_extract_credentials_strips_slash():
    auth = AuthConfig(
        auth_type="api_key",
        credentials={"url": "https://shop.example.com/", "key": "k", "secret": "s"},
    )
    creds = extract_credentials(auth)
    assert not creds.url.endswith("/")


def test_extract_credentials_missing_url_raises():
    auth = AuthConfig(auth_type="api_key", credentials={"key": "k", "secret": "s"})
    with pytest.raises(ConnectorError) as exc_info:
        extract_credentials(auth)
    assert exc_info.value.code == ConnectorErrorCode.AUTH_FAILED


def test_extract_credentials_missing_key_raises():
    auth = AuthConfig(auth_type="api_key", credentials={"url": "https://shop.example.com", "secret": "s"})
    with pytest.raises(ConnectorError) as exc_info:
        extract_credentials(auth)
    assert exc_info.value.code == ConnectorErrorCode.AUTH_FAILED


def test_extract_credentials_missing_secret_raises():
    auth = AuthConfig(auth_type="api_key", credentials={"url": "https://shop.example.com", "key": "k"})
    with pytest.raises(ConnectorError) as exc_info:
        extract_credentials(auth)
    assert exc_info.value.code == ConnectorErrorCode.AUTH_FAILED


def test_extract_credentials_wrong_auth_type_raises():
    auth = AuthConfig(auth_type="basic", credentials={"url": "https://shop.example.com"})
    with pytest.raises(ConnectorError) as exc_info:
        extract_credentials(auth)
    assert exc_info.value.code == ConnectorErrorCode.AUTH_FAILED


# -- connector basics ----------------------------------------------------------

def test_connector_id_and_type():
    wc = WooCommerceConnector()
    assert wc.connector_id == "woocommerce"
    assert wc.connector_type == ConnectorType.DESTINATION


def test_capabilities():
    wc = WooCommerceConnector()
    caps = wc.capabilities()
    assert caps.can_list_products is True
    assert caps.can_read_inventory is True
    assert caps.can_list_folders is False
    assert caps.can_list_files is False


# -- connect / disconnect ------------------------------------------------------

def test_connect_stores_credentials():
    wc = WooCommerceConnector()

    async def _run():
        with patch(
            "app.connectors.destinations.woocommerce.connector.ping",
            new=AsyncMock(return_value={"reachable": True, "sample_count": 5}),
        ):
            await wc.connect(_AUTH)

    asyncio.run(_run())
    assert wc._creds is not None
    assert wc._creds.key == "ck_abc"


def test_disconnect_clears_credentials():
    wc = WooCommerceConnector()

    async def _run():
        with patch(
            "app.connectors.destinations.woocommerce.connector.ping",
            new=AsyncMock(return_value={"reachable": True, "sample_count": 0}),
        ):
            await wc.connect(_AUTH)
        await wc.disconnect()

    asyncio.run(_run())
    assert wc._creds is None


# -- health --------------------------------------------------------------------

def test_health_not_connected_returns_unhealthy():
    wc = WooCommerceConnector()
    result = asyncio.run(wc.health())
    assert result.status == HealthStatus.UNHEALTHY


def test_health_connected_returns_healthy():
    wc = WooCommerceConnector()

    async def _run():
        with patch(
            "app.connectors.destinations.woocommerce.connector.ping",
            new=AsyncMock(return_value={"reachable": True, "sample_count": 3}),
        ):
            await wc.connect(_AUTH)
            return await wc.health()

    result = asyncio.run(_run())
    assert result.status == HealthStatus.HEALTHY
    assert result.latency_ms is not None


def test_health_on_error_returns_unhealthy():
    wc = WooCommerceConnector()

    async def _run():
        with patch(
            "app.connectors.destinations.woocommerce.connector.ping",
            new=AsyncMock(return_value={"reachable": True, "sample_count": 0}),
        ):
            await wc.connect(_AUTH)

        with patch(
            "app.connectors.destinations.woocommerce.connector.ping",
            new=AsyncMock(side_effect=ConnectorError(
                code=ConnectorErrorCode.NETWORK,
                message="refused",
                provider="woocommerce",
            )),
        ):
            return await wc.health()

    result = asyncio.run(_run())
    assert result.status == HealthStatus.UNHEALTHY


# -- test_connection -----------------------------------------------------------

def test_test_connection_ok():
    async def _run():
        wc = WooCommerceConnector()
        with patch(
            "app.connectors.destinations.woocommerce.connector.ping",
            new=AsyncMock(return_value={"reachable": True, "sample_count": 7}),
        ):
            return await wc.test_connection(_AUTH)

    result = asyncio.run(_run())
    assert result.ok is True
    assert "7" in result.message
    assert result.latency_ms is not None


def test_test_connection_auth_failure():
    async def _run():
        wc = WooCommerceConnector()
        with patch(
            "app.connectors.destinations.woocommerce.connector.ping",
            new=AsyncMock(side_effect=ConnectorError(
                code=ConnectorErrorCode.AUTH_FAILED,
                message="invalid key",
                provider="woocommerce",
            )),
        ):
            return await wc.test_connection(_AUTH)

    result = asyncio.run(_run())
    assert result.ok is False
    assert "invalid key" in result.message


# -- list_products / read_inventory --------------------------------------------

def test_list_products_delegates():
    wc = WooCommerceConnector()

    async def _run():
        with patch(
            "app.connectors.destinations.woocommerce.connector.ping",
            new=AsyncMock(return_value={"reachable": True, "sample_count": 1}),
        ):
            await wc.connect(_AUTH)
        with patch(
            "app.connectors.destinations.woocommerce.connector.list_products",
            new=AsyncMock(return_value=[_SAMPLE_PRODUCT]),
        ):
            return await wc.list_products(page=1, per_page=50)

    products = asyncio.run(_run())
    assert len(products) == 1
    assert products[0]["id"] == 10


def test_read_inventory_returns_stock_fields():
    wc = WooCommerceConnector()

    async def _run():
        with patch(
            "app.connectors.destinations.woocommerce.connector.ping",
            new=AsyncMock(return_value={"reachable": True, "sample_count": 1}),
        ):
            await wc.connect(_AUTH)
        with patch(
            "app.connectors.destinations.woocommerce.connector.get_product",
            new=AsyncMock(return_value=_SAMPLE_PRODUCT),
        ):
            return await wc.read_inventory(10)

    inv = asyncio.run(_run())
    assert inv["id"] == 10
    assert inv["stock_quantity"] == 50
    assert inv["stock_status"] == "instock"
    assert inv["manage_stock"] is True
    assert inv["price"] == "19.99"


def test_list_products_not_connected_raises():
    wc = WooCommerceConnector()
    with pytest.raises(ConnectorError) as exc_info:
        asyncio.run(wc.list_products())
    assert exc_info.value.code == ConnectorErrorCode.UNKNOWN


def test_read_inventory_not_connected_raises():
    wc = WooCommerceConnector()
    with pytest.raises(ConnectorError) as exc_info:
        asyncio.run(wc.read_inventory(1))
    assert exc_info.value.code == ConnectorErrorCode.UNKNOWN


# -- Isolation check -----------------------------------------------------------

def test_no_direct_httpx_import_in_connector():
    """connector.py must not import httpx - only rest_client.py may do so."""
    import ast
    import pathlib

    connector_src = pathlib.Path(
        "C:/Users/nimas/OneDrive/Documents/GitHub/FlowHub/app/connectors/destinations/woocommerce/connector.py"
    ).read_text()
    tree = ast.parse(connector_src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else ([node.module] if node.module else [])
            )
            for name in names:
                assert "httpx" not in (name or ""), (
                    "connector.py must not import httpx directly - use rest_client.py"
                )
