"""Production maintenance-mode guard for state-changing write operations."""

from __future__ import annotations

import json
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.flowhub.auth.dependencies import get_current_user
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.auth.repository import create_audit_event
from app.flowhub.database import get_db
from app.flowhub.setup.service import AppConfigService


MAINTENANCE_CONFIG_KEY = "maintenance_mode"
MAINTENANCE_ERROR_CODE = "MAINTENANCE_MODE_ACTIVE"
MAINTENANCE_ERROR_MESSAGE = "Write operations are unavailable while maintenance mode is active."
_WRITE_ROLES = frozenset({"owner", "super_admin", "admin"})
_MAINTENANCE_BYPASS_ROLES = frozenset({"owner", "super_admin"})


@dataclass(frozen=True)
class MaintenanceState:
    enabled: bool
    message: str = ""


class MaintenanceModeActiveError(Exception):
    """Raised when a production write operation is blocked by maintenance."""


def load_maintenance_state(db: Session) -> MaintenanceState:
    """Load the production maintenance state and reject malformed persisted data."""
    raw = AppConfigService(db).get(MAINTENANCE_CONFIG_KEY)
    if raw in (None, ""):
        return MaintenanceState(enabled=False)
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Maintenance state is invalid.") from exc
    if isinstance(payload, bool):
        return MaintenanceState(enabled=payload)
    if not isinstance(payload, dict) or not isinstance(payload.get("enabled"), bool):
        raise RuntimeError("Maintenance state is invalid.")
    message = payload.get("message")
    if message is not None and not isinstance(message, str):
        raise RuntimeError("Maintenance state is invalid.")
    return MaintenanceState(enabled=payload["enabled"], message=message or "")


def require_write_operation_available(
    user: FlowHubUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FlowHubUser:
    """Authorize an operator and block write-batch advancement during maintenance."""
    if user.role not in _WRITE_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin permission required.")

    try:
        maintenance = load_maintenance_state(db)
    except Exception as exc:
        db.rollback()
        raise MaintenanceModeActiveError from exc

    if not maintenance.enabled:
        return user
    if user.role not in _MAINTENANCE_BYPASS_ROLES:
        raise MaintenanceModeActiveError

    try:
        create_audit_event(
            db,
            username=user.username,
            event="maintenance_write_bypass",
            ip_address="api",
        )
    except Exception as exc:
        db.rollback()
        raise MaintenanceModeActiveError from exc
    return user
