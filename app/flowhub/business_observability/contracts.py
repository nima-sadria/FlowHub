"""Pydantic contracts and enumerations for FlowHub Business Observability v1.

The shapes here implement the Structured Business Event Contract from
``docs/draw/00-flowhub-master.drawio`` (``business_event_contract`` node) as
finalized in the Owner interview: Capability/domain, Status, Business
impact, Reason, Affected scope, Recommended operator action, Timestamp /
correlation reference — with severity and business impact kept as separate
axes, and lifecycle (open/acknowledged/resolved) modeled as an append-only
transition log rather than a mutable field on the fact row.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

# Domains that may emit business events. Extensible: a future producer
# (e.g. Orders, Exchange Rates, or a Pricing anomaly detector) can add a
# new value here without changing the shape of the contract itself.
BUSINESS_EVENT_DOMAINS = ("source_acquisition", "pricing", "channels", "write_pipeline")

SEVERITY_VALUES = ("info", "warning", "degraded", "error", "critical")

BUSINESS_IMPACT_VALUES = (
    "none",
    "degraded",
    "blocking",
    "partial_failure",
    "critical_business_failure",
)

SCOPE_TYPES = (
    "source",
    "worksheet",
    "workspace",
    "product",
    "revision",
    "pricing_run",
    "review",
    "changeset",
    "channel",
    "order",
    "connector",
    "batch",
)

# Monotonic in v1: OPEN -> ACKNOWLEDGED -> RESOLVED. RESOLVED is terminal;
# there is no reopen transition. If the same business problem recurs after
# resolution, the producer emits a new business event.
LIFECYCLE_STATUSES = ("open", "acknowledged", "resolved")

_ALLOWED_LIFECYCLE_TRANSITIONS: dict[str | None, tuple[str, ...]] = {
    None: ("acknowledged", "resolved"),
    "open": ("acknowledged", "resolved"),
    "acknowledged": ("resolved",),
    "resolved": (),
}


def assert_valid_transition(from_status: str | None, to_status: str) -> None:
    from app.flowhub.business_observability.errors import BusinessObservabilityError

    if to_status not in LIFECYCLE_STATUSES:
        raise BusinessObservabilityError("lifecycle_status_invalid", to_status)
    allowed = _ALLOWED_LIFECYCLE_TRANSITIONS.get(from_status, ())
    if to_status not in allowed:
        raise BusinessObservabilityError(
            "lifecycle_transition_not_allowed",
            f"{from_status or 'unset'} -> {to_status} is not a permitted v1 lifecycle transition",
        )


class BusinessEventScopeShape(BaseModel):
    scopeType: str
    scopeId: str
    scopeLabel: str | None = None


class BusinessEventLifecycleTransitionShape(BaseModel):
    id: int
    fromStatus: str | None
    toStatus: str
    actor: str
    occurredAt: datetime
    note: str | None = None


class BusinessEventShape(BaseModel):
    model_config = {"populate_by_name": True}

    id: str
    domain: str
    eventType: str
    severity: str
    businessImpact: str
    reasonCode: str
    reasonMessage: str
    primaryScope: BusinessEventScopeShape
    secondaryScopes: list[BusinessEventScopeShape] = Field(default_factory=list)
    recommendedAction: str
    retryable: bool
    actionRouteKey: str | None = None
    actionUrl: str | None = None
    correlationId: str
    producer: str
    occurredAt: datetime
    createdAt: datetime
    metadata: dict = Field(default_factory=dict)
    status: str
    acknowledgedAt: datetime | None = None
    acknowledgedBy: str | None = None
    resolvedAt: datetime | None = None
    resolvedBy: str | None = None


class BusinessEventListResponse(BaseModel):
    items: list[BusinessEventShape]
    total: int
    page: int
    pageSize: int


class BusinessEventLifecycleActionRequest(BaseModel):
    note: str | None = None


class BusinessEventKpiShape(BaseModel):
    openBlockingByDomain: dict[str, int]
    writePipelinePartialFailureRate30d: float
    oldestUnresolvedBlockingEventAgeSeconds: float | None
