"""Tests for the Nextcloud WebDAV client (webdav.py).

All HTTP calls are mocked at the SourceHttpClient boundary - no real
Nextcloud required, and no raw httpx call sites exist in webdav.py to mock.
"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
from app.connectors.common.source_http import SourceHttpError, SourceHttpResponse
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

def _mock_response(status: int, content: bytes = b"", headers: dict | None = None) -> SourceHttpResponse:
    return SourceHttpResponse(status_code=status, headers=headers or {}, content=content, url="https://cloud.example.com/")


class _ClientPatch:
    """Context manager wiring SourceHttpClient(...).with_allowed_private_networks(...).request to a fake."""

    def __init__(self, request_mock: AsyncMock) -> None:
        self._request_mock = request_mock
        self._patcher = patch("app.connectors.sources.nextcloud.webdav.SourceHttpClient")

    def __enter__(self):
        mock_cls = self._patcher.start()
        mock_cls.return_value.with_allowed_private_networks.return_value.request = self._request_mock
        return mock_cls

    def __exit__(self, *exc) -> None:
        self._patcher.stop()


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
    mock_resp = _mock_response(207, content=_PROPFIND_207.encode("utf-8"))
    request_mock = AsyncMock(return_value=mock_resp)

    async def _run():
        with _ClientPatch(request_mock):
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


def test_propfind_root_uses_custom_webdav_files_root_url():
    mock_resp = _mock_response(207, content=_PROPFIND_207.encode("utf-8"))
    request_mock = AsyncMock(return_value=mock_resp)
    creds = NextcloudCredentials(
        url="https://example.com/nextcloud",
        username="alice",
        password="secret",
        webdav_files_root_url="https://example.com/nextcloud/remote.php/dav/files/alice/",
    )

    async def _run():
        with _ClientPatch(request_mock):
            await propfind_path(creds, "/")
            return request_mock.call_args.args[1]

    assert asyncio.run(_run()) == "https://example.com/nextcloud/remote.php/dav/files/alice/"


def test_propfind_folder_uses_custom_webdav_files_root_url():
    mock_resp = _mock_response(207, content=_PROPFIND_207.encode("utf-8"))
    request_mock = AsyncMock(return_value=mock_resp)
    creds = NextcloudCredentials(
        url="https://example.com/nextcloud",
        username="alice",
        password="secret",
        webdav_files_root_url="https://example.com/nextcloud/remote.php/dav/files/alice/",
    )

    async def _run():
        with _ClientPatch(request_mock):
            await propfind_path(creds, "/folder/")
            return request_mock.call_args.args[1]

    assert asyncio.run(_run()) == "https://example.com/nextcloud/remote.php/dav/files/alice/folder/"


def test_propfind_401_raises_auth_error():
    mock_resp = _mock_response(401)
    request_mock = AsyncMock(return_value=mock_resp)

    async def _run():
        with _ClientPatch(request_mock):
            return await propfind_path(_CREDS, "/")

    with pytest.raises(ConnectorError) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.code == ConnectorErrorCode.AUTH_FAILED
    assert exc_info.value.http_status == 401


def test_propfind_404_raises_not_found():
    mock_resp = _mock_response(404)
    request_mock = AsyncMock(return_value=mock_resp)

    async def _run():
        with _ClientPatch(request_mock):
            return await propfind_path(_CREDS, "/missing/")

    with pytest.raises(ConnectorError) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.code == ConnectorErrorCode.NOT_FOUND


def test_propfind_timeout_raises_retryable():
    request_mock = AsyncMock(side_effect=SourceHttpError("total_timeout"))

    async def _run():
        with _ClientPatch(request_mock):
            return await propfind_path(_CREDS, "/")

    with pytest.raises(ConnectorError) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.code == ConnectorErrorCode.TIMEOUT
    assert exc_info.value.retryable is True


def test_propfind_connect_error_raises_network():
    request_mock = AsyncMock(side_effect=SourceHttpError("connection_failed"))

    async def _run():
        with _ClientPatch(request_mock):
            return await propfind_path(_CREDS, "/")

    with pytest.raises(ConnectorError) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.code == ConnectorErrorCode.NETWORK
    assert exc_info.value.retryable is True


def test_propfind_unsafe_destination_raises_network():
    """A SourceHttpClient SSRF-policy rejection surfaces as a NETWORK error, not a silent pass-through."""
    request_mock = AsyncMock(side_effect=SourceHttpError("unsafe_destination"))

    async def _run():
        with _ClientPatch(request_mock):
            return await propfind_path(_CREDS, "/")

    with pytest.raises(ConnectorError) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.code == ConnectorErrorCode.NETWORK
    assert exc_info.value.raw == "unsafe_destination"


# -- get_file tests ------------------------------------------------------------

def test_get_file_returns_bytes_and_meta():
    content = b"PK test_double xlsx bytes"
    mock_resp = _mock_response(
        200,
        content=content,
        headers={
            "etag": '"abc"',
            "last-modified": "Mon, 01 Jan 2024 00:00:00 GMT",
            "content-type": "application/vnd.ms-excel",
        },
    )
    request_mock = AsyncMock(return_value=mock_resp)

    async def _run():
        with _ClientPatch(request_mock):
            return await get_file(_CREDS, "/docs/prices.xlsx")

    data, meta = asyncio.run(_run())
    assert data == content
    assert meta["etag"] == "abc"
    assert "last_modified" in meta


def test_get_file_403_raises_permission():
    mock_resp = _mock_response(403)
    request_mock = AsyncMock(return_value=mock_resp)

    async def _run():
        with _ClientPatch(request_mock):
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
    mock_resp = _mock_response(207, content=_PROPFIND_SINGLE.encode("utf-8"))
    request_mock = AsyncMock(return_value=mock_resp)

    async def _run():
        with _ClientPatch(request_mock):
            return await get_metadata(_CREDS, "/docs/prices.xlsx")

    meta = asyncio.run(_run())
    assert meta["etag"] == "etag99"
    assert meta["is_collection"] is False
    assert meta["content_length"] == 9876


# -- trusted_private_networks threading -----------------------------------------

def test_propfind_threads_trusted_private_networks_into_client():
    """creds.trusted_private_networks must reach SourceHttpClient.with_allowed_private_networks."""
    import ipaddress

    mock_resp = _mock_response(207, content=_PROPFIND_207.encode("utf-8"))
    request_mock = AsyncMock(return_value=mock_resp)
    networks = (ipaddress.ip_network("10.0.0.0/8"),)
    creds = NextcloudCredentials(
        url="https://cloud.example.com",
        username="alice",
        password="secret",
        trusted_private_networks=networks,
    )

    async def _run():
        with patch("app.connectors.sources.nextcloud.webdav.SourceHttpClient") as mock_cls:
            mock_cls.return_value.with_allowed_private_networks.return_value.request = request_mock
            await propfind_path(creds, "/")
            return mock_cls.return_value.with_allowed_private_networks.call_args.args[0]

    assert asyncio.run(_run()) == networks
