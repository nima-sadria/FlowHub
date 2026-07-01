"""FlowHub - Nextcloud client (BU5).

All HTTP calls are delegated to app/connectors/sources/nextcloud/.
No direct httpx usage in this module.

Read-only: file download + metadata only.  No upload, no write, no delete.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from app.connectors.common.auth import AuthConfig
from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
from app.connectors.sources.nextcloud.auth import NextcloudCredentials
from app.connectors.sources.nextcloud.connector import NextcloudConnector
from app.connectors.sources.nextcloud.webdav import get_file, get_metadata, head_file

from .errors import IntegrationError

if TYPE_CHECKING:
    from app.beta.setup.service import AppConfigService

logger = logging.getLogger(__name__)

_PROVIDER = "Nextcloud"


# -- Error mapping -------------------------------------------------------------

def _to_integration_error(exc: ConnectorError, endpoint: str) -> IntegrationError:
    """Map ConnectorError to IntegrationError for the API layer."""
    code = exc.code
    if code == ConnectorErrorCode.AUTH_FAILED:
        msg = "Authentication failed - check username and app password"
    elif code == ConnectorErrorCode.PERMISSION:
        msg = "Access denied - check WebDAV permissions"
    elif code == ConnectorErrorCode.NOT_FOUND:
        msg = f"File not found: {endpoint}"
    elif code == ConnectorErrorCode.TIMEOUT:
        msg = "Connection timed out"
    elif code == ConnectorErrorCode.NETWORK:
        msg = "Could not connect to Nextcloud - check URL and network"
    else:
        msg = exc.message or f"Nextcloud error: {code.value}"
    return IntegrationError(_PROVIDER, endpoint, msg, status_code=exc.http_status)


# -- Client --------------------------------------------------------------------

class NextcloudClient:
    """Async read-only Nextcloud / WebDAV client backed by the connector framework."""

    def __init__(self, url: str, username: str, password: str) -> None:
        self._creds = NextcloudCredentials(
            url=url.rstrip("/"),
            username=username,
            password=password,
        )

    @classmethod
    def from_config(cls, config: "AppConfigService") -> "NextcloudClient | None":
        """Build from AppConfigService.  Returns None if not fully configured."""
        url = config.get("nextcloud.url")
        username = config.get("nextcloud.username")
        password = config.get("nextcloud.password")
        if not url or not username or not password:
            return None
        return cls(url, username, password)

    def _clean_path(self, path: str) -> str:
        """Ensure path starts with /."""
        return "/" + path.lstrip("/")

    async def download_file(self, path: str) -> tuple[bytes, dict[str, str | None]]:
        """Download file at path.  Returns (raw_bytes, metadata_dict).

        metadata keys: etag, last_modified, content_length
        Raises IntegrationError on HTTP or network failure.
        """
        clean_path = self._clean_path(path)
        endpoint = (
            f"{self._creds.url}/remote.php/dav/files/{self._creds.username}{clean_path}"
        )
        logger.info("nc download_file provider=%s path=%s", _PROVIDER, path)
        t0 = time.monotonic()
        try:
            content, raw_meta = await get_file(self._creds, clean_path)
        except ConnectorError as exc:
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.warning(
                "nc download_file provider=%s path=%s error=%s duration_ms=%.0f",
                _PROVIDER, path, exc.message, elapsed_ms,
            )
            raise _to_integration_error(exc, endpoint) from exc
        except Exception as exc:
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.warning(
                "nc download_file provider=%s path=%s unexpected_error=%s duration_ms=%.0f",
                _PROVIDER, path, exc, elapsed_ms,
            )
            raise IntegrationError(_PROVIDER, endpoint, str(exc)[:200]) from exc

        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.info(
            "nc download_file provider=%s path=%s bytes=%d duration_ms=%.0f success=true",
            _PROVIDER, path, len(content), elapsed_ms,
        )
        meta: dict[str, str | None] = {
            "etag": raw_meta.get("etag") or None,
            "last_modified": raw_meta.get("last_modified") or None,
            "content_length": raw_meta.get("content_length") or None,
        }
        return content, meta

    async def get_file_meta(self, path: str) -> dict[str, str | None]:
        """Fetch file metadata via HEAD, falling back to PROPFIND.

        Never raises - returns empty dict on failure (used for optional checks).
        """
        clean_path = self._clean_path(path)

        # HEAD first - lightweight
        meta = await head_file(self._creds, clean_path)
        if any(v for v in meta.values()):
            return meta

        # PROPFIND fallback
        logger.debug(
            "nc get_file_meta HEAD provider=%s path=%s - etag absent, trying PROPFIND",
            _PROVIDER, path,
        )
        try:
            raw = await get_metadata(self._creds, clean_path)
            return {
                "etag": raw.get("etag") or None,
                "last_modified": raw.get("last_modified") or None,
                "content_length": (
                    str(raw["content_length"])
                    if raw.get("content_length") is not None
                    else None
                ),
            }
        except Exception:
            return {"etag": None, "last_modified": None, "content_length": None}

    async def test_connection(self) -> tuple[bool, str, float]:
        """Test Nextcloud connectivity.  Returns (ok, message, latency_ms)."""
        auth = AuthConfig(
            auth_type="basic",
            credentials={
                "url": self._creds.url,
                "username": self._creds.username,
                "password": self._creds.password,
            },
        )
        t0 = time.monotonic()
        try:
            connector = NextcloudConnector()
            result = await connector.test_connection(auth)
            latency_ms = result.latency_ms or (time.monotonic() - t0) * 1000
            logger.info(
                "nc test_connection provider=%s ok=%s latency_ms=%.0f",
                _PROVIDER, result.ok, latency_ms,
            )
            return result.ok, result.message, latency_ms
        except Exception as exc:
            latency_ms = (time.monotonic() - t0) * 1000
            logger.warning(
                "nc test_connection provider=%s error=%s latency_ms=%.0f",
                _PROVIDER, exc, latency_ms,
            )
            return False, f"Error: {str(exc)[:200]}", latency_ms
