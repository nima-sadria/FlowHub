"""NextcloudConnector - concrete SourceConnector for Nextcloud via WebDAV + OCS.

The only concrete class in this package. Business logic (adapters, rule engine)
must import only this class - never webdav.py or ocs.py directly.

Capabilities:
  can_list_folders    = True
  can_list_files      = True
  can_list_worksheets = False  (Excel/XLSX parsing is the adapter's job)
  can_read_worksheet  = False  (same)
  can_get_metadata    = True
  can_watch_changes   = False  (polling is handled at adapter level)
"""
from __future__ import annotations

import time

from app.connectors.common.auth import AuthConfig
from app.connectors.common.base import SourceConnector
from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
from app.connectors.common.health import HealthResult, HealthStatus
from app.connectors.common.test_result import ConnectionTestResult
from app.connectors.common.types import ConnectorCapabilities, ConnectorID

from .auth import NextcloudCredentials, extract_credentials
from .ocs import check_server_info
from .webdav import get_file, get_metadata, propfind_path


class NextcloudConnector(SourceConnector):
    """Read-only Nextcloud source connector.

    Lifecycle:
      1. test_connection(auth)  - probe without storing state (safe to call any time)
      2. connect(auth)          - store credentials for subsequent calls
      3. health()               - lightweight OCS ping
      4. list_folders(path)     - PROPFIND depth=1, collections only
      5. list_files(path)       - PROPFIND depth=1, non-collections only
      6. get_metadata(path)     - PROPFIND depth=0
      7. read_file(path)        - WebDAV GET (returns raw bytes + meta)
      8. disconnect()           - clears stored credentials
    """

    connector_id: ConnectorID = "nextcloud"

    def __init__(self) -> None:
        self._creds: NextcloudCredentials | None = None

    def capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            can_list_folders=True,
            can_list_files=True,
            can_list_worksheets=False,
            can_read_worksheet=False,
            can_get_metadata=True,
            can_watch_changes=False,
        )

    # -- Lifecycle -------------------------------------------------------------

    async def connect(self, auth: AuthConfig) -> None:
        """Store credentials and verify the server is reachable."""
        creds = extract_credentials(auth)
        await check_server_info(creds)
        self._creds = creds

    async def disconnect(self) -> None:
        self._creds = None

    # -- Health ----------------------------------------------------------------

    async def health(self) -> HealthResult:
        if self._creds is None:
            return HealthResult(
                status=HealthStatus.UNHEALTHY,
                detail="Not connected - call connect() first",
            )
        t0 = time.monotonic()
        try:
            info = await check_server_info(self._creds)
            latency = (time.monotonic() - t0) * 1000
            detail = f"Nextcloud {info.version}" if info.version else None
            return HealthResult(status=HealthStatus.HEALTHY, latency_ms=latency, detail=detail)
        except ConnectorError as exc:
            latency = (time.monotonic() - t0) * 1000
            return HealthResult(
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency,
                detail=str(exc),
            )

    # -- Connection test -------------------------------------------------------

    async def test_connection(self, auth: AuthConfig) -> ConnectionTestResult:
        """Probe the Nextcloud server without storing state."""
        t0 = time.monotonic()
        try:
            creds = extract_credentials(auth)
            info = await check_server_info(creds)
            latency = (time.monotonic() - t0) * 1000
            version = info.version or "unknown"
            return ConnectionTestResult(
                ok=True,
                message=f"Connected to Nextcloud {version}",
                latency_ms=round(latency, 1),
            )
        except ConnectorError as exc:
            latency = (time.monotonic() - t0) * 1000
            return ConnectionTestResult(
                ok=False,
                message=str(exc),
                latency_ms=round(latency, 1),
            )
        except Exception as exc:
            latency = (time.monotonic() - t0) * 1000
            return ConnectionTestResult(
                ok=False,
                message=f"Unexpected error: {exc}",
                latency_ms=round(latency, 1),
            )

    # -- Source operations -----------------------------------------------------

    def _require_connected(self) -> NextcloudCredentials:
        if self._creds is None:
            raise ConnectorError(
                code=ConnectorErrorCode.UNKNOWN,
                message="NextcloudConnector is not connected - call connect() first",
                provider="nextcloud",
            )
        return self._creds

    async def list_folders(self, path: str = "/") -> list[str]:
        """Return DAV hrefs for all sub-collections under path."""
        creds = self._require_connected()
        resources = await propfind_path(creds, path, depth="1")
        # Skip the first entry which is the path itself
        return [r.href for r in resources[1:] if r.is_collection]

    async def list_files(self, path: str = "/") -> list[str]:
        """Return DAV hrefs for all non-collection resources under path."""
        creds = self._require_connected()
        resources = await propfind_path(creds, path, depth="1")
        return [r.href for r in resources if not r.is_collection]

    async def get_metadata(self, path: str) -> dict:
        """Return ETag, last-modified, and size for a single resource."""
        creds = self._require_connected()
        return await get_metadata(creds, path)

    async def read_file(self, path: str) -> tuple[bytes, dict]:
        """Download a file and return (content_bytes, metadata_dict).

        This method is NOT part of the SourceConnector ABC but is a
        NextcloudConnector extension for adapters that need raw file bytes.
        """
        creds = self._require_connected()
        return await get_file(creds, path)
