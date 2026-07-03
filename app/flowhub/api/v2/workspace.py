"""FlowHub /api/v2/workspace router.

Workspace reads are served from Integration Platform/Data Layer records. No
Apply, Scheduler execution, automatic pricing, WooCommerce writes, Nextcloud
writes, or live external connector calls are exposed here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.flowhub.auth.dependencies import get_current_user
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import get_db
from app.flowhub.integration_platform.contracts import WorkspaceIntegrationSummary, WorkspacePreviewResponse
from app.flowhub.integration_platform.service import IntegrationPlatformService

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
    _: FlowHubUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspacePreviewResponse:
    return IntegrationPlatformService(db).workspace_preview()
