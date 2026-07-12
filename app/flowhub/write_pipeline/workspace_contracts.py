"""Provider-neutral commands and outcomes for Workspace writes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class WriteOutcome(StrEnum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    PROVIDER_ACCEPTED = "provider_accepted"
    VERIFIED_APPLIED = "verified_applied"
    FAILED = "failed"
    RECONCILIATION_REQUIRED = "reconciliation_required"


@dataclass(frozen=True, slots=True)
class WorkspaceWriteIntent:
    apply_job_id: str
    apply_item_ids: tuple[str, ...]
    workspace_id: str
    snapshot_id: str
    draft_revision_id: str
    review_id: str
    selection_checksum: str
    listing_id: str
    channel_id: str
    external_primary_id: str
    sku: str | None
    product_type: str
    parent_external_id: str | None
    current_price: float | None
    current_stock: float | None
    current_status: str | None
    target_price: float | None
    target_stock: float | None
    target_status: str | None
    currency: str | None
    unit: str | None
    mapping_version: int
    cache_version: int
    cache_checksum: str
    capability_version: str
    currency_digest: str
    idempotency_key: str
    payload_hash: str

    def normalized_payload(self) -> dict[str, Any]:
        return {
            "listing_id": self.listing_id,
            "channel_id": self.channel_id,
            "external_primary_id": self.external_primary_id,
            "parent_external_id": self.parent_external_id,
            "target_price": self.target_price,
            "target_stock": self.target_stock,
            "target_status": self.target_status,
            "currency": self.currency,
            "unit": self.unit,
            "mapping_version": self.mapping_version,
            "cache_version": self.cache_version,
            "cache_checksum": self.cache_checksum,
            "capability_version": self.capability_version,
            "currency_digest": self.currency_digest,
        }


@dataclass(frozen=True, slots=True)
class WorkspaceWriteBatchCommand:
    workspace_id: str
    snapshot_id: str
    draft_revision_id: str
    review_id: str
    selection_checksum: str
    correlation_id: str
    requested_by: str
    intents: tuple[WorkspaceWriteIntent, ...]


@dataclass(frozen=True, slots=True)
class WorkspaceWriteResult:
    listing_id: str
    outcome: WriteOutcome
    provider_accepted: bool = False
    response: dict[str, Any] = field(default_factory=dict)
    external_response_id: str | None = None
    error_category: str | None = None
    error_message: str | None = None
    retry_eligible: bool = False
    accepted_price: float | None = None
    accepted_stock: float | None = None
    accepted_status: str | None = None

    @property
    def verified(self) -> bool:
        return self.outcome is WriteOutcome.VERIFIED_APPLIED
