from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthResult:
    status: HealthStatus
    latency_ms: float | None = None
    detail: str | None = None
