"""Unified channel health reporting.

Normal health reads are local and lightweight. Explicit refresh performs one
bounded provider probe per channel and caches the sanitized result in the
existing Data Layer connector health table.
"""

from __future__ import annotations

import asyncio
import logging
import os
import traceback
from datetime import datetime, timedelta
from time import monotonic
from typing import Any, cast

from fastapi import HTTPException, status
from sqlalchemy import func, inspect
from sqlalchemy.orm import Session

from app.flowhub.channels.contracts import ConnectorErrorCategory
from app.flowhub.commerce.service import CommerceHubService
from app.flowhub.config.values import parse_config_bool
from app.flowhub.data_layer.health_service import ConnectorHealthService
from app.flowhub.data_layer.models import DlConnectorHealth, DlProductCache, DlRefreshJob
from app.flowhub.diagnostics.semantics import (
    DiagnosticPresentation,
    DiagnosticState,
    diagnostic_presentation,
)
from app.flowhub.integration_platform.models import (
    IntegrationConnectorEvent,
    IntegrationConnectorInstance,
    IntegrationPollingPolicy,
)
from app.flowhub.integration_platform.registry import registry
from app.flowhub.orders.models import ChannelOrderRecord, OrderSyncCheckpoint
from app.flowhub.product_pricing.models import ProductPriceOperation, ProductPriceOperationItem
from app.flowhub.webhooks.models import WebhookDeadLetter, WebhookReceipt

DEFAULT_CHANNEL_IDS = ("woocommerce:primary", "snappshop:main", "tapsishop:main")
SOURCE_CONNECTOR_TYPES = frozenset({"nextcloud", "csv", "gsheets", "erp"})
HEALTH_CACHE_SECONDS = 60
EXTERNAL_CHECK_TIMEOUT_SECONDS = 8.0
STALE_SYNC_AFTER = timedelta(hours=24)
STALE_HEALTH_AFTER = timedelta(hours=24)
_REFRESH_LOCKS: dict[str, asyncio.Lock] = {}
logger = logging.getLogger(__name__)


class ChannelHealthReporter:
    def __init__(self, db: Session) -> None:
        self.db = db

    def report(self) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
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

    def _unavailable_channel_shape(self, channel_id: str) -> dict[str, Any]:
        connector_type = channel_id.split(":", 1)[0]
        unavailable = _dimension(
            DiagnosticState.ERROR,
            "Channel diagnostics could not be generated.",
            reason_code="diagnostic_generation_failed",
            checked_at=None,
            evidence_source="channel_diagnostics",
            is_actionable=True,
            recommended_action="Retry the diagnostic check.",
        )
        return {
            "channelId": channel_id,
            "channelType": connector_type,
            "enabled": False,
            "accessMode": "read_only",
            "status": "Unable to check",
            "state": DiagnosticState.ERROR.value,
            "reason_code": unavailable["reason_code"],
            "checked_at": unavailable["checked_at"],
            "evidence_source": unavailable["evidence_source"],
            "is_actionable": unavailable["is_actionable"],
            "recommended_action": unavailable["recommended_action"],
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

    async def refresh(self, channel_id: str | None = None) -> dict[str, Any]:
        known_ids = set(self._channel_ids())
        ids = [channel_id] if channel_id else list(known_ids)
        external_call_performed = False
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
                external_call_performed = await self._refresh_one(cid) or external_call_performed
        payload = self.report()
        payload["external_call_performed"] = external_call_performed
        return payload

    async def _refresh_one(self, channel_id: str) -> bool:
        service = CommerceHubService(self.db)
        started = monotonic()
        try:
            result = await asyncio.wait_for(service.test_channel_connection(channel_id), timeout=EXTERNAL_CHECK_TIMEOUT_SECONDS)
        except TimeoutError:
            self._record_health(channel_id, "unknown", (monotonic() - started) * 1000, "Lightweight channel health probe timed out.", "timeout")
            return True
        except Exception:
            self._record_health(channel_id, "unhealthy", (monotonic() - started) * 1000, "Lightweight channel health probe failed.", "unexpected_response")
            return True

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
        return bool(result.get("external_call_performed"))

    def _channel_shape(self, channel_id: str) -> dict[str, Any]:
        instance = self.db.get(IntegrationConnectorInstance, channel_id)
        connector_type = channel_id.split(":", 1)[0]
        definition = registry.get_definition(connector_type)
        health = self._health(channel_id)
        product_read = self._last_product_read(channel_id)
        product_write = self._last_product_write(channel_id)
        order_sync = self._last_order_sync(channel_id)
        enabled = bool(instance and instance.enabled)
        configured = self._configured(instance)
        credentials_configured = self._credentials_configured(instance)
        capability_state = definition.connector.capabilities.model_dump() if definition else {}
        product_read_supported = bool(capability_state.get("read_products"))
        external_probe_supported = connector_type in {"woocommerce", "snappshop", "tapsishop"}
        webhook = self._webhook_state(channel_id, connector_type, instance)
        polling_policy = self._polling_policy(channel_id)
        order_sync_expected = enabled and configured and self._order_sync_expected(
            connector_type,
            polling_policy=polling_policy,
            webhook_enabled=bool(webhook["enabled"]),
        )
        checkpoint = self._checkpoint(channel_id, "snappshop_events")
        cached_product_count = self.db.query(DlProductCache).filter_by(connector_id=channel_id).count()
        latest_product_refresh = self._latest_product_refresh(channel_id)
        vendor_selected = self._setting_configured(instance, "vendor_id") if connector_type == "snappshop" else None
        configuration_checked_at = _iso(self._configuration_checked_at(instance))

        dimensions = {
            "configuration": _dimension(
                DiagnosticState.HEALTHY if configured else DiagnosticState.WARNING,
                "Required configuration is present." if configured else "Required configuration is incomplete.",
                reason_code="configuration_complete" if configured else "configuration_incomplete",
                checked_at=configuration_checked_at,
                evidence_source="connector_settings",
                is_actionable=not configured,
                recommended_action="" if configured else "Complete channel configuration.",
            ),
            "credentials": self._credential_dimension(enabled, credentials_configured, health),
            "externalApi": self._external_dimension(enabled, configured, health, external_probe_supported),
            "readCapability": self._capability_dimension(
                bool(capability_state.get("read_products") or capability_state.get("read_orders")),
                "Product or order reads are supported.",
                reason_code="read_capability_supported",
            ),
            "writeCapability": self._capability_dimension(
                bool(capability_state.get("write_prices") or capability_state.get("write_inventory")),
                "Price or stock updates are supported. FlowHub still requires Review and Apply confirmation.",
                reason_code="write_capability_supported",
            ),
            "lastProductSync": self._product_sync_dimension(
                enabled=enabled,
                configured=configured,
                supported=product_read_supported,
                last_at=product_read,
            ),
            "lastOrderSync": self._order_sync_dimension(
                enabled=enabled,
                connector_type=connector_type,
                expected=order_sync_expected,
                last_at=order_sync,
            ),
            "webhookReceipt": self._webhook_receipt_dimension(webhook),
            "webhookProcessing": self._webhook_processing_dimension(webhook),
            "queueDeadLetter": self._dead_letter_dimension(webhook),
            "tokenRefresh": self._token_refresh_dimension(instance, connector_type, enabled),
            "polling": self._polling_dimension(
                connector_type,
                checkpoint,
                polling_policy,
                enabled,
                configured,
            ),
        }
        if connector_type == "snappshop":
            dimensions["vendorSelection"] = (
                _dimension(
                    DiagnosticState.DISABLED,
                    "Channel is disabled.",
                    reason_code="channel_disabled",
                    checked_at=configuration_checked_at,
                    evidence_source="connector_instance",
                )
                if not enabled
                else _dimension(
                    DiagnosticState.HEALTHY if vendor_selected else DiagnosticState.WARNING,
                    "A vendor is selected." if vendor_selected else "Select a vendor before product synchronization.",
                    reason_code="vendor_selected" if vendor_selected else "vendor_not_selected",
                    checked_at=configuration_checked_at,
                    evidence_source="connector_settings",
                    is_actionable=not vendor_selected,
                    recommended_action="" if vendor_selected else "Select a vendor before product synchronization.",
                )
            )
            dimensions["productCache"] = self._product_cache_dimension(enabled, latest_product_refresh)
        state, controlling_dimension = _channel_state(enabled, dimensions, self._core_dimension_names(
            product_read_supported=product_read_supported,
            order_sync_expected=order_sync_expected,
            external_probe_supported=external_probe_supported,
            connector_type=connector_type,
        ))
        legacy_status = _legacy_channel_status(state)
        summary = self._state_summary(state, controlling_dimension)
        recommended_action = str(controlling_dimension.get("recommended_action") or "")
        return {
            "channelId": channel_id,
            "channelType": connector_type,
            "enabled": enabled,
            "accessMode": self._access_mode(instance),
            "status": legacy_status,
            "state": state.value,
            "reason_code": str(controlling_dimension.get("reason_code") or "diagnostic_state_available"),
            "checked_at": controlling_dimension.get("checked_at"),
            "evidence_source": str(controlling_dimension.get("evidence_source") or "channel_diagnostics"),
            "is_actionable": bool(controlling_dimension.get("is_actionable")),
            "recommended_action": recommended_action,
            "summary": summary,
            "lastChecked": _iso(cast(datetime, health.checked_at)) if health else None,
            "lastSuccessfulVerification": _iso(cast(datetime | None, health.last_success_at)) if health else None,
            "latency": health.latency_ms if health else None,
            "lastSuccessfulOperation": _iso(
                _max_dt(
                    product_read,
                    product_write,
                    order_sync,
                    cast(datetime | None, health.last_success_at) if health else None,
                )
            ),
            "lastSuccessfulSyncOrRead": _iso(_max_dt(product_read, order_sync)),
            "lastErrorCategory": health.error_class if health else None,
            "capabilityState": capability_state,
            "nextRecommendedAction": recommended_action,
            "dimensions": dimensions,
            "lastProductRead": _iso(product_read),
            "credentialsConfigured": credentials_configured,
            "credentialsVerified": bool(health and health.last_success_at),
            "vendorSelected": vendor_selected,
            "vendorAccessible": bool(vendor_selected and health and health.status == "healthy") if connector_type == "snappshop" else None,
            "productReadStatus": latest_product_refresh.status if latest_product_refresh else "not_run",
            "cachedProductCount": cached_product_count,
            "lastProductSync": _iso(product_read),
            "lastSyncErrorCategory": (
                str(cast(dict[str, Any], latest_product_refresh.meta or {}).get("error_category") or "") or None
                if latest_product_refresh and latest_product_refresh.status == "failed"
                else None
            ),
            "lastProductWrite": _iso(product_write),
            "lastOrderSync": _iso(order_sync),
            "polling": {
                "enabled": bool(polling_policy and polling_policy.enabled),
                "cursor": checkpoint.cursor if checkpoint else None,
                "lastRunAt": _iso(_max_dt(
                    checkpoint.last_run_at if checkpoint else None,
                    polling_policy.last_run_at if polling_policy else None,
                )),
                "nextRunAt": _iso(polling_policy.next_run_at) if polling_policy else None,
            },
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

    def _setting_present(self, instance: IntegrationConnectorInstance | None, key: str) -> bool:
        if instance is None:
            return False
        row = next((item for item in instance.settings if item.key == key), None)
        return bool(row and row.configured)

    def _configuration_checked_at(self, instance: IntegrationConnectorInstance | None) -> datetime | None:
        if instance is None:
            return None
        return _max_dt(instance.updated_at, *(item.updated_at for item in instance.settings))

    def _order_sync_expected(
        self,
        connector_type: str,
        *,
        polling_policy: IntegrationPollingPolicy | None,
        webhook_enabled: bool,
    ) -> bool:
        if not parse_config_bool(os.environ.get("FLOWHUB_ORDER_SYNC_ENABLED"), default=True):
            return False
        if connector_type == "snappshop":
            return bool(polling_policy and polling_policy.enabled)
        if connector_type == "tapsishop":
            return webhook_enabled
        return False

    def _capability_dimension(
        self,
        supported: bool,
        supported_message: str,
        *,
        reason_code: str,
    ) -> DiagnosticPresentation:
        if supported:
            return _dimension(
                DiagnosticState.INFO,
                supported_message,
                reason_code=reason_code,
                checked_at=None,
                evidence_source="connector_registry",
            )
        return _dimension(
            DiagnosticState.NOT_APPLICABLE,
            "This capability is not used by this Channel.",
            reason_code="capability_not_applicable",
            checked_at=None,
            evidence_source="connector_registry",
        )

    def _product_sync_dimension(
        self,
        *,
        enabled: bool,
        configured: bool,
        supported: bool,
        last_at: datetime | None,
    ) -> DiagnosticPresentation:
        if not enabled:
            return _dimension(
                DiagnosticState.DISABLED,
                "Channel is disabled.",
                reason_code="channel_disabled",
                checked_at=None,
                evidence_source="connector_instance",
            )
        if not supported:
            return _dimension(
                DiagnosticState.NOT_APPLICABLE,
                "Product synchronization is not supported for this Channel.",
                reason_code="product_sync_not_applicable",
                checked_at=None,
                evidence_source="connector_registry",
            )
        if not configured:
            return _dimension(
                DiagnosticState.NOT_CHECKED,
                "Product synchronization cannot run until Channel configuration is complete.",
                reason_code="product_sync_not_checked_configuration_incomplete",
                checked_at=None,
                evidence_source="data_layer_product_cache",
                is_actionable=True,
                recommended_action="Complete channel configuration.",
            )
        if last_at is None:
            return _dimension(
                DiagnosticState.NOT_CHECKED,
                "No successful product synchronization has been recorded.",
                reason_code="product_sync_not_checked",
                checked_at=None,
                evidence_source="data_layer_product_cache",
                is_actionable=True,
                recommended_action="Refresh products.",
            )
        if _is_stale(last_at, STALE_SYNC_AFTER):
            return _dimension(
                DiagnosticState.WARNING,
                f"Last successful product sync was {_age_text(last_at)} ago. Expected freshness: within 24 hours.",
                reason_code="product_sync_stale",
                checked_at=_iso(last_at),
                evidence_source="data_layer_product_cache",
                is_actionable=True,
                recommended_action="Refresh products.",
                freshness_threshold_hours=24,
            )
        return _dimension(
            DiagnosticState.HEALTHY,
            "Product data was synchronized within the expected 24-hour freshness window.",
            reason_code="product_sync_fresh",
            checked_at=_iso(last_at),
            evidence_source="data_layer_product_cache",
            freshness_threshold_hours=24,
        )

    def _order_sync_dimension(
        self,
        *,
        enabled: bool,
        connector_type: str,
        expected: bool,
        last_at: datetime | None,
    ) -> DiagnosticPresentation:
        if not enabled:
            return _dimension(
                DiagnosticState.DISABLED,
                "Channel is disabled.",
                reason_code="channel_disabled",
                checked_at=None,
                evidence_source="connector_instance",
            )
        if not expected:
            state = (
                DiagnosticState.DISABLED
                if self._connector_has_order_sync(connector_type) and not parse_config_bool(
                    os.environ.get("FLOWHUB_ORDER_SYNC_ENABLED"), default=True
                )
                else DiagnosticState.NOT_APPLICABLE
            )
            return _dimension(
                state,
                "Order synchronization is not enabled for this Channel." if state == DiagnosticState.DISABLED else "Order synchronization is not used for this Channel.",
                reason_code="order_sync_disabled" if state == DiagnosticState.DISABLED else "order_sync_not_applicable",
                checked_at=None,
                evidence_source="order_sync_configuration",
            )
        if last_at is None:
            return _dimension(
                DiagnosticState.WARNING,
                "No successful order synchronization has been recorded.",
                reason_code="order_sync_never_succeeded",
                checked_at=None,
                evidence_source="order_sync_checkpoint",
                is_actionable=True,
                recommended_action="Review order synchronization settings.",
            )
        if _is_stale(last_at, STALE_SYNC_AFTER):
            return _dimension(
                DiagnosticState.WARNING,
                f"Last successful order sync was {_age_text(last_at)} ago. Expected freshness: within 24 hours.",
                reason_code="order_sync_stale",
                checked_at=_iso(last_at),
                evidence_source="order_sync_checkpoint",
                is_actionable=True,
                recommended_action="Review order synchronization.",
                freshness_threshold_hours=24,
            )
        return _dimension(
            DiagnosticState.HEALTHY,
            "Order synchronization completed within the expected freshness window.",
            reason_code="order_sync_fresh",
            checked_at=_iso(last_at),
            evidence_source="order_sync_checkpoint",
            freshness_threshold_hours=24,
        )

    def _connector_has_order_sync(self, connector_type: str) -> bool:
        return connector_type in {"snappshop", "tapsishop"}

    def _core_dimension_names(
        self,
        *,
        product_read_supported: bool,
        order_sync_expected: bool,
        external_probe_supported: bool,
        connector_type: str,
    ) -> tuple[str, ...]:
        # Preserve a stable controlling-check order so identical evidence always
        # produces the same summary reason and recommended action.
        names = ["configuration", "credentials"]
        if external_probe_supported:
            names.append("externalApi")
        if product_read_supported:
            names.append("lastProductSync")
        if order_sync_expected:
            names.append("lastOrderSync")
        if connector_type == "snappshop":
            names.extend(("vendorSelection", "productCache"))
        return tuple(names)

    def _state_summary(
        self,
        state: DiagnosticState,
        controlling_dimension: DiagnosticPresentation,
    ) -> str:
        if state == DiagnosticState.DISABLED:
            return "Channel is disabled."
        if state == DiagnosticState.HEALTHY:
            return "All required Channel checks have verified healthy evidence."
        if state == DiagnosticState.NOT_CHECKED:
            return "One or more required checks have not run yet."
        if state == DiagnosticState.INFO:
            return "Channel diagnostics are informational."
        return str(controlling_dimension.get("message") or "Channel diagnostics need attention.")

    def _latest_product_refresh(self, channel_id: str) -> DlRefreshJob | None:
        return (
            self.db.query(DlRefreshJob)
            .filter_by(connector_id=channel_id, entity_type="products")
            .order_by(DlRefreshJob.created_at.desc(), DlRefreshJob.id.desc())
            .first()
        )

    def _product_cache_dimension(self, enabled: bool, refresh: DlRefreshJob | None) -> DiagnosticPresentation:
        if not enabled:
            return _dimension(
                DiagnosticState.DISABLED,
                "Channel is disabled.",
                reason_code="channel_disabled",
                checked_at=None,
                evidence_source="connector_instance",
            )
        if refresh is None:
            return _dimension(
                DiagnosticState.NOT_CHECKED,
                "No product cache refresh has been run.",
                reason_code="product_cache_not_checked",
                checked_at=None,
                evidence_source="data_layer_refresh_job",
                is_actionable=True,
                recommended_action="Refresh products.",
            )
        if refresh.status == "completed":
            return _dimension(
                DiagnosticState.HEALTHY,
                "The local product cache was refreshed successfully.",
                reason_code="product_cache_refresh_completed",
                checked_at=_iso(refresh.completed_at or refresh.created_at),
                evidence_source="data_layer_refresh_job",
            )
        if refresh.status == "failed":
            return _dimension(
                DiagnosticState.ERROR,
                "The latest product synchronization failed; the previous cache was preserved.",
                reason_code="product_cache_refresh_failed",
                checked_at=_iso(refresh.completed_at or refresh.created_at),
                evidence_source="data_layer_refresh_job",
                is_actionable=True,
                recommended_action="Review the synchronization error and retry product refresh.",
            )
        return _dimension(
            DiagnosticState.INFO,
            "Product synchronization is still in progress.",
            reason_code="product_cache_refresh_in_progress",
            checked_at=_iso(refresh.started_at or refresh.created_at),
            evidence_source="data_layer_refresh_job",
        )

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
        return cast(
            datetime | None,
            self.db.query(func.max(ProductPriceOperation.applied_at))
            .join(ProductPriceOperationItem, ProductPriceOperationItem.operation_id == ProductPriceOperation.id)
            .filter(ProductPriceOperationItem.channel_id == channel_id, ProductPriceOperationItem.status == "applied")
            .scalar(),
        )

    def _last_order_sync(self, channel_id: str) -> datetime | None:
        if not self._table_exists(ChannelOrderRecord) or not self._table_exists(OrderSyncCheckpoint):
            return None
        order_time = self.db.query(func.max(ChannelOrderRecord.last_seen_at)).filter(ChannelOrderRecord.channel_id == channel_id).scalar()
        checkpoint_time = self.db.query(func.max(OrderSyncCheckpoint.last_success_at)).filter(OrderSyncCheckpoint.channel_id == channel_id).scalar()
        return _max_dt(order_time, checkpoint_time)

    def _checkpoint(self, channel_id: str, source: str) -> OrderSyncCheckpoint | None:
        if not self._table_exists(OrderSyncCheckpoint):
            return None
        return (
            self.db.query(OrderSyncCheckpoint)
            .filter_by(channel_id=channel_id, source=source)
            .order_by(OrderSyncCheckpoint.updated_at.desc())
            .first()
        )

    def _polling_policy(self, channel_id: str) -> IntegrationPollingPolicy | None:
        if not self._table_exists(IntegrationPollingPolicy):
            return None
        return self.db.get(IntegrationPollingPolicy, channel_id)

    def _webhook_state(
        self,
        channel_id: str,
        connector_type: str,
        instance: IntegrationConnectorInstance | None,
    ) -> dict[str, Any]:
        if connector_type != "tapsishop":
            return {"supported": False, "enabled": False, "received": 0, "queued": 0, "processed": 0, "deadLetter": 0, "lastReceivedAt": None, "lastProcessedAt": None}
        webhook_enabled = self._setting_present(instance, "webhook_token")
        if not self._table_exists(WebhookReceipt) or not self._table_exists(WebhookDeadLetter):
            return {"supported": True, "enabled": webhook_enabled, "received": 0, "queued": 0, "processed": 0, "deadLetter": 0, "lastReceivedAt": None, "lastProcessedAt": None}
        q = self.db.query(WebhookReceipt).filter_by(channel_id=channel_id)
        receipts = q.all()
        dead = self.db.query(WebhookDeadLetter).filter_by(channel_id=channel_id).count()
        return {
            "supported": True,
            "enabled": webhook_enabled,
            "received": len(receipts),
            "queued": sum(1 for item in receipts if item.processing_state in {"queued", "retry_scheduled"}),
            "processed": sum(1 for item in receipts if item.processing_state == "processed"),
            "deadLetter": dead,
            "lastReceivedAt": _iso(max((item.received_at for item in receipts), default=None)),
            "lastProcessedAt": _iso(max((item.processed_at for item in receipts if item.processed_at), default=None)),
        }

    def _credential_dimension(self, enabled: bool, configured: bool, health: DlConnectorHealth | None) -> DiagnosticPresentation:
        if not enabled:
            return _dimension(
                DiagnosticState.DISABLED,
                "Channel is disabled.",
                reason_code="channel_disabled",
                checked_at=None,
                evidence_source="connector_instance",
            )
        if health and health.error_class in {"authentication", "authentication_failed"}:
            return _dimension(
                DiagnosticState.ERROR,
                "Credential verification failed.",
                reason_code="credential_verification_failed",
                checked_at=_iso(health.checked_at),
                evidence_source="data_layer_health",
                is_actionable=True,
                recommended_action="Review credentials and run the connection test again.",
            )
        if not configured:
            return _dimension(
                DiagnosticState.WARNING,
                "Credentials are not fully configured.",
                reason_code="credentials_incomplete",
                checked_at=None,
                evidence_source="connector_settings",
                is_actionable=True,
                recommended_action="Complete the required credentials.",
            )
        if health is None:
            return _dimension(
                DiagnosticState.NOT_CHECKED,
                "Credential verification has not run yet.",
                reason_code="credentials_not_checked",
                checked_at=None,
                evidence_source="data_layer_health",
                is_actionable=True,
                recommended_action="Run the connection test to verify credentials.",
            )
        if _is_stale(health.checked_at, STALE_HEALTH_AFTER):
            return _dimension(
                DiagnosticState.WARNING,
                "Credential verification evidence is older than 24 hours.",
                reason_code="credential_evidence_expired",
                checked_at=_iso(health.checked_at),
                evidence_source="data_layer_health",
                is_actionable=True,
                recommended_action="Run the connection test again.",
            )
        if health.status == "healthy" and health.last_success_at:
            return _dimension(
                DiagnosticState.HEALTHY,
                "Credentials were verified successfully.",
                reason_code="credentials_verified",
                checked_at=_iso(health.checked_at),
                evidence_source="data_layer_health",
            )
        return _dimension(
            DiagnosticState.WARNING,
            "Credential verification could not be completed.",
            reason_code="credential_verification_inconclusive",
            checked_at=_iso(health.checked_at),
            evidence_source="data_layer_health",
            is_actionable=True,
            recommended_action="Run the connection test again.",
            legacy_status="Unable to check",
        )

    def _external_dimension(
        self,
        enabled: bool,
        configured: bool,
        health: DlConnectorHealth | None,
        supported: bool,
    ) -> DiagnosticPresentation:
        if not enabled:
            return _dimension(
                DiagnosticState.DISABLED,
                "Channel is disabled.",
                reason_code="channel_disabled",
                checked_at=None,
                evidence_source="connector_instance",
            )
        if not supported:
            return _dimension(
                DiagnosticState.NOT_APPLICABLE,
                "This connector does not provide a separate API health probe.",
                reason_code="external_api_probe_not_applicable",
                checked_at=None,
                evidence_source="connector_capability",
            )
        if not configured:
            return _dimension(
                DiagnosticState.NOT_CHECKED,
                "The API connection cannot be checked until configuration is complete.",
                reason_code="external_api_not_checked_configuration_incomplete",
                checked_at=None,
                evidence_source="data_layer_health",
                is_actionable=True,
                recommended_action="Complete channel configuration.",
            )
        if health is None:
            return _dimension(
                DiagnosticState.NOT_CHECKED,
                "No API health check has been recorded.",
                reason_code="external_api_not_checked",
                checked_at=None,
                evidence_source="data_layer_health",
                is_actionable=True,
                recommended_action="Run the connection test.",
            )
        if _is_stale(health.checked_at, STALE_HEALTH_AFTER):
            return _dimension(
                DiagnosticState.WARNING,
                "API health evidence is older than 24 hours.",
                reason_code="external_api_evidence_expired",
                checked_at=_iso(health.checked_at),
                evidence_source="data_layer_health",
                is_actionable=True,
                recommended_action="Run the connection test again.",
            )
        if health.error_class == "timeout" or health.status == "unknown":
            return _dimension(
                DiagnosticState.WARNING,
                "The latest API health check was inconclusive.",
                reason_code="external_api_check_inconclusive",
                checked_at=_iso(health.checked_at),
                evidence_source="data_layer_health",
                is_actionable=True,
                recommended_action="Retry the connection test.",
                legacy_status="Unable to check",
            )
        if health.status == "healthy":
            return _dimension(
                DiagnosticState.HEALTHY,
                "The latest API health check completed successfully.",
                reason_code="external_api_healthy",
                checked_at=_iso(health.checked_at),
                evidence_source="data_layer_health",
            )
        if health.status == "degraded":
            return _dimension(
                DiagnosticState.WARNING,
                _safe_message(cast(str | None, health.detail) or "The API health check needs review."),
                reason_code="external_api_degraded",
                checked_at=_iso(health.checked_at),
                evidence_source="data_layer_health",
                is_actionable=True,
                recommended_action="Review the connection details.",
            )
        return _dimension(
            DiagnosticState.ERROR,
            _safe_message(cast(str | None, health.detail) or "The API health check failed."),
            reason_code="external_api_check_failed",
            checked_at=_iso(health.checked_at),
            evidence_source="data_layer_health",
            is_actionable=True,
            recommended_action="Review the connection error and credentials.",
        )

    def _webhook_receipt_dimension(self, state: dict[str, Any]) -> DiagnosticPresentation:
        if not state["supported"]:
            return _dimension(
                DiagnosticState.NOT_APPLICABLE,
                "This Channel does not use webhooks.",
                reason_code="webhook_not_applicable",
                checked_at=None,
                evidence_source="connector_capability",
            )
        if not state["enabled"]:
            return _dimension(
                DiagnosticState.DISABLED,
                "Webhook receipt is turned off for this Channel.",
                reason_code="webhook_disabled",
                checked_at=None,
                evidence_source="connector_settings",
            )
        if state["received"] == 0:
            return _dimension(
                DiagnosticState.NOT_CHECKED,
                "No webhook receipt evidence has been recorded yet.",
                reason_code="webhook_receipt_not_checked",
                checked_at=None,
                evidence_source="webhook_receipts",
            )
        return _dimension(
            DiagnosticState.HEALTHY,
            "Webhook receipts are being accepted.",
            reason_code="webhook_receipt_healthy",
            checked_at=cast(str | None, state["lastReceivedAt"]),
            evidence_source="webhook_receipts",
        )

    def _webhook_processing_dimension(self, state: dict[str, Any]) -> DiagnosticPresentation:
        if not state["supported"]:
            return _dimension(
                DiagnosticState.NOT_APPLICABLE,
                "This Channel does not use webhook processing.",
                reason_code="webhook_processing_not_applicable",
                checked_at=None,
                evidence_source="connector_capability",
            )
        if not state["enabled"]:
            return _dimension(
                DiagnosticState.DISABLED,
                "Webhook processing is turned off for this Channel.",
                reason_code="webhook_processing_disabled",
                checked_at=None,
                evidence_source="connector_settings",
            )
        if state["queued"] > 0:
            return _dimension(
                DiagnosticState.WARNING,
                "Accepted webhook receipts are waiting for processing.",
                reason_code="webhook_processing_delayed",
                checked_at=cast(str | None, state["lastReceivedAt"]),
                evidence_source="webhook_receipts",
                is_actionable=True,
                recommended_action="Review queued webhook receipts.",
            )
        if not state["processed"]:
            return _dimension(
                DiagnosticState.NOT_CHECKED,
                "No webhook processing evidence has been recorded yet.",
                reason_code="webhook_processing_not_checked",
                checked_at=None,
                evidence_source="webhook_receipts",
            )
        return _dimension(
            DiagnosticState.HEALTHY,
            "Webhook receipts are being processed.",
            reason_code="webhook_processing_healthy",
            checked_at=cast(str | None, state["lastProcessedAt"]),
            evidence_source="webhook_receipts",
        )

    def _dead_letter_dimension(self, state: dict[str, Any]) -> DiagnosticPresentation:
        if not state["supported"]:
            return _dimension(
                DiagnosticState.NOT_APPLICABLE,
                "This Channel does not use a dead-letter queue.",
                reason_code="dead_letter_queue_not_applicable",
                checked_at=None,
                evidence_source="connector_capability",
            )
        if not state["enabled"]:
            return _dimension(
                DiagnosticState.DISABLED,
                "Webhook recovery queues are turned off with webhook processing.",
                reason_code="dead_letter_queue_disabled",
                checked_at=None,
                evidence_source="connector_settings",
            )
        if state["deadLetter"] > 0:
            return _dimension(
                DiagnosticState.ERROR,
                "Webhook dead letters require review.",
                reason_code="dead_letter_queue_has_items",
                checked_at=cast(str | None, state["lastReceivedAt"]),
                evidence_source="webhook_dead_letters",
                is_actionable=True,
                recommended_action="Review and resolve webhook dead letters.",
            )
        return _dimension(
            DiagnosticState.HEALTHY,
            "No webhook dead letters are waiting for recovery.",
            reason_code="dead_letter_queue_empty",
            checked_at=cast(str | None, state["lastReceivedAt"]),
            evidence_source="webhook_dead_letters",
        )

    def _token_refresh_dimension(
        self,
        instance: IntegrationConnectorInstance | None,
        connector_type: str,
        channel_enabled: bool,
    ) -> DiagnosticPresentation:
        if connector_type != "tapsishop":
            return _dimension(
                DiagnosticState.NOT_APPLICABLE,
                "This authentication method does not require token refresh.",
                reason_code="token_refresh_not_applicable",
                checked_at=None,
                evidence_source="connector_capability",
            )
        if not channel_enabled:
            return _dimension(
                DiagnosticState.DISABLED,
                "Channel is disabled.",
                reason_code="channel_disabled",
                checked_at=None,
                evidence_source="connector_instance",
            )
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
        if not enabled:
            return _dimension(
                DiagnosticState.DISABLED,
                "Token refresh is turned off.",
                reason_code="token_refresh_disabled",
                checked_at=_iso(settings["token_refresh_enabled"].updated_at) if settings.get("token_refresh_enabled") else None,
                evidence_source="connector_settings",
            )
        if last_event is None:
            return _dimension(
                DiagnosticState.NOT_CHECKED,
                "Token refresh is enabled, but no refresh event has been recorded.",
                reason_code="token_refresh_not_checked",
                checked_at=None,
                evidence_source="connector_events",
            )
        if "fail" in last_event.event_name.lower() or last_event.severity.lower() in {"warning", "error"}:
            return _dimension(
                DiagnosticState.WARNING if last_event.severity.lower() != "error" else DiagnosticState.ERROR,
                "The latest token refresh event needs attention.",
                reason_code="token_refresh_failed",
                checked_at=_iso(last_event.created_at),
                evidence_source="connector_events",
                is_actionable=True,
                recommended_action="Review credentials and token refresh settings.",
            )
        return _dimension(
            DiagnosticState.HEALTHY,
            "The latest token refresh event completed successfully.",
            reason_code="token_refresh_healthy",
            checked_at=_iso(last_event.created_at),
            evidence_source="connector_events",
        )

    def _channel_ids(self) -> list[str]:
        rows = (
            self.db.query(IntegrationConnectorInstance.id, IntegrationConnectorInstance.connector_type)
            .order_by(IntegrationConnectorInstance.id.asc())
            .all()
        )
        ids = {row.id for row in rows if _is_channel_connector_type(row.connector_type)}
        ids.update(DEFAULT_CHANNEL_IDS)
        return sorted(ids)

    def _runner_state(self) -> dict[str, Any]:
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

    def _order_sync_state(self, channel_id: str) -> dict[str, Any]:
        checkpoints = self.db.query(OrderSyncCheckpoint).filter_by(channel_id=channel_id).all() if self._table_exists(OrderSyncCheckpoint) else []
        last_failure = _max_dt(*(item.last_failure_at for item in checkpoints))
        last_success = _max_dt(
            *(
                item.last_success_at
                for item in checkpoints
            )
        )
        next_run_values = [
            value
            for item in checkpoints
            if (value := item.next_run_at) is not None
        ]
        next_run = min(next_run_values) if next_run_values else None
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
        return bool(inspect(self.db.get_bind()).has_table(model.__tablename__))

    def _polling_dimension(
        self,
        connector_type: str,
        checkpoint: OrderSyncCheckpoint | None,
        policy: IntegrationPollingPolicy | None,
        enabled: bool,
        configured: bool,
    ) -> DiagnosticPresentation:
        if connector_type != "snappshop":
            return _dimension(
                DiagnosticState.NOT_APPLICABLE,
                "This Channel does not use order polling.",
                reason_code="polling_not_applicable",
                checked_at=None,
                evidence_source="connector_capability",
            )
        if not enabled:
            return _dimension(
                DiagnosticState.DISABLED,
                "Channel is disabled.",
                reason_code="channel_disabled",
                checked_at=None,
                evidence_source="connector_instance",
            )
        if (
            not parse_config_bool(os.environ.get("FLOWHUB_ORDER_SYNC_ENABLED"), default=True)
            or policy is None
            or not policy.enabled
        ):
            return _dimension(
                DiagnosticState.DISABLED,
                "Order polling is turned off.",
                reason_code="polling_disabled",
                checked_at=_iso(policy.updated_at) if policy else None,
                evidence_source="integration_polling_policy",
            )
        if not configured:
            return _dimension(
                DiagnosticState.NOT_CHECKED,
                "Order polling cannot run until Channel configuration is complete.",
                reason_code="polling_not_checked_configuration_incomplete",
                checked_at=None,
                evidence_source="order_sync_checkpoint",
                is_actionable=True,
                recommended_action="Complete channel configuration.",
            )
        last_run_at = _max_dt(
            checkpoint.last_run_at if checkpoint else None,
            policy.last_run_at,
        )
        if checkpoint is None or checkpoint.last_success_at is None:
            return _dimension(
                DiagnosticState.WARNING,
                "Order polling is enabled, but no successful polling run has been recorded.",
                reason_code="polling_never_succeeded",
                checked_at=_iso(last_run_at),
                evidence_source="integration_polling_policy_and_order_sync_checkpoint",
                is_actionable=True,
                recommended_action="Review order polling settings.",
            )
        if _is_stale(checkpoint.last_success_at, STALE_SYNC_AFTER):
            return _dimension(
                DiagnosticState.WARNING,
                f"Last successful order polling run was {_age_text(checkpoint.last_success_at)} ago.",
                reason_code="polling_stale",
                checked_at=_iso(checkpoint.last_success_at),
                evidence_source="order_sync_checkpoint",
                is_actionable=True,
                recommended_action="Review order polling.",
                freshness_threshold_hours=24,
            )
        return _dimension(
            DiagnosticState.HEALTHY,
            "Order polling is running successfully.",
            reason_code="polling_healthy",
            checked_at=_iso(checkpoint.last_success_at),
            evidence_source="order_sync_checkpoint",
            freshness_threshold_hours=24,
        )


def _dimension(
    state: DiagnosticState,
    message: str,
    *,
    reason_code: str,
    checked_at: str | None,
    evidence_source: str,
    is_actionable: bool = False,
    recommended_action: str = "",
    legacy_status: str | None = None,
    freshness_threshold_hours: int | None = None,
) -> DiagnosticPresentation:
    return diagnostic_presentation(
        state,
        message,
        reason_code=reason_code,
        checked_at=checked_at,
        evidence_source=evidence_source,
        is_actionable=is_actionable,
        recommended_action=recommended_action,
        legacy_status=legacy_status,
        freshness_threshold_hours=freshness_threshold_hours,
    )


def _channel_state(
    enabled: bool,
    dimensions: dict[str, DiagnosticPresentation],
    core_names: tuple[str, ...],
) -> tuple[DiagnosticState, DiagnosticPresentation]:
    if not enabled:
        return DiagnosticState.DISABLED, _dimension(
            DiagnosticState.DISABLED,
            "Channel is disabled.",
            reason_code="channel_disabled",
            checked_at=None,
            evidence_source="connector_instance",
        )

    for state in (DiagnosticState.ERROR, DiagnosticState.WARNING):
        match = next(
            (
                item
                for item in dimensions.values()
                if item["state"] == state.value and item["is_actionable"]
            ),
            None,
        )
        if match is not None:
            return state, match

    core = [dimensions[name] for name in core_names if name in dimensions]
    missing = next(
        (item for item in core if item["state"] == DiagnosticState.NOT_CHECKED.value),
        None,
    )
    if missing is not None:
        return DiagnosticState.NOT_CHECKED, missing
    if core and all(item["state"] == DiagnosticState.HEALTHY.value for item in core):
        return DiagnosticState.HEALTHY, core[0]

    informative = next(
        (
            item
            for item in dimensions.values()
            if item["state"] in {DiagnosticState.INFO.value, DiagnosticState.NOT_APPLICABLE.value}
        ),
        None,
    )
    if informative is not None:
        return DiagnosticState.INFO, informative
    fallback = core[0] if core else next(iter(dimensions.values()))
    return DiagnosticState.NOT_CHECKED, fallback


def _legacy_channel_status(state: DiagnosticState) -> str:
    return {
        DiagnosticState.HEALTHY: "Operational",
        DiagnosticState.INFO: "Information",
        DiagnosticState.NOT_CHECKED: "Not checked",
        DiagnosticState.NOT_APPLICABLE: "Not applicable",
        DiagnosticState.DISABLED: "Disabled",
        DiagnosticState.WARNING: "Warning",
        DiagnosticState.ERROR: "Error",
    }[state]


def _summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {
        "Operational": 0,
        "Information": 0,
        "Not checked": 0,
        "Not applicable": 0,
        "Warning": 0,
        "Error": 0,
        "Unable to check": 0,
        "Disabled": 0,
    }
    state_counts = {state.value: 0 for state in DiagnosticState}
    for item in items:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
        state_counts[str(item.get("state") or DiagnosticState.NOT_CHECKED.value)] += 1

    if state_counts[DiagnosticState.ERROR.value]:
        overall_state = DiagnosticState.ERROR
    elif state_counts[DiagnosticState.WARNING.value]:
        overall_state = DiagnosticState.WARNING
    elif state_counts[DiagnosticState.NOT_CHECKED.value]:
        overall_state = DiagnosticState.NOT_CHECKED
    elif state_counts[DiagnosticState.HEALTHY.value]:
        overall_state = DiagnosticState.HEALTHY
    elif state_counts[DiagnosticState.INFO.value]:
        overall_state = DiagnosticState.INFO
    elif state_counts[DiagnosticState.DISABLED.value]:
        overall_state = DiagnosticState.DISABLED
    else:
        overall_state = DiagnosticState.NOT_APPLICABLE
    return {
        "overall": _legacy_channel_status(overall_state),
        "overall_state": overall_state.value,
        "counts": counts,
        "state_counts": state_counts,
    }


def _error_category_from_result(result: dict[str, Any]) -> str | None:
    value = str(result.get("code") or result.get("error_code") or result.get("status") or "").lower()
    if "auth" in value or result.get("authenticated") is False:
        return str(ConnectorErrorCategory.AUTHENTICATION.value)
    if "timeout" in value:
        return str(ConnectorErrorCategory.TIMEOUT.value)
    if "rate" in value:
        return str(ConnectorErrorCategory.RATE_LIMIT.value)
    if value in {"not_configured", "disabled"}:
        return "not_configured"
    return str(ConnectorErrorCategory.UNEXPECTED_RESPONSE.value) if result.get("ok") is False else None


def _max_dt(*values: datetime | None) -> datetime | None:
    present = [value for value in values if value is not None]
    return max(present) if present else None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None


def _is_stale(value: datetime, maximum_age: timedelta) -> bool:
    return value < datetime.utcnow() - maximum_age


def _age_text(value: datetime) -> str:
    seconds = max(0, int((datetime.utcnow() - value).total_seconds()))
    days = seconds // 86_400
    if days:
        return f"{days} day" if days == 1 else f"{days} days"
    hours = seconds // 3_600
    if hours:
        return f"{hours} hour" if hours == 1 else f"{hours} hours"
    minutes = seconds // 60
    return f"{minutes} minute" if minutes == 1 else f"{minutes} minutes"


def _safe_message(value: str) -> str:
    blocked = ("token", "authorization", "secret", "phone", "national", "address")
    text = str(value or "")[:400]
    lowered = text.lower()
    if any(word in lowered for word in blocked):
        return "Sensitive diagnostic details were protected."
    return text


def _is_channel_connector_type(connector_type: str) -> bool:
    """Keep Source-only connector instances out of marketplace channel health."""
    return connector_type not in SOURCE_CONNECTOR_TYPES and registry.get_definition(connector_type) is not None
