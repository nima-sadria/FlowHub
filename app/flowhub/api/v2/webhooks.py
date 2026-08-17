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
    MAX_WOOCOMMERCE_WEBHOOK_BYTES,
    WOOCOMMERCE_PRODUCT_TOPICS,
    WebhookIngestionService,
    is_woocommerce_ping,
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


@router.post("/woocommerce/{channel_id}")
async def receive_woocommerce_webhook(
    channel_id: str,
    request: Request,
    wc_webhook_topic: str | None = Header(default=None, alias="X-WC-Webhook-Topic"),
    wc_webhook_resource: str | None = Header(default=None, alias="X-WC-Webhook-Resource"),
    wc_webhook_event: str | None = Header(default=None, alias="X-WC-Webhook-Event"),
    wc_webhook_signature: str | None = Header(default=None, alias="X-WC-Webhook-Signature"),
    wc_webhook_id: str | None = Header(default=None, alias="X-WC-Webhook-ID"),
    wc_webhook_delivery_id: str | None = Header(default=None, alias="X-WC-Webhook-Delivery-ID"),
    db: Session = Depends(get_db),
) -> JSONResponse:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_WOOCOMMERCE_WEBHOOK_BYTES:
                raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Webhook payload is too large.")
        except ValueError:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid Content-Length header.") from None

    service = WebhookIngestionService(db)
    # Lifecycle guard first: channel must exist, be a WooCommerce channel, and
    # be enabled, before any content-type, ping, or signature material is
    # even considered.
    service.authenticate_woocommerce(channel_id)

    if is_woocommerce_ping(
        topic=wc_webhook_topic,
        resource=wc_webhook_resource,
        event=wc_webhook_event,
        signature=wc_webhook_signature,
        webhook_id=wc_webhook_id,
        delivery_id=wc_webhook_delivery_id,
    ):
        # WooCommerce's "the first time you save a webhook as Active, it sends
        # a ping to the Delivery URL" handshake. It has no Content-Type and
        # none of the X-WC-Webhook-* headers, so it must never reach the
        # strict real-delivery checks below. It is acknowledged, not
        # processed: no receipt, no signature check, no product cache write,
        # no Business Event.
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"message": "WooCommerce webhook ping acknowledged.", "succeed": True},
        )

    content_type = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type != "application/json":
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Webhook payload must be application/json.")

    raw_body = await request.body()
    if len(raw_body) > MAX_WOOCOMMERCE_WEBHOOK_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Webhook payload is too large.")

    # Signature verification happens before any durable write and before the
    # body is parsed as JSON, mirroring the TapsiShop route's ordering.
    service.verify_woocommerce_signature(channel_id, raw_body, wc_webhook_signature)

    payload = parse_json_body(raw_body)

    topic = (wc_webhook_topic or wc_webhook_resource or wc_webhook_event or "").strip().lower()
    if topic not in WOOCOMMERCE_PRODUCT_TOPICS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unsupported webhook topic.")
    if not wc_webhook_id or not wc_webhook_delivery_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing webhook delivery identity headers.")

    try:
        accepted = service.accept_woocommerce_event(
            channel_id,
            topic,
            payload,
            raw_body,
            webhook_id=wc_webhook_id,
            delivery_id=wc_webhook_delivery_id,
        )
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
