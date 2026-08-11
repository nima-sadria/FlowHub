"""Transactional Source Acquisition Run lifecycle service.

This module intentionally owns only durable command state. Provider reads,
observations, scheduling, and diagnostics are later phases.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.flowhub.business_observability.service import BusinessObservabilityService
from app.flowhub.source_acquisition.errors import SourceAcquisitionError
from app.flowhub.source_acquisition.models import (
    ACTIVE_RUN_STATUSES,
    TERMINAL_RUN_STATUSES,
    AcquisitionRun,
)
from app.flowhub.source_workspace.models import SourceProfile
from app.flowhub.unified_workspace.domain import checksum, utcnow


RUN_RESULTS = {"observed", "not_modified", "content_unchanged_reparse"}
RETRYABLE_STATUSES = {"failed", "cancelled", "abandoned"}
TRIGGER_KINDS = {"manual", "retry", "scheduled", "system", "webhook"}
MAX_LEASE_SECONDS = 3600
_FAILURE_CODE = re.compile(r"^[a-z][a-z0-9_]{0,119}$")


class SourceAcquisitionService:
    """Coordinates durable Run state using the database as the authority.

    Timestamps come from the common UTC application clock. A future worker must
    use the same clock source for lease acquisition and renewal.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def request_run(
        self,
        *,
        source_id: str,
        trigger_kind: str,
        resource_scope: str = "source",
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
        actor_user_id: int | None = None,
        request_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create one queued Run or replay the exact retained idempotent Run.

        Idempotency keys are Unicode-normalized, whitespace-trimmed opaque
        identifiers. They are retained for the lifetime of the Run in this
        phase, so replay remains stable until retention is implemented.
        """

        return self._request(
            source_id=source_id,
            trigger_kind=trigger_kind,
            resource_scope=resource_scope,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            actor_user_id=actor_user_id,
            request_payload=request_payload,
            parent=None,
        )

    def start_run(
        self, run_id: str, *, worker_id: str, lease_seconds: int, now: datetime | None = None
    ) -> dict[str, Any]:
        now = now or utcnow()
        lease_seconds = self._lease_seconds(lease_seconds)
        row = self._locked_run(run_id)
        if row.status != "queued":
            raise SourceAcquisitionError("invalid_run_transition")
        row.status = "running"
        row.started_at = now
        row.worker_id = self._worker_id(worker_id)
        row.lease_expires_at = now + timedelta(seconds=lease_seconds)
        row.updated_at = now
        self.db.commit()
        return self._shape(row)

    def heartbeat(
        self, run_id: str, *, worker_id: str, lease_seconds: int, now: datetime | None = None
    ) -> dict[str, Any]:
        now = now or utcnow()
        row = self._locked_run(run_id)
        self._assert_worker_lease(row, worker_id, now)
        row.lease_expires_at = now + timedelta(seconds=self._lease_seconds(lease_seconds))
        row.updated_at = now
        self.db.commit()
        return self._shape(row)

    def succeed_run(
        self, run_id: str, *, worker_id: str, result: str, now: datetime | None = None
    ) -> dict[str, Any]:
        if result not in RUN_RESULTS:
            raise SourceAcquisitionError("invalid_run_result")
        return self._terminal_by_worker(
            run_id,
            worker_id=worker_id,
            status="succeeded",
            result=result,
            failure_code=None,
            now=now,
        )

    def complete_with_observation(
        self,
        run_id: str,
        *,
        worker_id: str,
        result: str,
        resource_identity: str,
        provenance: dict[str, Any],
        evidence: list[dict[str, Any]],
        snapshot_references: list[dict[str, Any]] | None = None,
        observed_at: datetime | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Atomically persist an Observation and complete its running Run.

        Cancellation wins when requested before the locked completion boundary.
        The Observation graph and terminal Run transition share one commit, so
        neither can become authoritative without the other.
        """

        if result not in {"observed", "content_unchanged_reparse"}:
            raise SourceAcquisitionError("invalid_run_result")
        now = now or utcnow()
        row = self._locked_run(run_id)
        self._assert_worker_lease(row, worker_id, now)
        if row.cancellation_requested_at is not None:
            self._set_terminal(row, status="cancelled", result="none", now=now)
            self.db.commit()
            return {"run": self._shape(row), "observation": None}

        from app.flowhub.source_acquisition.observations import SourceObservationService

        try:
            observation = SourceObservationService(self.db)._stage_observation(
                run=row,
                resource_identity=resource_identity,
                provenance=provenance,
                evidence=evidence,
                snapshot_references=snapshot_references,
                observed_at=observed_at or now,
            )
            self._set_terminal(row, status="succeeded", result=result, now=now)
            row.failure_code = None
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return {
            "run": self._shape(row),
            "observation": SourceObservationService(self.db).observation(observation.id),
        }

    def fail_run(
        self, run_id: str, *, worker_id: str, failure_code: str, now: datetime | None = None
    ) -> dict[str, Any]:
        return self._terminal_by_worker(
            run_id,
            worker_id=worker_id,
            status="failed",
            result="none",
            failure_code=self._failure_code(failure_code),
            now=now,
        )

    def request_cancellation(
        self, run_id: str, *, requester_user_id: int | None, now: datetime | None = None
    ) -> dict[str, Any]:
        """Request cancellation; running work acknowledges it at a safe boundary."""

        now = now or utcnow()
        row = self._locked_run(run_id)
        if row.status == "cancelled":
            return self._shape(row)
        if row.status in TERMINAL_RUN_STATUSES:
            raise SourceAcquisitionError("run_not_cancellable")
        if row.status == "queued":
            self._set_terminal(row, status="cancelled", result="none", now=now)
            row.cancellation_requested_at = now
            row.cancellation_requested_by_user_id = requester_user_id
        else:
            if row.cancellation_requested_at is None:
                row.cancellation_requested_at = now
                row.cancellation_requested_by_user_id = requester_user_id
                row.updated_at = now
        self.db.commit()
        return self._shape(row)

    def acknowledge_cancellation(
        self, run_id: str, *, worker_id: str, now: datetime | None = None
    ) -> dict[str, Any]:
        now = now or utcnow()
        row = self._locked_run(run_id)
        self._assert_worker_lease(row, worker_id, now)
        if row.cancellation_requested_at is None:
            raise SourceAcquisitionError("run_not_cancellable")
        self._set_terminal(row, status="cancelled", result="none", now=now)
        self.db.commit()
        return self._shape(row)

    def abandon_expired_runs(self, *, now: datetime | None = None) -> int:
        """Durably classify lost worker leases without attributing fault to the Source."""

        now = now or utcnow()
        rows = (
            self.db.query(AcquisitionRun)
            .filter(
                AcquisitionRun.status == "running",
                AcquisitionRun.lease_expires_at.is_not(None),
                AcquisitionRun.lease_expires_at <= now,
            )
            .with_for_update()
            .all()
        )
        for row in rows:
            self._set_terminal(row, status="abandoned", result="none", now=now)
            row.failure_code = "worker_lease_expired"
        if rows:
            self.db.commit()
        return len(rows)

    def retry_run(
        self,
        run_id: str,
        *,
        idempotency_key: str | None,
        correlation_id: str | None = None,
        actor_user_id: int | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        parent = self._locked_run(run_id)
        if parent.status in ACTIVE_RUN_STATUSES:
            raise SourceAcquisitionError("run_not_retryable")
        if parent.status not in RETRYABLE_STATUSES:
            raise SourceAcquisitionError("run_not_retryable")
        return self._request(
            source_id=parent.source_id,
            trigger_kind="retry",
            resource_scope=parent.resource_scope,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            actor_user_id=actor_user_id,
            request_payload={"retry_of_run_id": parent.id},
            parent=parent,
            now=now,
        )

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self._shape(self._run_or_error(run_id))

    def _request(
        self,
        *,
        source_id: str,
        trigger_kind: str,
        resource_scope: str,
        idempotency_key: str | None,
        correlation_id: str | None,
        actor_user_id: int | None,
        request_payload: dict[str, Any] | None,
        parent: AcquisitionRun | None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        # Serialize new reads with Source lifecycle changes. A concurrent
        # archive/delete holds the same row lock and wins before this request
        # can decide whether new processing is allowed.
        source = (
            self.db.query(SourceProfile)
            .filter(SourceProfile.id == source_id)
            .with_for_update()
            .one_or_none()
        )
        if source is None:
            raise SourceAcquisitionError("source_not_found")
        if source.status != "active":
            raise SourceAcquisitionError("source_archived")
        trigger_kind = self._trigger_kind(trigger_kind)
        resource_scope = self._opaque(resource_scope, "resource_scope")
        idempotency_key = self._optional_opaque(idempotency_key, "idempotency_key")
        intent = {
            "trigger_kind": trigger_kind,
            "resource_scope": resource_scope,
            "parent_run_id": parent.id if parent else None,
            "request_payload": request_payload or {},
        }
        request_fingerprint = checksum(intent)
        if idempotency_key:
            existing = (
                self.db.query(AcquisitionRun)
                .filter(
                    AcquisitionRun.source_id == source_id,
                    AcquisitionRun.resource_scope == resource_scope,
                    AcquisitionRun.idempotency_key == idempotency_key,
                )
                .one_or_none()
            )
            if existing is not None:
                if existing.request_fingerprint != request_fingerprint:
                    raise SourceAcquisitionError("idempotency_key_conflict")
                return self._shape(existing)
        active = self._active_run(source_id, resource_scope)
        if active is not None:
            raise SourceAcquisitionError("active_run_conflict")

        now = now or utcnow()
        row_id = str(uuid.uuid4())
        root_run_id = parent.root_run_id if parent else row_id
        attempt_number = 1
        if parent is not None:
            attempt_number = (
                int(
                    self.db.query(func.max(AcquisitionRun.attempt_number))
                    .filter(AcquisitionRun.root_run_id == root_run_id)
                    .scalar()
                    or 0
                )
                + 1
            )
        row = AcquisitionRun(
            id=row_id,
            source_id=source_id,
            resource_scope=resource_scope,
            trigger_kind=trigger_kind,
            actor_user_id=actor_user_id,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            correlation_id=self._optional_opaque(correlation_id, "correlation_id") or row_id,
            parent_run_id=parent.id if parent else None,
            root_run_id=root_run_id,
            attempt_number=attempt_number,
            status="queued",
            result="none",
            queued_at=now,
            created_at=now,
            updated_at=now,
        )
        try:
            self.db.add(row)
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            return self._resolve_create_conflict(
                source_id=source_id,
                resource_scope=resource_scope,
                idempotency_key=idempotency_key,
                request_fingerprint=request_fingerprint,
            )
        return self._shape(row)

    def _resolve_create_conflict(
        self,
        *,
        source_id: str,
        resource_scope: str,
        idempotency_key: str | None,
        request_fingerprint: str,
    ) -> dict[str, Any]:
        if idempotency_key:
            existing = (
                self.db.query(AcquisitionRun)
                .filter(
                    AcquisitionRun.source_id == source_id,
                    AcquisitionRun.resource_scope == resource_scope,
                    AcquisitionRun.idempotency_key == idempotency_key,
                )
                .one_or_none()
            )
            if existing is not None:
                if existing.request_fingerprint != request_fingerprint:
                    raise SourceAcquisitionError("idempotency_key_conflict")
                return self._shape(existing)
        if self._active_run(source_id, resource_scope) is not None:
            raise SourceAcquisitionError("active_run_conflict")
        raise SourceAcquisitionError("acquisition_run_create_conflict")

    def _terminal_by_worker(
        self,
        run_id: str,
        *,
        worker_id: str,
        status: str,
        result: str,
        failure_code: str | None,
        now: datetime | None,
    ) -> dict[str, Any]:
        now = now or utcnow()
        row = self._locked_run(run_id)
        self._assert_worker_lease(row, worker_id, now)
        if row.cancellation_requested_at is not None:
            raise SourceAcquisitionError("cancellation_requested")
        self._set_terminal(row, status=status, result=result, now=now)
        row.failure_code = failure_code
        if status == "failed":
            self._emit_run_failed_business_event(row, reason_code=failure_code or "unknown")
        self.db.commit()
        return self._shape(row)

    def _set_terminal(self, row: AcquisitionRun, *, status: str, result: str, now: datetime) -> None:
        if row.status in TERMINAL_RUN_STATUSES:
            raise SourceAcquisitionError("terminal_run_immutable")
        row.status = status
        row.result = result
        row.terminal_at = now
        row.lease_expires_at = None
        row.updated_at = now

    def _assert_worker_lease(self, row: AcquisitionRun, worker_id: str, now: datetime) -> None:
        if row.status != "running":
            raise SourceAcquisitionError("invalid_run_transition")
        if row.lease_expires_at is None or row.lease_expires_at <= now:
            self._set_terminal(row, status="abandoned", result="none", now=now)
            row.failure_code = "worker_lease_expired"
            self._emit_run_abandoned_business_event(row)
            self.db.commit()
            raise SourceAcquisitionError("lease_expired")
        if row.worker_id != self._worker_id(worker_id):
            raise SourceAcquisitionError("worker_ownership_conflict")

    # Source Acquisition domain producer (Business Observability v1, Phase 2).
    # Hooked at the two points a Run reaches a non-success terminal state:
    # an explicit worker-reported failure, and a lease expiring before the
    # worker finished (a stalled/crashed worker). Successful and cancelled
    # runs are intentionally not reported - Business Observability surfaces
    # what needs operator attention, not a full run history.

    def _emit_run_failed_business_event(self, row: AcquisitionRun, *, reason_code: str) -> None:
        BusinessObservabilityService(self.db).emit_event(
            domain="source_acquisition",
            event_type="source_read_failed",
            severity="error",
            business_impact="degraded",
            reason_code=reason_code,
            reason_message=f"Source read failed: {reason_code}",
            primary_scope_type="source",
            primary_scope_id=row.source_id,
            secondary_scopes=[("batch", row.id, None)],
            recommended_action="Review the source connection and retry the read.",
            retryable=True,
            action_route_key="source.detail",
            action_route_params={"source_id": row.source_id},
            correlation_id=row.correlation_id,
            producer="source_acquisition.service._terminal_by_worker",
            commit=False,
        )

    def _emit_run_abandoned_business_event(self, row: AcquisitionRun) -> None:
        BusinessObservabilityService(self.db).emit_event(
            domain="source_acquisition",
            event_type="source_run_abandoned",
            severity="error",
            business_impact="degraded",
            reason_code="worker_lease_expired",
            reason_message="Source read abandoned: worker lease expired before completion.",
            primary_scope_type="source",
            primary_scope_id=row.source_id,
            secondary_scopes=[("batch", row.id, None)],
            recommended_action="Review the source connection and retry the read.",
            retryable=True,
            action_route_key="source.detail",
            action_route_params={"source_id": row.source_id},
            correlation_id=row.correlation_id,
            producer="source_acquisition.service._assert_worker_lease",
            commit=False,
        )

    def _locked_run(self, run_id: str) -> AcquisitionRun:
        row = self.db.query(AcquisitionRun).filter(AcquisitionRun.id == run_id).with_for_update().one_or_none()
        if row is None:
            raise SourceAcquisitionError("run_not_found")
        return row

    def _run_or_error(self, run_id: str) -> AcquisitionRun:
        row = self.db.get(AcquisitionRun, run_id)
        if row is None:
            raise SourceAcquisitionError("run_not_found")
        return row

    def _active_run(self, source_id: str, resource_scope: str) -> AcquisitionRun | None:
        return (
            self.db.query(AcquisitionRun)
            .filter(
                AcquisitionRun.source_id == source_id,
                AcquisitionRun.resource_scope == resource_scope,
                AcquisitionRun.status.in_(ACTIVE_RUN_STATUSES),
            )
            .one_or_none()
        )

    @staticmethod
    def _trigger_kind(value: str) -> str:
        normalized = str(value).strip().lower()
        if normalized not in TRIGGER_KINDS:
            raise SourceAcquisitionError("trigger_kind_invalid")
        return normalized

    @staticmethod
    def _lease_seconds(value: int) -> int:
        try:
            seconds = int(value)
        except (TypeError, ValueError) as exc:
            raise SourceAcquisitionError("lease_duration_invalid") from exc
        if not 1 <= seconds <= MAX_LEASE_SECONDS:
            raise SourceAcquisitionError("lease_duration_invalid")
        return seconds

    @staticmethod
    def _failure_code(value: str) -> str:
        normalized = str(value).strip().lower()
        if not _FAILURE_CODE.fullmatch(normalized):
            raise SourceAcquisitionError("failure_code_invalid")
        return normalized

    @staticmethod
    def _opaque(value: str, field: str) -> str:
        normalized = unicodedata.normalize("NFKC", str(value)).strip()
        if not normalized or len(normalized) > 240:
            raise SourceAcquisitionError(f"{field}_invalid")
        return normalized

    @classmethod
    def _optional_opaque(cls, value: str | None, field: str) -> str | None:
        return cls._opaque(value, field) if value is not None else None

    @staticmethod
    def _worker_id(value: str) -> str:
        normalized = str(value).strip()
        if not normalized or len(normalized) > 120:
            raise SourceAcquisitionError("worker_id_invalid")
        return normalized

    @staticmethod
    def _shape(row: AcquisitionRun) -> dict[str, Any]:
        return {
            "id": row.id,
            "sourceId": row.source_id,
            "resourceScope": row.resource_scope,
            "triggerKind": row.trigger_kind,
            "actorUserId": row.actor_user_id,
            "idempotencyKey": row.idempotency_key,
            "correlationId": row.correlation_id,
            "parentRunId": row.parent_run_id,
            "rootRunId": row.root_run_id,
            "attemptNumber": row.attempt_number,
            "status": row.status,
            "result": row.result,
            "queuedAt": row.queued_at,
            "startedAt": row.started_at,
            "terminalAt": row.terminal_at,
            "cancellationRequestedAt": row.cancellation_requested_at,
            "cancellationRequestedByUserId": row.cancellation_requested_by_user_id,
            "workerId": row.worker_id,
            "leaseExpiresAt": row.lease_expires_at,
            "failureCode": row.failure_code,
            "createdAt": row.created_at,
            "updatedAt": row.updated_at,
        }
