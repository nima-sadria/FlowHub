"""Normalized marketplace order API."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.connectors.destinations.woocommerce.auth import WooCommerceCredentials
from app.flowhub.auth.dependencies import get_current_user
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.channels.woocommerce import WooCommerceOrderConnector
from app.flowhub.database import get_db
from app.flowhub.integration_platform.models import IntegrationConnectorInstance
from app.flowhub.orders.models import OrderSyncCheckpoint
from app.flowhub.orders.service import OrderSyncService

router = APIRouter(prefix="/orders", tags=["orders"])


def _service(db: Annotated[Session, Depends(get_db)]) -> OrderSyncService:
    return OrderSyncService(db)


def _require_operator(user: FlowHubUser) -> None:
    if user.role not in {"owner", "super_admin", "admin", "operator"}:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Operational permission required."
        )


def _require_admin(user: FlowHubUser) -> None:
    if user.role not in {"owner", "super_admin", "admin"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin permission required.")


@router.get("")
async def list_orders(
    _: Annotated[FlowHubUser, Depends(get_current_user)],
    service: Annotated[OrderSyncService, Depends(_service)],
    page: int = 1,
    pageSize: int = 50,
    channelId: str | None = None,
    status: str | None = None,
    search: str | None = None,
    dateFrom: str | None = None,
    dateTo: str | None = None,
) -> dict[str, Any]:
    return service.list_orders(
        page=page,
        page_size=pageSize,
        channel_id=channelId,
        normalized_status=status,
        search=search,
        date_from=dateFrom,
        date_to=dateTo,
    )


@router.get("/sync-status")
async def get_order_sync_status(
    _: Annotated[FlowHubUser, Depends(get_current_user)],
    service: Annotated[OrderSyncService, Depends(_service)],
) -> dict[str, Any]:
    rows = (
        service.db.query(IntegrationConnectorInstance)
        .filter(
            IntegrationConnectorInstance.connector_type.in_(
                ("woocommerce", "snappshop", "tapsishop")
            )
        )
        .order_by(IntegrationConnectorInstance.name.asc())
        .all()
    )
    items: list[dict[str, Any]] = []
    for row in rows:
        checkpoint = (
            service.db.query(OrderSyncCheckpoint)
            .filter_by(channel_id=row.id, source="reconciliation")
            .first()
        )
        if not row.enabled:
            state = "disabled"
        elif checkpoint and checkpoint.last_failure_at and (
            checkpoint.last_success_at is None
            or checkpoint.last_failure_at > checkpoint.last_success_at
        ):
            state = "error"
        elif checkpoint and checkpoint.last_success_at:
            state = "ready"
        else:
            state = "never_run"
        items.append(
            {
                "channelId": row.id,
                "connectorType": row.connector_type,
                "displayName": row.name,
                "enabled": row.enabled,
                "state": state,
                "lastRunAt": _iso(checkpoint.last_run_at if checkpoint else None),
                "lastSuccessAt": _iso(
                    checkpoint.last_success_at if checkpoint else None
                ),
                "lastFailureAt": _iso(
                    checkpoint.last_failure_at if checkpoint else None
                ),
                "failureCategory": (
                    checkpoint.last_failure_category if checkpoint else None
                ),
            }
        )
    return {"items": items}


@router.post("/channels/{channel_id}/sync")
async def synchronize_channel_orders(
    channel_id: str,
    user: Annotated[FlowHubUser, Depends(get_current_user)],
    service: Annotated[OrderSyncService, Depends(_service)],
) -> dict[str, Any]:
    """Run one explicit read-only order reconciliation."""
    _require_operator(user)
    channel = service.db.get(IntegrationConnectorInstance, channel_id)
    if channel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel not found.")
    if not channel.enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Channel is disabled.")
    if channel.connector_type != "woocommerce":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Manual order synchronization is not available for this channel.",
        )
    settings = {
        item.key: item.value_json for item in channel.settings if item.configured
    }
    url = str(settings.get("url") or "").strip()
    key = str(settings.get("key") or "").strip()
    secret = str(settings.get("secret") or "").strip()
    if not all((url, key, secret)):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "WooCommerce order synchronization is not configured.",
        )
    connector = WooCommerceOrderConnector(
        channel_id=channel.id,
        credentials=WooCommerceCredentials(
            url=url.rstrip("/"),
            key=key,
            secret=secret,
        ),
    )
    result = await service.reconcile_recent_orders(
        channel.id,
        connector,
        page_size=50,
    )
    return {
        "channelId": result.channel_id,
        "source": result.source,
        "processed": result.processed,
        "duplicates": result.duplicates,
        "state": result.state,
        "canonicalInventoryMutated": False,
        "productPricesWritten": False,
        "providerMutationPerformed": False,
    }


@router.post("/channels/{channel_id}/process-tapsishop-webhooks")
async def process_tapsishop_webhooks(
    channel_id: str,
    user: Annotated[FlowHubUser, Depends(get_current_user)],
    service: Annotated[OrderSyncService, Depends(_service)],
) -> dict[str, Any]:
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


@router.get("/{internal_id}")
async def get_order(
    internal_id: int,
    _: Annotated[FlowHubUser, Depends(get_current_user)],
    service: Annotated[OrderSyncService, Depends(_service)],
) -> dict[str, Any]:
    return service.get_order(internal_id)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
