"""Commerce Hub API.

Product-facing Sources and Channels surface. All operations are local,
read-only with respect to external systems, and runtime writes remain blocked.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.flowhub.auth.dependencies import get_current_user
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.commerce.service import CommerceHubService
from app.flowhub.database import get_db

router = APIRouter(prefix="/commerce", tags=["commerce"])


def _service(db: Session = Depends(get_db)) -> CommerceHubService:
    return CommerceHubService(db)


def _require_admin(user: FlowHubUser) -> None:
    if user.role not in {"owner", "super_admin", "admin"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin permission required.")


@router.get("/sources")
async def list_sources(
    _: FlowHubUser = Depends(get_current_user),
    service: CommerceHubService = Depends(_service),
) -> dict:
    return service.list_sources()


@router.get("/source-types")
async def list_source_types(
    _: FlowHubUser = Depends(get_current_user),
    service: CommerceHubService = Depends(_service),
) -> dict:
    return service.list_source_types()


@router.get("/sources/{source_id}")
async def get_source_detail(
    source_id: str,
    _: FlowHubUser = Depends(get_current_user),
    service: CommerceHubService = Depends(_service),
) -> dict:
    return service.get_source(source_id)


@router.post("/sources/{source_id}/test")
async def test_source_connection(
    source_id: str,
    user: FlowHubUser = Depends(get_current_user),
    service: CommerceHubService = Depends(_service),
) -> dict:
    _require_admin(user)
    return await service.test_source_connection(source_id)


@router.post("/sources/{source_id}/browse")
async def browse_source_files(
    source_id: str,
    body: dict,
    user: FlowHubUser = Depends(get_current_user),
    service: CommerceHubService = Depends(_service),
) -> dict:
    _require_admin(user)
    return await service.browse_source_files(source_id, body)


@router.post("/sources/{source_id}/read")
async def read_source_now(
    source_id: str,
    user: FlowHubUser = Depends(get_current_user),
    service: CommerceHubService = Depends(_service),
) -> dict:
    _require_admin(user)
    return await service.read_source_now(source_id, user.username, user.id)


@router.put("/sources/{source_id}/settings")
async def update_source_settings(
    source_id: str,
    body: dict,
    user: FlowHubUser = Depends(get_current_user),
    service: CommerceHubService = Depends(_service),
) -> dict:
    _require_admin(user)
    return service.update_source_settings(source_id, body)


@router.get("/channels")
async def list_channels(
    _: FlowHubUser = Depends(get_current_user),
    service: CommerceHubService = Depends(_service),
) -> dict:
    return service.list_channels()


@router.get("/channel-types")
async def list_channel_types(
    _: FlowHubUser = Depends(get_current_user),
    service: CommerceHubService = Depends(_service),
) -> dict:
    return service.list_channel_types()


@router.get("/channels/{channel_id}")
async def get_channel_detail(
    channel_id: str,
    _: FlowHubUser = Depends(get_current_user),
    service: CommerceHubService = Depends(_service),
) -> dict:
    return service.get_channel(channel_id)


@router.post("/channels/{channel_id}/test")
async def test_channel_connection(
    channel_id: str,
    user: FlowHubUser = Depends(get_current_user),
    service: CommerceHubService = Depends(_service),
) -> dict:
    _require_admin(user)
    return await service.test_channel_connection(channel_id)


@router.post("/channels/{channel_id}/refresh-cache")
async def refresh_channel_cache(
    channel_id: str,
    user: FlowHubUser = Depends(get_current_user),
    service: CommerceHubService = Depends(_service),
) -> dict:
    _require_admin(user)
    return await service.refresh_channel_cache(channel_id, user.username)


@router.get("/channels/{channel_id}/health")
async def get_channel_health(
    channel_id: str,
    _: FlowHubUser = Depends(get_current_user),
    service: CommerceHubService = Depends(_service),
) -> dict:
    return service.get_channel_health(channel_id)


@router.get("/channels/{channel_id}/capabilities")
async def get_channel_capabilities(
    channel_id: str,
    _: FlowHubUser = Depends(get_current_user),
    service: CommerceHubService = Depends(_service),
) -> dict:
    return service.get_channel_capabilities(channel_id)


@router.put("/channels/{channel_id}/settings")
async def update_channel_settings(
    channel_id: str,
    body: dict,
    user: FlowHubUser = Depends(get_current_user),
    service: CommerceHubService = Depends(_service),
) -> dict:
    _require_admin(user)
    return service.update_channel_settings(channel_id, body)
