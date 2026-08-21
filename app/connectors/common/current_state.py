"""Provider-neutral bulk current-state retrieval contracts.

Business workflows ask for current state through this module. Connectors remain
responsible for selecting collection, batch-by-id, grouped, cache, or
unsupported retrieval strategies while preserving per-entity evidence.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any


class CurrentStateStrategy(StrEnum):
    BATCH_BY_ID = "batch_by_id"
    COLLECTION_SCAN = "collection_scan"
    GROUPED_COLLECTION = "grouped_collection"
    SNAPSHOT = "snapshot"
    WEBHOOK_CACHE = "webhook_cache"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class CurrentStateIdentity:
    key: str
    external_id: str
    parent_external_id: str | None = None
    sku: str | None = None


@dataclass(frozen=True, slots=True)
class CurrentStateRequest:
    channel_id: str
    entities: tuple[CurrentStateIdentity, ...]
    required_fields: frozenset[str]
    purpose: str = "verification"
    max_staleness_seconds: float = 0

    def __post_init__(self) -> None:
        if not self.channel_id:
            raise ValueError("Current-state channel_id is required.")
        keys = [entity.key for entity in self.entities]
        if any(not key for key in keys):
            raise ValueError("Current-state entity keys are required.")
        if len(keys) != len(set(keys)):
            raise ValueError("Current-state entity keys must be unique.")
        if any(not entity.external_id for entity in self.entities):
            raise ValueError("Current-state external identifiers are required.")
        if self.max_staleness_seconds < 0:
            raise ValueError("Current-state max staleness cannot be negative.")


@dataclass(frozen=True, slots=True)
class CurrentStateRecord:
    key: str
    provider: str
    external_id: str
    parent_external_id: str | None = None
    # Pricing verification must retain the provider's decimal value exactly.
    # Callers may serialize this to canonical text for durable evidence, but
    # must never round-trip it through float first.
    price: Decimal | None = None
    stock: float | None = None
    status: str | None = None
    currency: str | None = None
    unit: str | None = None
    product_type: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def canonical_decimal(value: object) -> Decimal | None:
    """Normalize one provider numeric value without binary-float loss."""
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


@dataclass(frozen=True, slots=True)
class CurrentStateError:
    key: str
    category: str
    message: str
    retry_eligible: bool = False


@dataclass(frozen=True, slots=True)
class TransportReport:
    operation_id: str
    strategy: CurrentStateStrategy
    purpose: str
    entities_requested: int
    entities_returned: int
    requests_issued: int
    batches_issued: int
    retries: int
    failed_requests: int
    provider_response_ms: float
    slowest_request_ms: float
    total_duration_ms: float
    bottleneck_stage: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "strategy": self.strategy.value,
            "purpose": self.purpose,
            "entities_requested": self.entities_requested,
            "entities_returned": self.entities_returned,
            "requests_issued": self.requests_issued,
            "batches_issued": self.batches_issued,
            "retries": self.retries,
            "failed_requests": self.failed_requests,
            "provider_response_ms": self.provider_response_ms,
            "slowest_request_ms": self.slowest_request_ms,
            "total_duration_ms": self.total_duration_ms,
            "bottleneck_stage": self.bottleneck_stage,
        }


@dataclass(frozen=True, slots=True)
class CurrentStateResult:
    records: dict[str, CurrentStateRecord]
    errors: dict[str, CurrentStateError]
    transport: TransportReport

    def __post_init__(self) -> None:
        overlap = set(self.records).intersection(self.errors)
        if overlap:
            raise ValueError("Current-state entities cannot have both a record and an error.")
        if len(self.records) + len(self.errors) != self.transport.entities_requested:
            raise ValueError("Current-state results require one record or error per entity.")
        if len(self.records) != self.transport.entities_returned:
            raise ValueError("Current-state transport returned count does not match records.")


class TransportRecorder:
    """Collect request-level evidence without coupling callers to HTTP clients."""

    def __init__(
        self,
        *,
        strategy: CurrentStateStrategy,
        purpose: str,
        entities_requested: int,
        operation_id: str | None = None,
    ) -> None:
        self.operation_id = operation_id or f"csr_{uuid.uuid4().hex[:24]}"
        self.strategy = strategy
        self.purpose = purpose
        self.entities_requested = entities_requested
        self.requests_issued = 0
        self.batches_issued = 0
        self.retries = 0
        self.failed_requests = 0
        self.provider_response_ms = 0.0
        self.slowest_request_ms = 0.0
        self._stage_durations: dict[str, float] = {}
        self._started = time.perf_counter()

    def record_batch(self) -> None:
        self.batches_issued += 1

    def record_stage(self, *, stage: str, duration_ms: float) -> None:
        duration = max(float(duration_ms), 0.0)
        self._stage_durations[stage] = self._stage_durations.get(stage, 0.0) + duration

    def record_request(
        self,
        *,
        stage: str,
        duration_ms: float,
        retry: bool = False,
        failed: bool = False,
    ) -> None:
        duration = max(float(duration_ms), 0.0)
        self.requests_issued += 1
        self.retries += int(retry)
        self.failed_requests += int(failed)
        self.provider_response_ms += duration
        self.slowest_request_ms = max(self.slowest_request_ms, duration)
        self._stage_durations[stage] = self._stage_durations.get(stage, 0.0) + duration

    def finish(self, *, entities_returned: int) -> TransportReport:
        bottleneck = (
            max(self._stage_durations, key=self._stage_durations.get)
            if self._stage_durations
            else None
        )
        return TransportReport(
            operation_id=self.operation_id,
            strategy=self.strategy,
            purpose=self.purpose,
            entities_requested=self.entities_requested,
            entities_returned=entities_returned,
            requests_issued=self.requests_issued,
            batches_issued=self.batches_issued,
            retries=self.retries,
            failed_requests=self.failed_requests,
            provider_response_ms=round(self.provider_response_ms, 3),
            slowest_request_ms=round(self.slowest_request_ms, 3),
            total_duration_ms=round((time.perf_counter() - self._started) * 1000, 3),
            bottleneck_stage=bottleneck,
        )


def unsupported_current_state(
    request: CurrentStateRequest,
    *,
    message: str,
) -> CurrentStateResult:
    recorder = TransportRecorder(
        strategy=CurrentStateStrategy.UNSUPPORTED,
        purpose=request.purpose,
        entities_requested=len(request.entities),
    )
    errors = {
        entity.key: CurrentStateError(
            key=entity.key,
            category="unsupported_capability",
            message=message,
        )
        for entity in request.entities
    }
    return CurrentStateResult(
        records={},
        errors=errors,
        transport=recorder.finish(entities_returned=0),
    )


def failed_current_state(
    request: CurrentStateRequest,
    *,
    strategy: CurrentStateStrategy,
    category: str,
    message: str,
    retry_eligible: bool = False,
) -> CurrentStateResult:
    recorder = TransportRecorder(
        strategy=strategy,
        purpose=request.purpose,
        entities_requested=len(request.entities),
    )
    return CurrentStateResult(
        records={},
        errors={
            entity.key: CurrentStateError(
                key=entity.key,
                category=category,
                message=message,
                retry_eligible=retry_eligible,
            )
            for entity in request.entities
        },
        transport=recorder.finish(entities_returned=0),
    )
