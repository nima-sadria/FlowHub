"""Manual read endpoints for IncrementalReadEngine."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.flowhub.auth.dependencies import get_current_user
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import get_db
from app.flowhub.read_engine.manual import ManualReadService

router = APIRouter(prefix="/read", tags=["read"])


def _service(db: Session = Depends(get_db)) -> ManualReadService:
    return ManualReadService(db)


def _require_admin(user: FlowHubUser) -> None:
    if user.role not in {"owner", "super_admin", "admin"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin permission required.")


@router.post("/manual/{connector_id:path}")
async def run_manual_read(
    connector_id: str,
    user: FlowHubUser = Depends(get_current_user),
    service: ManualReadService = Depends(_service),
) -> dict:
    _require_admin(user)
    return await service.run_manual(connector_id, triggered_by=user.username)
