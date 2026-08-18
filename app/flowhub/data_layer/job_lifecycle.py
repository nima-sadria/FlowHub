"""Durable, provider-neutral lifecycle ownership for data-layer jobs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.flowhub.data_layer.models import DlRefreshJob
from app.flowhub.integration_platform.models import IntegrationConnectorEvent


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class RefreshJobLifecycle:
    """Owns leases for every durable ``DlRefreshJob`` consumer.

    Recovery changes only run metadata. It never repeats provider I/O or
    removes already-committed cache/source rows.
    """

    _POLICY_SECONDS = {
        "products:initial_full_read": 1_800,
        "products:modified_since": 900,
        "products:metadata_filter": 600,
        "products:default": 900,
        "source:default": 1_800,
        "destination:default": 1_800,
        "connectors:default": 600,
    }

    def __init__(self, db: Session) -> None:
        self.db = db

    def lease_seconds(self, job: DlRefreshJob) -> int:
        strategy = str((job.meta or {}).get("strategy") or "default")
        return self._POLICY_SECONDS.get(
            f"{job.entity_type}:{strategy}",
            self._POLICY_SECONDS.get(f"{job.entity_type}:default", 900),
        )

    def start(self, job: DlRefreshJob, *, now: datetime | None = None) -> None:
        now = now or utcnow()
        active = (
            self.db.query(DlRefreshJob)
            .filter(
                DlRefreshJob.id != job.id,
                DlRefreshJob.connector_id == job.connector_id,
                DlRefreshJob.entity_type == job.entity_type,
                DlRefreshJob.status == "running",
                DlRefreshJob.lease_expires_at.is_not(None),
                DlRefreshJob.lease_expires_at > now,
            )
            .with_for_update()
            .first()
        )
        if active is not None:
            job.status = "cancelled"
            job.completed_at = now
            job.error_message = f"An active refresh job ({active.id}) already owns this channel."
            self.db.commit()
            raise RefreshJobAlreadyRunning(active.id)
        job.status = "running"
        job.started_at = job.started_at or now
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=self.lease_seconds(job))
        job.recovery_reason = None
        self.db.commit()

    def heartbeat(
        self, job: DlRefreshJob, *, now: datetime | None = None, commit: bool = True
    ) -> None:
        now = now or utcnow()
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=self.lease_seconds(job))
        if commit:
            self.db.commit()

    def finish(
        self,
        job: DlRefreshJob,
        status: str = "completed",
        *,
        now: datetime | None = None,
        commit: bool = True,
    ) -> None:
        now = now or utcnow()
        job.status = status
        job.completed_at = now
        job.heartbeat_at = now
        job.lease_expires_at = None
        job.recovery_reason = None
        if job.started_at:
            job.duration_ms = (now - job.started_at).total_seconds() * 1000
        if commit:
            self.db.commit()

    def recover_expired(self, *, now: datetime | None = None, limit: int = 100) -> list[DlRefreshJob]:
        now = now or utcnow()
        candidates = (
            self.db.query(DlRefreshJob)
            .filter(DlRefreshJob.status == "running")
            .order_by(DlRefreshJob.started_at.asc(), DlRefreshJob.id.asc())
            .limit(limit)
            .with_for_update()
            .all()
        )
        rows = [job for job in candidates if self.is_expired(job, now)]
        for job in rows:
            job.status = "failed"
            job.completed_at = now
            job.lease_expires_at = None
            job.recovery_reason = "execution_lease_expired"
            job.error_message = "Completion was not durably recorded before the execution lease expired."
            if job.started_at:
                job.duration_ms = (now - job.started_at).total_seconds() * 1000
            if job.connector_id:
                self.db.add(
                    IntegrationConnectorEvent(
                        connector_id=job.connector_id,
                        event_name="job_recovery_marked",
                        severity="warning",
                        message="A durable refresh job was marked stale after its execution lease expired.",
                        metadata_json={
                            "job_id": job.id,
                            "entity_type": job.entity_type,
                            "recovery_reason": job.recovery_reason,
                            "provider_io_retried": False,
                            "business_data_changed": False,
                        },
                    )
                )
        if rows:
            self.db.commit()
        return rows

    def is_expired(self, job: DlRefreshJob, now: datetime) -> bool:
        """Has this job outlived the execution window its policy allows?

        Also covers pre-migration RUNNING rows that have no lease evidence, and
        PENDING rows nothing ever leased. Read-only consumers (Diagnostics)
        share this single definition so "abandoned" means the same thing to the
        recovery path and to the projection.
        """

        if job.lease_expires_at is not None:
            return job.lease_expires_at < now
        last_evidence = job.heartbeat_at or job.started_at or job.created_at
        if last_evidence is None:
            return True
        return last_evidence + timedelta(seconds=self.lease_seconds(job)) < now


class RefreshJobAlreadyRunning(RuntimeError):
    """Raised when an unexpired durable job already owns a channel refresh."""

    def __init__(self, active_job_id: int) -> None:
        self.active_job_id = active_job_id
        super().__init__(f"Refresh job {active_job_id} is already running.")
