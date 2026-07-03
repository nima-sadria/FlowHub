"""FlowHub /api/v2/sources router.

Read-only source list backed by Integration Platform/Data Layer records.
This router never calls source systems directly.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.flowhub.auth.dependencies import get_current_user
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import get_db
from app.flowhub.integration_platform.contracts import ConnectorSourceListResponse
from app.flowhub.integration_platform.service import IntegrationPlatformService

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=ConnectorSourceListResponse)
async def list_sources(
    _: FlowHubUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConnectorSourceListResponse:
    return IntegrationPlatformService(db).list_sources()
