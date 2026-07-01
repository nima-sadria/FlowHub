"""FlowHub - /api/v2/activity router (BU5).

Paginated audit event log.  Backed by the beta_login_audit table.
Maps audit events to the ActivityEvent shape expected by the frontend.

Routes:
  GET /api/v2/activity?page=1&pageSize=20  - paginated audit log
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.beta.auth.dependencies import get_current_user
from app.beta.auth.models import BetaLoginAudit, BetaUser
from app.beta.database import get_db

router = APIRouter(prefix="/activity", tags=["activity"])

# Event -> (kind, level) mapping
_EVENT_MAP: dict[str, tuple[str, str]] = {
    "login_success": ("user_action", "success"),
    "login_failed": ("user_action", "error"),
    "logout": ("user_action", "info"),
    "token_refreshed": ("system_log", "info"),
    "setup_admin_created": ("system_log", "success"),
    "setup_completed": ("system_log", "success"),
    "settings_changed": ("user_action", "info"),
    "woocommerce_connected": ("user_action", "success"),
    "nextcloud_connected": ("user_action", "success"),
    "preview_started": ("user_action", "info"),
    "preview_completed": ("user_action", "success"),
    "preview_failed": ("user_action", "error"),
}


def _map_event(row: BetaLoginAudit) -> dict:
    kind, level = _EVENT_MAP.get(row.event, ("system_log", "info"))
    return {
        "id": str(row.id),
        "timestamp": row.created_at.isoformat() + "Z",
        "kind": kind,
        "level": level,
        "actor": row.username,
        "action": row.event,
        "detail": row.ip_address if row.ip_address not in ("api", "setup_wizard", "") else None,
    }


@router.get("")
async def list_activity(
    page: int = 1,
    pageSize: int = 20,
    _: BetaUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return paginated audit events, newest first."""
    per_page = max(1, min(pageSize, 100))
    offset = (max(1, page) - 1) * per_page

    total: int = db.query(BetaLoginAudit).count()
    rows: list[BetaLoginAudit] = (
        db.query(BetaLoginAudit)
        .order_by(BetaLoginAudit.created_at.desc())
        .offset(offset)
        .limit(per_page)
        .all()
    )

    return {
        "items": [_map_event(r) for r in rows],
        "total": total,
        "page": page,
        "pageSize": per_page,
    }
