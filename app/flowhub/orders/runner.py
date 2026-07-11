"""Production runner for marketplace order synchronization.

Run as a separate process:

    python -m app.flowhub.orders.runner

The API process must not start this loop. Channel leases in the database prevent
overlap between runner instances and between polling/reconciliation work for the
same channel.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.flowhub.channels.contracts import ChannelCapability
from app.flowhub.channels.registry import default_marketplace_registry
from app.flowhub.channels.snappshop import SnappShopConfig, SnappShopConnector
from app.flowhub.channels.tapsishop import TapsiShopConfig, TapsiShopConnector
from app.flowhub.database import _get_engine
from app.flowhub.integration_platform.models import (
    IntegrationConnectorEvent,
    IntegrationConnectorInstance,
    IntegrationConnectorSetting,
)
from app.flowhub.orders.service import LOCK_TTL_SECONDS, OrderSyncResult, OrderSyncService
from app.flowhub.security.redaction import redact_sensitive


LOGGER = logging.getLogger("flowhub.orders.runner")
RUNNER_EVENT_NAME = "order_sync_runner_heartbeat"
RUN_EVENT_PREFIX = "order_sync_"


@dataclass(frozen=True)
class OrderSyncRunnerSettings:
    enabled: bool
    loop_interval_seconds: int
    polling_interval_seconds: int
    reconciliation_interval_seconds: int
    lease_seconds: int
    snappshop_max_pages: int
    reconciliation_page_size: int
    tapsishop_webhook_batch_size: int
    operation_timeout_seconds: int

    @classmethod
    def from_env(cls) -> "OrderSyncRunnerSettings":
        return cls(
            enabled=_env_bool("FLOWHUB_ORDER_SYNC_ENABLED", True),
            loop_interval_seconds=_env_int("FLOWHUB_ORDER_SYNC_RUNNER_POLL_SECONDS", 30),
            polling_interval_seconds=_env_int("FLOWHUB_ORDER_SYNC_POLL_INTERVAL_SECONDS", 300),
            reconciliation_interval_seconds=_env_int("FLOWHUB_ORDER_SYNC_RECONCILE_INTERVAL_SECONDS", 900),
            lease_seconds=_env_int("FLOWHUB_ORDER_SYNC_LEASE_SECONDS", LOCK_TTL_SECONDS),
            snappshop_max_pages=_env_int("FLOWHUB_ORDER_SYNC_MAX_PAGES", 10),
            reconciliation_page_size=_env_int("FLOWHUB_ORDER_SYNC_RECONCILE_PAGE_SIZE", 50),
            tapsishop_webhook_batch_size=_env_int("FLOWHUB_ORDER_SYNC_WEBHOOK_BATCH_SIZE", 100),
            operation_timeout_seconds=_env_int("FLOWHUB_ORDER_SYNC_OPERATION_TIMEOUT_SECONDS", 60),
        )


class OrderSyncRunner:
    def __init__(
        self,
        session_factory: sessionmaker,
        *,
        settings: OrderSyncRunnerSettings | None = None,
        runner_id: str | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings or OrderSyncRunnerSettings.from_env()
        self.runner_id = runner_id or f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:12]}"
        self._registry = default_marketplace_registry()
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def serve_forever(self) -> None:
        LOGGER.info("order_sync_runner_started", extra={"runner_id": self.runner_id, "enabled": self.settings.enabled})
        while not self._stop.is_set():
            if self.settings.enabled:
                await self.run_once()
            else:
                self._record_runner_heartbeat("disabled")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.settings.loop_interval_seconds)
            except TimeoutError:
                continue
        self._record_runner_heartbeat("stopped")
        LOGGER.info("order_sync_runner_stopped", extra={"runner_id": self.runner_id})

    async def run_once(self) -> dict[str, Any]:
        self._record_runner_heartbeat("running")
        channels = self._discover_channels()
        results: list[dict[str, Any]] = []
        for channel in channels:
            try:
                channel_results = await self._run_channel(channel)
                results.extend(channel_results)
            except Exception as exc:
                self._record_event(
                    channel.id,
                    "order_sync_channel_failed",
                    "Order synchronization failed for one channel; other channels will continue.",
                    {"category": _error_category(exc), "runner_id": self.runner_id},
                    severity="error",
                )
                LOGGER.warning(
                    "order_sync_channel_failed",
                    extra={"channel_id": channel.id, "connector_type": channel.connector_type, "category": _error_category(exc)},
                )
        self._record_runner_heartbeat("idle")
        return {"runnerId": self.runner_id, "channels": len(channels), "results": results}

    def _discover_channels(self) -> list[IntegrationConnectorInstance]:
        with self.session_factory() as db:
            return (
                db.query(IntegrationConnectorInstance)
                .filter(IntegrationConnectorInstance.enabled.is_(True))
                .order_by(IntegrationConnectorInstance.id.asc())
                .all()
            )

    async def _run_channel(self, channel: IntegrationConnectorInstance) -> list[dict[str, Any]]:
        capabilities = self._capabilities(channel)
        if not capabilities.intersection({
            ChannelCapability.ORDERS_EVENTS_POLL,
            ChannelCapability.ORDERS_READ,
            ChannelCapability.ORDERS_WEBHOOK_RECEIVE,
        }):
            return []

        settings = _settings(channel)
        results: list[dict[str, Any]] = []
        if channel.connector_type == "snappshop":
            connector = self._snappshop_connector(channel.id, settings)
            if connector and ChannelCapability.ORDERS_EVENTS_POLL in capabilities and self._due(channel.id, "snappshop_events", self._int_setting(settings, "order_sync_poll_interval_seconds", self.settings.polling_interval_seconds)):
                result = await self._bounded(
                    self._sync_snappshop(
                        channel.id,
                        connector,
                        limit_pages=self._int_setting(settings, "order_sync_max_pages", self.settings.snappshop_max_pages),
                        lease_seconds=self._int_setting(settings, "order_sync_lease_seconds", self.settings.lease_seconds),
                        interval_seconds=self._int_setting(settings, "order_sync_poll_interval_seconds", self.settings.polling_interval_seconds),
                    )
                )
                results.append(self._result_shape(result))
            if connector and ChannelCapability.ORDERS_READ in capabilities and self._due(channel.id, "reconciliation", self._int_setting(settings, "order_sync_reconcile_interval_seconds", self.settings.reconciliation_interval_seconds)):
                result = await self._bounded(
                    self._reconcile(
                        channel.id,
                        connector,
                        page_size=self._int_setting(settings, "order_sync_reconcile_page_size", self.settings.reconciliation_page_size),
                        lease_seconds=self._int_setting(settings, "order_sync_lease_seconds", self.settings.lease_seconds),
                        interval_seconds=self._int_setting(settings, "order_sync_reconcile_interval_seconds", self.settings.reconciliation_interval_seconds),
                    )
                )
                results.append(self._result_shape(result))
        elif channel.connector_type == "tapsishop":
            connector = self._tapsishop_connector(channel.id, settings) if ChannelCapability.ORDERS_READ in capabilities else None
            if ChannelCapability.ORDERS_WEBHOOK_RECEIVE in capabilities:
                result = await self._bounded(
                    self._process_tapsishop_webhooks(
                        channel.id,
                        connector,
                        limit=self._int_setting(settings, "order_sync_webhook_batch_size", self.settings.tapsishop_webhook_batch_size),
                        lease_seconds=self._int_setting(settings, "order_sync_lease_seconds", self.settings.lease_seconds),
                    )
                )
                results.append(self._result_shape(result))
            if connector and self._due(channel.id, "reconciliation", self._int_setting(settings, "order_sync_reconcile_interval_seconds", self.settings.reconciliation_interval_seconds)):
                result = await self._bounded(
                    self._reconcile(
                        channel.id,
                        connector,
                        page_size=self._int_setting(settings, "order_sync_reconcile_page_size", self.settings.reconciliation_page_size),
                        lease_seconds=self._int_setting(settings, "order_sync_lease_seconds", self.settings.lease_seconds),
                        interval_seconds=self._int_setting(settings, "order_sync_reconcile_interval_seconds", self.settings.reconciliation_interval_seconds),
                    )
                )
                results.append(self._result_shape(result))
        return results

    async def _bounded(self, operation: Any) -> OrderSyncResult:
        return await asyncio.wait_for(operation, timeout=self.settings.operation_timeout_seconds)

    async def _sync_snappshop(self, channel_id: str, connector: Any, **kwargs: Any) -> OrderSyncResult:
        db = self.session_factory()
        try:
            return await OrderSyncService(db).sync_snappshop_events(channel_id, connector, **kwargs)
        finally:
            db.close()

    async def _reconcile(self, channel_id: str, connector: Any, **kwargs: Any) -> OrderSyncResult:
        db = self.session_factory()
        try:
            return await OrderSyncService(db).reconcile_recent_orders(channel_id, connector, **kwargs)
        finally:
            db.close()

    async def _process_tapsishop_webhooks(self, channel_id: str, connector: Any | None, **kwargs: Any) -> OrderSyncResult:
        db = self.session_factory()
        try:
            return await OrderSyncService(db).process_tapsishop_webhook_receipts(channel_id, connector, **kwargs)
        finally:
            db.close()

    def _capabilities(self, channel: IntegrationConnectorInstance) -> set[ChannelCapability]:
        definition = self._registry.get_definition(channel.id)
        if definition is not None:
            return set(definition.capabilities)
        for item in self._registry.list_definitions():
            if item.connector_type == channel.connector_type:
                return set(item.capabilities)
        return set()

    def _due(self, channel_id: str, source: str, interval_seconds: int) -> bool:
        with self.session_factory() as db:
            from app.flowhub.orders.models import OrderSyncCheckpoint

            row = db.query(OrderSyncCheckpoint).filter_by(channel_id=channel_id, source=source).first()
            if row is None or row.next_run_at is None:
                return True
            return row.next_run_at <= datetime.utcnow() or row.last_run_at is None or row.last_run_at < datetime.utcnow() - timedelta(seconds=max(1, interval_seconds))

    def _snappshop_connector(self, channel_id: str, settings: dict[str, Any]) -> SnappShopConnector | None:
        try:
            config = SnappShopConfig.from_values(settings=settings, secrets=settings)
        except (TypeError, ValueError):
            self._record_event(channel_id, "order_sync_channel_skipped", "SnappShop order sync skipped because configuration is incomplete.", {"category": "configuration"})
            return None
        return SnappShopConnector(channel_id=channel_id, config=config)

    def _tapsishop_connector(self, channel_id: str, settings: dict[str, Any]) -> TapsiShopConnector | None:
        try:
            config = TapsiShopConfig.from_values(settings=settings, secrets=settings)
        except (TypeError, ValueError):
            self._record_event(channel_id, "order_sync_channel_skipped", "TapsiShop order reconciliation skipped because configuration is incomplete.", {"category": "configuration"})
            return None

        def update_token(new_token: str) -> None:
            with self.session_factory() as db:
                _upsert_setting(db, channel_id, "token", new_token, secret=True)

        return TapsiShopConnector(channel_id=channel_id, config=config, token_updater=update_token)

    def _record_runner_heartbeat(self, state: str) -> None:
        self._record_event(
            "flowhub:order-sync-runner",
            RUNNER_EVENT_NAME,
            f"Order sync runner heartbeat: {state}.",
            {"runner_id": self.runner_id, "state": state},
        )

    def _record_event(self, connector_id: str, event_name: str, message: str, metadata: dict, *, severity: str = "info") -> None:
        with self.session_factory() as db:
            db.add(IntegrationConnectorEvent(
                connector_id=connector_id,
                event_name=event_name,
                severity=severity,
                message=message,
                metadata_json=redact_sensitive(metadata),
                created_at=datetime.utcnow(),
            ))
            db.commit()

    def _result_shape(self, result: OrderSyncResult) -> dict:
        self._record_event(
            result.channel_id,
            f"{RUN_EVENT_PREFIX}{result.source}_completed",
            "Order synchronization operation completed.",
            {
                "runner_id": self.runner_id,
                "source": result.source,
                "processed": result.processed,
                "duplicates": result.duplicates,
                "effects_created": result.effects_created,
                "cursor": result.cursor,
                "state": result.state,
                "canonical_inventory_mutated": False,
                "product_prices_written": False,
            },
        )
        return {
            "channelId": result.channel_id,
            "source": result.source,
            "processed": result.processed,
            "duplicates": result.duplicates,
            "effectsCreated": result.effects_created,
            "state": result.state,
        }

    def _int_setting(self, settings: dict[str, Any], key: str, default: int) -> int:
        try:
            return max(1, int(settings.get(key) or default))
        except (TypeError, ValueError):
            return max(1, int(default))


def make_session_factory() -> sessionmaker:
    db_url = os.environ.get("FLOWHUB_DATABASE_URL", "")
    if not db_url:
        raise RuntimeError("FLOWHUB_DATABASE_URL is not configured")
    return sessionmaker(autocommit=False, autoflush=False, bind=_get_engine(db_url))


async def main_async() -> None:
    logging.basicConfig(level=os.environ.get("FLOWHUB_LOG_LEVEL", "INFO"))
    runner = OrderSyncRunner(make_session_factory())
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, runner.stop)
        except NotImplementedError:
            pass
    await runner.serve_forever()


def main() -> None:
    asyncio.run(main_async())


def _settings(channel: IntegrationConnectorInstance) -> dict[str, Any]:
    return {item.key: item.value_json for item in channel.settings if item.configured}


def _upsert_setting(db: Session, channel_id: str, key: str, value: Any, *, secret: bool) -> None:
    row = db.query(IntegrationConnectorSetting).filter_by(connector_id=channel_id, key=key).first()
    if row is None:
        row = IntegrationConnectorSetting(connector_id=channel_id, key=key, secret=secret)
        db.add(row)
    row.value_json = value
    row.configured = value not in (None, "")
    row.secret = secret
    row.updated_at = datetime.utcnow()
    db.commit()


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, "") or default))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _error_category(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    if isinstance(detail, str) and detail:
        return detail[:80]
    return exc.__class__.__name__


if __name__ == "__main__":
    main()
