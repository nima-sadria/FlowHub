"""WebDAV client for the Nextcloud source connector.

THIS IS THE ONLY MODULE PERMITTED TO MAKE WebDAV CALLS.
No other FlowHub module may call PROPFIND, GET on DAV URLs, or
access remote.php/dav directly.

Supported operations (read-only):
  - propfind_path()   — list a folder or get single-resource metadata
  - get_file()        — download file bytes
  - get_metadata()    — ETag + last-modified for a single resource
"""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
from app.connectors.sources.nextcloud.auth import NextcloudCredentials

_DAV = "DAV:"
_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)

# Base path for WebDAV file access on Nextcloud
_DAV_PATH = "/remote.php/dav/files/{username}"


@dataclass
class DavResource:
    href: str
    is_collection: bool
    etag: str = ""
    last_modified: str = ""
    content_length: int | None = None
    content_type: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def _dav_base(creds: NextcloudCredentials) -> str:
    return creds.url + _DAV_PATH.format(username=creds.username)


def _auth(creds: NextcloudCredentials) -> tuple[str, str]:
    return (creds.username, creds.password)


def _map_http_error(status: int, provider: str = "nextcloud") -> ConnectorError:
    if status == 401:
        return ConnectorError(
            code=ConnectorErrorCode.AUTH_FAILED,
            message="WebDAV authentication failed (HTTP 401)",
            provider=provider,
            http_status=status,
        )
    if status == 403:
        return ConnectorError(
            code=ConnectorErrorCode.PERMISSION,
            message="WebDAV access denied (HTTP 403)",
            provider=provider,
            http_status=status,
        )
    if status == 404:
        return ConnectorError(
            code=ConnectorErrorCode.NOT_FOUND,
            message="WebDAV resource not found (HTTP 404)",
            provider=provider,
            http_status=status,
        )
    if status == 429:
        return ConnectorError(
            code=ConnectorErrorCode.RATE_LIMITED,
            message="WebDAV rate limited (HTTP 429)",
            provider=provider,
            http_status=status,
            retryable=True,
        )
    return ConnectorError(
        code=ConnectorErrorCode.PROVIDER_ERROR,
        message=f"Unexpected WebDAV status: HTTP {status}",
        provider=provider,
        http_status=status,
    )


def _parse_propfind(xml_text: str) -> list[DavResource]:
    """Parse a WebDAV PROPFIND multistatus response into DavResource objects."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ConnectorError(
            code=ConnectorErrorCode.PROVIDER_ERROR,
            message=f"Failed to parse PROPFIND response: {exc}",
            provider="nextcloud",
        ) from exc

    resources: list[DavResource] = []
    for response in root.iter(f"{{{_DAV}}}response"):
        href = (response.findtext(f"{{{_DAV}}}href") or "").strip()
        prop = response.find(f".//{{{_DAV}}}prop")
        if prop is None:
            continue

        rt = prop.find(f"{{{_DAV}}}resourcetype")
        is_col = rt is not None and rt.find(f"{{{_DAV}}}collection") is not None

        etag = (prop.findtext(f"{{{_DAV}}}getetag") or "").strip().strip('"')
        lm = (prop.findtext(f"{{{_DAV}}}getlastmodified") or "").strip()
        cl_text = prop.findtext(f"{{{_DAV}}}getcontentlength") or ""
        cl = int(cl_text) if cl_text.isdigit() else None
        ct = (prop.findtext(f"{{{_DAV}}}getcontenttype") or "").strip()

        resources.append(DavResource(
            href=href,
            is_collection=is_col,
            etag=etag,
            last_modified=lm,
            content_length=cl,
            content_type=ct,
        ))
    return resources


async def propfind_path(
    creds: NextcloudCredentials,
    path: str,
    depth: str = "1",
) -> list[DavResource]:
    """PROPFIND a path. depth='0' for single resource, '1' for directory listing."""
    url = _dav_base(creds) + path
    body = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<d:propfind xmlns:d="DAV:"><d:prop>'
        "<d:resourcetype/><d:getetag/><d:getlastmodified/>"
        "<d:getcontentlength/><d:getcontenttype/>"
        "</d:prop></d:propfind>"
    )
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(auth=_auth(creds), follow_redirects=True) as client:
            r = await client.request(
                "PROPFIND",
                url,
                content=body.encode("utf-8"),
                headers={"Depth": depth, "Content-Type": "application/xml; charset=utf-8"},
                timeout=_TIMEOUT,
            )
    except httpx.TimeoutException as exc:
        raise ConnectorError(
            code=ConnectorErrorCode.TIMEOUT,
            message="WebDAV PROPFIND timed out",
            provider="nextcloud",
            retryable=True,
        ) from exc
    except httpx.ConnectError as exc:
        raise ConnectorError(
            code=ConnectorErrorCode.NETWORK,
            message=f"WebDAV connection failed: {exc}",
            provider="nextcloud",
            retryable=True,
        ) from exc

    _ = time.monotonic() - t0  # latency available for future observability
    if r.status_code not in (207, 200):
        raise _map_http_error(r.status_code)
    return _parse_propfind(r.text)


async def get_file(creds: NextcloudCredentials, path: str) -> tuple[bytes, dict]:
    """Download a file from WebDAV. Returns (content_bytes, metadata_dict)."""
    url = _dav_base(creds) + path
    try:
        async with httpx.AsyncClient(auth=_auth(creds), follow_redirects=True) as client:
            r = await client.get(url, timeout=_TIMEOUT)
    except httpx.TimeoutException as exc:
        raise ConnectorError(
            code=ConnectorErrorCode.TIMEOUT,
            message="WebDAV GET timed out",
            provider="nextcloud",
            retryable=True,
        ) from exc
    except httpx.ConnectError as exc:
        raise ConnectorError(
            code=ConnectorErrorCode.NETWORK,
            message=f"WebDAV connection failed: {exc}",
            provider="nextcloud",
            retryable=True,
        ) from exc

    if r.status_code != 200:
        raise _map_http_error(r.status_code)

    meta = {
        "etag": r.headers.get("etag", "").strip('"'),
        "last_modified": r.headers.get("last-modified", ""),
        "content_type": r.headers.get("content-type", ""),
    }
    return r.content, meta


async def get_metadata(creds: NextcloudCredentials, path: str) -> dict:
    """Return ETag and last-modified for a single resource via PROPFIND depth=0."""
    resources = await propfind_path(creds, path, depth="0")
    if not resources:
        raise ConnectorError(
            code=ConnectorErrorCode.NOT_FOUND,
            message=f"No metadata returned for path: {path}",
            provider="nextcloud",
        )
    r = resources[0]
    return {
        "etag": r.etag,
        "last_modified": r.last_modified,
        "is_collection": r.is_collection,
        "content_length": r.content_length,
        "content_type": r.content_type,
    }
