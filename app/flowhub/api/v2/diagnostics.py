# ruff: noqa: B008
"""FlowHub /api/v2/diagnostics router.

Diagnostics read Integration Platform contracts and Data Layer records only.
No live WooCommerce, Nextcloud, or direct httpx call is performed here.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.flowhub.auth.dependencies import get_current_user
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.data_layer.models import DlSourceSnapshot
from app.flowhub.database import get_db
from app.flowhub.diagnostics.channel_health import ChannelHealthReporter
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
    details: dict[str, Any]
    skipped_because: str | None


class RepairStepShape(BaseModel):
    step_number: int
    description: str
    command: str | None
    detail: str | None


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
) -> dict[str, Any]:
    service = IntegrationPlatformService(db)
    run = service.diagnostics_run("all")
    connector_status = service.list_instances_contract()
    source_last_reads = {
        connector_id: last_read
        for connector_id, last_read in (
            db.query(DlSourceSnapshot.connector_id, func.max(DlSourceSnapshot.snapshotted_at))
            .group_by(DlSourceSnapshot.connector_id)
            .all()
        )
    }
    connectors = [
        {
            **item,
            "last_successful_operation": (
                source_last_reads[item["id"]].isoformat() + "Z"
                if item["id"] in source_last_reads
                else None
            ),
        }
        for item in connector_status["items"]
    ]
    channel_health = ChannelHealthReporter(db).report()
    telemetry = service.telemetry(limit=20)
    telemetry_contract = service.telemetry_contract(limit=20)
    rate_limits = RateLimitService(db).diagnostics()
    return {
        "overall_status": run["overall_status"],
        "checkedAt": run["completed_at"],
        "checks": run["checks"],
        "connectors": connectors,
        "channelHealth": channel_health,
        "telemetry": telemetry.model_dump(),
        "telemetryContract": telemetry_contract,
        "rateLimiter": rate_limits,
        "external_call_performed": False,
    }


def _require_admin(user: FlowHubUser) -> None:
    if user.role not in {"owner", "super_admin", "admin"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin permission required.")


@router.get("/channels/health")
async def channel_health(
    _: FlowHubUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return ChannelHealthReporter(db).report()


@router.post("/channels/health/refresh")
async def refresh_channel_health(
    body: dict[str, Any] | None = None,
    user: FlowHubUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_admin(user)
    channel_id = str((body or {}).get("channelId") or "").strip() or None
    return await ChannelHealthReporter(db).refresh(channel_id)


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
) -> dict[str, Any]:
    return {"runs": [], "limit": limit, "external_call_performed": False}
