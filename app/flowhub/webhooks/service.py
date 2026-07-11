"""Secure durable webhook ingestion service."""

from __future__ import annotations

import hmac
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.integration_platform.models import (
    IntegrationConnectorEvent,
    IntegrationConnectorInstance,
    IntegrationConnectorSetting,
)
from app.flowhub.security.redaction import redact_sensitive
from app.flowhub.webhooks.models import WebhookDeadLetter, WebhookProcessingAttempt, WebhookReceipt


MAX_TAPSISHOP_WEBHOOK_BYTES = 256 * 1024
WEBHOOK_RETENTION_DAYS = 90
MAX_PROCESSING_ATTEMPTS = 5
TRANSIENT_ERRORS = {"timeout", "rate_limit", "upstream_unavailable", "storage_unavailable", "temporary"}
PERMANENT_ERRORS = {"validation", "malformed_payload", "unsupported_event"}


@dataclass(frozen=True)
class AcceptedWebhook:
    receipt: WebhookReceipt
    duplicate: bool


class WebhookIngestionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def authenticate_tapsishop(self, channel_id: str, supplied_token: str | None) -> IntegrationConnectorInstance:
        instance = self.db.get(IntegrationConnectorInstance, channel_id)
        if instance is None or instance.connector_type != "tapsishop" or not instance.enabled:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook channel not found.")
        expected = self._secret_setting(channel_id, "webhook_token")
        if not expected or not supplied_token or not hmac.compare_digest(str(supplied_token), str(expected)):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Webhook authentication failed.")
        return instance

    def accept_tapsishop(self, channel_id: str, payload: dict, raw_body: bytes) -> AcceptedWebhook:
        normalized = normalize_tapsishop_payload(payload)
        provider_event_id = normalized["requestId"]
        existing = (
            self.db.query(WebhookReceipt)
            .filter_by(channel_id=channel_id, provider_event_id=provider_event_id)
            .first()
        )
        if existing is not None:
            self._record_event(
                channel_id,
                "webhook_duplicate",
                "Duplicate TapsiShop webhook requestId accepted without reprocessing.",
                {"provider_event_id": provider_event_id, "duplicate": True},
                commit=True,
            )
            return AcceptedWebhook(existing, duplicate=True)

        now = datetime.utcnow()
        receipt = WebhookReceipt(
            channel_id=channel_id,
            provider="tapsishop",
            provider_event_id=provider_event_id,
            payload_hash=sha256(raw_body).hexdigest(),
            payload_summary_json=payload_summary(normalized),
            normalized_event_json=normalized,
            received_at=now,
            acknowledged_at=now,
            processing_state="queued",
            attempt_count=0,
            retention_until=now + timedelta(days=WEBHOOK_RETENTION_DAYS),
        )
        self.db.add(receipt)
        self._record_event(
            channel_id,
            "webhook_accepted",
            "TapsiShop webhook was durably accepted. Business effects were not applied in the request handler.",
            {
                "provider": "tapsishop",
                "provider_event_id": provider_event_id,
                "payload_hash": receipt.payload_hash,
                "direct_business_effects": False,
                "queued_for_processing": True,
            },
            commit=False,
        )
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            duplicate = (
                self.db.query(WebhookReceipt)
                .filter_by(channel_id=channel_id, provider_event_id=provider_event_id)
                .first()
            )
            if duplicate is None:
                raise
            return AcceptedWebhook(duplicate, duplicate=True)
        self.db.refresh(receipt)
        return AcceptedWebhook(receipt, duplicate=False)

    def process_receipt(self, receipt_id: int, *, error_category: str | None = None, error_message: str | None = None) -> dict:
        receipt = self.db.get(WebhookReceipt, receipt_id)
        if receipt is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook receipt not found.")
        if receipt.processing_state == "processed":
            return self._receipt_shape(receipt)
        if receipt.processing_state == "dead_letter":
            raise HTTPException(status.HTTP_409_CONFLICT, "Dead-lettered webhook must be replayed before processing.")

        receipt.attempt_count += 1
        attempt_no = receipt.attempt_count
        if error_category:
            retryable = error_category in TRANSIENT_ERRORS and attempt_no < MAX_PROCESSING_ATTEMPTS
            next_attempt_at = datetime.utcnow() + _backoff(attempt_no) if retryable else None
            receipt.processing_state = "retry_scheduled" if retryable else "dead_letter"
            receipt.last_error_category = error_category
            receipt.next_attempt_at = next_attempt_at
            attempt = WebhookProcessingAttempt(
                receipt_id=receipt.id,
                channel_id=receipt.channel_id,
                provider=receipt.provider,
                attempt_number=attempt_no,
                state=receipt.processing_state,
                error_category=error_category,
                error_message=_safe_error(error_message or error_category),
                retryable=retryable,
                next_attempt_at=next_attempt_at,
            )
            self.db.add(attempt)
            if not retryable:
                self._dead_letter(receipt, error_category, error_message or error_category)
            self.db.commit()
            self.db.refresh(receipt)
            return self._receipt_shape(receipt)

        receipt.processing_state = "processed"
        receipt.processed_at = datetime.utcnow()
        receipt.last_error_category = None
        receipt.next_attempt_at = None
        self.db.add(WebhookProcessingAttempt(
            receipt_id=receipt.id,
            channel_id=receipt.channel_id,
            provider=receipt.provider,
            attempt_number=attempt_no,
            state="processed",
            retryable=False,
        ))
        self._record_event(
            receipt.channel_id,
            "webhook_normalized",
            "TapsiShop webhook was normalized into a channel event. Canonical inventory was not mutated.",
            {"provider_event_id": receipt.provider_event_id, "canonical_inventory_mutated": False},
            commit=False,
        )
        self.db.commit()
        self.db.refresh(receipt)
        return self._receipt_shape(receipt)

    def replay(self, receipt_id: int, user: FlowHubUser) -> dict:
        if user.role not in {"owner", "super_admin", "admin"}:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin permission required.")
        receipt = self.db.get(WebhookReceipt, receipt_id)
        if receipt is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook receipt not found.")
        if receipt.processing_state == "processed":
            return self._receipt_shape(receipt)
        receipt.processing_state = "queued"
        receipt.next_attempt_at = None
        self._record_event(
            receipt.channel_id,
            "webhook_replay_requested",
            "Webhook replay was requested by an administrator. Idempotency keys were preserved.",
            {"provider_event_id": receipt.provider_event_id, "actor": user.username},
            commit=False,
        )
        self.db.commit()
        self.db.refresh(receipt)
        return self._receipt_shape(receipt)

    def metrics(self, user: FlowHubUser, channel_id: str | None = None) -> dict:
        if user.role not in {"owner", "super_admin", "admin"}:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin permission required.")
        q = self.db.query(WebhookReceipt)
        if channel_id:
            q = q.filter(WebhookReceipt.channel_id == channel_id)
        receipts = q.all()
        dead = sum(1 for item in receipts if item.processing_state == "dead_letter")
        failed = sum(1 for item in receipts if item.processing_state in {"retry_scheduled", "dead_letter"})
        processed = [item for item in receipts if item.processed_at and item.received_at]
        latencies = [(item.processed_at - item.received_at).total_seconds() * 1000 for item in processed]
        duplicate_count = max(0, self.db.query(IntegrationConnectorEvent).filter_by(event_name="webhook_duplicate").count())
        return {
            "received": len(receipts),
            "accepted": len(receipts),
            "duplicate": duplicate_count,
            "failed": failed,
            "dead_letter": dead,
            "processing_latency_ms": {
                "avg": round(sum(latencies) / len(latencies), 2) if latencies else 0,
                "max": round(max(latencies), 2) if latencies else 0,
            },
        }

    def _secret_setting(self, channel_id: str, key: str) -> str | None:
        row = (
            self.db.query(IntegrationConnectorSetting)
            .filter_by(connector_id=channel_id, key=key, secret=True, configured=True)
            .first()
        )
        return str(row.value_json or "") if row else None

    def _dead_letter(self, receipt: WebhookReceipt, category: str, reason: str) -> None:
        if self.db.query(WebhookDeadLetter).filter_by(receipt_id=receipt.id).first() is not None:
            return
        self.db.add(WebhookDeadLetter(
            receipt_id=receipt.id,
            channel_id=receipt.channel_id,
            provider=receipt.provider,
            provider_event_id=receipt.provider_event_id,
            reason=_safe_error(reason),
            error_category=category,
        ))

    def _record_event(self, connector_id: str, event_name: str, message: str, metadata: dict, *, commit: bool) -> None:
        self.db.add(IntegrationConnectorEvent(
            connector_id=connector_id,
            event_name=event_name,
            severity="warning" if event_name.endswith("duplicate") else "info",
            message=message,
            metadata_json=redact_sensitive(metadata),
        ))
        if commit:
            self.db.commit()

    def _receipt_shape(self, receipt: WebhookReceipt) -> dict:
        return {
            "id": receipt.id,
            "channel_id": receipt.channel_id,
            "provider": receipt.provider,
            "provider_event_id": receipt.provider_event_id,
            "payload_hash": receipt.payload_hash,
            "received_at": _iso(receipt.received_at),
            "acknowledged_at": _iso(receipt.acknowledged_at),
            "processing_state": receipt.processing_state,
            "attempt_count": receipt.attempt_count,
            "last_error_category": receipt.last_error_category,
            "processed_at": _iso(receipt.processed_at),
            "next_attempt_at": _iso(receipt.next_attempt_at),
            "event": receipt.normalized_event_json,
        }


def parse_json_body(raw_body: bytes) -> dict:
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Malformed JSON payload.") from None
    if not isinstance(payload, dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Webhook payload must be a JSON object.")
    return payload


def normalize_tapsishop_payload(payload: dict[str, Any]) -> dict:
    order_detail = _dict(payload.get("orderDetail") or payload.get("order") or {})
    request_id = _required_str(payload.get("requestId") or order_detail.get("requestId"), "requestId")
    order_id = _required_str(payload.get("orderId") or order_detail.get("orderId") or order_detail.get("id"), "orderId")
    change_type = _required_int(payload.get("changeType") or order_detail.get("changeType"), "changeType")
    if change_type not in {1, 2}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unsupported TapsiShop changeType.")
    raw_items = payload.get("items") or order_detail.get("items") or order_detail.get("orderItems")
    if not isinstance(raw_items, list) or not raw_items:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "items are required.")
    items = [_normalize_item(item) for item in raw_items]
    return {
        "requestId": request_id,
        "orderId": order_id,
        "changeType": change_type,
        "changeTypeLabel": "deducted_due_to_purchase" if change_type == 1 else "added_due_to_cancellation",
        "occurredAt": _optional_str(payload.get("timestamp") or payload.get("createdAt") or order_detail.get("createdAt")),
        "orderDetail": {
            "orderId": order_id,
            "orderNumber": _optional_str(order_detail.get("orderNumber")),
            "effectiveDate": _optional_str(order_detail.get("effectiveDate")),
            "status": _optional_str(order_detail.get("orderStatusId") or order_detail.get("orderStatus")),
        },
        "items": items,
    }


def payload_summary(normalized: dict) -> dict:
    return {
        "requestId": normalized["requestId"],
        "orderId": normalized["orderId"],
        "changeType": normalized["changeType"],
        "changeTypeLabel": normalized["changeTypeLabel"],
        "itemCount": len(normalized["items"]),
        "items": [
            {
                "orderItemId": item.get("orderItemId"),
                "productId": item.get("productId"),
                "sku": item.get("sku"),
                "quantity": item.get("quantity"),
            }
            for item in normalized["items"]
        ],
    }


def _normalize_item(raw: Any) -> dict:
    item = _dict(raw)
    order_item_id = _required_str(item.get("orderItemId") or item.get("id"), "orderItemId")
    product_id = _optional_str(item.get("productId") or item.get("productID") or item.get("id"))
    sku = _optional_str(item.get("sku") or item.get("sellerSku"))
    if not product_id and not sku:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "productId or SKU is required for each item.")
    quantity = _required_number(item.get("quantity") or item.get("count"), "quantity")
    return {
        "orderItemId": order_item_id,
        "productId": product_id,
        "sku": sku,
        "quantity": quantity,
        "price": _optional_number(item.get("price") or item.get("finalPrice") or item.get("originalPrice")),
        "timestamp": _optional_str(item.get("timestamp") or item.get("updatedAt")),
    }


def _dict(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid webhook payload schema.")


def _required_str(value: Any, field: str) -> str:
    if value is None or str(value).strip() == "":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{field} is required.")
    return str(value).strip()


def _optional_str(value: Any) -> str | None:
    return None if value in (None, "") else str(value)


def _required_int(value: Any, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{field} must be an integer.") from None


def _required_number(value: Any, field: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{field} must be numeric.") from None
    if not math.isfinite(parsed) or parsed < 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{field} must be non-negative.")
    return parsed


def _optional_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return _required_number(value, "price")


def _backoff(attempt_no: int) -> timedelta:
    return timedelta(seconds=min(300, 2 ** max(0, attempt_no - 1)))


def _safe_error(value: str) -> str:
    return str(redact_sensitive({"error": value})["error"])[:500]


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None
