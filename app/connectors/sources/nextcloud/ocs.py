"""Nextcloud OCS API client for the Nextcloud source connector.

THIS IS THE ONLY MODULE PERMITTED TO MAKE OCS API CALLS.
No other FlowHub module may call /ocs/ endpoints directly.

Supported operations (read-only):
  - check_server_info()  - verify OCS API is reachable and get server version
  - check_user_quota()   - confirm the authenticated user exists and is active

OCS API reference: https://docs.nextcloud.com/server/latest/developer_manual/client_apis/OCS/
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx

from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
from app.connectors.sources.nextcloud.auth import NextcloudCredentials
from app.flowhub.rate_limit import acquire_connector_rate_limit

_TIMEOUT = httpx.Timeout(connect=10.0, read=15.0, write=5.0, pool=5.0)
_OCS_CAPS = "/ocs/v1.php/cloud/capabilities?format=xml"
_OCS_USER = "/ocs/v1.php/cloud/user?format=xml"


@dataclass
class OCSServerInfo:
    version: str
    edition: str
    ocs_status_code: int


@dataclass
class OCSUserInfo:
    user_id: str
    display_name: str
    quota_used: int | None
    quota_total: int | None


def _auth(creds: NextcloudCredentials) -> tuple[str, str]:
    return (creds.username, creds.password)


def _ocs_status(xml_text: str) -> int:
    try:
        root = ET.fromstring(xml_text)
        code = root.findtext(".//meta/statuscode") or ""
        return int(code) if code.isdigit() else 0
    except Exception:
        return 0


async def check_server_info(creds: NextcloudCredentials) -> OCSServerInfo:
    """Probe the OCS capabilities endpoint to confirm Nextcloud is reachable."""
    url = creds.url + _OCS_CAPS
    try:
        await acquire_connector_rate_limit("nextcloud:primary", "read")
        async with httpx.AsyncClient(
            auth=_auth(creds),
            follow_redirects=True,
            headers={"OCS-APIREQUEST": "true"},
        ) as client:
            r = await client.get(url, timeout=_TIMEOUT)
    except httpx.TimeoutException as exc:
        raise ConnectorError(
            code=ConnectorErrorCode.TIMEOUT,
            message="OCS capabilities request timed out",
            provider="nextcloud",
            retryable=True,
        ) from exc
    except httpx.ConnectError as exc:
        raise ConnectorError(
            code=ConnectorErrorCode.NETWORK,
            message="OCS connection failed.",
            provider="nextcloud",
            retryable=True,
        ) from exc

    if r.status_code == 401:
        raise ConnectorError(
            code=ConnectorErrorCode.AUTH_FAILED,
            message="OCS authentication failed (HTTP 401)",
            provider="nextcloud",
            http_status=401,
        )
    if r.status_code not in (200,):
        raise ConnectorError(
            code=ConnectorErrorCode.PROVIDER_ERROR,
            message=f"OCS capabilities returned HTTP {r.status_code}",
            provider="nextcloud",
            http_status=r.status_code,
        )

    ocs_code = _ocs_status(r.text)
    if ocs_code not in (100, 200):
        raise ConnectorError(
            code=ConnectorErrorCode.PROVIDER_ERROR,
            message=f"OCS returned non-OK status code: {ocs_code}",
            provider="nextcloud",
        )

    try:
        root = ET.fromstring(r.text)
        version = root.findtext(".//version/string") or ""
        edition = root.findtext(".//edition") or ""
    except ET.ParseError:
        version = ""
        edition = ""

    return OCSServerInfo(version=version, edition=edition, ocs_status_code=ocs_code)


async def check_user_quota(creds: NextcloudCredentials) -> OCSUserInfo:
    """Verify the authenticated user exists and return basic account info."""
    url = creds.url + _OCS_USER
    try:
        await acquire_connector_rate_limit("nextcloud:primary", "read")
        async with httpx.AsyncClient(
            auth=_auth(creds),
            follow_redirects=True,
            headers={"OCS-APIREQUEST": "true"},
        ) as client:
            r = await client.get(url, timeout=_TIMEOUT)
    except httpx.TimeoutException as exc:
        raise ConnectorError(
            code=ConnectorErrorCode.TIMEOUT,
            message="OCS user request timed out",
            provider="nextcloud",
            retryable=True,
        ) from exc
    except httpx.ConnectError as exc:
        raise ConnectorError(
            code=ConnectorErrorCode.NETWORK,
            message="OCS connection failed.",
            provider="nextcloud",
            retryable=True,
        ) from exc

    if r.status_code == 401:
        raise ConnectorError(
            code=ConnectorErrorCode.AUTH_FAILED,
            message="OCS user authentication failed (HTTP 401)",
            provider="nextcloud",
            http_status=401,
        )
    if r.status_code != 200:
        raise ConnectorError(
            code=ConnectorErrorCode.PROVIDER_ERROR,
            message=f"OCS user endpoint returned HTTP {r.status_code}",
            provider="nextcloud",
            http_status=r.status_code,
        )

    try:
        root = ET.fromstring(r.text)
        user_id = root.findtext(".//id") or ""
        display_name = root.findtext(".//display-name") or ""
        used_text = root.findtext(".//quota/used") or ""
        total_text = root.findtext(".//quota/total") or ""
        quota_used = int(used_text) if used_text.lstrip("-").isdigit() else None
        quota_total = int(total_text) if total_text.lstrip("-").isdigit() else None
    except ET.ParseError:
        user_id = ""
        display_name = ""
        quota_used = None
        quota_total = None

    return OCSUserInfo(
        user_id=user_id,
        display_name=display_name,
        quota_used=quota_used,
        quota_total=quota_total,
    )
