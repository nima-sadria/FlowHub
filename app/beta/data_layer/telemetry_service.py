"""Connector telemetry data service - reads and writes dl_connector_telemetry."""

from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.beta.data_layer.models import DlConnectorTelemetry


class ConnectorTelemetryService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_summary(self) -> dict:
        """Return telemetry totals across all tracked connectors."""
        rows = self._db.query(DlConnectorTelemetry).all()
        return {
            "initialized": len(rows) > 0,
            "connectors_tracked": len(rows),
            "total_requests": sum((r.request_count or 0) for r in rows),
            "total_errors": sum((r.error_count or 0) for r in rows),
            "total_products_fetched": sum((r.products_fetched or 0) for r in rows),
            "total_rows_parsed": sum((r.rows_parsed or 0) for r in rows),
        }

    def get_all(self) -> list[dict]:
        """Return all connector telemetry records, most recently updated first."""
        rows = (
            self._db.query(DlConnectorTelemetry)
            .order_by(DlConnectorTelemetry.updated_at.desc())
            .all()
        )
        return [_telemetry_to_dict(r) for r in rows]

    def increment(
        self,
        connector_id: str,
        connector_type: str,
        *,
        requests: int = 0,
        errors: int = 0,
        retries: int = 0,
        throttles: int = 0,
        products_fetched: int = 0,
        rows_parsed: int = 0,
        latency_ms: Optional[float] = None,
    ) -> DlConnectorTelemetry:
        """Increment telemetry counters for a connector."""
        now = datetime.datetime.utcnow()
        row = (
            self._db.query(DlConnectorTelemetry)
            .filter_by(connector_id=connector_id)
            .first()
        )
        if row is None:
            row = DlConnectorTelemetry(
                connector_id=connector_id,
                connector_type=connector_type,
                window_start=now,
            )
            self._db.add(row)
        row.request_count = (row.request_count or 0) + requests
        row.error_count = (row.error_count or 0) + errors
        row.retry_count = (row.retry_count or 0) + retries
        row.throttle_events = (row.throttle_events or 0) + throttles
        row.products_fetched = (row.products_fetched or 0) + products_fetched
        row.rows_parsed = (row.rows_parsed or 0) + rows_parsed
        if latency_ms is not None:
            row.avg_latency_ms = latency_ms
        row.window_end = now
        row.updated_at = now
        self._db.commit()
        self._db.refresh(row)
        return row

    def set_refresh_duration(self, connector_id: str, duration_ms: float) -> None:
        """Record the duration of the last completed refresh for a connector."""
        row = self._db.query(DlConnectorTelemetry).filter_by(connector_id=connector_id).first()
        if row is not None:
            row.last_refresh_duration_ms = duration_ms
            row.updated_at = datetime.datetime.utcnow()
            self._db.commit()

    def set_preview_duration(self, connector_id: str, duration_ms: float) -> None:
        """Record the duration of the last preview operation for a connector."""
        row = self._db.query(DlConnectorTelemetry).filter_by(connector_id=connector_id).first()
        if row is not None:
            row.last_preview_duration_ms = duration_ms
            row.updated_at = datetime.datetime.utcnow()
            self._db.commit()


def _telemetry_to_dict(r: DlConnectorTelemetry) -> dict:
    return {
        "id": r.id,
        "connector_id": r.connector_id,
        "connector_type": r.connector_type,
        "request_count": r.request_count,
        "error_count": r.error_count,
        "retry_count": r.retry_count,
        "throttle_events": r.throttle_events,
        "avg_latency_ms": r.avg_latency_ms,
        "p95_latency_ms": r.p95_latency_ms,
        "products_fetched": r.products_fetched,
        "rows_parsed": r.rows_parsed,
        "last_refresh_duration_ms": r.last_refresh_duration_ms,
        "last_preview_duration_ms": r.last_preview_duration_ms,
        "window_start": _iso(r.window_start),
        "window_end": _iso(r.window_end),
        "updated_at": _iso(r.updated_at),
    }


def _iso(dt: Optional[datetime.datetime]) -> Optional[str]:
    return dt.isoformat() + "Z" if dt is not None else None
