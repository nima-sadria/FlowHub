"""Marker-based redaction for persisted and returned structured payloads."""

from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"

_SENSITIVE_MARKERS = (
    "secret",
    "token",
    "password",
    "authorization",
    "api_key",
    "apikey",
    "consumer_key",
    "consumer_secret",
    "access_token",
    "refresh_token",
)

_CREDENTIAL_KEY_CONTEXT = (
    "api",
    "auth",
    "consumer",
    "credential",
    "client",
    "private",
    "access",
    "refresh",
    "app",
)

_SENSITIVE_TEXT_PATTERN = re.compile(
    r"(?i)\b(secret|token|password|authorization|api_key|apikey|consumer_key|consumer_secret|access_token|refresh_token|key)"
    r"(\s*[:=]\s*)"
    r"([^,\s;&]+)"
)


def is_sensitive_key(key: object) -> bool:
    normalized = str(key).strip().lower().replace("-", "_")
    if any(marker in normalized for marker in _SENSITIVE_MARKERS):
        return True
    if normalized == "key":
        return True
    if normalized.endswith("_key"):
        return any(marker in normalized for marker in _CREDENTIAL_KEY_CONTEXT)
    return False


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[Any, Any] = {}
        for key, item in value.items():
            result[key] = REDACTED if is_sensitive_key(key) else redact_sensitive(item)
        return result
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive(item) for item in value)
    if isinstance(value, str):
        return redact_sensitive_text(value)
    return value


def redact_sensitive_text(value: str) -> str:
    return _SENSITIVE_TEXT_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}{REDACTED}", value)
