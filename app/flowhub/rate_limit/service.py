"""DB-backed rate limit settings and telemetry."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.flowhub.data_layer.models import DlConnectorTelemetry
from app.flowhub.rate_limit.limiter import (
    DEFAULT_READ_RPM,
    DEFAULT_WRITE_RPM,
    MAX_RPM,
    MIN_RPM,
    RateLimitAcquireResult,
    RateLimitSettings,
    global_rate_limiter_registry,
)
from app.flowhub.setup.service import AppConfigService

READ_LIMIT_KEY = "rate_limit.read_requests_per_minute"
WRITE_LIMIT_KEY = "rate_limit.write_requests_per_minute"


class RateLimitService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.config = AppConfigService(db)
        global_rate_limiter_registry.configure(self.get_settings())

    def get_settings(self) -> RateLimitSettings:
        return RateLimitSettings(
            read_requests_per_minute=_parse_rpm(self.config.get(READ_LIMIT_KEY), DEFAULT_READ_RPM),
            write_requests_per_minute=_parse_rpm(self.config.get(WRITE_LIMIT_KEY), DEFAULT_WRITE_RPM),
        )

    def update_settings(self, read_requests_per_minute: int, write_requests_per_minute: int, updated_by: str) -> RateLimitSettings:
        settings = RateLimitSettings(
            read_requests_per_minute=_validate_rpm(read_requests_per_minute),
            write_requests_per_minute=_validate_rpm(write_requests_per_minute),
        )
        self.config.set_many(
            {
                READ_LIMIT_KEY: str(settings.read_requests_per_minute),
                WRITE_LIMIT_KEY: str(settings.write_requests_per_minute),
            },
            updated_by=updated_by,
        )
        global_rate_limiter_registry.configure(settings)
        return settings

    async def acquire(
        self,
        connector_id: str,
        operation: str,
        *,
        connector_type: str | None = None,
    ) -> RateLimitAcquireResult:
        global_rate_limiter_registry.configure(self.get_settings())
        result = await global_rate_limiter_registry.acquire(connector_id, "write" if operation == "write" else "read")
        self.record_acquire(result, connector_type=connector_type)
        return result

    def record_acquire(self, result: RateLimitAcquireResult, *, connector_type: str | None = None) -> None:
        now = datetime.utcnow()
        row = self.db.query(DlConnectorTelemetry).filter_by(connector_id=result.connector_id).first()
        if row is None:
            row = DlConnectorTelemetry(
                connector_id=result.connector_id,
                connector_type=connector_type or result.connector_id.split(":")[0],
                request_count=0,
                error_count=0,
                retry_count=0,
                throttle_events=0,
                updated_at=now,
            )
            self.db.add(row)
        row.connector_type = connector_type or row.connector_type or result.connector_id.split(":")[0]
        row.request_count = (row.request_count or 0) + 1
        if result.delayed:
            row.throttle_events = (row.throttle_events or 0) + 1
        row.queue_length = result.queue_length
        row.last_throttle_at = result.last_throttle_at
        row.last_connector_delay_ms = result.last_connector_delay_ms
        row.updated_at = now
        self.db.commit()

    def diagnostics(self) -> dict:
        settings = self.get_settings()
        snapshot = global_rate_limiter_registry.snapshot()
        rows = self.db.query(DlConnectorTelemetry).all()
        last_throttle = _latest([row.last_throttle_at for row in rows] + [snapshot.get("last_throttle")])
        queue_length = max(int(snapshot.get("queue_length") or 0), sum((row.queue_length or 0) for row in rows))
        request_duration = _avg_nullable([row.last_request_duration_ms for row in rows])
        avg_latency = _avg_nullable([row.avg_latency_ms for row in rows])
        limiter_delay = _max_nullable([row.last_connector_delay_ms for row in rows] + [snapshot.get("last_connector_delay_ms")])
        eta = (
            queue_length * (60.0 / min(settings.read_requests_per_minute, settings.write_requests_per_minute))
            if queue_length > 0
            else None
        )
        return {
            "settings": {
                "read_requests_per_minute": settings.read_requests_per_minute,
                "write_requests_per_minute": settings.write_requests_per_minute,
                "read_delay_ms": round((60.0 / settings.read_requests_per_minute) * 1000, 2),
                "write_delay_ms": round((60.0 / settings.write_requests_per_minute) * 1000, 2),
            },
            "current_read_rpm": settings.read_requests_per_minute,
            "current_write_rpm": settings.write_requests_per_minute,
            "queue_length": queue_length,
            "average_request_duration_ms": _round_or_none(request_duration),
            "average_latency_ms": _round_or_none(avg_latency),
            "throttle_count": max(int(snapshot.get("throttle_count") or 0), sum((row.throttle_events or 0) for row in rows)),
            "throttle_events": max(int(snapshot.get("throttle_count") or 0), sum((row.throttle_events or 0) for row in rows)),
            "last_throttle": _iso(last_throttle),
            "last_connector_delay_ms": _round_or_none(limiter_delay),
            "last_limiter_delay_ms": _round_or_none(limiter_delay),
            "requests_completed": snapshot.get("requests_completed", 0),
            "requests_delayed": snapshot.get("requests_delayed", 0),
            "remaining_queue": queue_length,
            "estimated_completion_seconds": _round_or_none(eta),
        }


def _parse_rpm(value: str | None, default: int) -> int:
    try:
        return _validate_rpm(int(value)) if value is not None else default
    except (TypeError, ValueError):
        return default


def _validate_rpm(value: int) -> int:
    value = int(value)
    if value < MIN_RPM or value > MAX_RPM:
        raise ValueError(f"RPM must be between {MIN_RPM} and {MAX_RPM}")
    return value


def _ewma(current: float | None, sample: float) -> float:
    if current is None:
        return sample
    return (current * 0.8) + (sample * 0.2)


def _avg(values: list[float]) -> float:
    meaningful = [value for value in values if value]
    return sum(meaningful) / len(meaningful) if meaningful else 0.0


def _avg_nullable(values: list[float | None]) -> float | None:
    meaningful = [value for value in values if value is not None]
    return sum(meaningful) / len(meaningful) if meaningful else None


def _max_nullable(values: list[float | None]) -> float | None:
    meaningful = [value for value in values if value is not None]
    return max(meaningful) if meaningful else None


def _round_or_none(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None


def _latest(values: list[datetime | None]) -> datetime | None:
    meaningful = [value for value in values if value is not None]
    return max(meaningful) if meaningful else None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None
