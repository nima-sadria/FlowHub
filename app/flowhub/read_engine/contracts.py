"""Contracts for source/channel product reads."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class ConnectorReadCapabilities:
    supports_modified_since: bool = False
    supports_delta_sync: bool = False
    supports_updated_after: bool = False
    supports_pagination: bool = False
    supports_batch_read: bool = False


@dataclass(frozen=True)
class ReadPage:
    items: list[dict]
    next_cursor: str | None = None
    latency_ms: float | None = None
    metadata_only: bool = False


class ReadConnectorAdapter(Protocol):
    connector_id: str
    connector_type: str
    capabilities: ConnectorReadCapabilities

    async def fetch_products(
        self,
        *,
        modified_since: datetime | None = None,
        cursor: str | None = None,
        product_ids: list[str] | None = None,
    ) -> ReadPage:
        """Fetch a page of products or requested product IDs."""
        ...

    async def fetch_metadata(
        self,
        *,
        cursor: str | None = None,
    ) -> ReadPage:
        """Fetch lightweight metadata when API-side modified filtering is absent."""
        ...
