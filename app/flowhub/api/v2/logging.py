"""FlowHub Unified Logging Platform API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.flowhub.auth.dependencies import get_current_user
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import get_db
from app.flowhub.logging_platform.service import LoggingPlatformService

router = APIRouter(prefix="/logging", tags=["logging"])


def _service(db: Session = Depends(get_db)) -> LoggingPlatformService:
    return LoggingPlatformService(db)


def _require_admin(user: FlowHubUser) -> None:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin permission required.")


def _filters(
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
    severity: str | None = None,
    component: str | None = None,
    module: str | None = None,
    operation: str | None = None,
    category: str | None = None,
    connector: str | None = None,
    channel: str | None = None,
    user: str | None = None,
    correlation_id: str | None = None,
    request_id: str | None = None,
    result: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 50,
    sort: str = "-timestamp",
) -> dict:
    return {
        "from": from_,
        "to": to,
        "severity": severity,
        "component": component,
        "module": module,
        "operation": operation,
        "category": category,
        "connector": connector,
        "channel": channel,
        "user": user,
        "correlation_id": correlation_id,
        "request_id": request_id,
        "result": result,
        "search": search,
        "page": page,
        "page_size": page_size,
        "sort": sort,
    }


@router.get("/summary")
async def summary(
    filters: dict = Depends(_filters),
    _: FlowHubUser = Depends(get_current_user),
    service: LoggingPlatformService = Depends(_service),
) -> dict:
    return service.summary(filters)


@router.get("/logs")
async def logs(
    filters: dict = Depends(_filters),
    _: FlowHubUser = Depends(get_current_user),
    service: LoggingPlatformService = Depends(_service),
) -> dict:
    return service.search(filters)


@router.get("/logs/{log_id}")
async def log_detail(
    log_id: str,
    _: FlowHubUser = Depends(get_current_user),
    service: LoggingPlatformService = Depends(_service),
) -> dict:
    return service.detail(log_id)


@router.get("/correlations/{correlation_id}")
async def correlation(
    correlation_id: str,
    page: int = 1,
    page_size: int = 50,
    _: FlowHubUser = Depends(get_current_user),
    service: LoggingPlatformService = Depends(_service),
) -> dict:
    return service.correlation(correlation_id, page=page, page_size=page_size)


@router.get("/requests/{request_id}")
async def request_trace(
    request_id: str,
    _: FlowHubUser = Depends(get_current_user),
    service: LoggingPlatformService = Depends(_service),
) -> dict:
    return service.request_trace(request_id)


@router.post("/frontend")
async def frontend_ingest(
    body: dict,
    user: FlowHubUser = Depends(get_current_user),
    service: LoggingPlatformService = Depends(_service),
) -> dict:
    return service.ingest_frontend(body, username=user.username)


@router.post("/backend")
async def backend_ingest(
    body: dict,
    service: LoggingPlatformService = Depends(_service),
) -> dict:
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Backend log ingestion is internal-only and is disabled until internal auth exists.")


@router.get("/export")
async def export(
    filters: dict = Depends(_filters),
    format: str = "json",
    user: FlowHubUser = Depends(get_current_user),
    service: LoggingPlatformService = Depends(_service),
) -> Response:
    _require_admin(user)
    content_type, content = service.export({**filters, "format": format}, requested_by=user.username)
    return Response(content=content, media_type=content_type)


@router.get("/retention")
async def retention(
    _: FlowHubUser = Depends(get_current_user),
    service: LoggingPlatformService = Depends(_service),
) -> dict:
    return service.retention()


@router.put("/retention")
async def update_retention(
    body: dict,
    user: FlowHubUser = Depends(get_current_user),
    service: LoggingPlatformService = Depends(_service),
) -> dict:
    _require_admin(user)
    return service.update_retention(body, username=user.username)


@router.get("/live")
async def live(
    _: FlowHubUser = Depends(get_current_user),
    service: LoggingPlatformService = Depends(_service),
) -> dict:
    return service.live_contract()


@router.get("/redaction-policy")
async def redaction_policy(
    _: FlowHubUser = Depends(get_current_user),
    service: LoggingPlatformService = Depends(_service),
) -> dict:
    return service.redaction_policy()
