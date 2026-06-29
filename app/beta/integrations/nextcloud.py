"""FlowHub Beta — Nextcloud client (BU5).

Adapted from production-proven WooPrice nextcloud.py.
Read-only: file download + metadata only.  No upload, no write, no delete.

WebDAV metadata strategy:
  1. HEAD request — lightweight, no body.
  2. PROPFIND fallback — if HEAD response lacks ETag (some proxies strip it).

Logging:
  - Every external request: provider, endpoint, duration_ms, status_code.
  - Errors: readable message, no credentials logged.
"""

from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

import httpx

from .errors import IntegrationError

if TYPE_CHECKING:
    from app.beta.setup.service import AppConfigService

logger = logging.getLogger(__name__)

# Timeout policy — split connect vs read to avoid hanging on large files
_TIMEOUT_QUICK = httpx.Timeout(connect=10.0, read=15.0, write=10.0, pool=5.0)
_TIMEOUT_DOWNLOAD = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=5.0)

_DAVNS = "{DAV:}"
_PROVIDER = "Nextcloud"


# ── PROPFIND XML parser (adapted from WooPrice) ───────────────────────────────

def _parse_propfind_meta(xml_text: str) -> dict[str, str | None]:
    """Extract etag, last_modified, content_length from a WebDAV PROPFIND response."""
    meta: dict[str, str | None] = {"etag": None, "last_modified": None, "content_length": None}
    try:
        root = ET.fromstring(xml_text)
        for response in root.iter(f"{_DAVNS}response"):
            for propstat in response.iter(f"{_DAVNS}propstat"):
                status_el = propstat.find(f"{_DAVNS}status")
                if status_el is None or "200" not in (status_el.text or ""):
                    continue
                prop = propstat.find(f"{_DAVNS}prop")
                if prop is None:
                    continue
                etag_el = prop.find(f"{_DAVNS}getetag")
                if etag_el is not None and etag_el.text:
                    meta["etag"] = etag_el.text.strip('"')
                lm_el = prop.find(f"{_DAVNS}getlastmodified")
                if lm_el is not None:
                    meta["last_modified"] = lm_el.text
                cl_el = prop.find(f"{_DAVNS}getcontentlength")
                if cl_el is not None:
                    meta["content_length"] = cl_el.text
    except ET.ParseError as exc:
        logger.warning("nc propfind_parse provider=%s parse_error=%s", _PROVIDER, exc)
    return meta


# ── Client ────────────────────────────────────────────────────────────────────

class NextcloudClient:
    """Async read-only Nextcloud / WebDAV client."""

    def __init__(self, url: str, username: str, password: str) -> None:
        self._url = url.rstrip("/")
        self._username = username
        self._auth = (username, password)

    @classmethod
    def from_config(cls, config: "AppConfigService") -> "NextcloudClient | None":
        """Build from AppConfigService.  Returns None if not fully configured."""
        url = config.get("nextcloud.url")
        username = config.get("nextcloud.username")
        password = config.get("nextcloud.password")
        if not url or not username or not password:
            return None
        return cls(url, username, password)

    def _dav_path(self, path: str) -> str:
        """Build WebDAV file URL for a given server-relative path."""
        clean_path = "/" + path.lstrip("/")
        return f"{self._url}/remote.php/dav/files/{self._username}{clean_path}"

    async def download_file(self, path: str) -> tuple[bytes, dict[str, str | None]]:
        """Download file at path.  Returns (raw_bytes, metadata_dict).

        metadata keys: etag, last_modified, content_length
        Raises IntegrationError on HTTP or network failure.
        """
        url = self._dav_path(path)
        t0 = time.monotonic()
        logger.info("nc download_file provider=%s path=%s", _PROVIDER, path)
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_DOWNLOAD, follow_redirects=True) as client:
                r = await client.get(url, auth=self._auth)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.warning(
                "nc download_file provider=%s path=%s error=%s duration_ms=%.0f",
                _PROVIDER, path, exc, elapsed_ms,
            )
            raise IntegrationError(
                _PROVIDER, url,
                "Could not connect to Nextcloud — check URL and network",
            ) from exc
        except Exception as exc:
            elapsed_ms = (time.monotonic() - t0) * 1000
            logger.warning(
                "nc download_file provider=%s path=%s unexpected_error=%s duration_ms=%.0f",
                _PROVIDER, path, exc, elapsed_ms,
            )
            raise IntegrationError(_PROVIDER, url, str(exc)[:200]) from exc

        elapsed_ms = (time.monotonic() - t0) * 1000

        if not r.is_success:
            logger.warning(
                "nc download_file provider=%s path=%s status=%d duration_ms=%.0f success=false",
                _PROVIDER, path, r.status_code, elapsed_ms,
            )
            raise IntegrationError(
                _PROVIDER, url,
                f"Nextcloud returned HTTP {r.status_code} for {path}",
                status_code=r.status_code,
            )

        logger.info(
            "nc download_file provider=%s path=%s status=%d bytes=%d duration_ms=%.0f success=true",
            _PROVIDER, path, r.status_code, len(r.content), elapsed_ms,
        )
        meta: dict[str, str | None] = {
            "etag": r.headers.get("etag", "").strip('"') or None,
            "last_modified": r.headers.get("last-modified") or None,
            "content_length": r.headers.get("content-length") or None,
        }
        return r.content, meta

    async def get_file_meta(self, path: str) -> dict[str, str | None]:
        """Fetch file metadata via HEAD, falling back to PROPFIND.

        Never raises — returns empty dict on failure (used for optional checks).
        """
        url = self._dav_path(path)
        meta: dict[str, str | None] = {"etag": None, "last_modified": None, "content_length": None}

        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=_TIMEOUT_QUICK, follow_redirects=True) as client:
            try:
                r = await client.head(url, auth=self._auth)
                elapsed_ms = (time.monotonic() - t0) * 1000
                logger.info(
                    "nc get_file_meta HEAD provider=%s path=%s status=%d duration_ms=%.0f",
                    _PROVIDER, path, r.status_code, elapsed_ms,
                )
                if r.status_code == 200:
                    meta["etag"] = r.headers.get("etag", "").strip('"') or None
                    meta["last_modified"] = r.headers.get("last-modified") or None
                    meta["content_length"] = r.headers.get("content-length") or None
                    if any(v for v in meta.values()):
                        return meta
                    logger.debug(
                        "nc get_file_meta HEAD provider=%s path=%s — etag absent, trying PROPFIND",
                        _PROVIDER, path,
                    )
            except httpx.HTTPError as exc:
                logger.debug(
                    "nc get_file_meta HEAD provider=%s path=%s failed=%s — trying PROPFIND",
                    _PROVIDER, path, exc,
                )

            # PROPFIND fallback
            try:
                t1 = time.monotonic()
                r = await client.request(
                    "PROPFIND",
                    url,
                    auth=self._auth,
                    headers={"Depth": "0"},
                )
                elapsed_ms = (time.monotonic() - t1) * 1000
                logger.info(
                    "nc get_file_meta PROPFIND provider=%s path=%s status=%d duration_ms=%.0f",
                    _PROVIDER, path, r.status_code, elapsed_ms,
                )
                if r.status_code in (200, 207):
                    meta = _parse_propfind_meta(r.text)
            except httpx.HTTPError as exc:
                logger.warning(
                    "nc get_file_meta PROPFIND provider=%s path=%s failed=%s",
                    _PROVIDER, path, exc,
                )

        return meta

    async def test_connection(self) -> tuple[bool, str, float]:
        """Test Nextcloud connectivity via PROPFIND on user root.

        Returns: (ok, message, latency_ms)
        """
        test_url = f"{self._url}/remote.php/dav/files/{self._username}/"
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_QUICK, follow_redirects=True) as client:
                r = await client.request(
                    "PROPFIND",
                    test_url,
                    auth=self._auth,
                    headers={"Depth": "0"},
                )
            latency_ms = (time.monotonic() - t0) * 1000
            logger.info(
                "nc test_connection provider=%s status=%d latency_ms=%.0f",
                _PROVIDER, r.status_code, latency_ms,
            )
            if r.status_code in (200, 207):
                return True, "Connected successfully", latency_ms
            if r.status_code == 401:
                return False, "Authentication failed — check username and app password", latency_ms
            if r.status_code == 404:
                return False, "User not found or WebDAV disabled", latency_ms
            return False, f"Unexpected HTTP {r.status_code}", latency_ms
        except httpx.ConnectError:
            latency_ms = (time.monotonic() - t0) * 1000
            logger.warning(
                "nc test_connection provider=%s error=ConnectError latency_ms=%.0f",
                _PROVIDER, latency_ms,
            )
            return False, "Could not connect — check URL", latency_ms
        except httpx.TimeoutException:
            latency_ms = (time.monotonic() - t0) * 1000
            logger.warning(
                "nc test_connection provider=%s error=Timeout latency_ms=%.0f",
                _PROVIDER, latency_ms,
            )
            return False, "Connection timed out", latency_ms
        except Exception as exc:
            latency_ms = (time.monotonic() - t0) * 1000
            logger.warning(
                "nc test_connection provider=%s error=%s latency_ms=%.0f",
                _PROVIDER, exc, latency_ms,
            )
            return False, f"Error: {str(exc)[:200]}", latency_ms
