"""FlowHub Beta /api/v2/sources router.

Read-only source list backed by Integration Platform/Data Layer records.
This router never calls source systems directly.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.beta.auth.dependencies import get_current_user
from app.beta.auth.models import BetaUser
from app.beta.database import get_db
from app.beta.integration_platform.contracts import ConnectorSourceListResponse
from app.beta.integration_platform.service import IntegrationPlatformService

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=ConnectorSourceListResponse)
async def list_sources(
    _: BetaUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConnectorSourceListResponse:
    return IntegrationPlatformService(db).list_sources()
