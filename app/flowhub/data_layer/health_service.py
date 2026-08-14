"""Connector health data service - reads and writes dl_connector_health."""

from __future__ import annotations

import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.flowhub.data_layer.models import DlConnectorHealth
from app.flowhub.integration_platform.models import IntegrationConnectorHealthSnapshot
from app.flowhub.security.redaction import redact_sensitive

_VALID_STATUSES = frozenset({"healthy", "degraded", "unhealthy", "unknown"})
_SAFE_EVIDENCE_KEYS = frozenset(
    {
        "endpoint_class",
        "endpoint_path_template",
        "http_status",
        "error_category",
        "latency_ms",
        "correlation_id",
        "provider_request_attempted",
        "provider_status",
    }
)


class ConnectorHealthService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_summary(self) -> dict:
        """Return health status counts across all tracked connectors."""
        rows = self._db.query(DlConnectorHealth).all()
        counts: dict[str, int] = {"healthy": 0, "degraded": 0, "unhealthy": 0, "unknown": 0}
        for r in rows:
            key = r.status if r.status in counts else "unknown"
            counts[key] += 1
        return {
            "initialized": len(rows) > 0,
            "total": len(rows),
            **counts,
        }

    def get_all(self) -> list[dict]:
        """Return all connector health records, most recently checked first."""
        rows = (
            self._db.query(DlConnectorHealth)
            .order_by(DlConnectorHealth.checked_at.desc())
            .all()
        )
        return [_health_to_dict(r) for r in rows]

    def upsert(
        self,
        connector_id: str,
        connector_type: str,
        status: str,
        latency_ms: Optional[float] = None,
        detail: Optional[str] = None,
        error_class: Optional[str] = None,
        evidence: Optional[dict[str, Any]] = None,
    ) -> DlConnectorHealth:
        """Insert current health and append safe historical evidence."""
        if status not in _VALID_STATUSES:
            raise ValueError(f"Invalid health status: {status!r}")
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        row = (
            self._db.query(DlConnectorHealth)
            .filter_by(connector_id=connector_id)
            .first()
        )
        if row is None:
            row = DlConnectorHealth(
                connector_id=connector_id,
                connector_type=connector_type,
                checked_at=now,
            )
            self._db.add(row)
        row.connector_type = connector_type
        row.status = status
        row.latency_ms = latency_ms
        row.detail = detail
        row.error_class = error_class
        row.checked_at = now
        if status in {"healthy", "degraded"}:
            row.last_success_at = now
            row.consecutive_failures = 0
        else:
            row.consecutive_failures = (row.consecutive_failures or 0) + 1
        snapshot_evidence = _safe_health_evidence(
            {
                **(evidence or {}),
                "latency_ms": latency_ms,
                "error_category": error_class,
            }
        )
        self._db.add(
            IntegrationConnectorHealthSnapshot(
                connector_id=connector_id,
                status=status,
                message=str(detail or "")[:500],
                checked_at=now,
                details_json=snapshot_evidence,
            )
        )
        self._db.commit()
        self._db.refresh(row)
        return row


def _health_to_dict(r: DlConnectorHealth) -> dict:
    return {
        "id": r.id,
        "connector_id": r.connector_id,
        "connector_type": r.connector_type,
        "status": r.status,
        "latency_ms": r.latency_ms,
        "detail": r.detail,
        "error_class": r.error_class,
        "consecutive_failures": r.consecutive_failures,
        "checked_at": _iso(r.checked_at),
        "last_success_at": _iso(r.last_success_at),
    }


def _iso(dt: Optional[datetime.datetime]) -> Optional[str]:
    return dt.isoformat() + "Z" if dt is not None else None


def _safe_health_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key in _SAFE_EVIDENCE_KEYS:
        value = evidence.get(key)
        if value is None:
            continue
        if key == "provider_request_attempted":
            safe[key] = bool(value)
        elif key == "http_status":
            try:
                safe[key] = int(value)
            except (TypeError, ValueError):
                continue
        elif key == "latency_ms":
            try:
                safe[key] = round(float(value), 2)
            except (TypeError, ValueError):
                continue
        else:
            safe[key] = str(value)[:255]
    return redact_sensitive(safe)
