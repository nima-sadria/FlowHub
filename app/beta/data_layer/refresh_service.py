"""Refresh job status model and service â€” reads and writes dl_refresh_jobs."""

from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.beta.data_layer.models import DlRefreshJob

_VALID_STATUSES = frozenset({"pending", "running", "completed", "failed", "cancelled"})
_VALID_JOB_TYPES = frozenset({"manual", "webhook", "etag", "scheduled"})
_VALID_ENTITY_TYPES = frozenset({"products", "source", "destination", "connectors"})


class RefreshJobService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_summary(self) -> dict:
        """Return job status counts."""
        rows = self._db.query(DlRefreshJob).all()
        counts: dict[str, int] = {s: 0 for s in _VALID_STATUSES}
        for r in rows:
            key = r.status if r.status in counts else "pending"
            counts[key] += 1
        return {
            "initialized": len(rows) > 0,
            "total": len(rows),
            **counts,
        }

    def list_recent(self, limit: int = 20) -> list[dict]:
        """Return the most recently created refresh jobs."""
        rows = (
            self._db.query(DlRefreshJob)
            .order_by(DlRefreshJob.created_at.desc())
            .limit(limit)
            .all()
        )
        return [_job_to_dict(r) for r in rows]

    def create(
        self,
        job_type: str,
        entity_type: str,
        connector_id: Optional[str] = None,
        triggered_by: Optional[str] = None,
        meta: Optional[dict] = None,
    ) -> DlRefreshJob:
        """Create a new refresh job record."""
        now = datetime.datetime.utcnow()
        job = DlRefreshJob(
            job_type=job_type,
            entity_type=entity_type,
            connector_id=connector_id,
            status="pending",
            triggered_by=triggered_by,
            meta=meta,
            created_at=now,
        )
        self._db.add(job)
        self._db.commit()
        self._db.refresh(job)
        return job

    def update_status(
        self,
        job_id: int,
        status: str,
        error_message: Optional[str] = None,
        duration_ms: Optional[float] = None,
    ) -> Optional[DlRefreshJob]:
        """Update the status of an existing refresh job."""
        if status not in _VALID_STATUSES:
            raise ValueError(f"Invalid job status: {status!r}")
        row = self._db.query(DlRefreshJob).filter_by(id=job_id).first()
        if row is None:
            return None
        now = datetime.datetime.utcnow()
        row.status = status
        if status == "running":
            row.started_at = now
        elif status in ("completed", "failed", "cancelled"):
            if status == "failed":
                row.failed_at = now
            else:
                row.completed_at = now
            if duration_ms is not None:
                row.duration_ms = duration_ms
            if error_message is not None:
                row.error_message = error_message
        self._db.commit()
        self._db.refresh(row)
        return row


def _job_to_dict(r: DlRefreshJob) -> dict:
    return {
        "id": r.id,
        "job_type": r.job_type,
        "entity_type": r.entity_type,
        "connector_id": r.connector_id,
        "status": r.status,
        "triggered_by": r.triggered_by,
        "retry_count": r.retry_count,
        "max_retries": r.max_retries,
        "duration_ms": r.duration_ms,
        "error_message": r.error_message,
        "created_at": _iso(r.created_at),
        "started_at": _iso(r.started_at),
        "completed_at": _iso(r.completed_at),
        "failed_at": _iso(r.failed_at),
    }


def _iso(dt: Optional[datetime.datetime]) -> Optional[str]:
    return dt.isoformat() + "Z" if dt is not None else None
