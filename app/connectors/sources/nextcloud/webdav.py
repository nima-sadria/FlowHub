"""WebDAV client for the Nextcloud source connector.

THIS IS THE ONLY MODULE PERMITTED TO MAKE WebDAV CALLS.
No other FlowHub module may call PROPFIND, GET on DAV URLs, or
access remote.php/dav directly.

All outbound requests go through SourceHttpClient - the shared SSRF-safe
HTTP boundary. No direct httpx usage is permitted in this module.

Supported operations (read-only):
  - propfind_path()   - list a folder or get single-resource metadata
  - get_file()        - download file bytes
  - get_metadata()    - ETag + last-modified for a single resource
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
from app.connectors.common.source_http import SourceHttpClient, SourceHttpError, SourceHttpPolicy
from app.connectors.sources.nextcloud.auth import NextcloudCredentials
from app.flowhub.rate_limit import acquire_connector_rate_limit

_DAV = "DAV:"
# Matches the previous httpx.Timeout(connect=10.0, read=60.0, ...) profile;
# total is read + connect plus a small buffer so legitimate slow responses
# are not cut off earlier than before.
_POLICY = SourceHttpPolicy(connect_timeout_seconds=10.0, read_timeout_seconds=60.0, total_timeout_seconds=75.0)

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
    if creds.webdav_files_root_url:
        return creds.webdav_files_root_url.rstrip("/")
    return creds.url + _DAV_PATH.format(username=creds.username)


def _auth(creds: NextcloudCredentials) -> tuple[str, str]:
    return (creds.username, creds.password)


def _client(creds: NextcloudCredentials) -> SourceHttpClient:
    return SourceHttpClient(policy=_POLICY).with_allowed_private_networks(creds.trusted_private_networks)


def _map_transport_error(exc: SourceHttpError) -> ConnectorError:
    """Map a SourceHttpClient boundary failure onto the existing WebDAV error taxonomy."""
    if "timeout" in exc.code:
        return ConnectorError(
            code=ConnectorErrorCode.TIMEOUT,
            message="WebDAV request timed out",
            provider="nextcloud",
            retryable=True,
            raw=exc.code,
        )
    return ConnectorError(
        code=ConnectorErrorCode.NETWORK,
        message="WebDAV connection failed.",
        provider="nextcloud",
        retryable=True,
        raw=exc.code,
    )


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


def _parse_propfind(xml_content: bytes | str) -> list[DavResource]:
    """Parse a WebDAV PROPFIND multistatus response into DavResource objects."""
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as exc:
        raise ConnectorError(
            code=ConnectorErrorCode.PROVIDER_ERROR,
            message="WebDAV returned an invalid response.",
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
    try:
        await acquire_connector_rate_limit("nextcloud:primary", "read")
        response = await _client(creds).request(
            "PROPFIND",
            url,
            content=body.encode("utf-8"),
            headers={"Depth": depth, "Content-Type": "application/xml; charset=utf-8"},
            basic_auth=_auth(creds),
        )
    except SourceHttpError as exc:
        raise _map_transport_error(exc) from exc

    if response.status_code not in (207, 200):
        raise _map_http_error(response.status_code)
    return _parse_propfind(response.content)


async def get_file(creds: NextcloudCredentials, path: str) -> tuple[bytes, dict]:
    """Download a file from WebDAV. Returns (content_bytes, metadata_dict)."""
    url = _dav_base(creds) + path
    try:
        await acquire_connector_rate_limit("nextcloud:primary", "read")
        response = await _client(creds).request("GET", url, basic_auth=_auth(creds))
    except SourceHttpError as exc:
        raise _map_transport_error(exc) from exc

    if response.status_code != 200:
        raise _map_http_error(response.status_code)

    meta = {
        "etag": response.headers.get("etag", "").strip('"'),
        "last_modified": response.headers.get("last-modified", ""),
        "content_type": response.headers.get("content-type", ""),
        "content_length": response.headers.get("content-length", ""),
    }
    return response.content, meta


async def head_file(creds: NextcloudCredentials, path: str) -> dict:
    """HEAD request for lightweight file metadata.

    Returns dict with etag/last_modified/content_length keys.
    Never raises - returns dict of None values on any error.
    """
    url = _dav_base(creds) + path
    try:
        await acquire_connector_rate_limit("nextcloud:primary", "read")
        response = await _client(creds).request("HEAD", url, basic_auth=_auth(creds))
    except SourceHttpError:
        return {"etag": None, "last_modified": None, "content_length": None}

    if response.status_code != 200:
        return {"etag": None, "last_modified": None, "content_length": None}

    return {
        "etag": response.headers.get("etag", "").strip('"') or None,
        "last_modified": response.headers.get("last-modified") or None,
        "content_length": response.headers.get("content-length") or None,
    }


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
