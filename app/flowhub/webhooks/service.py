"""Secure durable webhook ingestion service."""

from __future__ import annotations

import base64
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.connectors.destinations.woocommerce.auth import (
    WOOCOMMERCE_WEBHOOK_SECRET_APP_CONFIG_KEY,
    WOOCOMMERCE_WEBHOOK_SECRET_SETTING_KEY,
)
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.business_observability.service import BusinessObservabilityService
from app.flowhub.channels.tapsishop import (
    normalize_tapsishop_webhook_payload,
    summarize_tapsishop_webhook,
)
from app.flowhub.integration_platform.models import (
    IntegrationConnectorEvent,
    IntegrationConnectorInstance,
    IntegrationConnectorSetting,
)
from app.flowhub.security.redaction import redact_sensitive
from app.flowhub.setup.service import AppConfigService
from app.flowhub.webhooks.models import (
    WebhookDeadLetter,
    WebhookProcessingAttempt,
    WebhookProviderEventIdentity,
    WebhookReceipt,
)


MAX_TAPSISHOP_WEBHOOK_BYTES = 256 * 1024
MAX_WOOCOMMERCE_WEBHOOK_BYTES = 256 * 1024
WEBHOOK_RETENTION_DAYS = 90
MAX_PROCESSING_ATTEMPTS = 5
TRANSIENT_ERRORS = {"timeout", "rate_limit", "upstream_unavailable", "storage_unavailable", "temporary"}
PERMANENT_ERRORS = {"validation", "malformed_payload", "unsupported_event"}

# WooCommerce core product webhook topics supported in Phase 1. Orders,
# customers, and product.restored (not a WooCommerce core topic) are
# explicitly out of scope; any other topic is rejected before durable
# acceptance.
WOOCOMMERCE_PRODUCT_TOPICS = frozenset({"product.created", "product.updated", "product.deleted"})


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
        provider_event_ids = normalized["requestIds"]
        existing = self._matching_tapsishop_receipt(channel_id, provider_event_ids)
        if existing is not None:
            self._record_event(
                channel_id,
                "webhook_duplicate",
                "Duplicate TapsiShop webhook requestId accepted without reprocessing.",
                {"provider_event_id": provider_event_id, "duplicate": True},
                commit=True,
            )
            return AcceptedWebhook(existing, duplicate=True)

        now = datetime.now(timezone.utc).replace(tzinfo=None)
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
        try:
            # flush() (not just commit()) can be where the unique constraint
            # actually fires, since it issues the INSERT immediately to
            # populate receipt.id for the identity rows below. Both must be
            # covered by the same duplicate-race recovery.
            self.db.flush()
            self.db.add_all(
                [
                    WebhookProviderEventIdentity(
                        receipt_id=receipt.id,
                        channel_id=channel_id,
                        provider="tapsishop",
                        provider_event_id=item_event_id,
                        created_at=now,
                    )
                    for item_event_id in provider_event_ids
                ]
            )
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
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            duplicate = self._matching_tapsishop_receipt(channel_id, provider_event_ids)
            if duplicate is None:
                raise
            return AcceptedWebhook(duplicate, duplicate=True)
        self.db.refresh(receipt)
        return AcceptedWebhook(receipt, duplicate=False)

    def _matching_tapsishop_receipt(
        self,
        channel_id: str,
        provider_event_ids: list[str],
    ) -> WebhookReceipt | None:
        identities = (
            self.db.query(WebhookProviderEventIdentity)
            .filter(
                WebhookProviderEventIdentity.channel_id == channel_id,
                WebhookProviderEventIdentity.provider_event_id.in_(provider_event_ids),
            )
            .all()
        )
        if not identities and len(provider_event_ids) == 1:
            # Compatibility with receipts stored before item-level identities existed.
            return (
                self.db.query(WebhookReceipt)
                .filter_by(channel_id=channel_id, provider_event_id=provider_event_ids[0])
                .first()
            )
        if not identities:
            return None
        matched_ids = {identity.provider_event_id for identity in identities}
        receipt_ids = {identity.receipt_id for identity in identities}
        if matched_ids == set(provider_event_ids) and len(receipt_ids) == 1:
            return self.db.get(WebhookReceipt, next(iter(receipt_ids)))
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "TapsiShop webhook contains a partially duplicated requestId batch.",
        )

    def authenticate_woocommerce(self, channel_id: str) -> IntegrationConnectorInstance:
        """Lifecycle guard only. Signature verification happens separately,
        against the raw request body, in verify_woocommerce_signature."""
        instance = self.db.get(IntegrationConnectorInstance, channel_id)
        if instance is None or instance.connector_type != "woocommerce" or not instance.enabled:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Webhook channel not found.")
        return instance

    def verify_woocommerce_signature(self, channel_id: str, raw_body: bytes, supplied_signature: str | None) -> None:
        secret = self._secret_setting(channel_id, WOOCOMMERCE_WEBHOOK_SECRET_SETTING_KEY)
        if not secret or not supplied_signature:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Webhook authentication failed.")
        if not woocommerce_signature_matches(secret, raw_body, supplied_signature):
            self._emit_business_event(
                channel_id,
                event_type="woocommerce_webhook_signature_rejected",
                severity="warning",
                business_impact="degraded",
                reason_code="signature_mismatch",
                reason_message="WooCommerce webhook signature did not match the configured webhook secret.",
            )
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Webhook authentication failed.")

    def accept_woocommerce_event(
        self,
        channel_id: str,
        topic: str,
        payload: dict,
        raw_body: bytes,
        *,
        webhook_id: str,
        delivery_id: str,
    ) -> AcceptedWebhook:
        provider_event_id = f"{webhook_id}:{delivery_id}"
        existing = (
            self.db.query(WebhookReceipt)
            .filter_by(channel_id=channel_id, provider="woocommerce", provider_event_id=provider_event_id)
            .first()
        )
        if existing is not None:
            self._record_event(
                channel_id,
                "webhook_duplicate",
                "Duplicate WooCommerce webhook delivery accepted without reprocessing.",
                {"provider_event_id": provider_event_id, "duplicate": True, "topic": topic},
                commit=True,
            )
            self._emit_business_event(
                channel_id,
                event_type="woocommerce_webhook_duplicate",
                severity="info",
                business_impact="none",
                reason_code="duplicate_delivery",
                reason_message=f"Duplicate WooCommerce {topic} webhook delivery was acknowledged without reprocessing.",
                metadata={"topic": topic},
            )
            return AcceptedWebhook(existing, duplicate=True)

        normalized = normalize_woocommerce_product_payload(topic, payload)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        receipt = WebhookReceipt(
            channel_id=channel_id,
            provider="woocommerce",
            provider_event_id=provider_event_id,
            payload_hash=sha256(raw_body).hexdigest(),
            payload_summary_json={
                "topic": topic,
                "wc_product_id": normalized.get("wc_product_id"),
                "sku": normalized.get("sku"),
            },
            normalized_event_json=normalized,
            received_at=now,
            acknowledged_at=now,
            processing_state="queued",
            attempt_count=0,
            retention_until=now + timedelta(days=WEBHOOK_RETENTION_DAYS),
        )
        self.db.add(receipt)
        try:
            # flush() (not just commit()) can be where the unique constraint
            # actually fires, since it issues the INSERT immediately to
            # populate receipt.id for the identity row below. Both must be
            # covered by the same duplicate-race recovery.
            self.db.flush()
            self.db.add(
                WebhookProviderEventIdentity(
                    receipt_id=receipt.id,
                    channel_id=channel_id,
                    provider="woocommerce",
                    provider_event_id=provider_event_id,
                    created_at=now,
                )
            )
            self._record_event(
                channel_id,
                "webhook_accepted",
                "WooCommerce webhook was durably accepted. Business effects were not applied in the request handler.",
                {
                    "provider": "woocommerce",
                    "provider_event_id": provider_event_id,
                    "topic": topic,
                    "payload_hash": receipt.payload_hash,
                    "direct_business_effects": False,
                    "queued_for_processing": True,
                },
                commit=False,
            )
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            duplicate = (
                self.db.query(WebhookReceipt)
                .filter_by(channel_id=channel_id, provider="woocommerce", provider_event_id=provider_event_id)
                .first()
            )
            if duplicate is None:
                raise
            return AcceptedWebhook(duplicate, duplicate=True)
        self.db.refresh(receipt)
        self._emit_business_event(
            channel_id,
            event_type="woocommerce_webhook_received",
            severity="info",
            business_impact="none",
            reason_code="webhook_accepted",
            reason_message=f"WooCommerce {topic} webhook was durably accepted for asynchronous processing.",
            metadata={"topic": topic, "wc_product_id": normalized.get("wc_product_id")},
        )
        return AcceptedWebhook(receipt, duplicate=False)

    def pending_woocommerce_receipt_ids(self, channel_id: str, *, limit: int = 200) -> list[int]:
        """Queued/retryable WooCommerce receipts whose retry backoff (if any)
        has elapsed. Used by the out-of-band processor, never by the request
        handler."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        rows = (
            self.db.query(WebhookReceipt)
            .with_entities(WebhookReceipt.id)
            .filter(
                WebhookReceipt.channel_id == channel_id,
                WebhookReceipt.provider == "woocommerce",
                WebhookReceipt.processing_state.in_(["queued", "retry_scheduled"]),
            )
            .filter((WebhookReceipt.next_attempt_at.is_(None)) | (WebhookReceipt.next_attempt_at <= now))
            .order_by(WebhookReceipt.received_at.asc(), WebhookReceipt.id.asc())
            .limit(limit)
            .all()
        )
        return [row_id for (row_id,) in rows]

    def mark_woocommerce_receipt_processed(self, receipt_id: int) -> dict:
        result = self.process_receipt(receipt_id)
        receipt = self.db.get(WebhookReceipt, receipt_id)
        if receipt is not None:
            topic = (receipt.normalized_event_json or {}).get("topic", "unknown")
            self._emit_business_event(
                receipt.channel_id,
                event_type="woocommerce_product_event_processed",
                severity="info",
                business_impact="none",
                reason_code="product_cache_refreshed",
                reason_message=(
                    f"WooCommerce {topic} webhook was processed by refreshing the channel product cache "
                    "through the existing polling entrypoint."
                ),
                metadata={"topic": topic, "receipt_id": receipt_id},
            )
        return result

    def mark_woocommerce_receipt_failed(self, receipt_id: int, error_category: str, error_message: str) -> dict:
        result = self.process_receipt(receipt_id, error_category=error_category, error_message=error_message)
        receipt = self.db.get(WebhookReceipt, receipt_id)
        if receipt is not None:
            self._emit_business_event(
                receipt.channel_id,
                event_type="woocommerce_webhook_processing_failed",
                severity="error",
                business_impact="degraded",
                reason_code=error_category,
                reason_message=f"WooCommerce webhook processing failed: {error_message}",
                metadata={"receipt_id": receipt_id, "processing_state": result.get("processing_state")},
            )
        return result

    def _emit_business_event(
        self,
        channel_id: str,
        *,
        event_type: str,
        severity: str,
        business_impact: str,
        reason_code: str,
        reason_message: str,
        metadata: dict | None = None,
    ) -> None:
        BusinessObservabilityService(self.db).emit_event(
            domain="channels",
            event_type=event_type,
            severity=severity,
            business_impact=business_impact,
            reason_code=reason_code,
            reason_message=reason_message,
            primary_scope_type="channel",
            primary_scope_id=channel_id,
            producer="woocommerce_webhook_ingestion",
            metadata=redact_sensitive(metadata or {}),
        )

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
            next_attempt_at = datetime.now(timezone.utc).replace(tzinfo=None) + _backoff(attempt_no) if retryable else None
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
        receipt.processed_at = datetime.now(timezone.utc).replace(tzinfo=None)
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
            f"{receipt.provider} webhook was normalized into a channel event. Canonical inventory was not mutated.",
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
        if channel_id == "tapsishop:main" and key == "webhook_token":
            configured = AppConfigService(self.db).get("tapsishop.webhook_token")
            if configured:
                return configured
        if channel_id == "woocommerce:primary" and key == WOOCOMMERCE_WEBHOOK_SECRET_SETTING_KEY:
            configured = AppConfigService(self.db).get(WOOCOMMERCE_WEBHOOK_SECRET_APP_CONFIG_KEY)
            if configured:
                return configured
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
    try:
        return normalize_tapsishop_webhook_payload(payload)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


def payload_summary(normalized: dict) -> dict:
    return summarize_tapsishop_webhook(normalized)


def woocommerce_signature_matches(secret: str, raw_body: bytes, supplied_signature: str | None) -> bool:
    """WooCommerce signs webhooks with base64(HMAC-SHA256(raw_body, secret)),
    NOT the hex digest used by integration_platform/service.py's generic
    webhook verifier. Comparison is constant-time."""
    if not supplied_signature:
        return False
    computed = base64.b64encode(hmac.new(secret.encode("utf-8"), raw_body, sha256).digest()).decode("ascii")
    try:
        return hmac.compare_digest(computed, supplied_signature.strip())
    except TypeError:
        return False


def normalize_woocommerce_product_payload(topic: str, payload: dict[str, Any]) -> dict:
    """Minimal normalized shape for a WooCommerce product webhook event.

    This does NOT upsert into the product cache. It only records what the
    webhook told us so the out-of-band processor (which reuses the existing
    polling/upsert path) can log what triggered the refresh. The actual
    cache write always goes through the same WooCommerceProductReadAdapter
    the scheduled/manual poll already uses.
    """
    product_id = payload.get("id")
    return {
        "topic": topic,
        "wc_product_id": str(product_id) if product_id is not None else None,
        "sku": payload.get("sku"),
        "status": payload.get("status"),
        "type": payload.get("type"),
    }


def _backoff(attempt_no: int) -> timedelta:
    return timedelta(seconds=min(300, 2 ** max(0, attempt_no - 1)))


def _safe_error(value: str) -> str:
    return str(redact_sensitive({"error": value})["error"])[:500]


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None
