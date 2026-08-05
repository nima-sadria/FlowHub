"""Append-safe persistence for Source Acquisition Run lifecycle state."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    event,
    inspect,
    text,
)
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from app.flowhub.database import FlowHubBase
from app.flowhub.unified_workspace.domain import ImmutableRecordError, utcnow


ACTIVE_RUN_STATUSES = ("queued", "running")
TERMINAL_RUN_STATUSES = ("succeeded", "failed", "cancelled", "abandoned")


class AcquisitionRun(FlowHubBase):
    """One requested Source read, without any provider execution implementation."""

    __tablename__ = "saq_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled','abandoned')",
            name="ck_saq_run_status",
        ),
        CheckConstraint(
            "result IN ('observed','not_modified','content_unchanged_reparse','none')",
            name="ck_saq_run_result",
        ),
        CheckConstraint(
            "(status IN ('queued','running') AND result = 'none') "
            "OR (status = 'succeeded' AND result IN "
            "('observed','not_modified','content_unchanged_reparse')) "
            "OR (status IN ('failed','cancelled','abandoned') AND result = 'none')",
            name="ck_saq_run_status_result",
        ),
        CheckConstraint("attempt_number > 0", name="ck_saq_run_attempt_number"),
        CheckConstraint(
            "(status IN ('queued','running') AND terminal_at IS NULL) "
            "OR (status IN ('succeeded','failed','cancelled','abandoned') "
            "AND terminal_at IS NOT NULL)",
            name="ck_saq_run_terminal_timestamp",
        ),
        Index("ix_saq_runs_source_scope_status", "source_id", "resource_scope", "status"),
        Index("ix_saq_runs_correlation_id", "correlation_id"),
        Index("ix_saq_runs_lease_expiry", "lease_expires_at"),
        Index(
            "uq_saq_runs_idempotency_scope",
            "source_id",
            "resource_scope",
            "idempotency_key",
            unique=True,
            sqlite_where=text("idempotency_key IS NOT NULL"),
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index(
            "uq_saq_runs_active_scope",
            "source_id",
            "resource_scope",
            unique=True,
            sqlite_where=text("status IN ('queued','running')"),
            postgresql_where=text("status IN ('queued','running')"),
        ),
        Index("uq_saq_runs_root_attempt", "root_run_id", "attempt_number", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("sc_sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    resource_scope: Mapped[str] = mapped_column(String(240), nullable=False, default="source")
    trigger_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(240), nullable=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(120), nullable=False)
    parent_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("saq_runs.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    root_run_id: Mapped[str] = mapped_column(
        ForeignKey("saq_runs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", index=True)
    result: Mapped[str] = mapped_column(String(40), nullable=False, default="none")
    queued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancellation_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancellation_requested_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=True
    )
    worker_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


def _reject_terminal_mutation(
    _mapper: Mapper[Any], _connection: Connection, target: AcquisitionRun
) -> None:
    state = inspect(target)
    status_history = state.attrs.status.history
    previous_status = status_history.deleted[0] if status_history.deleted else target.status
    if previous_status in TERMINAL_RUN_STATUSES:
        raise ImmutableRecordError("Terminal AcquisitionRun records are immutable.")


def _reject_run_delete(
    _mapper: Mapper[Any], _connection: Connection, _target: AcquisitionRun
) -> None:
    raise ImmutableRecordError("AcquisitionRun records are append-safe and cannot be deleted.")


event.listen(AcquisitionRun, "before_update", _reject_terminal_mutation)
event.listen(AcquisitionRun, "before_delete", _reject_run_delete)


class SourceObservationVersionHead(FlowHubBase):
    """Mutable allocator; immutable Observations never calculate their own version."""

    __tablename__ = "saq_observation_version_heads"

    source_id: Mapped[str] = mapped_column(
        ForeignKey("sc_sources.id", ondelete="RESTRICT"), primary_key=True
    )
    resource_scope: Mapped[str] = mapped_column(String(240), primary_key=True)
    next_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class SourceObservation(FlowHubBase):
    """Immutable provider-neutral fact recorded for one successful Acquisition Run."""

    __tablename__ = "saq_observations"
    __table_args__ = (
        CheckConstraint("observation_version > 0", name="ck_saq_observation_version"),
        UniqueConstraint("acquisition_run_id", name="uq_saq_observation_run"),
        UniqueConstraint(
            "source_id",
            "resource_scope",
            "observation_version",
            name="uq_saq_observation_scope_version",
        ),
        UniqueConstraint("checksum", name="uq_saq_observation_checksum"),
        Index("ix_saq_observations_source_scope_observed", "source_id", "resource_scope", "observed_at"),
        Index("ix_saq_observations_resource_identity_hash", "resource_identity_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    acquisition_run_id: Mapped[str] = mapped_column(
        ForeignKey("saq_runs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("sc_sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    resource_scope: Mapped[str] = mapped_column(String(240), nullable=False)
    resource_identity: Mapped[str] = mapped_column(String(240), nullable=False)
    resource_identity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    observation_version: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class SourceObservationEvidence(FlowHubBase):
    """Append-only evidence chain for one immutable Observation."""

    __tablename__ = "saq_observation_evidence"
    __table_args__ = (
        CheckConstraint("sequence_number > 0", name="ck_saq_evidence_sequence"),
        UniqueConstraint("observation_id", "sequence_number", name="uq_saq_evidence_sequence"),
        Index("ix_saq_evidence_observation_recorded", "observation_id", "recorded_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    observation_id: Mapped[str] = mapped_column(
        ForeignKey("saq_observations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_kind: Mapped[str] = mapped_column(String(80), nullable=False)
    evidence_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    previous_evidence_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class SourceObservationSnapshotReference(FlowHubBase):
    """Append-only reference to a snapshot without coupling this phase to Workspace creation."""

    __tablename__ = "saq_observation_snapshot_references"
    __table_args__ = (
        UniqueConstraint(
            "observation_id",
            "snapshot_kind",
            "snapshot_reference",
            name="uq_saq_observation_snapshot_reference",
        ),
        Index("ix_saq_snapshot_reference_observation", "observation_id", "linked_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    observation_id: Mapped[str] = mapped_column(
        ForeignKey("saq_observations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    snapshot_kind: Mapped[str] = mapped_column(String(80), nullable=False)
    snapshot_reference: Mapped[str] = mapped_column(String(240), nullable=False)
    snapshot_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    linked_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


_APPEND_ONLY_OBSERVATION_MODELS = (
    SourceObservation,
    SourceObservationEvidence,
    SourceObservationSnapshotReference,
)


def _reject_append_only_mutation(
    _mapper: Mapper[Any], _connection: Connection, target: Any
) -> None:
    raise ImmutableRecordError(f"{target.__class__.__name__} records are append-only.")


for _model in _APPEND_ONLY_OBSERVATION_MODELS:
    event.listen(_model, "before_update", _reject_append_only_mutation)
    event.listen(_model, "before_delete", _reject_append_only_mutation)
