"""Nextcloud spreadsheet read adapter.

FlowHub 1.0.0 can read a whole spreadsheet through the existing Nextcloud
integration, but it cannot safely batch-read individual spreadsheet product
rows by product ID. Incremental reads therefore fail closed instead of silently
downloading the full spreadsheet in metadata-filter mode.
"""

from __future__ import annotations

from datetime import datetime

from app.flowhub.read_engine.contracts import ConnectorReadCapabilities, ReadPage
from app.flowhub.read_engine.exceptions import IncrementalReadUnsupported


class NextcloudSpreadsheetReadAdapter:
    connector_id = "nextcloud:primary"
    connector_type = "nextcloud"
    capabilities = ConnectorReadCapabilities(
        supports_modified_since=False,
        supports_delta_sync=False,
        supports_updated_after=False,
        supports_pagination=False,
        supports_batch_read=False,
    )

    def __init__(self, *, url: str = "", username: str = "", password: str = "", spreadsheet_path: str = "") -> None:
        self.url = url.rstrip("/")
        self.username = username
        self.password = password
        self.spreadsheet_path = spreadsheet_path

    async def fetch_products(
        self,
        *,
        modified_since: datetime | None = None,
        cursor: str | None = None,
        product_ids: list[str] | None = None,
    ) -> ReadPage:
        _ = (modified_since, cursor, product_ids)
        raise IncrementalReadUnsupported(
            "incremental_read_unsupported: nextcloud spreadsheet cannot batch-read products safely"
        )

    async def fetch_metadata(self, *, cursor: str | None = None) -> ReadPage:
        _ = cursor
        raise IncrementalReadUnsupported(
            "incremental_read_unsupported: nextcloud spreadsheet metadata is file-level, not product-level"
        )
