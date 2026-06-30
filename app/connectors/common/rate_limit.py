from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RateLimitConfig:
    requests_per_minute: int | None = None
    burst: int | None = None
    respect_retry_after: bool = True
