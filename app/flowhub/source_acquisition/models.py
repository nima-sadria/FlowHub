"""Append-safe persistence for Source Acquisition Run lifecycle state."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
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
