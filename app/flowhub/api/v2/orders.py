"""Normalized marketplace order API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.flowhub.auth.dependencies import get_current_user
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import get_db
from app.flowhub.orders.service import OrderSyncService

router = APIRouter(prefix="/orders", tags=["orders"])


def _service(db: Session = Depends(get_db)) -> OrderSyncService:
    return OrderSyncService(db)


def _require_admin(user: FlowHubUser) -> None:
    if user.role not in {"owner", "super_admin", "admin"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin permission required.")


@router.get("")
async def list_orders(
    page: int = 1,
    pageSize: int = 50,
    channelId: str | None = None,
    _: FlowHubUser = Depends(get_current_user),
    service: OrderSyncService = Depends(_service),
) -> dict:
    return service.list_orders(page=page, page_size=pageSize, channel_id=channelId)


@router.get("/{internal_id}")
async def get_order(
    internal_id: int,
    _: FlowHubUser = Depends(get_current_user),
    service: OrderSyncService = Depends(_service),
) -> dict:
    return service.get_order(internal_id)


@router.post("/channels/{channel_id}/process-tapsishop-webhooks")
async def process_tapsishop_webhooks(
    channel_id: str,
    user: FlowHubUser = Depends(get_current_user),
    service: OrderSyncService = Depends(_service),
) -> dict:
    _require_admin(user)
    result = await service.process_tapsishop_webhook_receipts(channel_id)
    return {
        "channelId": result.channel_id,
        "source": result.source,
        "processed": result.processed,
        "duplicates": result.duplicates,
        "effectsCreated": result.effects_created,
        "state": result.state,
        "canonicalInventoryMutated": False,
        "productPricesWritten": False,
    }
