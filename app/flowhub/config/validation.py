"""FlowHub - Configuration validation.

Validates a flat dict[str, str] of environment variables and returns a
structured ValidationResult. Never raises, never terminates the process.
The caller decides what to do with the result.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .defaults import DEFAULTS, LOG_LEVELS, SSL_MODES
from .secrets import SECRET_FIELDS

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

REQUIRED_FIELDS: tuple[str, ...] = (
    "FLOWHUB_ENV",
    "FLOWHUB_DOMAIN",
    "FLOWHUB_PORT",
    "FLOWHUB_DATABASE_URL",
    "FLOWHUB_POSTGRES_DB",
    "FLOWHUB_POSTGRES_USER",
    "FLOWHUB_POSTGRES_PASSWORD",
    "FLOWHUB_JWT_SECRET",
    "FLOWHUB_REST_API_SECRET",
    "FLOWHUB_TIMEZONE",
    "FLOWHUB_CURRENCY",
    "FLOWHUB_ADMIN_EMAIL",
    "FLOWHUB_STORAGE_PATH",
    "FLOWHUB_BACKUP_PATH",
    "FLOWHUB_SSL_MODE",
)

OPTIONAL_FIELDS: tuple[str, ...] = (
    "FLOWHUB_LOG_LEVEL",
    "FLOWHUB_JWT_ACCESS_TTL_MINUTES",
    "FLOWHUB_JWT_REFRESH_TTL_DAYS",
    "FLOWHUB_MAX_UPLOAD_MB",
    "FLOWHUB_PLUGIN_DIR",
    "FLOWHUB_WORKER_CONCURRENCY",
    "FLOWHUB_SCHEDULER_POLL_SECONDS",
    "FLOWHUB_BACKUP_RETAIN_DAYS",
    "FLOWHUB_NEXTCLOUD_URL",
    "FLOWHUB_NEXTCLOUD_FILE_PATH",
    "FLOWHUB_NEXTCLOUD_USERNAME",
    "FLOWHUB_NEXTCLOUD_PASSWORD",
    "FLOWHUB_WOOCOMMERCE_URL",
    "FLOWHUB_WOOCOMMERCE_KEY",
    "FLOWHUB_WOOCOMMERCE_SECRET",
)


@dataclass
class FieldError:
    field: str
    value: Any
    message: str

    def __str__(self) -> str:
        display = "[REDACTED]" if self.field in SECRET_FIELDS else repr(self.value)
        return f"{self.field}={display}: {self.message}"


@dataclass
class ValidationResult:
    errors: list[FieldError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def add_error(self, field_name: str, value: Any, message: str) -> None:
        self.errors.append(FieldError(field=field_name, value=value, message=message))

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def __bool__(self) -> bool:
        return self.is_valid

    def format_errors(self) -> str:
        if not self.errors:
            return "No errors."
        return "\n".join(f"  - {e}" for e in self.errors)

    def format_warnings(self) -> str:
        if not self.warnings:
            return "No warnings."
        return "\n".join(f"  - {w}" for w in self.warnings)


class ConfigValidator:
    """Validates a flat env dict and returns structured ValidationResult."""

    def __init__(self, check_paths: bool = True) -> None:
        self._check_paths = check_paths

    def validate(self, env: dict[str, str]) -> ValidationResult:
        result = ValidationResult()
        self._check_required_present(env, result)
        self._check_field_values(env, result)
        return result

    def _check_required_present(self, env: dict[str, str], result: ValidationResult) -> None:
        for name in REQUIRED_FIELDS:
            if not env.get(name, "").strip():
                result.add_error(name, None, "Required variable is missing or empty")

    def _check_field_values(self, env: dict[str, str], result: ValidationResult) -> None:
        get = env.get

        _v(result, "FLOWHUB_ENV", get("FLOWHUB_ENV", ""), _check_env)
        _v(result, "FLOWHUB_PORT", get("FLOWHUB_PORT", ""), _check_port)
        _v(result, "FLOWHUB_DATABASE_URL", get("FLOWHUB_DATABASE_URL", ""), _check_database_url)
        _v(result, "FLOWHUB_JWT_SECRET", get("FLOWHUB_JWT_SECRET", ""), _check_jwt_secret)
        _v(result, "FLOWHUB_REST_API_SECRET", get("FLOWHUB_REST_API_SECRET", ""), _check_rest_secret)
        _v(result, "FLOWHUB_NEXTCLOUD_URL", get("FLOWHUB_NEXTCLOUD_URL", ""), _check_url)
        _v(result, "FLOWHUB_WOOCOMMERCE_URL", get("FLOWHUB_WOOCOMMERCE_URL", ""), _check_url)
        _v(result, "FLOWHUB_TIMEZONE", get("FLOWHUB_TIMEZONE", ""), _check_timezone)
        _v(result, "FLOWHUB_CURRENCY", get("FLOWHUB_CURRENCY", ""), _check_currency)
        _v(result, "FLOWHUB_ADMIN_EMAIL", get("FLOWHUB_ADMIN_EMAIL", ""), _check_email)
        _v(result, "FLOWHUB_SSL_MODE", get("FLOWHUB_SSL_MODE", ""), _check_ssl_mode)
        _v(result, "FLOWHUB_LOG_LEVEL", get("FLOWHUB_LOG_LEVEL", str(DEFAULTS["FLOWHUB_LOG_LEVEL"])), _check_log_level)
        _v(result, "FLOWHUB_JWT_ACCESS_TTL_MINUTES", get("FLOWHUB_JWT_ACCESS_TTL_MINUTES", str(DEFAULTS["FLOWHUB_JWT_ACCESS_TTL_MINUTES"])), _check_positive_int)
        _v(result, "FLOWHUB_JWT_REFRESH_TTL_DAYS", get("FLOWHUB_JWT_REFRESH_TTL_DAYS", str(DEFAULTS["FLOWHUB_JWT_REFRESH_TTL_DAYS"])), _check_positive_int)
        _v(result, "FLOWHUB_MAX_UPLOAD_MB", get("FLOWHUB_MAX_UPLOAD_MB", str(DEFAULTS["FLOWHUB_MAX_UPLOAD_MB"])), _check_positive_int)
        _v(result, "FLOWHUB_WORKER_CONCURRENCY", get("FLOWHUB_WORKER_CONCURRENCY", str(DEFAULTS["FLOWHUB_WORKER_CONCURRENCY"])), _check_positive_int)
        _v(result, "FLOWHUB_SCHEDULER_POLL_SECONDS", get("FLOWHUB_SCHEDULER_POLL_SECONDS", str(DEFAULTS["FLOWHUB_SCHEDULER_POLL_SECONDS"])), _check_positive_int)
        _v(result, "FLOWHUB_BACKUP_RETAIN_DAYS", get("FLOWHUB_BACKUP_RETAIN_DAYS", str(DEFAULTS["FLOWHUB_BACKUP_RETAIN_DAYS"])), _check_positive_int)

        if self._check_paths:
            _v(result, "FLOWHUB_STORAGE_PATH", get("FLOWHUB_STORAGE_PATH", ""), _check_writable_path)
            _v(result, "FLOWHUB_BACKUP_PATH", get("FLOWHUB_BACKUP_PATH", ""), _check_writable_path)

        env_val = get("FLOWHUB_ENV", "")
        if env_val == "production":
            result.add_warning(
                "FLOWHUB_ENV=production detected. Production guard is active. "
                "All destructive CLI operations require --i-know-what-i-am-doing."
            )


def _v(
    result: ValidationResult,
    field_name: str,
    value: str,
    checker: Callable[[str], str | None],
) -> None:
    message = checker(value)
    if message:
        result.add_error(field_name, value, message)


def _check_env(value: str) -> str | None:
    if not value:
        return None
    if value not in ("dev", "production"):
        return f"Must be one of: dev, production (got {value!r})"
    return None


def _check_port(value: str) -> str | None:
    if not value:
        return None
    try:
        port = int(value)
    except ValueError:
        return f"Must be an integer (got {value!r})"
    if not (1024 <= port <= 65535):
        return f"Must be between 1024 and 65535 (got {port})"
    return None


def _check_database_url(value: str) -> str | None:
    if not value:
        return None
    valid_prefixes = ("postgresql://", "postgresql+asyncpg://", "postgresql+psycopg2://")
    if not value.startswith(valid_prefixes):
        return "Must be a PostgreSQL connection string (postgresql://...)"
    return None


def _check_jwt_secret(value: str) -> str | None:
    if not value:
        return None
    if len(value) < 64:
        return f"Must be at least 64 characters (got {len(value)})"
    return None


def _check_rest_secret(value: str) -> str | None:
    if not value:
        return None
    if len(value) < 32:
        return f"Must be at least 32 characters (got {len(value)})"
    return None


def _check_url(value: str) -> str | None:
    if not value:
        return None
    if not _URL_RE.match(value):
        return f"Must be a valid URL with http:// or https:// scheme (got {value!r})"
    return None


def _check_timezone(value: str) -> str | None:
    if not value:
        return None
    try:
        import zoneinfo
        zoneinfo.ZoneInfo(value)
    except Exception:
        return (
            f"Must be a valid IANA timezone string (got {value!r}). "
            "Install tzdata package if running in a minimal environment."
        )
    return None


def _check_currency(value: str) -> str | None:
    if not value:
        return None
    if not _CURRENCY_RE.match(value):
        return f"Must be a 3-letter uppercase ISO 4217 code (got {value!r})"
    return None


def _check_email(value: str) -> str | None:
    if not value:
        return None
    if not _EMAIL_RE.match(value):
        return f"Must be a valid email address (got {value!r})"
    return None


def _check_ssl_mode(value: str) -> str | None:
    if not value:
        return None
    if value not in SSL_MODES:
        return f"Must be one of: {', '.join(sorted(SSL_MODES))} (got {value!r})"
    return None


def _check_log_level(value: str) -> str | None:
    if not value:
        return None
    if value.upper() not in LOG_LEVELS:
        return f"Must be one of: {', '.join(sorted(LOG_LEVELS))} (got {value!r})"
    return None


def _check_positive_int(value: str) -> str | None:
    if not value:
        return None
    try:
        n = int(value)
    except ValueError:
        return f"Must be an integer (got {value!r})"
    if n <= 0:
        return f"Must be a positive integer (got {n})"
    return None


def _check_writable_path(value: str) -> str | None:
    if not value:
        return None
    p = Path(value)
    if not p.exists():
        return f"Path does not exist: {value}"
    if not os.access(p, os.W_OK):
        return f"Path is not writable: {value}"
    return None
