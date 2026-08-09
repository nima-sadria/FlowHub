"""FlowHub Business Observability v1 ORM models.

``BusinessEvent`` is the immutable fact record: producers insert it once,
when the outcome is known, and it is never updated or deleted afterwards.

``BusinessEventLifecycleTransition`` is the append-only lifecycle log.
Acknowledge/resolve actions append a transition row here; they never touch
the fact row. Current effective status is a read-time projection over the
latest transition per event (``BusinessObservabilityService``), not a
second mutable source of truth.

Both models enforce their append-only contract at the ORM layer via
``before_update``/``before_delete`` listeners, mirroring the pattern
already used for ``AcquisitionRun`` and the ``_APPEND_ONLY_OBSERVATION_MODELS``
in ``app/flowhub/source_acquisition/models.py``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    event,
)
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, Mapper, mapped_column, relationship

from app.flowhub.database import FlowHubBase
from app.flowhub.unified_workspace.domain import ImmutableRecordError


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class BusinessEvent(FlowHubBase):
    """Immutable, insert-only Business Event fact."""

    __tablename__ = "bo_business_events"
    __table_args__ = (
        CheckConstraint(
            "domain IN ('source_acquisition','pricing','channels','write_pipeline')",
            name="ck_bo_event_domain",
        ),
        CheckConstraint("event_type != ''", name="ck_bo_event_type_nonempty"),
        CheckConstraint(
            "severity IN ('info','warning','degraded','error','critical')",
            name="ck_bo_event_severity",
        ),
        CheckConstraint(
            "business_impact IN ('none','degraded','blocking','partial_failure',"
            "'critical_business_failure')",
            name="ck_bo_event_business_impact",
        ),
        CheckConstraint("reason_code != ''", name="ck_bo_event_reason_code_nonempty"),
        CheckConstraint(
            "primary_scope_type IN ('source','worksheet','workspace','product','revision',"
            "'pricing_run','review','changeset','channel','order','connector','batch')",
            name="ck_bo_event_primary_scope_type",
        ),
        CheckConstraint("primary_scope_id != ''", name="ck_bo_event_primary_scope_id_nonempty"),
        CheckConstraint("producer != ''", name="ck_bo_event_producer_nonempty"),
        Index("ix_bo_events_domain", "domain"),
        Index("ix_bo_events_event_type", "event_type"),
        Index("ix_bo_events_correlation_id", "correlation_id"),
        Index("ix_bo_events_occurred_at", "occurred_at"),
        Index("ix_bo_events_primary_scope", "primary_scope_type", "primary_scope_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    domain: Mapped[str] = mapped_column(String(40), nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    business_impact: Mapped[str] = mapped_column(String(30), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(120), nullable=False)
    reason_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    primary_scope_type: Mapped[str] = mapped_column(String(40), nullable=False)
    primary_scope_id: Mapped[str] = mapped_column(String(160), nullable=False)
    primary_scope_label: Mapped[str | None] = mapped_column(String(240), nullable=True)
    secondary_scopes_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False, default="")
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    action_route_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    action_route_params_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    correlation_id: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    producer: Mapped[str] = mapped_column(String(120), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    lifecycle_transitions: Mapped[list[BusinessEventLifecycleTransition]] = relationship(
        "BusinessEventLifecycleTransition",
        back_populates="business_event",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="BusinessEventLifecycleTransition.id",
    )


class BusinessEventLifecycleTransition(FlowHubBase):
    """Append-only lifecycle state change: OPEN -> ACKNOWLEDGED -> RESOLVED."""

    __tablename__ = "bo_business_event_lifecycle_transitions"
    __table_args__ = (
        CheckConstraint(
            "from_status IS NULL OR from_status IN ('open','acknowledged','resolved')",
            name="ck_bo_transition_from_status",
        ),
        CheckConstraint(
            "to_status IN ('open','acknowledged','resolved')",
            name="ck_bo_transition_to_status",
        ),
        CheckConstraint("actor != ''", name="ck_bo_transition_actor_nonempty"),
        Index("ix_bo_transitions_event", "business_event_id"),
        Index("ix_bo_transitions_event_occurred", "business_event_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_event_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("bo_business_events.id", ondelete="RESTRICT"),
        nullable=False,
    )
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    actor: Mapped[str] = mapped_column(String(160), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    business_event: Mapped[BusinessEvent] = relationship(
        "BusinessEvent", back_populates="lifecycle_transitions"
    )


def _reject_business_event_mutation(
    _mapper: Mapper[Any], _connection: Connection, _target: BusinessEvent
) -> None:
    raise ImmutableRecordError("BusinessEvent records are immutable and cannot be updated.")


def _reject_business_event_delete(
    _mapper: Mapper[Any], _connection: Connection, _target: BusinessEvent
) -> None:
    raise ImmutableRecordError("BusinessEvent records are immutable and cannot be deleted.")


def _reject_transition_mutation(
    _mapper: Mapper[Any], _connection: Connection, _target: BusinessEventLifecycleTransition
) -> None:
    raise ImmutableRecordError(
        "BusinessEventLifecycleTransition records are append-only and cannot be updated."
    )


def _reject_transition_delete(
    _mapper: Mapper[Any], _connection: Connection, _target: BusinessEventLifecycleTransition
) -> None:
    raise ImmutableRecordError(
        "BusinessEventLifecycleTransition records are append-only and cannot be deleted."
    )


event.listen(BusinessEvent, "before_update", _reject_business_event_mutation)
event.listen(BusinessEvent, "before_delete", _reject_business_event_delete)
event.listen(BusinessEventLifecycleTransition, "before_update", _reject_transition_mutation)
event.listen(BusinessEventLifecycleTransition, "before_delete", _reject_transition_delete)
