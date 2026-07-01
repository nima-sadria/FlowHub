"""Tests for NextcloudConnector (connector.py + auth.py).

All HTTP calls are mocked - no real Nextcloud required.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.connectors.common.auth import AuthConfig
from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
from app.connectors.common.health import HealthStatus
from app.connectors.common.types import ConnectorType
from app.connectors.sources.nextcloud.auth import extract_credentials
from app.connectors.sources.nextcloud.connector import NextcloudConnector
from app.connectors.sources.nextcloud.ocs import OCSServerInfo

_AUTH = AuthConfig(
    auth_type="basic",
    credentials={"url": "https://cloud.example.com", "username": "alice", "password": "s3cr3t"},
)

# -- auth.py tests -------------------------------------------------------------

def test_extract_credentials_basic():
    creds = extract_credentials(_AUTH)
    assert creds.url == "https://cloud.example.com"
    assert creds.username == "alice"
    assert creds.password == "s3cr3t"


def test_extract_credentials_strips_trailing_slash():
    auth = AuthConfig(
        auth_type="basic",
        credentials={"url": "https://cloud.example.com/", "username": "u", "password": "p"},
    )
    creds = extract_credentials(auth)
    assert not creds.url.endswith("/")


def test_extract_credentials_missing_url_raises():
    auth = AuthConfig(auth_type="basic", credentials={"username": "u", "password": "p"})
    with pytest.raises(ConnectorError) as exc_info:
        extract_credentials(auth)
    assert exc_info.value.code == ConnectorErrorCode.AUTH_FAILED


def test_extract_credentials_missing_username_raises():
    auth = AuthConfig(auth_type="basic", credentials={"url": "https://nc.example.com", "password": "p"})
    with pytest.raises(ConnectorError) as exc_info:
        extract_credentials(auth)
    assert exc_info.value.code == ConnectorErrorCode.AUTH_FAILED


def test_extract_credentials_wrong_auth_type_raises():
    auth = AuthConfig(auth_type="oauth2", credentials={"url": "https://nc.example.com"})
    with pytest.raises(ConnectorError) as exc_info:
        extract_credentials(auth)
    assert exc_info.value.code == ConnectorErrorCode.AUTH_FAILED


# -- NextcloudConnector instantiation -----------------------------------------

def test_connector_id_and_type():
    nc = NextcloudConnector()
    assert nc.connector_id == "nextcloud"
    assert nc.connector_type == ConnectorType.SOURCE


def test_capabilities():
    nc = NextcloudConnector()
    caps = nc.capabilities()
    assert caps.can_list_folders is True
    assert caps.can_list_files is True
    assert caps.can_get_metadata is True
    assert caps.can_list_worksheets is False
    assert caps.can_read_worksheet is False
    assert caps.can_watch_changes is False


# -- connect / disconnect ------------------------------------------------------

def test_connect_stores_credentials():
    nc = NextcloudConnector()
    mock_info = OCSServerInfo(version="28.0.1", edition="Community", ocs_status_code=100)

    async def _run():
        with patch(
            "app.connectors.sources.nextcloud.connector.check_server_info",
            new=AsyncMock(return_value=mock_info),
        ):
            await nc.connect(_AUTH)

    asyncio.run(_run())
    assert nc._creds is not None
    assert nc._creds.username == "alice"


def test_disconnect_clears_credentials():
    nc = NextcloudConnector()
    mock_info = OCSServerInfo(version="28.0.1", edition="", ocs_status_code=100)

    async def _run():
        with patch(
            "app.connectors.sources.nextcloud.connector.check_server_info",
            new=AsyncMock(return_value=mock_info),
        ):
            await nc.connect(_AUTH)
        await nc.disconnect()

    asyncio.run(_run())
    assert nc._creds is None


# -- health --------------------------------------------------------------------

def test_health_not_connected_returns_unhealthy():
    nc = NextcloudConnector()
    result = asyncio.run(nc.health())
    assert result.status == HealthStatus.UNHEALTHY


def test_health_connected_returns_healthy():
    nc = NextcloudConnector()
    mock_info = OCSServerInfo(version="28.0.1", edition="Community", ocs_status_code=100)

    async def _run():
        with patch(
            "app.connectors.sources.nextcloud.connector.check_server_info",
            new=AsyncMock(return_value=mock_info),
        ):
            await nc.connect(_AUTH)
            return await nc.health()

    result = asyncio.run(_run())
    assert result.status == HealthStatus.HEALTHY
    assert result.latency_ms is not None
    assert "28.0.1" in (result.detail or "")


def test_health_on_error_returns_unhealthy():
    nc = NextcloudConnector()
    mock_info = OCSServerInfo(version="28.0.1", edition="", ocs_status_code=100)

    async def _run():
        with patch(
            "app.connectors.sources.nextcloud.connector.check_server_info",
            new=AsyncMock(return_value=mock_info),
        ):
            await nc.connect(_AUTH)

        with patch(
            "app.connectors.sources.nextcloud.connector.check_server_info",
            new=AsyncMock(side_effect=ConnectorError(
                code=ConnectorErrorCode.NETWORK,
                message="reset",
                provider="nextcloud",
            )),
        ):
            return await nc.health()

    result = asyncio.run(_run())
    assert result.status == HealthStatus.UNHEALTHY


# -- test_connection -----------------------------------------------------------

def test_test_connection_ok():
    mock_info = OCSServerInfo(version="28.0.1", edition="", ocs_status_code=100)

    async def _run():
        nc = NextcloudConnector()
        with patch(
            "app.connectors.sources.nextcloud.connector.check_server_info",
            new=AsyncMock(return_value=mock_info),
        ):
            return await nc.test_connection(_AUTH)

    result = asyncio.run(_run())
    assert result.ok is True
    assert "28.0.1" in result.message
    assert result.latency_ms is not None


def test_test_connection_auth_failure():
    async def _run():
        nc = NextcloudConnector()
        with patch(
            "app.connectors.sources.nextcloud.connector.check_server_info",
            new=AsyncMock(side_effect=ConnectorError(
                code=ConnectorErrorCode.AUTH_FAILED,
                message="bad credentials",
                provider="nextcloud",
                http_status=401,
            )),
        ):
            return await nc.test_connection(_AUTH)

    result = asyncio.run(_run())
    assert result.ok is False
    assert "bad credentials" in result.message


# -- list_folders / list_files -------------------------------------------------

_PROPFIND_RESOURCES = [
    MagicMock(href="/remote.php/dav/files/alice/docs/", is_collection=True),
    MagicMock(href="/remote.php/dav/files/alice/docs/sub/", is_collection=True),
    MagicMock(href="/remote.php/dav/files/alice/docs/prices.xlsx", is_collection=False),
]


def test_list_folders_returns_collections_excluding_self():
    nc = NextcloudConnector()
    mock_info = OCSServerInfo(version="28", edition="", ocs_status_code=100)

    async def _run():
        with patch(
            "app.connectors.sources.nextcloud.connector.check_server_info",
            new=AsyncMock(return_value=mock_info),
        ):
            await nc.connect(_AUTH)
        with patch(
            "app.connectors.sources.nextcloud.connector.propfind_path",
            new=AsyncMock(return_value=_PROPFIND_RESOURCES),
        ):
            return await nc.list_folders("/docs/")

    folders = asyncio.run(_run())
    # resources[0] is self (skipped), resources[1] is sub/ (collection)
    assert len(folders) == 1
    assert "sub/" in folders[0]


def test_list_files_returns_non_collections():
    nc = NextcloudConnector()
    mock_info = OCSServerInfo(version="28", edition="", ocs_status_code=100)

    async def _run():
        with patch(
            "app.connectors.sources.nextcloud.connector.check_server_info",
            new=AsyncMock(return_value=mock_info),
        ):
            await nc.connect(_AUTH)
        with patch(
            "app.connectors.sources.nextcloud.connector.propfind_path",
            new=AsyncMock(return_value=_PROPFIND_RESOURCES),
        ):
            return await nc.list_files("/docs/")

    files = asyncio.run(_run())
    assert len(files) == 1
    assert "prices.xlsx" in files[0]


def test_list_folders_not_connected_raises():
    nc = NextcloudConnector()
    with pytest.raises(ConnectorError) as exc_info:
        asyncio.run(nc.list_folders("/"))
    assert exc_info.value.code == ConnectorErrorCode.UNKNOWN


# -- get_metadata --------------------------------------------------------------

def test_get_metadata_delegates_to_webdav():
    nc = NextcloudConnector()
    mock_info = OCSServerInfo(version="28", edition="", ocs_status_code=100)
    expected_meta = {"etag": "abc", "last_modified": "Mon...", "is_collection": False, "content_length": 1234, "content_type": ""}

    async def _run():
        with patch(
            "app.connectors.sources.nextcloud.connector.check_server_info",
            new=AsyncMock(return_value=mock_info),
        ):
            await nc.connect(_AUTH)
        with patch(
            "app.connectors.sources.nextcloud.connector.get_metadata",
            new=AsyncMock(return_value=expected_meta),
        ):
            return await nc.get_metadata("/docs/prices.xlsx")

    meta = asyncio.run(_run())
    assert meta["etag"] == "abc"
    assert meta["content_length"] == 1234


# -- Isolation check -----------------------------------------------------------

def test_no_direct_httpx_import_in_connector():
    """connector.py must not import httpx - only webdav.py and ocs.py may do so."""
    import ast
    import pathlib

    connector_src = pathlib.Path(
        "C:/Users/nimas/OneDrive/Documents/GitHub/FlowHub/app/connectors/sources/nextcloud/connector.py"
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
                    "connector.py must not import httpx directly - use webdav.py/ocs.py"
                )
