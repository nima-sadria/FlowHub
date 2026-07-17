"""Read-only business dashboard API."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.flowhub.auth.dependencies import get_current_user
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.dashboard.service import DashboardService
from app.flowhub.database import get_db

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/business-summary")  # type: ignore[untyped-decorator]
async def business_summary(
    _: Annotated[FlowHubUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    return DashboardService(db).business_summary()
