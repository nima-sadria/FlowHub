"""Shared connector contract — types, ABCs, and models used by all connectors."""

from .auth import AuthConfig
from .base import DestinationConnector, SourceConnector
from .errors import ConnectorError, ConnectorErrorCode
from .health import HealthResult, HealthStatus
from .rate_limit import RateLimitConfig
from .retry import RetryConfig
from .test_result import ConnectionTestResult
from .types import ConnectorCapabilities, ConnectorID, ConnectorType

__all__ = [
    "AuthConfig",
    "ConnectorCapabilities",
    "ConnectorError",
    "ConnectorErrorCode",
    "ConnectorID",
    "ConnectorType",
    "ConnectionTestResult",
    "DestinationConnector",
    "HealthResult",
    "HealthStatus",
    "RateLimitConfig",
    "RetryConfig",
    "SourceConnector",
]
