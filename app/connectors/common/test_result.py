from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConnectionTestResult:
    ok: bool
    message: str
    latency_ms: float | None = None
    detail: dict[str, Any] | None = field(default=None)
