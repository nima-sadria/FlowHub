"""CP1.3 - Runtime configuration field definitions and audit models.

EDITABLE_FIELDS: non-secret, non-identity fields that an operator can change
                 via 'flowhub configure set' without a reinstall.

INSTALLER_ONLY_FIELDS: set once during install; cannot be changed at runtime.

SECRET_RUNTIME_FIELDS: never exposed or written by RuntimeConfigService.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


EDITABLE_FIELDS: frozenset[str] = frozenset(
    {
        "FLOWHUB_LOG_LEVEL",
        "FLOWHUB_NEXTCLOUD_URL",
        "FLOWHUB_NEXTCLOUD_FILE_PATH",
        "FLOWHUB_WOOCOMMERCE_URL",
        "FLOWHUB_TIMEZONE",
        "FLOWHUB_CURRENCY",
        "FLOWHUB_SCHEDULER_POLL_SECONDS",
        "FLOWHUB_BACKUP_RETAIN_DAYS",
        "FLOWHUB_MAX_UPLOAD_MB",
        "FLOWHUB_WORKER_CONCURRENCY",
    }
)

INSTALLER_ONLY_FIELDS: frozenset[str] = frozenset(
    {
        "FLOWHUB_ENV",
        "FLOWHUB_DOMAIN",
        "FLOWHUB_PORT",
        "FLOWHUB_SSL_MODE",
        "FLOWHUB_DATABASE_URL",
        "FLOWHUB_POSTGRES_DB",
        "FLOWHUB_POSTGRES_USER",
        "FLOWHUB_ADMIN_EMAIL",
        "FLOWHUB_STORAGE_PATH",
        "FLOWHUB_BACKUP_PATH",
        "FLOWHUB_PLUGIN_DIR",
    }
)

SECRET_RUNTIME_FIELDS: frozenset[str] = frozenset(
    {
        "FLOWHUB_JWT_SECRET",
        "FLOWHUB_REST_API_SECRET",
        "FLOWHUB_POSTGRES_PASSWORD",
        "FLOWHUB_NEXTCLOUD_USERNAME",
        "FLOWHUB_NEXTCLOUD_PASSWORD",
        "FLOWHUB_WOOCOMMERCE_KEY",
        "FLOWHUB_WOOCOMMERCE_SECRET",
    }
)


@dataclass
class ConfigRecord:
    """Snapshot of a single configuration field - safe to display."""

    field_name: str
    current_value: str
    is_editable: bool
    is_secret: bool
    is_installer_only: bool
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_name": self.field_name,
            "current_value": "[REDACTED]" if self.is_secret else self.current_value,
            "is_editable": self.is_editable,
            "is_secret": self.is_secret,
            "is_installer_only": self.is_installer_only,
            "description": self.description,
        }


@dataclass
class ConfigChangeEvent:
    """Audit record of a runtime configuration change."""

    field_name: str
    old_value: Optional[str]
    new_value: str
    changed_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    changed_by: str = "cli"

    def to_dict(self) -> dict[str, Any]:
        is_secret = self.field_name in SECRET_RUNTIME_FIELDS
        return {
            "field_name": self.field_name,
            "old_value": "[REDACTED]" if is_secret else self.old_value,
            "new_value": "[REDACTED]" if is_secret else self.new_value,
            "changed_at": self.changed_at.isoformat(),
            "changed_by": self.changed_by,
        }
