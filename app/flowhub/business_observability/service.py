"""FlowHub Business Observability v1 service.

Producers call ``emit_event`` once, when an outcome is known; the row is
never mutated afterwards. Acknowledge/resolve append a lifecycle
transition; current effective status is projected in Python from the
already eager-loaded transition history (``_project_state``), never stored
as a mutable column — see ``models.py`` for why.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.flowhub.business_observability.contracts import (
    BUSINESS_EVENT_DOMAINS,
    BUSINESS_IMPACT_VALUES,
    SCOPE_TYPES,
    SEVERITY_VALUES,
    BusinessEventKpiShape,
    BusinessEventLifecycleTransitionShape,
    BusinessEventScopeShape,
    BusinessEventShape,
    assert_valid_transition,
)
from app.flowhub.business_observability.errors import BusinessObservabilityError
from app.flowhub.business_observability.models import (
    BusinessEvent,
    BusinessEventLifecycleTransition,
)
from app.flowhub.business_observability.route_registry import resolve_action_route
from app.flowhub.security.redaction import redact_sensitive

# Business-impact values that represent something an operator still needs
# to look at. "none" and "degraded" are informational; the remaining three
# are what the approved KPI set ("blocking business events by domain")
# counts.
BLOCKING_IMPACTS = ("blocking", "partial_failure", "critical_business_failure")

WRITE_PIPELINE_BATCH_OUTCOME_EVENT_TYPES = (
    "write_batch_applied",
    "write_batch_partially_failed",
    "write_batch_reconciliation_required",
    "write_batch_failed",
)
WRITE_PIPELINE_NON_FULL_SUCCESS_EVENT_TYPES = (
    "write_batch_partially_failed",
    "write_batch_reconciliation_required",
    "write_batch_failed",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _new_id() -> str:
    return str(uuid.uuid4())


class BusinessObservabilityService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Producer-facing API
    # ------------------------------------------------------------------

    def emit_event(
        self,
        *,
        domain: str,
        event_type: str,
        severity: str,
        business_impact: str,
        reason_code: str,
        reason_message: str = "",
        primary_scope_type: str,
        primary_scope_id: str,
        primary_scope_label: str | None = None,
        secondary_scopes: list[tuple[str, str, str | None]] | None = None,
        recommended_action: str = "",
        retryable: bool = False,
        action_route_key: str | None = None,
        action_route_params: dict[str, Any] | None = None,
        correlation_id: str = "",
        producer: str,
        occurred_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> BusinessEvent:
        """Insert one immutable Business Event fact. Never call again to edit a row."""

        if domain not in BUSINESS_EVENT_DOMAINS:
            raise BusinessObservabilityError("business_event_domain_invalid", domain)
        if severity not in SEVERITY_VALUES:
            raise BusinessObservabilityError("business_event_severity_invalid", severity)
        if business_impact not in BUSINESS_IMPACT_VALUES:
            raise BusinessObservabilityError("business_event_impact_invalid", business_impact)
        if primary_scope_type not in SCOPE_TYPES:
            raise BusinessObservabilityError(
                "business_event_scope_type_invalid", primary_scope_type
            )
        if not reason_code:
            raise BusinessObservabilityError("business_event_reason_code_required")
        if not primary_scope_id:
            raise BusinessObservabilityError("business_event_primary_scope_id_required")
        if not producer:
            raise BusinessObservabilityError("business_event_producer_required")

        secondary_rows = [
            {"scope_type": scope_type, "scope_id": scope_id, "scope_label": scope_label}
            for scope_type, scope_id, scope_label in (secondary_scopes or [])
            if scope_type in SCOPE_TYPES and scope_id
        ]

        event = BusinessEvent(
            id=_new_id(),
            domain=domain,
            event_type=event_type,
            severity=severity,
            business_impact=business_impact,
            reason_code=reason_code,
            reason_message=reason_message,
            primary_scope_type=primary_scope_type,
            primary_scope_id=primary_scope_id,
            primary_scope_label=primary_scope_label,
            secondary_scopes_json=secondary_rows,
            recommended_action=recommended_action,
            retryable=retryable,
            action_route_key=action_route_key,
            action_route_params_json=redact_sensitive(action_route_params or {}),
            correlation_id=correlation_id or f"corr_{uuid.uuid4().hex[:12]}",
            producer=producer,
            occurred_at=occurred_at or _utcnow(),
            metadata_json=redact_sensitive(metadata or {}),
        )
        self.db.add(event)
        if commit:
            self.db.commit()
            self.db.refresh(event)
        return event

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def acknowledge(self, event_id: str, *, actor: str, note: str | None = None) -> BusinessEvent:
        return self._transition(event_id, to_status="acknowledged", actor=actor, note=note)

    def resolve(self, event_id: str, *, actor: str, note: str | None = None) -> BusinessEvent:
        return self._transition(event_id, to_status="resolved", actor=actor, note=note)

    def _transition(
        self, event_id: str, *, to_status: str, actor: str, note: str | None
    ) -> BusinessEvent:
        row = self.db.get(BusinessEvent, event_id)
        if row is None:
            raise BusinessObservabilityError("business_event_not_found", event_id)
        current_status, *_ = self._project_state(row)
        assert_valid_transition(current_status, to_status)
        transition = BusinessEventLifecycleTransition(
            business_event_id=row.id,
            from_status=current_status,
            to_status=to_status,
            actor=actor,
            occurred_at=_utcnow(),
            note=note,
        )
        self.db.add(transition)
        self.db.commit()
        self.db.refresh(row)
        return row

    def lifecycle_history(self, event_id: str) -> list[BusinessEventLifecycleTransitionShape]:
        row = self.db.get(BusinessEvent, event_id)
        if row is None:
            raise BusinessObservabilityError("business_event_not_found", event_id)
        return [
            BusinessEventLifecycleTransitionShape(
                id=transition.id,
                fromStatus=transition.from_status,
                toStatus=transition.to_status,
                actor=transition.actor,
                occurredAt=transition.occurred_at,
                note=transition.note,
            )
            for transition in row.lifecycle_transitions
        ]

    @staticmethod
    def _project_state(
        row: BusinessEvent,
    ) -> tuple[str, datetime | None, str | None, datetime | None, str | None]:
        """Current status is never stored; it is projected from the append-only log."""

        status = "open"
        acknowledged_at: datetime | None = None
        acknowledged_by: str | None = None
        resolved_at: datetime | None = None
        resolved_by: str | None = None
        for transition in row.lifecycle_transitions:
            status = transition.to_status
            if transition.to_status == "acknowledged":
                acknowledged_at = transition.occurred_at
                acknowledged_by = transition.actor
            elif transition.to_status == "resolved":
                resolved_at = transition.occurred_at
                resolved_by = transition.actor
        return status, acknowledged_at, acknowledged_by, resolved_at, resolved_by

    # ------------------------------------------------------------------
    # Read model
    # ------------------------------------------------------------------

    def shape(self, row: BusinessEvent) -> BusinessEventShape:
        status, acknowledged_at, acknowledged_by, resolved_at, resolved_by = (
            self._project_state(row)
        )
        secondary = [
            BusinessEventScopeShape(
                scopeType=item.get("scope_type", ""),
                scopeId=item.get("scope_id", ""),
                scopeLabel=item.get("scope_label"),
            )
            for item in (row.secondary_scopes_json or [])
        ]
        return BusinessEventShape(
            id=row.id,
            domain=row.domain,
            eventType=row.event_type,
            severity=row.severity,
            businessImpact=row.business_impact,
            reasonCode=row.reason_code,
            reasonMessage=row.reason_message,
            primaryScope=BusinessEventScopeShape(
                scopeType=row.primary_scope_type,
                scopeId=row.primary_scope_id,
                scopeLabel=row.primary_scope_label,
            ),
            secondaryScopes=secondary,
            recommendedAction=row.recommended_action,
            retryable=row.retryable,
            actionRouteKey=row.action_route_key,
            actionUrl=resolve_action_route(
                row.action_route_key, row.action_route_params_json or {}
            ),
            correlationId=row.correlation_id,
            producer=row.producer,
            occurredAt=row.occurred_at,
            createdAt=row.created_at,
            metadata=row.metadata_json or {},
            status=status,
            acknowledgedAt=acknowledged_at,
            acknowledgedBy=acknowledged_by,
            resolvedAt=resolved_at,
            resolvedBy=resolved_by,
        )

    def list_events(
        self,
        *,
        domain: str | None = None,
        severity: str | None = None,
        business_impact: str | None = None,
        status: str | None = None,
        correlation_id: str | None = None,
        scope_type: str | None = None,
        scope_id: str | None = None,
        since: datetime | None = None,
        limit: int = 200,
    ) -> list[BusinessEventShape]:
        """Return recent events, newest first.

        ``status`` is a projected field, so it is filtered in Python after a
        bounded fetch rather than in SQL. At v1 event volume this is a
        reasonable tradeoff; if event volume grows enough for this to
        matter, a materialized projection table can be added later without
        changing this method's signature.
        """

        query = self.db.query(BusinessEvent)
        if domain:
            query = query.filter(BusinessEvent.domain == domain)
        if severity:
            query = query.filter(BusinessEvent.severity == severity)
        if business_impact:
            query = query.filter(BusinessEvent.business_impact == business_impact)
        if correlation_id:
            query = query.filter(BusinessEvent.correlation_id == correlation_id)
        if scope_type:
            query = query.filter(BusinessEvent.primary_scope_type == scope_type)
        if scope_id:
            query = query.filter(BusinessEvent.primary_scope_id == scope_id)
        if since:
            query = query.filter(BusinessEvent.occurred_at >= since)
        fetch_limit = limit if not status else max(limit * 4, limit)
        rows = query.order_by(BusinessEvent.occurred_at.desc(), BusinessEvent.id.desc()).limit(
            fetch_limit
        ).all()
        shapes = [self.shape(row) for row in rows]
        if status:
            shapes = [shape for shape in shapes if shape.status == status]
        return shapes[:limit]

    def get_event(self, event_id: str) -> BusinessEventShape:
        row = self.db.get(BusinessEvent, event_id)
        if row is None:
            raise BusinessObservabilityError("business_event_not_found", event_id)
        return self.shape(row)

    # ------------------------------------------------------------------
    # KPIs (Owner-approved set: blocking events by domain, Write Pipeline
    # 30-day rolling partial-failure rate, oldest unresolved blocking age)
    # ------------------------------------------------------------------

    def kpis(self, *, now: datetime | None = None) -> BusinessEventKpiShape:
        current = now or _utcnow()
        window_start = current - timedelta(days=30)

        open_blocking_by_domain: dict[str, int] = dict.fromkeys(BUSINESS_EVENT_DOMAINS, 0)
        oldest_unresolved_at: datetime | None = None
        for row in self.db.query(BusinessEvent).filter(
            BusinessEvent.business_impact.in_(BLOCKING_IMPACTS)
        ):
            status, *_ = self._project_state(row)
            if status == "resolved":
                continue
            open_blocking_by_domain[row.domain] = open_blocking_by_domain.get(row.domain, 0) + 1
            if oldest_unresolved_at is None or row.occurred_at < oldest_unresolved_at:
                oldest_unresolved_at = row.occurred_at

        total_batches = (
            self.db.query(func.count(BusinessEvent.id))
            .filter(
                BusinessEvent.domain == "write_pipeline",
                BusinessEvent.event_type.in_(WRITE_PIPELINE_BATCH_OUTCOME_EVENT_TYPES),
                BusinessEvent.occurred_at >= window_start,
            )
            .scalar()
            or 0
        )
        non_full_success_batches = (
            self.db.query(func.count(BusinessEvent.id))
            .filter(
                BusinessEvent.domain == "write_pipeline",
                BusinessEvent.event_type.in_(WRITE_PIPELINE_NON_FULL_SUCCESS_EVENT_TYPES),
                BusinessEvent.occurred_at >= window_start,
            )
            .scalar()
            or 0
        )
        partial_failure_rate = (
            float(non_full_success_batches) / float(total_batches) if total_batches else 0.0
        )

        oldest_age_seconds = (
            (current - oldest_unresolved_at).total_seconds() if oldest_unresolved_at else None
        )

        return BusinessEventKpiShape(
            openBlockingByDomain=open_blocking_by_domain,
            writePipelinePartialFailureRate30d=partial_failure_rate,
            oldestUnresolvedBlockingEventAgeSeconds=oldest_age_seconds,
        )
