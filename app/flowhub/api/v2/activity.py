"""FlowHub - /api/v2/activity router (BU5).

Paginated audit event log.  Backed by the flowhub_login_audit table.
Maps audit events to the ActivityEvent shape expected by the frontend.

Routes:
  GET /api/v2/activity?page=1&pageSize=20  - paginated audit log
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import String, case, cast, or_
from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubLoginAudit, FlowHubUser
from app.flowhub.business_observability.contracts import BusinessEventShape
from app.flowhub.business_observability.service import BusinessObservabilityService
from app.flowhub.database import get_db
from app.flowhub.unified_workspace.authorization import require_workspace_permission
from app.flowhub.unified_workspace.models import UnifiedAuditEntry

router = APIRouter(prefix="/activity", tags=["activity"])

# Business Observability domain -> Activity category, so a business event
# lands in the same filter bucket an operator would already use to find
# related work (e.g. a Channels business event next to "channel_connected").
_BUSINESS_EVENT_CATEGORY: dict[str, str] = {
    "source_acquisition": "sources",
    "pricing": "pricing",
    "channels": "channels",
    "write_pipeline": "apply",
}
_BUSINESS_EVENT_DOMAIN_ACTOR: dict[str, str] = {
    "source_acquisition": "Source Acquisition",
    "pricing": "Pricing",
    "channels": "Channels",
    "write_pipeline": "Write Pipeline",
}


def _business_event_level(shape: BusinessEventShape) -> str:
    """Map the Business Event severity/impact axes onto ActivityLevel.

    Business Observability keeps severity and business impact as separate
    concepts (Owner decision); Activity's ``level`` is a single presentation
    field, so this collapses the two the same way the rest of Activity
    already collapses UnifiedAuditEntry's free-text event_type.
    """

    if shape.severity == "critical":
        return "critical"
    if shape.severity == "error":
        return "error"
    if shape.severity in ("warning", "degraded"):
        return "warning"
    if shape.businessImpact == "none":
        return "success"
    return "info"


def _map_business_event(shape: BusinessEventShape) -> dict[str, str | None]:
    return {
        "id": f"business:{shape.id}",
        "timestamp": shape.occurredAt.isoformat() + "Z",
        "kind": "business_event",
        "level": _business_event_level(shape),
        "category": _BUSINESS_EVENT_CATEGORY.get(shape.domain, "system"),
        "actor": _BUSINESS_EVENT_DOMAIN_ACTOR.get(shape.domain, shape.domain),
        "action": shape.eventType,
        "detail": shape.reasonMessage or shape.reasonCode,
        "businessEventId": shape.id,
        "businessImpact": shape.businessImpact,
        "status": shape.status,
        "recommendedAction": shape.recommendedAction or None,
        "actionUrl": shape.actionUrl,
        "retryable": shape.retryable,
    }

# Event -> (kind, level, category) mapping. Categories are presentation
# metadata only; the append-only audit rows remain unchanged.
_EVENT_MAP: dict[str, tuple[str, str, str]] = {
    "login_success": ("user_action", "success", "authentication"),
    "login_failed": ("user_action", "error", "authentication"),
    "logout": ("user_action", "info", "authentication"),
    "token_refreshed": ("system_log", "debug", "system"),
    "setup_admin_created": ("system_log", "success", "users"),
    "user_created": ("user_action", "success", "users"),
    "user_role_changed": ("user_action", "info", "users"),
    "user_activation_changed": ("user_action", "info", "users"),
    "user_password_reset": ("user_action", "info", "security"),
    "user_deleted": ("user_action", "warning", "users"),
    "setup_completed": ("system_log", "success", "system"),
    "settings_changed": ("user_action", "info", "system"),
    "woocommerce_connected": ("user_action", "success", "channels"),
    "nextcloud_connected": ("user_action", "success", "sources"),
    "preview_started": ("user_action", "info", "products"),
    "preview_completed": ("user_action", "success", "products"),
    "preview_failed": ("user_action", "error", "products"),
}


def _map_login_event(row: FlowHubLoginAudit) -> dict[str, str | None]:
    kind, level, category = _EVENT_MAP.get(
        row.event, ("system_log", "info", "system")
    )
    return {
        "id": str(row.id),
        "timestamp": row.created_at.isoformat() + "Z",
        "kind": kind,
        "level": level,
        "category": category,
        "actor": row.username,
        "action": row.event,
        "detail": row.ip_address if row.ip_address not in ("api", "setup_wizard", "") else None,
    }


def _classify_unified_event(event_type: str) -> tuple[str, str]:
    if event_type.startswith("apply"):
        category = "apply"
    elif event_type.startswith("review"):
        category = "review"
    elif event_type.startswith(("workspace", "snapshot", "draft")):
        category = "workspace"
    elif event_type.startswith(("mapping", "source")):
        category = "sources"
    elif event_type.startswith("channel"):
        category = "channels"
    else:
        category = "system"

    if any(marker in event_type for marker in ("failed", "denied", "error")):
        level = "error"
    elif any(marker in event_type for marker in ("stale", "reconciliation", "lock_failed")):
        level = "warning"
    elif any(
        marker in event_type
        for marker in (
            "completed",
            "created",
            "saved",
            "restored",
            "refreshed",
            "reconciled",
            "succeeded",
        )
    ):
        level = "success"
    else:
        level = "info"
    return category, level


def _map_unified_event(
    row: UnifiedAuditEntry, username: str | None
) -> dict[str, str | None]:
    category, level = _classify_unified_event(row.event_type)
    detail = row.reason or row.correlation_id
    return {
        "id": f"unified:{row.id}",
        "timestamp": row.occurred_at.isoformat() + "Z",
        "kind": "user_action",
        "level": level,
        "category": category,
        "actor": username or f"user:{row.user_id}",
        "action": row.event_type,
        "detail": detail,
    }


_UNIFIED_CATEGORY = case(
    (UnifiedAuditEntry.event_type.like("apply%"), "apply"),
    (UnifiedAuditEntry.event_type.like("review%"), "review"),
    (
        or_(
            UnifiedAuditEntry.event_type.like("workspace%"),
            UnifiedAuditEntry.event_type.like("snapshot%"),
            UnifiedAuditEntry.event_type.like("draft%"),
        ),
        "workspace",
    ),
    (
        or_(
            UnifiedAuditEntry.event_type.like("mapping%"),
            UnifiedAuditEntry.event_type.like("source%"),
        ),
        "sources",
    ),
    (UnifiedAuditEntry.event_type.like("channel%"), "channels"),
    else_="system",
)

_UNIFIED_LEVEL = case(
    (
        or_(
            UnifiedAuditEntry.event_type.like("%failed%"),
            UnifiedAuditEntry.event_type.like("%denied%"),
            UnifiedAuditEntry.event_type.like("%error%"),
        ),
        "error",
    ),
    (
        or_(
            UnifiedAuditEntry.event_type.like("%stale%"),
            UnifiedAuditEntry.event_type.like("%reconciliation%"),
            UnifiedAuditEntry.event_type.like("%lock_failed%"),
        ),
        "warning",
    ),
    (
        or_(
            UnifiedAuditEntry.event_type.like("%completed%"),
            UnifiedAuditEntry.event_type.like("%created%"),
            UnifiedAuditEntry.event_type.like("%saved%"),
            UnifiedAuditEntry.event_type.like("%restored%"),
            UnifiedAuditEntry.event_type.like("%refreshed%"),
            UnifiedAuditEntry.event_type.like("%reconciled%"),
            UnifiedAuditEntry.event_type.like("%succeeded%"),
        ),
        "success",
    ),
    else_="info",
)


@router.get("")
async def list_activity(
    _: Annotated[
        FlowHubUser, Depends(require_workspace_permission("audit.read"))
    ],
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    pageSize: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(max_length=120)] = None,
    username: Annotated[str | None, Query(max_length=150)] = None,
    category: Annotated[str | None, Query(max_length=40)] = None,
    severity: Annotated[str | None, Query(max_length=20)] = None,
    dateFrom: Annotated[datetime | None, Query()] = None,
    dateTo: Annotated[datetime | None, Query()] = None,
    source: Annotated[str | None, Query(max_length=120)] = None,
    channel: Annotated[str | None, Query(max_length=120)] = None,
    includeDebug: Annotated[bool, Query()] = False,
) -> dict:
    """Return paginated audit events, newest first."""
    per_page = pageSize
    offset = (page - 1) * per_page
    login_query = db.query(FlowHubLoginAudit)
    if username:
        login_query = login_query.filter(FlowHubLoginAudit.username == username)
    if search:
        pattern = f"%{search.strip()}%"
        login_query = login_query.filter(
            or_(
                FlowHubLoginAudit.event.ilike(pattern),
                FlowHubLoginAudit.username.ilike(pattern),
                FlowHubLoginAudit.ip_address.ilike(pattern),
            )
        )
    if dateFrom:
        login_query = login_query.filter(FlowHubLoginAudit.created_at >= dateFrom)
    if dateTo:
        login_query = login_query.filter(FlowHubLoginAudit.created_at <= dateTo)
    for resource in (source, channel):
        if resource:
            login_query = login_query.filter(
                FlowHubLoginAudit.ip_address.ilike(f"%{resource}%")
            )
    if category:
        category_events = [
            event for event, (_, _, mapped_category) in _EVENT_MAP.items()
            if mapped_category == category
        ]
        login_query = login_query.filter(
            FlowHubLoginAudit.event.in_(category_events or [""])
        )
    if severity:
        severity_events = [
            event for event, (_, level, _) in _EVENT_MAP.items() if level == severity
        ]
        login_query = login_query.filter(
            FlowHubLoginAudit.event.in_(severity_events or [""])
        )
    if not includeDebug:
        debug_events = [
            event for event, (_, level, _) in _EVENT_MAP.items() if level == "debug"
        ]
        login_query = login_query.filter(~FlowHubLoginAudit.event.in_(debug_events))

    unified_query = db.query(UnifiedAuditEntry, FlowHubUser.username).outerjoin(
        FlowHubUser, FlowHubUser.id == UnifiedAuditEntry.user_id
    )
    if username:
        unified_query = unified_query.filter(FlowHubUser.username == username)
    if search:
        pattern = f"%{search.strip()}%"
        unified_query = unified_query.filter(
            or_(
                UnifiedAuditEntry.event_type.ilike(pattern),
                UnifiedAuditEntry.reason.ilike(pattern),
                UnifiedAuditEntry.correlation_id.ilike(pattern),
            )
        )
    if dateFrom:
        unified_query = unified_query.filter(UnifiedAuditEntry.occurred_at >= dateFrom)
    if dateTo:
        unified_query = unified_query.filter(UnifiedAuditEntry.occurred_at <= dateTo)
    if source:
        unified_query = unified_query.filter(
            cast(UnifiedAuditEntry.metadata_json, String).ilike(f"%{source}%")
        )
    if channel:
        unified_query = unified_query.filter(
            UnifiedAuditEntry.channel_id.ilike(f"%{channel}%")
        )
    if category:
        unified_query = unified_query.filter(category == _UNIFIED_CATEGORY)
    if severity:
        unified_query = unified_query.filter(severity == _UNIFIED_LEVEL)

    # Business Observability events (Business Observability v1). The
    # projected `status`/`level` fields cannot be filtered in SQL (see
    # BusinessObservabilityService.list_events), so business events are
    # fetched up to a generous bound and filtered in Python, mirroring the
    # same field semantics applied to the two SQL-backed sources above.
    # Business events have no per-user actor, so a username filter excludes
    # them entirely rather than matching nothing field-by-field.
    business_shapes: list[BusinessEventShape] = (
        [] if username else BusinessObservabilityService(db).list_events(limit=1000)
    )
    if search:
        needle = search.strip().lower()
        business_shapes = [
            shape
            for shape in business_shapes
            if needle in shape.eventType.lower()
            or needle in shape.reasonMessage.lower()
            or needle in shape.reasonCode.lower()
            or needle in shape.correlationId.lower()
        ]
    if dateFrom:
        business_shapes = [shape for shape in business_shapes if shape.occurredAt >= dateFrom]
    if dateTo:
        business_shapes = [shape for shape in business_shapes if shape.occurredAt <= dateTo]
    if channel:
        needle = channel.lower()
        business_shapes = [
            shape
            for shape in business_shapes
            if needle in shape.primaryScope.scopeId.lower()
            or any(needle in scope.scopeId.lower() for scope in shape.secondaryScopes)
        ]
    if category:
        business_shapes = [
            shape
            for shape in business_shapes
            if _BUSINESS_EVENT_CATEGORY.get(shape.domain) == category
        ]
    if severity:
        business_shapes = [
            shape for shape in business_shapes if _business_event_level(shape) == severity
        ]

    total = login_query.count() + unified_query.count() + len(business_shapes)
    fetch_limit = offset + per_page
    login_rows: list[FlowHubLoginAudit] = (
        login_query
        .order_by(FlowHubLoginAudit.created_at.desc(), FlowHubLoginAudit.id.desc())
        .limit(fetch_limit)
        .all()
    )
    unified_rows: list[tuple[UnifiedAuditEntry, str | None]] = (
        unified_query.order_by(
            UnifiedAuditEntry.occurred_at.desc(), UnifiedAuditEntry.id.desc()
        )
        .limit(fetch_limit)
        .all()
    )
    merged = [_map_login_event(row) for row in login_rows]
    merged.extend(_map_unified_event(row, actor) for row, actor in unified_rows)
    merged.extend(_map_business_event(shape) for shape in business_shapes[:fetch_limit])
    merged.sort(key=lambda item: item["timestamp"] or "", reverse=True)

    return {
        "items": merged[offset : offset + per_page],
        "total": total,
        "page": page,
        "pageSize": per_page,
    }
