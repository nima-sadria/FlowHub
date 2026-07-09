"""FlowHub /api/v2/diagnostics router.

Diagnostics read Integration Platform contracts and Data Layer records only.
No live WooCommerce, Nextcloud, or direct httpx call is performed here.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.flowhub.auth.dependencies import get_current_user
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import get_db
from app.flowhub.integration_platform.service import IntegrationPlatformService
from app.flowhub.rate_limit.service import RateLimitService

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


class DiagnosticRunRequest(BaseModel):
    target: str = "all"


class DiagnosticCheckShape(BaseModel):
    check_name: str
    category: str
    target: str
    status: str
    failure_class: str
    severity: str
    message: str
    repair_hint: str
    duration_ms: float
    checked_at: str
    details: dict
    skipped_because: Optional[str]


class RepairStepShape(BaseModel):
    step_number: int
    description: str
    command: Optional[str]
    detail: Optional[str]


class DiagnosticRunResponse(BaseModel):
    target: str
    started_at: str
    completed_at: str
    duration_ms: float
    overall_status: str
    overall_failure_class: str
    overall_severity: str
    summary: str
    checks: list[DiagnosticCheckShape]
    repair_steps: list[RepairStepShape]


@router.get("/status")
async def diagnostics_status(
    _: FlowHubUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    service = IntegrationPlatformService(db)
    run = service.diagnostics_run("all")
    connector_status = service.list_instances()
    telemetry = service.telemetry(limit=20)
    rate_limits = RateLimitService(db).diagnostics()
    return {
        "overall_status": run["overall_status"],
        "checkedAt": run["completed_at"],
        "connectors": [item.model_dump() for item in connector_status.items],
        "telemetry": telemetry.model_dump(),
        "rateLimiter": rate_limits,
        "external_call_performed": False,
    }


@router.post("/run", response_model=DiagnosticRunResponse)
async def run_diagnostics(
    body: DiagnosticRunRequest,
    _: FlowHubUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DiagnosticRunResponse:
    return DiagnosticRunResponse(**IntegrationPlatformService(db).diagnostics_run(body.target))


@router.get("/history")
async def diagnostic_history(
    limit: int = 10,
    _: FlowHubUser = Depends(get_current_user),
) -> dict:
    return {"runs": [], "limit": limit, "external_call_performed": False}
