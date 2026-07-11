"""Marketplace webhook ingestion endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.flowhub.auth.dependencies import get_current_user
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import get_db
from app.flowhub.webhooks.service import (
    MAX_TAPSISHOP_WEBHOOK_BYTES,
    WebhookIngestionService,
    parse_json_body,
)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/tapsishop/{channel_id}")
async def receive_tapsishop_webhook(
    channel_id: str,
    request: Request,
    tapsishop_webhook_authorization: str | None = Header(default=None, alias="TapsiShop.Hub.Webhook-Authorization"),
    db: Session = Depends(get_db),
) -> JSONResponse:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_TAPSISHOP_WEBHOOK_BYTES:
                raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Webhook payload is too large.")
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid Content-Length header.") from None
    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type != "application/json":
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Webhook payload must be application/json.")

    raw_body = await request.body()
    if len(raw_body) > MAX_TAPSISHOP_WEBHOOK_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Webhook payload is too large.")
    payload = parse_json_body(raw_body)
    service = WebhookIngestionService(db)
    service.authenticate_tapsishop(channel_id, tapsishop_webhook_authorization)
    try:
        accepted = service.accept_tapsishop(channel_id, payload, raw_body)
    except SQLAlchemyError:
        db.rollback()
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"message": "Webhook could not be durably accepted.", "succeed": False},
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "message": "Webhook accepted." if not accepted.duplicate else "Webhook already accepted.",
            "succeed": True,
        },
    )


@router.get("/metrics")
async def webhook_metrics(
    channel_id: str | None = None,
    user: FlowHubUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return WebhookIngestionService(db).metrics(user, channel_id=channel_id)


@router.post("/{receipt_id}/replay")
async def replay_webhook(
    receipt_id: int,
    user: FlowHubUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return WebhookIngestionService(db).replay(receipt_id, user)
