"""FlowHub Write Pipeline API."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.flowhub.auth.dependencies import get_current_user
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import get_db
from app.flowhub.maintenance import require_write_operation_available
from app.flowhub.write_pipeline.contracts import (
    WritePipelineApprovalRequest,
    WritePipelineBatchShape,
    WritePipelineDryRunRequest,
    WritePipelineEventShape,
)
from app.flowhub.write_pipeline.service import WritePipelineService

router = APIRouter(prefix="/write-pipeline", tags=["write-pipeline"])


def _service(db: Session = Depends(get_db)) -> WritePipelineService:
    return WritePipelineService(db)


@router.post("/dry-run", response_model=WritePipelineBatchShape, status_code=201)
async def create_dry_run(
    body: WritePipelineDryRunRequest,
    user: FlowHubUser = Depends(require_write_operation_available),
    service: WritePipelineService = Depends(_service),
) -> WritePipelineBatchShape:
    return service.create_dry_run(body, user)


@router.get("/batches/{batch_id}", response_model=WritePipelineBatchShape)
async def get_batch(
    batch_id: str,
    _: FlowHubUser = Depends(get_current_user),
    service: WritePipelineService = Depends(_service),
) -> WritePipelineBatchShape:
    return service.get_batch(batch_id)


@router.post("/batches/{batch_id}/approve", response_model=WritePipelineBatchShape)
async def approve_batch(
    batch_id: str,
    body: WritePipelineApprovalRequest,
    user: FlowHubUser = Depends(require_write_operation_available),
    service: WritePipelineService = Depends(_service),
) -> WritePipelineBatchShape:
    return service.approve(batch_id, body, user)


@router.post("/batches/{batch_id}/execute", response_model=WritePipelineBatchShape)
async def execute_batch(
    batch_id: str,
    user: FlowHubUser = Depends(require_write_operation_available),
    service: WritePipelineService = Depends(_service),
) -> WritePipelineBatchShape:
    return await service.execute(batch_id, user)


@router.get("/batches/{batch_id}/events", response_model=list[WritePipelineEventShape])
async def get_batch_events(
    batch_id: str,
    _: FlowHubUser = Depends(get_current_user),
    service: WritePipelineService = Depends(_service),
) -> list[WritePipelineEventShape]:
    return service.list_events(batch_id)
