"""Framework-free domain contracts and policies for Unified Workspace."""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any


class EntryPoint(StrEnum):
    SOURCE = "source"
    MANUAL = "manual"


class ProductKind(StrEnum):
    SIMPLE = "simple"
    VARIABLE = "variable"
    VARIATION = "variation"


class MappingState(StrEnum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    CONFLICT = "conflict"


class WorkspaceState(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class DraftState(StrEnum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    APPLIED = "applied"


class ReviewState(StrEnum):
    READY = "ready"
    BLOCKED = "blocked"
    STALE = "stale"


class ApplyState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PARTIALLY_APPLIED = "partially_applied"
    APPLIED = "applied"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"
    STALE = "stale"
    RECONCILIATION_REQUIRED = "reconciliation_required"


class ApplyItemOutcome(StrEnum):
    """Authoritative lifecycle for a single external write attempt."""

    PENDING = "pending"
    DISPATCH_INTENT_RECORDED = "dispatch_intent_recorded"
    DISPATCHED = "dispatched"
    PROVIDER_ACCEPTED = "provider_accepted"
    VERIFIED_APPLIED = "verified_applied"
    FAILED = "failed"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    RECOVERING = "recovering"


class CellStatus(StrEnum):
    UNCHANGED = "unchanged"
    EDITED = "edited"
    DRAFT_SAVED = "draft_saved"
    WARNING = "warning"
    ERROR = "error"
    READY = "ready"
    APPLYING = "applying"
    APPLIED = "applied"
    FAILED = "failed"
    READ_ONLY = "read_only"
    UNAVAILABLE = "unavailable"
    STALE_REVIEW = "stale_review"


class WorkspaceDomainError(ValueError):
    code = "WORKSPACE_DOMAIN_ERROR"


class ConcurrencyConflict(WorkspaceDomainError):
    code = "OPTIMISTIC_CONCURRENCY_CONFLICT"


class ImmutableRecordError(WorkspaceDomainError):
    code = "IMMUTABLE_RECORD"


class StaleReviewError(WorkspaceDomainError):
    code = "STALE_REVIEW"


class PermissionDenied(WorkspaceDomainError):
    code = "WORKSPACE_PERMISSION_DENIED"


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def canonical_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(text.strip().split())


def stable_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def checksum(value: object) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Money:
    raw_amount: str
    currency: str
    unit: str
    original_currency: str
    original_unit: str
    normalized_amount: Decimal
    normalized_currency: str
    normalized_unit: str
    conversion_factor: Decimal
    conversion_rule: str
    conversion_context: str
    configuration_reference: str

    @classmethod
    def create(
        cls,
        raw_amount: object,
        *,
        currency: str,
        unit: str,
        normalized_currency: str,
        normalized_unit: str,
        conversion_factor: object,
        conversion_rule: str,
        conversion_context: str,
        configuration_reference: str,
    ) -> Money:
        currency_value = canonical_text(currency).upper()
        unit_value = canonical_text(unit).upper()
        if not currency_value or not unit_value:
            raise WorkspaceDomainError("Currency and unit must be explicit.")
        if currency_value in {"TMN", "TOMAN"}:
            raise WorkspaceDomainError("Toman is a unit, not an ISO currency code.")
        try:
            amount = Decimal(canonical_text(raw_amount).replace(",", ""))
            factor = Decimal(canonical_text(conversion_factor))
        except InvalidOperation as exc:
            raise WorkspaceDomainError(
                "Money amount and conversion factor must be numeric."
            ) from exc
        if not amount.is_finite() or not factor.is_finite() or factor <= 0:
            raise WorkspaceDomainError(
                "Money values must be finite and conversion factor must be positive."
            )
        return cls(
            raw_amount=canonical_text(raw_amount),
            currency=currency_value,
            unit=unit_value,
            original_currency=currency_value,
            original_unit=unit_value,
            normalized_amount=amount * factor,
            normalized_currency=canonical_text(normalized_currency).upper(),
            normalized_unit=canonical_text(normalized_unit).upper(),
            conversion_factor=factor,
            conversion_rule=canonical_text(conversion_rule),
            conversion_context=canonical_text(conversion_context),
            configuration_reference=canonical_text(configuration_reference),
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "raw_amount": self.raw_amount,
            "currency": self.currency,
            "unit": self.unit,
            "original_currency": self.original_currency,
            "original_unit": self.original_unit,
            "normalized_amount": str(self.normalized_amount),
            "normalized_currency": self.normalized_currency,
            "normalized_unit": self.normalized_unit,
            "conversion_factor": str(self.conversion_factor),
            "conversion_rule": self.conversion_rule,
            "conversion_context": self.conversion_context,
            "configuration_reference": self.configuration_reference,
        }


@dataclass(frozen=True, slots=True)
class ChannelCapabilities:
    channel_id: str
    read_price: bool
    write_price: bool
    read_stock: bool
    write_stock: bool
    read_status: bool
    write_status: bool
    supports_bulk_update: bool
    supports_partial_update: bool
    supports_multiple_listings: bool
    supports_variations: bool
    requires_stock_management: bool
    maximum_batch_size: int
    rate_limit_per_minute: int | None
    health_state: str
    primary_identifier_type: str
    supported_statuses: tuple[str, ...]
    currency: str
    unit: str
    write_available: bool
    version: str

    def can_write(self, field: str) -> bool:
        return self.write_available and {
            "price": self.write_price,
            "stock": self.write_stock,
            "status": self.write_status,
        }.get(field, False)


@dataclass(frozen=True, slots=True)
class DraftChange:
    canonical_product_id: str
    listing_id: str
    channel_id: str
    field: str
    target_value: str
    currency: str | None = None
    unit: str | None = None

    def __post_init__(self) -> None:
        if self.field not in {"price", "stock", "status"}:
            raise WorkspaceDomainError(f"Unsupported editable field: {self.field}")
        if not all((self.canonical_product_id, self.listing_id, self.channel_id)):
            raise WorkspaceDomainError("Canonical product, listing, and channel are required.")
        if self.field in {"price", "stock"}:
            try:
                parsed = Decimal(canonical_text(self.target_value).replace(",", ""))
            except InvalidOperation as exc:
                raise WorkspaceDomainError(f"{self.field} must be numeric.") from exc
            if not parsed.is_finite() or parsed < 0:
                raise WorkspaceDomainError(f"{self.field} must be finite and non-negative.")
        if self.field == "price" and (not self.currency or not self.unit):
            raise WorkspaceDomainError("Price changes require explicit currency and unit.")

    def as_dict(self) -> dict[str, str | None]:
        return {
            "canonical_product_id": self.canonical_product_id,
            "listing_id": self.listing_id,
            "channel_id": self.channel_id,
            "field": self.field,
            "target_value": canonical_text(self.target_value),
            "currency": self.currency,
            "unit": self.unit,
        }


def validate_product_editable(product_type: str) -> None:
    if product_type == ProductKind.VARIABLE:
        raise WorkspaceDomainError(
            "Variable parent products are grouping-only and cannot be edited."
        )
    if product_type not in {ProductKind.SIMPLE, ProductKind.VARIATION}:
        raise WorkspaceDomainError("Unsupported product type.")


def deterministic_revision_checksum(changes: list[DraftChange], metadata: Mapping[str, Any]) -> str:
    ordered = sorted(
        (change.as_dict() for change in changes),
        key=lambda item: (
            str(item["canonical_product_id"]),
            str(item["listing_id"]),
            str(item["field"]),
        ),
    )
    return checksum({"changes": ordered, "metadata": dict(metadata)})


def values_equal(field: str, current: object, target: object) -> bool:
    if field in {"price", "stock"}:
        try:
            left = Decimal(canonical_text(current).replace(",", ""))
            right = Decimal(canonical_text(target).replace(",", ""))
        except InvalidOperation:
            return False
        return left.is_finite() and right.is_finite() and left == right
    return canonical_text(current).casefold() == canonical_text(target).casefold()


def finite_number(value: object) -> bool:
    try:
        return math.isfinite(float(canonical_text(value).replace(",", "")))
    except (TypeError, ValueError):
        return False
