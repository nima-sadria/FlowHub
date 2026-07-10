"""FlowHub /api/v2/workspace router.

Workspace preview is an explicit user-triggered source import. It may perform a
read-only Nextcloud download, then compares rows against the Data Layer product
cache. No Apply, Scheduler execution, automatic pricing, WooCommerce writes, or
Nextcloud writes are exposed here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.flowhub.auth.dependencies import get_current_user
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import get_db
from app.flowhub.integration_platform.contracts import WorkspaceIntegrationSummary, WorkspacePreviewResponse
from app.flowhub.integration_platform.service import IntegrationPlatformService
from app.flowhub.workspace.price_workflow import WorkspacePriceWorkflowService

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("", response_model=WorkspaceIntegrationSummary)
async def get_workspace_summary(
    _: FlowHubUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceIntegrationSummary:
    return IntegrationPlatformService(db).workspace_summary()


@router.get("/state")
async def get_state(
    _: FlowHubUser = Depends(get_current_user),
) -> dict:
    return {"state": "idle"}


@router.post("/preview", response_model=WorkspacePreviewResponse)
async def start_preview(
    user: FlowHubUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspacePreviewResponse:
    return await WorkspacePriceWorkflowService(db).preview_from_nextcloud(user)
