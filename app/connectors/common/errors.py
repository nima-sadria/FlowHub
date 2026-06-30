from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ConnectorErrorCode(Enum):
    AUTH_FAILED = "auth_failed"
    NOT_FOUND = "not_found"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    NETWORK = "network"
    PERMISSION = "permission"
    PROVIDER_ERROR = "provider_error"
    UNKNOWN = "unknown"


@dataclass
class ConnectorError(Exception):
    code: ConnectorErrorCode
    message: str
    provider: str
    retryable: bool = False
    http_status: int | None = None
    raw: str | None = None

    def __post_init__(self) -> None:
        super().__init__(self.message)

    def __str__(self) -> str:
        parts = [f"[{self.provider}] {self.code.value}: {self.message}"]
        if self.http_status is not None:
            parts.append(f"(HTTP {self.http_status})")
        return " ".join(parts)
