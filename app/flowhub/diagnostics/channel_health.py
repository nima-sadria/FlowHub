"""Unified channel health reporting.

Normal health reads are local and lightweight. Explicit refresh performs one
bounded provider probe per channel and caches the sanitized result in the
existing Data Layer connector health table.
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import datetime, timedelta
from time import monotonic
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, inspect
from sqlalchemy.orm import Session

from app.flowhub.channels.contracts import ConnectorErrorCategory
from app.flowhub.commerce.service import CommerceHubService
from app.flowhub.config.values import parse_config_bool
from app.flowhub.data_layer.health_service import ConnectorHealthService
from app.flowhub.data_layer.models import DlConnectorHealth, DlProductCache, DlRefreshJob
from app.flowhub.integration_platform.models import IntegrationConnectorEvent, IntegrationConnectorInstance
from app.flowhub.integration_platform.registry import registry
from app.flowhub.orders.models import ChannelOrderRecord, OrderSyncCheckpoint
from app.flowhub.product_pricing.models import ProductPriceOperation, ProductPriceOperationItem
from app.flowhub.webhooks.models import WebhookDeadLetter, WebhookReceipt


DEFAULT_CHANNEL_IDS = ("woocommerce:primary", "snappshop:main", "tapsishop:main")
HEALTH_CACHE_SECONDS = 60
EXTERNAL_CHECK_TIMEOUT_SECONDS = 8.0
STALE_SYNC_AFTER = timedelta(hours=24)
_REFRESH_LOCKS: dict[str, asyncio.Lock] = {}
logger = logging.getLogger(__name__)


class ChannelHealthReporter:
    def __init__(self, db: Session) -> None:
        self.db = db

    def report(self) -> dict:
        items = []
        for channel_id in self._channel_ids():
            try:
                items.append(self._channel_shape(channel_id))
            except Exception as exc:
                logger.error(
                    "channel_health_report_failed",
                    extra={
                        "channel_id": channel_id,
                        "channel_type": channel_id.split(":", 1)[0],
                        "exception_type": type(exc).__name__,
                        "traceback_frames": [
                            {"file": frame.filename, "line": frame.lineno, "function": frame.name}
                            for frame in traceback.extract_tb(exc.__traceback__)
                        ],
                    },
                )
                items.append(self._unavailable_channel_shape(channel_id))
        return {
            "checkedAt": _iso(datetime.utcnow()),
            "summary": _summary(items),
            "items": items,
            "orderSyncRunner": self._runner_state(),
            "external_call_performed": False,
        }

    def _unavailable_channel_shape(self, channel_id: str) -> dict:
        connector_type = channel_id.split(":", 1)[0]
        unavailable = _dimension("Unable to check", "Channel diagnostics are temporarily unavailable.")
        return {
            "channelId": channel_id,
            "channelType": connector_type,
            "enabled": False,
            "accessMode": "read_only",
            "status": "Unable to check",
            "summary": "Channel diagnostics are temporarily unavailable.",
            "lastChecked": None,
            "latency": None,
            "lastSuccessfulOperation": None,
            "lastErrorCategory": "diagnostic_unavailable",
            "capabilityState": {},
            "nextRecommendedAction": "Retry the diagnostic check.",
            "dimensions": {"configuration": unavailable, "externalApi": unavailable},
            "lastProductRead": None,
            "lastProductWrite": None,
            "lastOrderSync": None,
            "polling": {"cursor": None, "lastRunAt": None},
            "orderSync": {"lastRunPerSource": {}, "lastSuccess": None, "lastFailure": None, "lastFailureCategory": None, "nextScheduledRun": None},
            "webhooks": {"supported": connector_type == "tapsishop", "received": 0, "queued": 0, "processed": 0, "deadLetter": 0, "lastReceivedAt": None, "lastProcessedAt": None},
        }

    async def refresh(self, channel_id: str | None = None) -> dict:
        known_ids = set(self._channel_ids())
        ids = [channel_id] if channel_id else list(known_ids)
        for cid in ids:
            if cid not in known_ids:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel not found.")
            lock = _REFRESH_LOCKS.setdefault(cid, asyncio.Lock())
            if lock.locked():
                continue
            async with lock:
                current = self._health(cid)
                if current and current.checked_at > datetime.utcnow() - timedelta(seconds=HEALTH_CACHE_SECONDS):
                    continue
                await self._refresh_one(cid)
        payload = self.report()
        payload["external_call_performed"] = True
        return payload

    async def _refresh_one(self, channel_id: str) -> None:
        service = CommerceHubService(self.db)
        started = monotonic()
        try:
            result = await asyncio.wait_for(service.test_channel_connection(channel_id), timeout=EXTERNAL_CHECK_TIMEOUT_SECONDS)
        except TimeoutError:
            self._record_health(channel_id, "unknown", (monotonic() - started) * 1000, "Lightweight channel health probe timed out.", "timeout")
            return
        except Exception:
            self._record_health(channel_id, "unhealthy", (monotonic() - started) * 1000, "Lightweight channel health probe failed.", "unexpected_response")
            return

        external_status = str(result.get("status") or "")
        error_class = _error_category_from_result(result)
        if external_status in {"connected", "operational"} or result.get("ok") is True:
            dl_status = "healthy"
            error_class = None
        elif external_status in {"not_configured", "disabled"}:
            dl_status = "unknown"
            error_class = "not_configured"
        elif external_status in {"authentication_failed"}:
            dl_status = "unhealthy"
            error_class = "authentication"
        elif error_class == "timeout":
            dl_status = "unknown"
        else:
            dl_status = "unhealthy"
        self._record_health(
            channel_id,
            dl_status,
            float(result.get("latency_ms") or (monotonic() - started) * 1000),
            _safe_message(str(result.get("message") or "Channel health probe completed.")),
            error_class,
        )

    def _channel_shape(self, channel_id: str) -> dict:
        instance = self.db.get(IntegrationConnectorInstance, channel_id)
        connector_type = channel_id.split(":", 1)[0]
        definition = registry.get_definition(connector_type)
        health = self._health(channel_id)
        product_read = self._last_product_read(channel_id)
        product_write = self._last_product_write(channel_id)
        order_sync = self._last_order_sync(channel_id)
        webhook = self._webhook_state(channel_id, connector_type)
        checkpoint = self._checkpoint(channel_id)
        enabled = bool(instance and instance.enabled)
        configured = self._configured(instance)
        capability_state = definition.connector.capabilities.model_dump() if definition else {}
        cached_product_count = self.db.query(DlProductCache).filter_by(connector_id=channel_id).count()
        latest_product_refresh = self._latest_product_refresh(channel_id)
        vendor_selected = self._setting_configured(instance, "vendor_id") if connector_type == "snappshop" else None

        dimensions = {
            "configuration": _dimension("Operational" if configured else "Warning", "Required configuration is present." if configured else "Required configuration is incomplete."),
            "credentials": self._credential_dimension(enabled, configured, health),
            "externalApi": self._external_dimension(enabled, configured, health),
            "readCapability": _dimension("Operational" if capability_state.get("read_products") or capability_state.get("read_orders") else "Disabled", ""),
            "writeCapability": _dimension("Operational" if capability_state.get("write_prices") else "Disabled", "Capability advertised; FlowHub Apply protections still apply."),
            "lastProductSync": self._sync_dimension(product_read),
            "lastOrderSync": self._sync_dimension(order_sync),
            "webhookReceipt": self._webhook_receipt_dimension(webhook),
            "webhookProcessing": self._webhook_processing_dimension(webhook),
            "queueDeadLetter": self._dead_letter_dimension(webhook),
            "tokenRefresh": self._token_refresh_dimension(instance, connector_type),
            "polling": self._polling_dimension(connector_type, checkpoint),
        }
        if connector_type == "snappshop":
            dimensions["vendorSelection"] = (
                _dimension("Disabled", "Channel is disabled.")
                if not enabled
                else _dimension("Operational" if vendor_selected else "Warning", "A vendor is selected." if vendor_selected else "Select a vendor before product synchronization.")
            )
            dimensions["productCache"] = self._product_cache_dimension(enabled, latest_product_refresh)
        status = "Disabled" if not enabled else _worst_dimension(dimensions)
        return {
            "channelId": channel_id,
            "channelType": connector_type,
            "enabled": enabled,
            "accessMode": self._access_mode(instance),
            "status": status,
            "summary": self._summary(status, configured, health, product_read, order_sync, webhook),
            "lastChecked": _iso(health.checked_at) if health else None,
            "latency": health.latency_ms if health else None,
            "lastSuccessfulOperation": _iso(_max_dt(product_read, product_write, order_sync, health.last_success_at if health else None)),
            "lastErrorCategory": health.error_class if health else None,
            "capabilityState": capability_state,
            "nextRecommendedAction": self._next_action(status, configured, health, webhook),
            "dimensions": dimensions,
            "lastProductRead": _iso(product_read),
            "credentialsConfigured": self._credentials_configured(instance),
            "credentialsVerified": bool(health and health.last_success_at),
            "vendorSelected": vendor_selected,
            "vendorAccessible": bool(vendor_selected and health and health.status == "healthy") if connector_type == "snappshop" else None,
            "productReadStatus": latest_product_refresh.status if latest_product_refresh else "not_run",
            "cachedProductCount": cached_product_count,
            "lastProductSync": _iso(product_read),
            "lastSyncErrorCategory": (
                str((latest_product_refresh.meta or {}).get("error_category") or "") or None
                if latest_product_refresh and latest_product_refresh.status == "failed"
                else None
            ),
            "lastProductWrite": _iso(product_write),
            "lastOrderSync": _iso(order_sync),
            "polling": {"cursor": checkpoint.cursor if checkpoint else None, "lastRunAt": _iso(checkpoint.last_run_at) if checkpoint else None},
            "orderSync": self._order_sync_state(channel_id),
            "webhooks": webhook,
        }

    def _record_health(self, channel_id: str, health_status: str, latency_ms: float | None, detail: str, error_class: str | None) -> None:
        ConnectorHealthService(self.db).upsert(
            connector_id=channel_id,
            connector_type=channel_id.split(":", 1)[0],
            status=health_status,
            latency_ms=round(latency_ms, 2) if latency_ms is not None else None,
            detail=detail,
            error_class=error_class,
        )

    def _health(self, channel_id: str) -> DlConnectorHealth | None:
        return self.db.query(DlConnectorHealth).filter_by(connector_id=channel_id).first()

    def _configured(self, instance: IntegrationConnectorInstance | None) -> bool:
        if instance is None:
            return False
        required = {
            "woocommerce": {"url", "key", "secret"},
            "snappshop": {"token", "agent_identifier", "vendor_id"},
            "tapsishop": {"token"},
        }.get(instance.connector_type, set())
        settings = {item.key: item for item in instance.settings}
        return bool(required) and all(settings.get(key) and settings[key].configured for key in required)

    def _credentials_configured(self, instance: IntegrationConnectorInstance | None) -> bool:
        if instance is None:
            return False
        required = {
            "woocommerce": {"url", "key", "secret"},
            "snappshop": {"token", "agent_identifier"},
            "tapsishop": {"token"},
        }.get(instance.connector_type, set())
        settings = {item.key: item for item in instance.settings}
        return bool(required) and all(settings.get(key) and settings[key].configured for key in required)

    def _setting_configured(self, instance: IntegrationConnectorInstance | None, key: str) -> bool:
        if instance is None:
            return False
        row = next((item for item in instance.settings if item.key == key), None)
        return bool(row and row.configured and str(row.value_json or "").strip())

    def _latest_product_refresh(self, channel_id: str) -> DlRefreshJob | None:
        return (
            self.db.query(DlRefreshJob)
            .filter_by(connector_id=channel_id, entity_type="products")
            .order_by(DlRefreshJob.created_at.desc(), DlRefreshJob.id.desc())
            .first()
        )

    def _product_cache_dimension(self, enabled: bool, refresh: DlRefreshJob | None) -> dict:
        if not enabled:
            return _dimension("Disabled", "Channel is disabled.")
        if refresh is None:
            return _dimension("Warning", "No product synchronization has been run.")
        if refresh.status == "completed":
            return _dimension("Operational", "The local product cache was refreshed successfully.")
        if refresh.status == "failed":
            return _dimension("Error", "The latest product synchronization failed; the previous cache was preserved.")
        return _dimension("Warning", "Product synchronization has not completed.")

    def _access_mode(self, instance: IntegrationConnectorInstance | None) -> str:
        if instance is None:
            return "read_only"
        row = next((item for item in instance.settings if item.key == "access_mode"), None)
        return str(row.value_json or "read_only") if row else "read_only"

    def _last_product_read(self, channel_id: str) -> datetime | None:
        cache_time = self.db.query(func.max(DlProductCache.last_successful_read)).filter(DlProductCache.connector_id == channel_id).scalar()
        job_time = (
            self.db.query(func.max(DlRefreshJob.completed_at))
            .filter(DlRefreshJob.connector_id == channel_id, DlRefreshJob.entity_type == "products", DlRefreshJob.status == "completed")
            .scalar()
        )
        return _max_dt(cache_time, job_time)

    def _last_product_write(self, channel_id: str) -> datetime | None:
        if not self._table_exists(ProductPriceOperation) or not self._table_exists(ProductPriceOperationItem):
            return None
        return (
            self.db.query(func.max(ProductPriceOperation.applied_at))
            .join(ProductPriceOperationItem, ProductPriceOperationItem.operation_id == ProductPriceOperation.id)
            .filter(ProductPriceOperationItem.channel_id == channel_id, ProductPriceOperationItem.status == "applied")
            .scalar()
        )

    def _last_order_sync(self, channel_id: str) -> datetime | None:
        if not self._table_exists(ChannelOrderRecord) or not self._table_exists(OrderSyncCheckpoint):
            return None
        order_time = self.db.query(func.max(ChannelOrderRecord.last_seen_at)).filter(ChannelOrderRecord.channel_id == channel_id).scalar()
        checkpoint_time = self.db.query(func.max(OrderSyncCheckpoint.last_run_at)).filter(OrderSyncCheckpoint.channel_id == channel_id).scalar()
        return _max_dt(order_time, checkpoint_time)

    def _checkpoint(self, channel_id: str) -> OrderSyncCheckpoint | None:
        if not self._table_exists(OrderSyncCheckpoint):
            return None
        return (
            self.db.query(OrderSyncCheckpoint)
            .filter_by(channel_id=channel_id)
            .order_by(OrderSyncCheckpoint.updated_at.desc())
            .first()
        )

    def _webhook_state(self, channel_id: str, connector_type: str) -> dict:
        if connector_type != "tapsishop":
            return {"supported": False, "received": 0, "queued": 0, "processed": 0, "deadLetter": 0, "lastReceivedAt": None, "lastProcessedAt": None}
        if not self._table_exists(WebhookReceipt) or not self._table_exists(WebhookDeadLetter):
            return {"supported": True, "received": 0, "queued": 0, "processed": 0, "deadLetter": 0, "lastReceivedAt": None, "lastProcessedAt": None}
        q = self.db.query(WebhookReceipt).filter_by(channel_id=channel_id)
        receipts = q.all()
        dead = self.db.query(WebhookDeadLetter).filter_by(channel_id=channel_id).count()
        return {
            "supported": True,
            "received": len(receipts),
            "queued": sum(1 for item in receipts if item.processing_state in {"queued", "retry_scheduled"}),
            "processed": sum(1 for item in receipts if item.processing_state == "processed"),
            "deadLetter": dead,
            "lastReceivedAt": _iso(max((item.received_at for item in receipts), default=None)),
            "lastProcessedAt": _iso(max((item.processed_at for item in receipts if item.processed_at), default=None)),
        }

    def _credential_dimension(self, enabled: bool, configured: bool, health: DlConnectorHealth | None) -> dict:
        if not enabled:
            return _dimension("Disabled", "Channel is disabled.")
        if health and health.error_class in {"authentication", "authentication_failed"}:
            return _dimension("Error", "Credential validation failed.")
        if not configured:
            return _dimension("Warning", "Credentials are not fully configured.")
        return _dimension("Operational" if health and health.last_success_at else "Unable to check", "Credential validation uses the lightweight provider probe.")

    def _external_dimension(self, enabled: bool, configured: bool, health: DlConnectorHealth | None) -> dict:
        if not enabled:
            return _dimension("Disabled", "")
        if not configured:
            return _dimension("Warning", "Configure the channel before checking reachability.")
        if health is None:
            return _dimension("Unable to check", "No health check has been recorded.")
        if health.error_class == "timeout" or health.status == "unknown":
            return _dimension("Unable to check", health.detail or "Provider probe was inconclusive.")
        if health.status == "healthy":
            return _dimension("Operational", health.detail or "")
        if health.status == "degraded":
            return _dimension("Warning", health.detail or "")
        return _dimension("Error", health.detail or "Provider probe failed.")

    def _sync_dimension(self, last_at: datetime | None) -> dict:
        if last_at is None:
            return _dimension("Warning", "No successful sync has been recorded.")
        if last_at < datetime.utcnow() - STALE_SYNC_AFTER:
            return _dimension("Warning", "Last successful sync is stale.")
        return _dimension("Operational", "Recent successful sync recorded.")

    def _webhook_receipt_dimension(self, state: dict) -> dict:
        if not state["supported"]:
            return _dimension("Disabled", "Channel does not use webhooks.")
        if state["received"] == 0:
            return _dimension("Warning", "No webhook receipt has been accepted yet.")
        return _dimension("Operational", "Webhook receipts are being accepted.")

    def _webhook_processing_dimension(self, state: dict) -> dict:
        if not state["supported"]:
            return _dimension("Disabled", "")
        if state["queued"] > 0:
            return _dimension("Warning", "Accepted webhook receipts are waiting for processing.")
        return _dimension("Operational" if state["processed"] else "Warning", "No processed webhook receipt yet." if not state["processed"] else "")

    def _dead_letter_dimension(self, state: dict) -> dict:
        if not state["supported"]:
            return _dimension("Disabled", "")
        if state["deadLetter"] > 0:
            return _dimension("Error", "Webhook dead letters require operator review.")
        return _dimension("Operational", "No dead letters.")

    def _token_refresh_dimension(self, instance: IntegrationConnectorInstance | None, connector_type: str) -> dict:
        if connector_type != "tapsishop":
            return _dimension("Disabled", "Token refresh is not supported for this channel.")
        settings = {item.key: item for item in instance.settings} if instance else {}
        enabled = parse_config_bool(
            settings["token_refresh_enabled"].value_json
            if settings.get("token_refresh_enabled")
            else None
        )
        last_event = (
            self.db.query(IntegrationConnectorEvent)
            .filter(IntegrationConnectorEvent.connector_id == (instance.id if instance else ""), IntegrationConnectorEvent.event_name.ilike("%token%"))
            .order_by(IntegrationConnectorEvent.created_at.desc())
            .first()
        )
        event_label = last_event.event_name.replace("token", "credential") if last_event else ""
        return _dimension("Operational" if enabled else "Warning", f"Refresh policy {'enabled' if enabled else 'disabled'}." + (f" Last event {event_label}." if event_label else ""))

    def _channel_ids(self) -> list[str]:
        rows = self.db.query(IntegrationConnectorInstance.id).order_by(IntegrationConnectorInstance.id.asc()).all()
        ids = {row[0] for row in rows}
        ids.update(DEFAULT_CHANNEL_IDS)
        return sorted(ids)

    def _runner_state(self) -> dict:
        event = (
            self.db.query(IntegrationConnectorEvent)
            .filter_by(connector_id="flowhub:order-sync-runner", event_name="order_sync_runner_heartbeat")
            .order_by(IntegrationConnectorEvent.created_at.desc())
            .first()
        )
        metadata = event.metadata_json if event and isinstance(event.metadata_json, dict) else {}
        return {
            "lastHeartbeat": _iso(event.created_at) if event else None,
            "state": metadata.get("state") if event else "unknown",
            "runnerId": metadata.get("runner_id") if event else None,
        }

    def _order_sync_state(self, channel_id: str) -> dict:
        checkpoints = self.db.query(OrderSyncCheckpoint).filter_by(channel_id=channel_id).all() if self._table_exists(OrderSyncCheckpoint) else []
        last_failure = max((item.last_failure_at for item in checkpoints if item.last_failure_at), default=None)
        last_success = max((item.last_success_at or item.last_run_at for item in checkpoints if item.last_success_at or item.last_run_at), default=None)
        next_run = min((item.next_run_at for item in checkpoints if item.next_run_at), default=None)
        last_failure_category = next((item.last_failure_category for item in sorted(checkpoints, key=lambda row: row.last_failure_at or datetime.min, reverse=True) if item.last_failure_category), None)
        return {
            "lastRunPerSource": {
                item.source: {
                    "lastRunAt": _iso(item.last_run_at),
                    "lastSuccessAt": _iso(item.last_success_at),
                    "lastFailureAt": _iso(item.last_failure_at),
                    "lastFailureCategory": item.last_failure_category,
                    "nextRunAt": _iso(item.next_run_at),
                    "leaseOwnerPresent": bool(item.lock_owner),
                    "leaseExpiresAt": _iso(item.lease_expires_at),
                }
                for item in checkpoints
            },
            "lastSuccess": _iso(last_success),
            "lastFailure": _iso(last_failure),
            "lastFailureCategory": last_failure_category,
            "nextScheduledRun": _iso(next_run),
        }

    def _table_exists(self, model: Any) -> bool:
        return inspect(self.db.get_bind()).has_table(model.__tablename__)

    def _polling_dimension(self, connector_type: str, checkpoint: OrderSyncCheckpoint | None) -> dict:
        if connector_type != "snappshop":
            return _dimension("Disabled", "Order polling is not used for this channel.")
        if checkpoint is None or checkpoint.last_run_at is None:
            return _dimension("Warning", "No order event polling checkpoint has run.")
        return self._sync_dimension(checkpoint.last_run_at)

    def _summary(self, status_value: str, configured: bool, health: DlConnectorHealth | None, product_read: datetime | None, order_sync: datetime | None, webhook: dict) -> str:
        if status_value == "Disabled":
            return "Channel is disabled."
        if not configured:
            return "Channel configuration is incomplete."
        if health and health.error_class:
            return f"Last health check reported {health.error_class}."
        if webhook.get("deadLetter"):
            return "Webhook dead letters are present."
        if not product_read and not order_sync:
            return "Configured, but no recent product or order sync has been recorded."
        return "Channel health is derived from the unified diagnostics source."

    def _next_action(self, status_value: str, configured: bool, health: DlConnectorHealth | None, webhook: dict) -> str:
        if status_value == "Disabled":
            return "Enable the channel when it should be monitored."
        if not configured:
            return "Complete channel configuration and credentials."
        if health and health.error_class in {"authentication", "authentication_failed"}:
            return "Update credentials and run an explicit health refresh."
        if health and health.error_class == "timeout":
            return "Retry health refresh; keep recent successful sync state until timeout recurs."
        if webhook.get("deadLetter"):
            return "Review and replay or resolve webhook dead letters."
        return "No immediate action required."


def _dimension(status_value: str, message: str) -> dict:
    return {"status": status_value, "message": _safe_message(message)}


def _worst_dimension(dimensions: dict[str, dict]) -> str:
    order = {"Error": 4, "Warning": 3, "Unable to check": 2, "Operational": 1, "Disabled": 0}
    active = [item["status"] for item in dimensions.values() if item["status"] != "Disabled"]
    return max(active or ["Disabled"], key=lambda item: order.get(item, 0))


def _summary(items: list[dict]) -> dict:
    counts = {"Operational": 0, "Warning": 0, "Error": 0, "Unable to check": 0, "Disabled": 0}
    for item in items:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    overall = "Operational"
    for status_value in ("Error", "Warning", "Unable to check", "Disabled"):
        if counts.get(status_value):
            overall = status_value
            break
    return {"overall": overall, "counts": counts}


def _error_category_from_result(result: dict) -> str | None:
    value = str(result.get("code") or result.get("error_code") or result.get("status") or "").lower()
    if "auth" in value or result.get("authenticated") is False:
        return ConnectorErrorCategory.AUTHENTICATION.value
    if "timeout" in value:
        return ConnectorErrorCategory.TIMEOUT.value
    if "rate" in value:
        return ConnectorErrorCategory.RATE_LIMIT.value
    if value in {"not_configured", "disabled"}:
        return "not_configured"
    return ConnectorErrorCategory.UNEXPECTED_RESPONSE.value if result.get("ok") is False else None


def _max_dt(*values: datetime | None) -> datetime | None:
    present = [value for value in values if value is not None]
    return max(present) if present else None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None


def _safe_message(value: str) -> str:
    blocked = ("token", "authorization", "secret", "phone", "national", "address")
    text = str(value or "")[:400]
    lowered = text.lower()
    if any(word in lowered for word in blocked):
        return "Sanitized health detail is available in server logs."
    return text
