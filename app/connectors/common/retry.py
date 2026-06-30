from __future__ import annotations

from dataclasses import dataclass, field

from .errors import ConnectorErrorCode


@dataclass(frozen=True)
class RetryConfig:
    max_attempts: int = 3
    base_delay_s: float = 1.0
    max_delay_s: float = 30.0
    backoff_factor: float = 2.0
    retryable_codes: frozenset[ConnectorErrorCode] = field(
        default_factory=lambda: frozenset({
            ConnectorErrorCode.RATE_LIMITED,
            ConnectorErrorCode.TIMEOUT,
            ConnectorErrorCode.NETWORK,
        })
    )
