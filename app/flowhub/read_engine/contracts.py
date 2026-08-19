"""Contracts for source/channel product reads."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol


@dataclass(frozen=True)
class ConnectorReadCapabilities:
    supports_modified_since: bool = False
    supports_delta_sync: bool = False
    supports_updated_after: bool = False
    supports_pagination: bool = False
    supports_batch_read: bool = False  # equivalent to the canonical "supports_bulk_read" capability
    # --- Channel Read architecture additions (ADR_CHANNEL_READ_ARCHITECTURE.md) ---
    supports_entity_read: bool = False  # equivalent to the canonical "supports_targeted_read" capability
    supports_cursor: bool = False       # opaque cursor iteration, distinct from simple page-number pagination
    supports_change_feed: bool = False
    supports_full_snapshot: bool = False
    supports_deep_recovery: bool = False
    supports_variation_embedding: bool = False
    max_page_size: int | None = None
    recommended_concurrency: int = 1
    rate_limit_characteristics: str | None = None  # descriptive only; enforcement stays in RateLimitService


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

    async def fetch_entity(
        self,
        *,
        entity_id: str,
        parent_id: str | None = None,
    ) -> ReadPage:
        """Fetch exactly one entity (LIGHT/PRODUCT scope). Requires supports_entity_read."""
        ...


class ReadStrategy(StrEnum):
    """Provider-neutral Channel Read strategy. Never exposed to Workspace directly."""

    LIGHT = "LIGHT"
    FULL = "FULL"
    DEEP = "DEEP"


class ReadScope(StrEnum):
    CHANNEL = "CHANNEL"
    PRODUCT = "PRODUCT"


class ReadReason(StrEnum):
    WEBHOOK_PRODUCT_UPDATED = "WEBHOOK_PRODUCT_UPDATED"
    PERIODIC_RECONCILIATION = "PERIODIC_RECONCILIATION"
    OWNER_REQUESTED = "OWNER_REQUESTED"
    VERIFICATION = "VERIFICATION"
    INITIAL_BACKFILL = "INITIAL_BACKFILL"
    RECOVERY = "RECOVERY"


@dataclass(frozen=True)
class ChannelReadRequest:
    """Provider-neutral read intent. Strategy and Scope are independent axes;
    the Connector Strategy Resolver (strategy_resolver.py) is what turns a
    request into a concrete execution mechanism, not the caller."""

    connector_id: str
    strategy: ReadStrategy
    scope: ReadScope
    reason: ReadReason
    identifiers: tuple[str, ...] = field(default_factory=tuple)
    checkpoint: dict[str, Any] | None = None
    triggered_by: str = "system"
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        if self.scope is ReadScope.PRODUCT and not self.identifiers:
            raise ValueError("PRODUCT scope requires at least one identifier.")
        if self.scope is ReadScope.CHANNEL and self.identifiers:
            raise ValueError("CHANNEL scope must not carry entity identifiers.")
