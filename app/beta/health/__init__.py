"""CP1.2 â€” Health Engine package.

Public API:
    HealthEngine        â€” orchestrator for health checks
    HealthCheckResult   â€” structured result of a single health check
    HealthStatus        â€” enum: PASS / WARN / FAIL / SKIP / UNKNOWN
    CheckCategory       â€” enum: DNS / TCP / TLS / HTTP / AUTH / CONFIG / STORAGE / DATABASE / DOCKER / INTEGRATION
    SystemHealthSummary â€” aggregated health across all checks
    aggregate_results   â€” aggregate a list of HealthCheckResult
"""

from .aggregation import SystemHealthSummary, aggregate_results
from .engine import HealthEngine
from .models import CheckCategory, HealthCheckResult, HealthStatus

__all__ = [
    "CheckCategory",
    "HealthCheckResult",
    "HealthEngine",
    "HealthStatus",
    "SystemHealthSummary",
    "aggregate_results",
]
