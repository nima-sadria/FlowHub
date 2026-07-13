"""Provider-neutral commands and outcomes for Workspace writes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class WriteOutcome(StrEnum):
    PENDING = "pending"
    DISPATCH_INTENT_RECORDED = "dispatch_intent_recorded"
    DISPATCHED = "dispatched"
    PROVIDER_ACCEPTED = "provider_accepted"
    VERIFIED_APPLIED = "verified_applied"
    FAILED = "failed"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    RECOVERING = "recovering"


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
            "apply_job_id": self.apply_job_id,
            "apply_item_ids": list(self.apply_item_ids),
            "workspace_id": self.workspace_id,
            "snapshot_id": self.snapshot_id,
            "draft_revision_id": self.draft_revision_id,
            "review_id": self.review_id,
            "selection_checksum": self.selection_checksum,
            "listing_id": self.listing_id,
            "channel_id": self.channel_id,
            "external_primary_id": self.external_primary_id,
            "sku": self.sku,
            "product_type": self.product_type,
            "parent_external_id": self.parent_external_id,
            "current_price": self.current_price,
            "current_stock": self.current_stock,
            "current_status": self.current_status,
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
            "idempotency_key": self.idempotency_key,
            "payload_hash": self.payload_hash,
        }

    @classmethod
    def from_persisted_payload(cls, payload: dict[str, Any]) -> WorkspaceWriteIntent:
        required = {
            "apply_job_id",
            "apply_item_ids",
            "workspace_id",
            "snapshot_id",
            "draft_revision_id",
            "review_id",
            "selection_checksum",
            "listing_id",
            "channel_id",
            "external_primary_id",
            "product_type",
            "mapping_version",
            "cache_version",
            "cache_checksum",
            "capability_version",
            "currency_digest",
            "idempotency_key",
            "payload_hash",
        }
        missing = sorted(required.difference(payload))
        if missing:
            raise ValueError(f"Immutable dispatch payload is incomplete: {', '.join(missing)}")
        return cls(
            apply_job_id=str(payload["apply_job_id"]),
            apply_item_ids=tuple(str(value) for value in payload["apply_item_ids"]),
            workspace_id=str(payload["workspace_id"]),
            snapshot_id=str(payload["snapshot_id"]),
            draft_revision_id=str(payload["draft_revision_id"]),
            review_id=str(payload["review_id"]),
            selection_checksum=str(payload["selection_checksum"]),
            listing_id=str(payload["listing_id"]),
            channel_id=str(payload["channel_id"]),
            external_primary_id=str(payload["external_primary_id"]),
            sku=str(payload["sku"]) if payload.get("sku") is not None else None,
            product_type=str(payload["product_type"]),
            parent_external_id=(
                str(payload["parent_external_id"])
                if payload.get("parent_external_id") is not None
                else None
            ),
            current_price=_optional_float(payload.get("current_price")),
            current_stock=_optional_float(payload.get("current_stock")),
            current_status=(
                str(payload["current_status"])
                if payload.get("current_status") is not None
                else None
            ),
            target_price=_optional_float(payload.get("target_price")),
            target_stock=_optional_float(payload.get("target_stock")),
            target_status=(
                str(payload["target_status"]) if payload.get("target_status") is not None else None
            ),
            currency=str(payload["currency"]) if payload.get("currency") is not None else None,
            unit=str(payload["unit"]) if payload.get("unit") is not None else None,
            mapping_version=int(payload["mapping_version"]),
            cache_version=int(payload["cache_version"]),
            cache_checksum=str(payload["cache_checksum"]),
            capability_version=str(payload["capability_version"]),
            currency_digest=str(payload["currency_digest"]),
            idempotency_key=str(payload["idempotency_key"]),
            payload_hash=str(payload["payload_hash"]),
        )


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


def _optional_float(value: Any) -> float | None:
    return float(value) if value is not None else None
