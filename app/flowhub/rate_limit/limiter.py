"""Thread-safe async token bucket rate limiter.

The limiter is process-local for FlowHub 1.0.0 but all state is keyed by
connector instance and operation type so a future distributed backend can
replace the registry without changing connector call sites.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from threading import RLock

DEFAULT_READ_RPM = 60
DEFAULT_WRITE_RPM = 30
MIN_RPM = 1
MAX_RPM = 1000

OperationType = str
Clock = Callable[[], float]
Sleeper = Callable[[float], Awaitable[object]]


@dataclass(frozen=True)
class RateLimitSettings:
    read_requests_per_minute: int = DEFAULT_READ_RPM
    write_requests_per_minute: int = DEFAULT_WRITE_RPM

    def rpm_for(self, operation: OperationType) -> int:
        if operation == "write":
            return self.write_requests_per_minute
        return self.read_requests_per_minute


@dataclass(frozen=True)
class RateLimitAcquireResult:
    connector_id: str
    operation: OperationType
    rpm: int
    delay_seconds: float
    delayed: bool
    queue_length: int
    estimated_delay_ms: float
    requests_completed: int
    requests_delayed: int
    throttle_events: int
    average_request_duration_ms: float
    last_throttle_at: datetime | None
    last_connector_delay_ms: float


class AsyncTokenBucket:
    """One-token bucket with no burst above the configured RPM."""

    def __init__(
        self,
        connector_id: str,
        operation: OperationType,
        rpm: int,
        *,
        clock: Clock | None = None,
        sleeper: Sleeper | None = None,
    ) -> None:
        self.connector_id = connector_id
        self.operation = operation
        self._rpm = _clamp_rpm(rpm)
        self._clock = clock or time.monotonic
        self._sleeper = sleeper or asyncio.sleep
        self._lock = RLock()
        self._next_available = 0.0
        self._queue_length = 0
        self._requests_completed = 0
        self._requests_delayed = 0
        self._throttle_events = 0
        self._last_throttle_at: datetime | None = None
        self._last_connector_delay_ms = 0.0
        self._avg_request_duration_ms = 0.0

    @property
    def rpm(self) -> int:
        with self._lock:
            return self._rpm

    def update_rpm(self, rpm: int) -> None:
        with self._lock:
            self._rpm = _clamp_rpm(rpm)

    async def acquire(self) -> RateLimitAcquireResult:
        with self._lock:
            self._queue_length += 1
            rpm = self._rpm
            interval = 60.0 / rpm
            now = self._clock()
            delay = max(0.0, self._next_available - now)
            self._next_available = max(now, self._next_available) + interval
            delayed = delay > 0
            if delayed:
                self._requests_delayed += 1
                self._throttle_events += 1
                self._last_throttle_at = datetime.utcnow()
                self._last_connector_delay_ms = delay * 1000

        started = self._clock()
        if delay > 0:
            await self._sleeper(delay)
        elapsed_ms = max(0.0, (self._clock() - started) * 1000)

        with self._lock:
            self._queue_length = max(0, self._queue_length - 1)
            self._requests_completed += 1
            if elapsed_ms or self._avg_request_duration_ms == 0:
                if self._avg_request_duration_ms == 0:
                    self._avg_request_duration_ms = elapsed_ms
                else:
                    self._avg_request_duration_ms = (self._avg_request_duration_ms * 0.8) + (elapsed_ms * 0.2)
            return RateLimitAcquireResult(
                connector_id=self.connector_id,
                operation=self.operation,
                rpm=rpm,
                delay_seconds=delay,
                delayed=delayed,
                queue_length=self._queue_length,
                estimated_delay_ms=(60.0 / rpm) * 1000,
                requests_completed=self._requests_completed,
                requests_delayed=self._requests_delayed,
                throttle_events=self._throttle_events,
                average_request_duration_ms=self._avg_request_duration_ms,
                last_throttle_at=self._last_throttle_at,
                last_connector_delay_ms=self._last_connector_delay_ms,
            )

    def snapshot(self) -> RateLimitAcquireResult:
        with self._lock:
            return RateLimitAcquireResult(
                connector_id=self.connector_id,
                operation=self.operation,
                rpm=self._rpm,
                delay_seconds=0.0,
                delayed=False,
                queue_length=self._queue_length,
                estimated_delay_ms=(60.0 / self._rpm) * 1000,
                requests_completed=self._requests_completed,
                requests_delayed=self._requests_delayed,
                throttle_events=self._throttle_events,
                average_request_duration_ms=self._avg_request_duration_ms,
                last_throttle_at=self._last_throttle_at,
                last_connector_delay_ms=self._last_connector_delay_ms,
            )


class GlobalRateLimiterRegistry:
    def __init__(self) -> None:
        self._settings = RateLimitSettings()
        self._buckets: dict[tuple[str, OperationType], AsyncTokenBucket] = {}
        self._lock = RLock()

    def configure(self, settings: RateLimitSettings) -> None:
        settings = RateLimitSettings(
            read_requests_per_minute=_clamp_rpm(settings.read_requests_per_minute),
            write_requests_per_minute=_clamp_rpm(settings.write_requests_per_minute),
        )
        with self._lock:
            self._settings = settings
            for (connector_id, operation), bucket in self._buckets.items():
                _ = connector_id
                bucket.update_rpm(settings.rpm_for(operation))

    async def acquire(self, connector_id: str, operation: OperationType) -> RateLimitAcquireResult:
        return await self._bucket(connector_id, operation).acquire()

    def snapshot(self) -> dict:
        with self._lock:
            buckets = [bucket.snapshot() for bucket in self._buckets.values()]
            return {
                "settings": {
                    "read_requests_per_minute": self._settings.read_requests_per_minute,
                    "write_requests_per_minute": self._settings.write_requests_per_minute,
                },
                "queue_length": sum(item.queue_length for item in buckets),
                "average_request_duration_ms": _avg([item.average_request_duration_ms for item in buckets]),
                "throttle_count": sum(item.throttle_events for item in buckets),
                "last_throttle": _latest([item.last_throttle_at for item in buckets]),
                "last_connector_delay_ms": max([item.last_connector_delay_ms for item in buckets], default=0.0),
                "requests_completed": sum(item.requests_completed for item in buckets),
                "requests_delayed": sum(item.requests_delayed for item in buckets),
            }

    def reset_for_tests(self) -> None:
        with self._lock:
            self._settings = RateLimitSettings()
            self._buckets = {}

    def _bucket(self, connector_id: str, operation: OperationType) -> AsyncTokenBucket:
        normalized_operation = "write" if operation == "write" else "read"
        key = (connector_id, normalized_operation)
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = AsyncTokenBucket(connector_id, normalized_operation, self._settings.rpm_for(normalized_operation))
                self._buckets[key] = bucket
            return bucket


global_rate_limiter_registry = GlobalRateLimiterRegistry()


async def acquire_connector_rate_limit(connector_id: str, operation: OperationType) -> RateLimitAcquireResult:
    return await global_rate_limiter_registry.acquire(connector_id, operation)


def _clamp_rpm(value: int) -> int:
    return min(MAX_RPM, max(MIN_RPM, int(value)))


def _avg(values: list[float]) -> float:
    meaningful = [value for value in values if value]
    return sum(meaningful) / len(meaningful) if meaningful else 0.0


def _latest(values: list[datetime | None]) -> datetime | None:
    meaningful = [value for value in values if value is not None]
    return max(meaningful) if meaningful else None
