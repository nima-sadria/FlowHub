"""Deterministic SourceHttpClient fixtures for legacy beta Source workflows."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any
from urllib.parse import unquote, urlsplit

from app.connectors.common.source_http import SourceHttpClient, SourceHttpResponse
from app.flowhub.integrations.errors import IntegrationError


NextcloudDownload = Callable[[object, str], Awaitable[tuple[bytes, Mapping[str, Any]]]]


def install_nextcloud_download(monkeypatch: Any, download: NextcloudDownload) -> None:
    """Route legacy workbook fixtures through the production HTTP boundary.

    The beta workflows still express their test data as a logical WebDAV path and
    workbook bytes. This adapter preserves that fixture format while replacing the
    retired ``NextcloudClient.download_file`` mock with a synthetic
    ``SourceHttpClient`` response. No DNS lookup or network connection occurs.
    """

    async def request(
        _client: SourceHttpClient,
        method: str,
        url: str,
        **_kwargs: object,
    ) -> SourceHttpResponse:
        assert method == "GET"
        path = _webdav_resource_path(url)
        try:
            content, metadata = await download(None, path)
        except IntegrationError as exc:
            return SourceHttpResponse(
                status_code=exc.status_code or 502,
                headers={},
                content=b"",
                url=url,
            )
        headers = {
            str(key).replace("_", "-"): str(value)
            for key, value in metadata.items()
            if value is not None
        }
        return SourceHttpResponse(status_code=200, headers=headers, content=content, url=url)

    monkeypatch.setattr(SourceHttpClient, "request", request)


def _webdav_resource_path(url: str) -> str:
    path = unquote(urlsplit(url).path)
    marker = "/remote.php/dav/files/"
    _, separator, remainder = path.partition(marker)
    if not separator:
        raise AssertionError(f"Expected a Nextcloud WebDAV URL, got {url!r}")
    _username, separator, resource_path = remainder.partition("/")
    if not separator:
        raise AssertionError(f"Expected a file path in WebDAV URL, got {url!r}")
    return f"/{resource_path}"
