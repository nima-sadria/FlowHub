"""FlowHub - Nextcloud client (BU5).

All HTTP calls are delegated to app/connectors/sources/nextcloud/.
No direct httpx usage in this module.

Read-only: file download + metadata only.  No upload, no write, no delete.
"""

from __future__ import annotations

import logging
import posixpath
import time
from typing import TYPE_CHECKING
from urllib.parse import unquote

from app.connectors.common.auth import AuthConfig
from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
from app.connectors.sources.nextcloud.auth import NextcloudCredentials
from app.connectors.sources.nextcloud.connector import NextcloudConnector
from app.connectors.sources.nextcloud.webdav import DavResource, get_file, get_metadata, head_file, propfind_path

from .errors import IntegrationError

if TYPE_CHECKING:
    from app.flowhub.setup.service import AppConfigService

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
        """Normalize a user file path and reject traversal outside WebDAV root."""
        raw = unquote(str(path or "/")).strip().replace("\\", "/")
        if "\x00" in raw:
            raise IntegrationError(_PROVIDER, path, "Invalid Nextcloud path.", status_code=422)
        if not raw.startswith("/"):
            raw = "/" + raw
        raw_parts = [part for part in raw.split("/") if part]
        if any(part == ".." for part in raw_parts):
            raise IntegrationError(_PROVIDER, path, "Invalid Nextcloud path.", status_code=422)
        normalized = posixpath.normpath(raw)
        if normalized == ".":
            normalized = "/"
        if not normalized.startswith("/"):
            normalized = "/" + normalized
        parts = [part for part in normalized.split("/") if part]
        if any(part == ".." for part in parts):
            raise IntegrationError(_PROVIDER, path, "Invalid Nextcloud path.", status_code=422)
        return normalized

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

    async def browse_directory(self, path: str = "/") -> dict:
        """List a WebDAV directory with folders and spreadsheet-compatible files.

        Returns only directories and spreadsheet file extensions. CSV/XLS/ODS are
        visible but marked unsupported because the current parser supports
        openpyxl workbooks only.
        """
        clean_path = self._clean_path(path)
        endpoint = f"{self._creds.url}/remote.php/dav/files/{self._creds.username}{clean_path}"
        try:
            resources = await propfind_path(self._creds, clean_path, depth="1")
        except ConnectorError as exc:
            raise _to_integration_error(exc, endpoint) from exc
        current = clean_path.rstrip("/") or "/"
        directories: list[dict] = []
        files: list[dict] = []
        for resource in resources:
            item = self._resource_to_browser_item(resource)
            if item is None or item["path"].rstrip("/") == current.rstrip("/"):
                continue
            if item["type"] == "directory":
                directories.append(item)
            elif item["extension"] in _SPREADSHEET_EXTENSIONS:
                files.append(item)
        directories.sort(key=lambda item: item["name"].lower())
        files.sort(key=lambda item: item["name"].lower())
        return {
            "path": current,
            "directories": directories,
            "files": files,
            "read_only": True,
            "write_blocked": True,
        }

    async def get_resource_info(self, path: str) -> dict:
        """Return browser metadata for one resource, raising if it is unavailable."""
        clean_path = self._clean_path(path)
        endpoint = f"{self._creds.url}/remote.php/dav/files/{self._creds.username}{clean_path}"
        try:
            resources = await propfind_path(self._creds, clean_path, depth="0")
        except ConnectorError as exc:
            raise _to_integration_error(exc, endpoint) from exc
        if not resources:
            raise IntegrationError(_PROVIDER, endpoint, f"File not found: {clean_path}", status_code=404)
        item = self._resource_to_browser_item(resources[0])
        if item is None:
            raise IntegrationError(_PROVIDER, endpoint, f"File not found: {clean_path}", status_code=404)
        return item

    def _resource_to_browser_item(self, resource: DavResource) -> dict | None:
        path = self._path_from_href(resource.href)
        if path is None:
            return None
        name = path.rstrip("/").rsplit("/", 1)[-1] if path.rstrip("/") else "/"
        if resource.is_collection:
            return {
                "name": name,
                "path": path.rstrip("/") or "/",
                "type": "directory",
                "extension": "",
                "modified_at": resource.last_modified or None,
                "size": resource.content_length,
                "supported": True,
            }
        extension = _extension(name)
        return {
            "name": name,
            "path": path,
            "type": "file",
            "extension": extension,
            "modified_at": resource.last_modified or None,
            "size": resource.content_length,
            "supported": extension in _SUPPORTED_SPREADSHEET_EXTENSIONS,
        }

    def _path_from_href(self, href: str) -> str | None:
        decoded = unquote(str(href or ""))
        marker = f"/remote.php/dav/files/{self._creds.username}"
        index = decoded.find(marker)
        if index < 0:
            return None
        path = decoded[index + len(marker):] or "/"
        try:
            return self._clean_path(path)
        except IntegrationError:
            return None

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


_SPREADSHEET_EXTENSIONS = frozenset({".xlsx", ".xls", ".ods", ".csv"})
_SUPPORTED_SPREADSHEET_EXTENSIONS = frozenset({".xlsx"})


def _extension(name: str) -> str:
    if "." not in name:
        return ""
    return "." + name.rsplit(".", 1)[-1].lower()
