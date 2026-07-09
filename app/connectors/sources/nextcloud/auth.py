"""Nextcloud authentication helpers.

All credential extraction is isolated here. The connector and WebDAV/OCS
modules import from this file - they never receive raw credential dicts.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.connectors.common.auth import AuthConfig
from app.connectors.common.errors import ConnectorError, ConnectorErrorCode


@dataclass(frozen=True)
class NextcloudCredentials:
    url: str      # base URL, trailing slash stripped
    username: str
    password: str
    webdav_files_root_url: str | None = None


def extract_credentials(auth: AuthConfig) -> NextcloudCredentials:
    """Extract and validate Nextcloud credentials from an AuthConfig.

    Raises ConnectorError(AUTH_FAILED) if required fields are missing.
    """
    if auth.auth_type not in ("basic", "none"):
        raise ConnectorError(
            code=ConnectorErrorCode.AUTH_FAILED,
            message=f"Nextcloud connector requires auth_type 'basic', got '{auth.auth_type}'",
            provider="nextcloud",
        )
    url = auth.get("url", "")
    username = auth.get("username", "")
    password = auth.get("password", "")

    if not url:
        raise ConnectorError(
            code=ConnectorErrorCode.AUTH_FAILED,
            message="Nextcloud auth missing 'url'",
            provider="nextcloud",
        )
    if not username:
        raise ConnectorError(
            code=ConnectorErrorCode.AUTH_FAILED,
            message="Nextcloud auth missing 'username'",
            provider="nextcloud",
        )

    return NextcloudCredentials(
        url=url.rstrip("/"),
        username=username,
        password=password,
        webdav_files_root_url=auth.get("webdav_files_root_url", "") or None,
    )
