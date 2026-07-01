"""CP1.2 â€” Connection Manager package.

Public API:
    ConnectionManager   â€” orchestrates checks, circuit breaker, cache
    ConnectionDefinition â€” configuration for a registered connection
    ConnectionResult    â€” structured result of a connection probe
    ConnectionType      â€” enum of known connection service types
    ConnectionStatus    â€” enum of connection health states
    CircuitState        â€” enum of circuit breaker states
"""

from .cache import ConnectionCache
from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from .classifier import classify_exception, classify_http_response, is_retryable
from .manager import ConnectionManager
from .models import (
    CircuitState,
    ConnectionDefinition,
    ConnectionResult,
    ConnectionStatus,
    ConnectionType,
)

__all__ = [
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitState",
    "ConnectionCache",
    "ConnectionDefinition",
    "ConnectionManager",
    "ConnectionResult",
    "ConnectionStatus",
    "ConnectionType",
    "classify_exception",
    "classify_http_response",
    "is_retryable",
]
