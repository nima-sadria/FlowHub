"""FlowHub â€” AppConfigService (BU4).

DB-backed runtime configuration store. Reads and writes key-value pairs to
the beta_app_config table. Secret values are masked in safe read methods.

Key namespace conventions:
  setup.*          â€” wizard completion state
  server.*         â€” domain, port, environment, timezone, currency
  woocommerce.*    â€” URL, consumer key/secret
  nextcloud.*      â€” URL, username, password, spreadsheet path
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from .models import BetaAppConfig

_SECRET_KEYS: frozenset[str] = frozenset({
    "woocommerce.key",
    "woocommerce.secret",
    "nextcloud.password",
})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AppConfigService:
    """Key-value configuration store backed by the beta_app_config table."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, key: str) -> str | None:
        row = self._db.get(BetaAppConfig, key)
        return row.value if row else None

    def set(self, key: str, value: str | None, updated_by: str = "system") -> None:
        now = _utcnow()
        row = self._db.get(BetaAppConfig, key)
        if row is None:
            self._db.add(BetaAppConfig(key=key, value=value, updated_at=now, updated_by=updated_by))
        else:
            row.value = value
            row.updated_at = now
            row.updated_by = updated_by
        self._db.commit()

    def set_many(self, pairs: dict[str, str | None], updated_by: str = "system") -> None:
        now = _utcnow()
        for key, value in pairs.items():
            row = self._db.get(BetaAppConfig, key)
            if row is None:
                self._db.add(BetaAppConfig(key=key, value=value, updated_at=now, updated_by=updated_by))
            else:
                row.value = value
                row.updated_at = now
                row.updated_by = updated_by
        self._db.commit()

    def is_setup_completed(self) -> bool:
        return self.get("setup.completed") == "true"

    def mark_setup_complete(self, updated_by: str = "setup_wizard") -> None:
        self.set("setup.completed", "true", updated_by=updated_by)

    def get_safe(self) -> dict[str, Any]:
        """Return all config entries, masking secret values."""
        rows = self._db.query(BetaAppConfig).all()
        return {
            r.key: ("[REDACTED]" if r.key in _SECRET_KEYS else r.value)
            for r in rows
        }

    def get_non_secret(self) -> dict[str, str | None]:
        """Return only non-secret config entries."""
        rows = self._db.query(BetaAppConfig).all()
        return {r.key: r.value for r in rows if r.key not in _SECRET_KEYS}
