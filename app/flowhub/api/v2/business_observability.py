"""FlowHub Business Observability v1 API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.business_observability.contracts import (
    BusinessEventKpiShape,
    BusinessEventLifecycleActionRequest,
    BusinessEventLifecycleTransitionShape,
    BusinessEventListResponse,
    BusinessEventShape,
)
from app.flowhub.business_observability.errors import BusinessObservabilityError
from app.flowhub.business_observability.service import BusinessObservabilityService
from app.flowhub.database import get_db
from app.flowhub.unified_workspace.authorization import require_workspace_permission

router = APIRouter(prefix="/business-events", tags=["business-observability"])


def _service(db: Session = Depends(get_db)) -> BusinessObservabilityService:
    return BusinessObservabilityService(db)


@router.get("", response_model=BusinessEventListResponse)
async def list_business_events(
    _: Annotated[FlowHubUser, Depends(require_workspace_permission("audit.read"))],
    domain: str | None = None,
    severity: str | None = None,
    businessImpact: str | None = None,
    eventStatus: Annotated[str | None, Query(alias="status")] = None,
    correlationId: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    pageSize: Annotated[int, Query(ge=1, le=100)] = 20,
    service: BusinessObservabilityService = Depends(_service),
) -> BusinessEventListResponse:
    items = service.list_events(
        domain=domain,
        severity=severity,
        business_impact=businessImpact,
        status=eventStatus,
        correlation_id=correlationId,
        limit=page * pageSize,
    )
    offset = (page - 1) * pageSize
    return BusinessEventListResponse(
        items=items[offset : offset + pageSize],
        total=len(items),
        page=page,
        pageSize=pageSize,
    )


@router.get("/kpis", response_model=BusinessEventKpiShape)
async def business_event_kpis(
    _: Annotated[FlowHubUser, Depends(require_workspace_permission("audit.read"))],
    service: BusinessObservabilityService = Depends(_service),
) -> BusinessEventKpiShape:
    return service.kpis()


@router.get("/{event_id}", response_model=BusinessEventShape)
async def get_business_event(
    event_id: str,
    _: Annotated[FlowHubUser, Depends(require_workspace_permission("audit.read"))],
    service: BusinessObservabilityService = Depends(_service),
) -> BusinessEventShape:
    try:
        return service.get_event(event_id)
    except BusinessObservabilityError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, exc.code) from exc


@router.get("/{event_id}/lifecycle", response_model=list[BusinessEventLifecycleTransitionShape])
async def get_business_event_lifecycle(
    event_id: str,
    _: Annotated[FlowHubUser, Depends(require_workspace_permission("audit.read"))],
    service: BusinessObservabilityService = Depends(_service),
) -> list[BusinessEventLifecycleTransitionShape]:
    try:
        return service.lifecycle_history(event_id)
    except BusinessObservabilityError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, exc.code) from exc


@router.post("/{event_id}/acknowledge", response_model=BusinessEventShape)
async def acknowledge_business_event(
    event_id: str,
    body: BusinessEventLifecycleActionRequest,
    user: Annotated[FlowHubUser, Depends(require_workspace_permission("apply.execute"))],
    service: BusinessObservabilityService = Depends(_service),
) -> BusinessEventShape:
    try:
        row = service.acknowledge(event_id, actor=user.username, note=body.note)
    except BusinessObservabilityError as exc:
        raise _lifecycle_error(exc) from exc
    return service.shape(row)


@router.post("/{event_id}/resolve", response_model=BusinessEventShape)
async def resolve_business_event(
    event_id: str,
    body: BusinessEventLifecycleActionRequest,
    user: Annotated[FlowHubUser, Depends(require_workspace_permission("apply.execute"))],
    service: BusinessObservabilityService = Depends(_service),
) -> BusinessEventShape:
    try:
        row = service.resolve(event_id, actor=user.username, note=body.note)
    except BusinessObservabilityError as exc:
        raise _lifecycle_error(exc) from exc
    return service.shape(row)


def _lifecycle_error(exc: BusinessObservabilityError) -> HTTPException:
    if exc.code == "business_event_not_found":
        return HTTPException(status.HTTP_404_NOT_FOUND, exc.code)
    return HTTPException(status.HTTP_409_CONFLICT, exc.code)
