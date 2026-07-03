"""Tests for the Nextcloud WebDAV client (webdav.py).

All HTTP calls are mocked - no real Nextcloud required.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
from app.connectors.sources.nextcloud.auth import NextcloudCredentials
from app.connectors.sources.nextcloud.webdav import (
    DavResource,
    get_file,
    get_metadata,
    propfind_path,
)

_CREDS = NextcloudCredentials(
    url="https://cloud.example.com",
    username="alice",
    password="secret",
)

# -- Helpers -------------------------------------------------------------------

def _mock_response(status: int, text: str = "", content: bytes = b"") -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.text = text
    r.content = content
    r.headers = {}
    return r


_PROPFIND_207 = """\
<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/remote.php/dav/files/alice/docs/</d:href>
    <d:propstat>
      <d:prop>
        <d:resourcetype><d:collection/></d:resourcetype>
        <d:getetag>"abc123"</d:getetag>
        <d:getlastmodified>Mon, 01 Jan 2024 00:00:00 GMT</d:getlastmodified>
      </d:prop>
      <d:status>HTTP/1.1 200 OK</d:status>
    </d:propstat>
  </d:response>
  <d:response>
    <d:href>/remote.php/dav/files/alice/docs/prices.xlsx</d:href>
    <d:propstat>
      <d:prop>
        <d:resourcetype/>
        <d:getetag>"def456"</d:getetag>
        <d:getlastmodified>Tue, 02 Jan 2024 00:00:00 GMT</d:getlastmodified>
        <d:getcontentlength>12345</d:getcontentlength>
        <d:getcontenttype>application/vnd.openxmlformats-officedocument.spreadsheetml.sheet</d:getcontenttype>
      </d:prop>
      <d:status>HTTP/1.1 200 OK</d:status>
    </d:propstat>
  </d:response>
</d:multistatus>
"""

# -- propfind_path tests -------------------------------------------------------

def test_propfind_returns_resources():
    mock_resp = _mock_response(207, text=_PROPFIND_207)

    async def _run():
        with patch("httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
            instance.request = AsyncMock(return_value=mock_resp)
            return await propfind_path(_CREDS, "/docs/")

    resources = asyncio.run(_run())
    assert len(resources) == 2
    folder = resources[0]
    file_ = resources[1]
    assert folder.is_collection is True
    assert folder.etag == "abc123"
    file_resource = file_
    assert file_resource.is_collection is False
    assert file_resource.etag == "def456"
    assert file_resource.content_length == 12345


def test_propfind_401_raises_auth_error():
    mock_resp = _mock_response(401)

    async def _run():
        with patch("httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
            instance.request = AsyncMock(return_value=mock_resp)
            return await propfind_path(_CREDS, "/")

    with pytest.raises(ConnectorError) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.code == ConnectorErrorCode.AUTH_FAILED
    assert exc_info.value.http_status == 401


def test_propfind_404_raises_not_found():
    mock_resp = _mock_response(404)

    async def _run():
        with patch("httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
            instance.request = AsyncMock(return_value=mock_resp)
            return await propfind_path(_CREDS, "/missing/")

    with pytest.raises(ConnectorError) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.code == ConnectorErrorCode.NOT_FOUND


def test_propfind_timeout_raises_retryable():
    async def _run():
        with patch("httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
            instance.request = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            return await propfind_path(_CREDS, "/")

    with pytest.raises(ConnectorError) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.code == ConnectorErrorCode.TIMEOUT
    assert exc_info.value.retryable is True


def test_propfind_connect_error_raises_network():
    async def _run():
        with patch("httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
            instance.request = AsyncMock(side_effect=httpx.ConnectError("refused"))
            return await propfind_path(_CREDS, "/")

    with pytest.raises(ConnectorError) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.code == ConnectorErrorCode.NETWORK
    assert exc_info.value.retryable is True


# -- get_file tests ------------------------------------------------------------

def test_get_file_returns_bytes_and_meta():
    content = b"PK test_double xlsx bytes"
    mock_resp = _mock_response(200, content=content)
    mock_resp.headers = {
        "etag": '"abc"',
        "last-modified": "Mon, 01 Jan 2024 00:00:00 GMT",
        "content-type": "application/vnd.ms-excel",
    }

    async def _run():
        with patch("httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
            instance.get = AsyncMock(return_value=mock_resp)
            return await get_file(_CREDS, "/docs/prices.xlsx")

    data, meta = asyncio.run(_run())
    assert data == content
    assert meta["etag"] == "abc"
    assert "last_modified" in meta


def test_get_file_403_raises_permission():
    mock_resp = _mock_response(403)

    async def _run():
        with patch("httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
            instance.get = AsyncMock(return_value=mock_resp)
            return await get_file(_CREDS, "/restricted/file.xlsx")

    with pytest.raises(ConnectorError) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.code == ConnectorErrorCode.PERMISSION


# -- get_metadata tests --------------------------------------------------------

_PROPFIND_SINGLE = """\
<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/remote.php/dav/files/alice/docs/prices.xlsx</d:href>
    <d:propstat>
      <d:prop>
        <d:resourcetype/>
        <d:getetag>"etag99"</d:getetag>
        <d:getlastmodified>Wed, 03 Jan 2024 00:00:00 GMT</d:getlastmodified>
        <d:getcontentlength>9876</d:getcontentlength>
      </d:prop>
      <d:status>HTTP/1.1 200 OK</d:status>
    </d:propstat>
  </d:response>
</d:multistatus>
"""


def test_get_metadata_returns_dict():
    mock_resp = _mock_response(207, text=_PROPFIND_SINGLE)

    async def _run():
        with patch("httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            MockClient.return_value.__aenter__ = AsyncMock(return_value=instance)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=None)
            instance.request = AsyncMock(return_value=mock_resp)
            return await get_metadata(_CREDS, "/docs/prices.xlsx")

    meta = asyncio.run(_run())
    assert meta["etag"] == "etag99"
    assert meta["is_collection"] is False
    assert meta["content_length"] == 9876
