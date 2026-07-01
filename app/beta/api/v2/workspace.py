"""FlowHub Beta /api/v2/workspace router.

Workspace reads are served from Integration Platform/Data Layer records. No
Apply, Scheduler execution, automatic pricing, WooCommerce writes, Nextcloud
writes, or live external connector calls are exposed here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.beta.auth.dependencies import get_current_user
from app.beta.auth.models import BetaUser
from app.beta.database import get_db
from app.beta.integration_platform.contracts import WorkspaceIntegrationSummary, WorkspacePreviewResponse
from app.beta.integration_platform.service import IntegrationPlatformService

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("", response_model=WorkspaceIntegrationSummary)
async def get_workspace_summary(
    _: BetaUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceIntegrationSummary:
    return IntegrationPlatformService(db).workspace_summary()


@router.get("/state")
async def get_state(
    _: BetaUser = Depends(get_current_user),
) -> dict:
    return {"state": "idle"}


@router.post("/preview", response_model=WorkspacePreviewResponse)
async def start_preview(
    _: BetaUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspacePreviewResponse:
    return IntegrationPlatformService(db).workspace_preview()
