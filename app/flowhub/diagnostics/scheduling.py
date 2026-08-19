"""Due-work evaluation for Diagnostics evidence.

This is not a scheduler or daemon.  The existing order-sync runner calls this
evaluator from its established loop.  Diagnostics HTTP reads never call it.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import joinedload, sessionmaker

from app.flowhub.channels.contracts import ChannelCapability
from app.flowhub.channels.registry import default_marketplace_registry
from app.flowhub.commerce.service import CommerceHubService
from app.flowhub.data_layer.models import DlConnectorHealth, DlRefreshJob
from app.flowhub.diagnostics.state_model import (
    COMING_SOON_PROVIDERS,
    SOURCE_CONNECTOR_TYPES,
    DiagnosticsPolicyCatalog,
    ScheduleMode,
)
from app.flowhub.integration_platform.models import IntegrationConnectorInstance
from app.flowhub.security.upstream_errors import (
    CATEGORY_INTERNAL_ERROR,
    CATEGORY_REFRESH_IN_PROGRESS,
    classify_failure,
)
from app.flowhub.source_workspace.models import SourceProfile
from app.flowhub.webhooks.service import WebhookIngestionService


def _channel_read_targeted_light_enabled() -> bool:
    """When on, ChannelEntityWorkRunner (entity_work_runner.py) owns
    webhook-driven observation entirely, and a pending receipt must no
    longer make this evaluator's full-channel refresh due -- that coupling
    (channel-wide DlRefreshJob lease shared with webhook-driven work) is
    the root cause ADR_CHANNEL_READ_ARCHITECTURE.md fixes. Off preserves
    today's exact behavior unchanged; this is the rollback path, a config
    flip rather than a revert-and-redeploy."""
    value = os.environ.get("FLOWHUB_CHANNEL_READ_TARGETED_LIGHT_ENABLED")
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


class ScheduledDiagnosticsEvaluator:
    """Execute only explicitly due, read-only integration work."""

    def __init__(
        self,
        session_factory: sessionmaker,
        *,
        policies: DiagnosticsPolicyCatalog | None = None,
        now: datetime | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.policies = policies or DiagnosticsPolicyCatalog()
        self.now = now
        self.marketplace = default_marketplace_registry()

    async def run_once(self) -> dict[str, Any]:
        now = self.now or datetime.now(timezone.utc).replace(tzinfo=None)
        with self.session_factory() as db:
            archived_connector_ids = {
                connector_id
                for (connector_id,) in db.query(SourceProfile.external_source_id)
                .filter(
                    SourceProfile.status == "archived",
                    SourceProfile.external_source_id.is_not(None),
                )
                .all()
                if connector_id
            }
            instances = (
                db.query(IntegrationConnectorInstance)
                .options(joinedload(IntegrationConnectorInstance.settings))
                .filter(IntegrationConnectorInstance.enabled.is_(True))
                .order_by(IntegrationConnectorInstance.id.asc())
                .all()
            )
            candidates = [
                row
                for row in instances
                if row.id not in archived_connector_ids
                and row.connector_type not in COMING_SOON_PROVIDERS
                and self._configured(row)
            ]

        connection_results: list[dict[str, Any]] = []
        product_results: list[dict[str, Any]] = []
        for instance in candidates:
            connection_policy = self.policies.connection(instance.connector_type)
            if self._connection_due(instance.id, connection_policy.interval_seconds, now):
                connection_results.append(await self._check_connection(instance))

            if instance.connector_type in SOURCE_CONNECTOR_TYPES:
                continue
            product_policy = self.policies.product_sync(instance.connector_type)
            scheduled_poll_due = (
                product_policy.mode == ScheduleMode.SCHEDULED
                and product_policy.enabled
                and product_policy.interval_seconds is not None
                and self._supports_products(instance)
                and self._product_due(instance.id, product_policy.interval_seconds, now)
            )
            # WooCommerce product webhooks were originally event-driven
            # evidence handled right here: a queued receipt made a full
            # channel refresh due immediately, sharing the same
            # DlRefreshJob lease a full catalog scan uses. That coupling is
            # exactly what let a long full-catalog job block webhook-driven
            # observation (the 2026-08-18 dead-letter incident) -- see
            # ADR_CHANNEL_READ_ARCHITECTURE.md. When the flag is enabled,
            # ChannelEntityWorkRunner (entity_work_runner.py) owns this
            # entirely through the independent per-entity lease, and a
            # pending receipt must no longer influence this evaluator's
            # full-refresh due-check. When the flag is off, behavior here
            # is exactly what it always was -- unchanged.
            pending_woocommerce_receipt_ids: list[int] = []
            if (
                instance.connector_type == "woocommerce"
                and self._supports_products(instance)
                and not _channel_read_targeted_light_enabled()
            ):
                with self.session_factory() as db:
                    pending_woocommerce_receipt_ids = WebhookIngestionService(db).pending_woocommerce_receipt_ids(
                        instance.id
                    )
            if scheduled_poll_due or pending_woocommerce_receipt_ids:
                product_results.append(
                    await self._sync_products(instance.id, webhook_receipt_ids=pending_woocommerce_receipt_ids)
                )

        return {
            "connectionChecks": connection_results,
            "productSynchronizations": product_results,
            "externalWritePerformed": False,
        }

    def _connection_due(
        self, connector_id: str, interval_seconds: int | None, now: datetime
    ) -> bool:
        if interval_seconds is None:
            return False
        with self.session_factory() as db:
            checked_at = (
                db.query(func.max(DlConnectorHealth.checked_at))
                .filter(DlConnectorHealth.connector_id == connector_id)
                .scalar()
            )
        return checked_at is None or checked_at <= now - timedelta(seconds=interval_seconds)

    def _product_due(
        self, connector_id: str, interval_seconds: int, now: datetime
    ) -> bool:
        with self.session_factory() as db:
            latest = (
                db.query(func.max(DlRefreshJob.created_at))
                .filter(
                    DlRefreshJob.connector_id == connector_id,
                    DlRefreshJob.entity_type == "products",
                    DlRefreshJob.status.in_(
                        ("pending", "running", "completed", "completed_with_warnings", "failed", "partial_failed")
                    ),
                )
                .scalar()
            )
        return latest is None or latest <= now - timedelta(seconds=interval_seconds)

    async def _check_connection(
        self, instance: IntegrationConnectorInstance
    ) -> dict[str, Any]:
        with self.session_factory() as db:
            service = CommerceHubService(db)
            try:
                result = (
                    await service.test_source_connection(instance.id)
                    if instance.connector_type in SOURCE_CONNECTOR_TYPES
                    else await service.test_channel_connection(instance.id)
                )
                return {
                    "connectorId": instance.id,
                    "status": str(result.get("status") or "unknown"),
                    "externalCallPerformed": bool(result.get("external_call_performed")),
                }
            except Exception as exc:
                db.rollback()
                return {
                    "connectorId": instance.id,
                    "status": "failed",
                    "errorCategory": exc.__class__.__name__,
                    "externalCallPerformed": False,
                }

    async def _sync_products(
        self, channel_id: str, *, webhook_receipt_ids: list[int] | None = None
    ) -> dict[str, Any]:
        with self.session_factory() as db:
            try:
                result = await CommerceHubService(db).refresh_channel_cache(
                    channel_id,
                    "diagnostics-runner",
                    job_type="scheduled",
                )
                status_value = str(result.get("status") or "unknown")
                ok = status_value in {"completed", "completed_with_warnings"}
                error = result.get("error") if isinstance(result.get("error"), dict) else {}
                # Refresh responses retain the public error contract.  The
                # internal result object carries the classification for this
                # in-process evaluator without serialising it to API callers.
                category = str(
                    getattr(result, "failure_category", None) or error.get("category") or ""
                )
                # A deferred refresh was never executed (another unexpired
                # lease owns the channel). Leaving the receipts queued costs
                # them nothing; marking them failed burned one of their five
                # attempts per 30s runner tick and dead-lettered healthy
                # deliveries within ~2.5 minutes.
                deferred = bool(result.get("deferred")) or category == CATEGORY_REFRESH_IN_PROGRESS
                processed = 0
                if webhook_receipt_ids and not deferred:
                    service = WebhookIngestionService(db)
                    for receipt_id in webhook_receipt_ids:
                        if ok:
                            service.mark_woocommerce_receipt_processed(receipt_id)
                        else:
                            # Retryability must follow the real, normalized
                            # category. Hardcoding "temporary" made an expired
                            # credential and an internal bug retry five times
                            # exactly like a transient network blip.
                            service.mark_woocommerce_receipt_failed(
                                receipt_id,
                                category or "temporary",
                                str(error.get("message") or "product cache refresh failed"),
                            )
                        processed += 1
                return {
                    "channelId": channel_id,
                    "status": status_value,
                    "deferred": deferred,
                    "errorCategory": category or None,
                    "externalWritePerformed": False,
                    "webhookReceiptsProcessed": processed,
                }
            except Exception as exc:
                db.rollback()
                # An exception escaping refresh_channel_cache is FlowHub's own
                # failure, not the provider's: classify it honestly so the
                # receipt taxonomy stays truthful.
                safe = classify_failure(exc, source="woocommerce")
                category = str(safe.get("category") or CATEGORY_INTERNAL_ERROR)
                if webhook_receipt_ids:
                    service = WebhookIngestionService(db)
                    for receipt_id in webhook_receipt_ids:
                        try:
                            service.mark_woocommerce_receipt_failed(
                                receipt_id, category, str(safe.get("message") or exc.__class__.__name__)
                            )
                        except Exception:
                            db.rollback()
                return {
                    "channelId": channel_id,
                    "status": "failed",
                    "errorCategory": category,
                    "externalWritePerformed": False,
                }

    def _supports_products(self, instance: IntegrationConnectorInstance) -> bool:
        definition = self.marketplace.get_definition(instance.id)
        if definition is None:
            definition = next(
                (
                    item
                    for item in self.marketplace.list_definitions()
                    if item.connector_type == instance.connector_type
                ),
                None,
            )
        return bool(
            definition and ChannelCapability.PRODUCTS_READ in definition.capabilities
        )

    @staticmethod
    def _configured(instance: IntegrationConnectorInstance) -> bool:
        required = {
            "woocommerce": {"url", "key", "secret"},
            "snappshop": {"token", "agent_identifier", "vendor_id"},
            "tapsishop": {"token"},
            "technolife": {"api_key", "encryption_secret"},
            "nextcloud": {"url", "username", "password", "spreadsheet_path"},
        }.get(instance.connector_type)
        if not required:
            return False
        configured = {row.key for row in instance.settings if row.configured}
        return required.issubset(configured)
