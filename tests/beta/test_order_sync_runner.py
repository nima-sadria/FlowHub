from __future__ import annotations

import os
import uuid
from datetime import datetime

import pytest

os.environ.setdefault("FLOWHUB_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FLOWHUB_JWT_SECRET", "test-order-runner-jwt-secret-32bytes!")

from app.flowhub.auth import models as _auth_models  # noqa: F401
from app.flowhub.channels.contracts import (
    ChannelIdentifierSet,
    ChannelOrder,
    ChannelOrderEvent,
    ChannelOrderItem,
    CursorPagination,
    PaginatedResult,
)
from app.flowhub.integration_platform import models as _integration_models
from app.flowhub.orders import models as _order_models
from app.flowhub.webhooks import models as _webhook_models


@pytest.fixture()
def db_engine():
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    from app.flowhub.database import FlowHubBase, _get_engine

    _get_engine.cache_clear()
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    FlowHubBase.metadata.create_all(engine)
    yield engine
    FlowHubBase.metadata.drop_all(engine)
    engine.dispose()
    _get_engine.cache_clear()


@pytest.fixture()
def session_factory(db_engine):
    from sqlalchemy.orm import sessionmaker

    return sessionmaker(bind=db_engine)


class RunnerSnappConnector:
    connector_type = "snappshop"

    def __init__(self, channel_id: str, *, fail: bool = False) -> None:
        self.channel_id = channel_id
        self.fail = fail

    async def list_order_events(self, pagination):
        if self.fail:
            raise RuntimeError("upstream unavailable")
        return PaginatedResult(
            items=[
                ChannelOrderEvent(
                    channel_id=self.channel_id,
                    connector_type="snappshop",
                    event_id=f"event-{self.channel_id}",
                    event_type="NEW_ORDER",
                    occurred_at="2026-07-11T10:00:00Z",
                    order_identifiers=ChannelIdentifierSet(order_number=f"ORD-{self.channel_id}"),
                    raw={"event_id": f"event-{self.channel_id}", "event_type": "NEW_ORDER"},
                )
            ],
            pagination=CursorPagination(cursor=None, next_cursor="done", has_more=False, limit=50),
        )

    def acknowledge_order_events(self, page):
        return None

    async def get_order(self, identifiers):
        return ChannelOrder(
            channel_id=self.channel_id,
            connector_type="snappshop",
            identifiers=ChannelIdentifierSet(order_number=identifiers["order_number"]),
            status="NEW_ORDER",
            created_at="2026-07-11T10:00:00Z",
            updated_at="2026-07-11T10:00:00Z",
            items=[
                ChannelOrderItem(
                    identifiers=ChannelIdentifierSet(sku="SKU-RUN"),
                    name="Runner product",
                    quantity=1,
                    unit_price=100,
                    currency="IRR",
                    raw={"id": "item-1", "sku": "SKU-RUN", "quantity": 1},
                )
            ],
            total=100,
            currency="IRR",
            raw={"order_number": identifiers["order_number"]},
        )

    async def list_orders(self, pagination):
        return PaginatedResult(items=[await self.get_order({"order_number": f"ORD-{self.channel_id}"})], pagination=pagination)


class RunnerWooConnector:
    connector_type = "woocommerce"

    def __init__(self, channel_id: str) -> None:
        self.channel_id = channel_id
        self.read_calls = 0

    async def list_orders(self, pagination):
        self.read_calls += 1
        return PaginatedResult(
            items=[
                ChannelOrder(
                    channel_id=self.channel_id,
                    connector_type="woocommerce",
                    identifiers=ChannelIdentifierSet(
                        external_product_id="501", order_number="WC-501"
                    ),
                    status="processing",
                    items=[],
                    total=1200,
                    currency="IRR",
                    raw={"id": 501, "status": "processing"},
                )
            ],
            pagination=pagination,
        )


@pytest.mark.asyncio
async def test_runner_discovers_enabled_channels_filters_capabilities_and_records_heartbeat(session_factory, monkeypatch):
    from app.flowhub.orders.runner import OrderSyncRunner

    with session_factory() as db:
        _seed_channel(db, "snappshop:main", "snappshop", enabled=True, settings={"token": "secret", "agent_identifier": "agent", "order_sync_poll_interval_seconds": 1})
        _seed_channel(db, "tapsishop:main", "tapsishop", enabled=True, settings={"token": "secret"})
        _seed_channel(db, "woocommerce:primary", "woocommerce", enabled=True, settings={})
        _seed_channel(db, "snappshop:disabled", "snappshop", enabled=False, settings={"token": "secret", "agent_identifier": "agent"})
        _seed_receipt(db, "tapsishop:main")

    monkeypatch.setattr(OrderSyncRunner, "_snappshop_connector", lambda self, channel_id, settings: RunnerSnappConnector(channel_id))
    monkeypatch.setattr(OrderSyncRunner, "_tapsishop_connector", lambda self, channel_id, settings: None)
    runner = OrderSyncRunner(session_factory, settings=_settings(), runner_id="runner-test")

    result = await runner.run_once()

    assert result["channels"] == 3
    with session_factory() as db:
        assert db.query(_order_models.ChannelOrderRecord).filter_by(channel_id="snappshop:main").count() == 1
        assert db.query(_webhook_models.WebhookReceipt).filter_by(channel_id="tapsishop:main", processing_state="processed").count() == 1
        assert db.query(_integration_models.IntegrationConnectorEvent).filter_by(connector_id="flowhub:order-sync-runner", event_name="order_sync_runner_heartbeat").count() >= 2
        assert db.query(_order_models.ChannelOrderRecord).filter_by(channel_id="snappshop:disabled").count() == 0


@pytest.mark.asyncio
async def test_runner_channel_failure_does_not_stop_other_channels(session_factory, monkeypatch):
    from app.flowhub.orders.runner import OrderSyncRunner

    with session_factory() as db:
        _seed_channel(db, "snappshop:main", "snappshop", enabled=True, settings={"token": "secret", "agent_identifier": "agent"})
        _seed_channel(db, "snappshop:second", "snappshop", enabled=True, settings={"token": "secret", "agent_identifier": "agent"})

    def connector(self, channel_id, settings):
        return RunnerSnappConnector(channel_id, fail=channel_id == "snappshop:main")

    monkeypatch.setattr(OrderSyncRunner, "_snappshop_connector", connector)
    runner = OrderSyncRunner(session_factory, settings=_settings(), runner_id="runner-failure")

    await runner.run_once()

    with session_factory() as db:
        assert db.query(_order_models.ChannelOrderRecord).filter_by(channel_id="snappshop:second").count() == 1
        failure = db.query(_integration_models.IntegrationConnectorEvent).filter_by(connector_id="snappshop:main", event_name="order_sync_channel_failed").one()
        assert "secret" not in str(failure.metadata_json).lower()


@pytest.mark.asyncio
async def test_runner_reconciles_woocommerce_through_read_only_shared_service(
    session_factory, monkeypatch
):
    from app.flowhub.orders.runner import OrderSyncRunner

    with session_factory() as db:
        _seed_channel(
            db,
            "woocommerce:primary",
            "woocommerce",
            enabled=True,
            settings={
                "url": "https://woocommerce.example.invalid",
                "key": "test-key",
                "secret": "test-secret",
            },
        )

    connector = RunnerWooConnector("woocommerce:primary")
    monkeypatch.setattr(
        OrderSyncRunner,
        "_woocommerce_connector",
        lambda self, channel_id, settings: connector,
    )
    runner = OrderSyncRunner(
        session_factory, settings=_settings(), runner_id="runner-woo-read"
    )

    result = await runner.run_once()

    assert connector.read_calls == 1
    assert result["results"][0]["source"] == "reconciliation"
    with session_factory() as db:
        assert (
            db.query(_order_models.ChannelOrderRecord)
            .filter_by(channel_id="woocommerce:primary")
            .count()
            == 1
        )
        assert db.query(_order_models.ChannelInventoryEffectRecord).count() == 0


@pytest.mark.asyncio
async def test_runner_records_sanitized_lost_lease_category_without_success(session_factory, monkeypatch):
    from app.flowhub.orders.runner import OrderSyncRunner
    from app.flowhub.orders.service import OrderSyncLeaseError

    with session_factory() as db:
        _seed_channel(db, "snappshop:lease-lost", "snappshop", enabled=True, settings={"token": "secret", "agent_identifier": "agent"})

    monkeypatch.setattr(OrderSyncRunner, "_snappshop_connector", lambda self, channel_id, settings: RunnerSnappConnector(channel_id))

    async def lose_lease(self, channel_id, connector, **kwargs):
        raise OrderSyncLeaseError("lease_lost")

    monkeypatch.setattr(OrderSyncRunner, "_sync_snappshop", lose_lease)
    runner = OrderSyncRunner(session_factory, settings=_settings(), runner_id="runner-lease-lost")

    await runner.run_once()

    with session_factory() as db:
        failure = db.query(_integration_models.IntegrationConnectorEvent).filter_by(
            connector_id="snappshop:lease-lost", event_name="order_sync_channel_failed"
        ).one()
        assert failure.metadata_json["category"] == "lease_lost"
        assert "secret" not in str(failure.metadata_json).lower()
        assert db.query(_integration_models.IntegrationConnectorEvent).filter_by(
            connector_id="snappshop:lease-lost", event_name="order_sync_snappshop_events_completed"
        ).count() == 0


@pytest.mark.asyncio
async def test_runner_graceful_shutdown_records_stopped_heartbeat(session_factory):
    from app.flowhub.orders.runner import OrderSyncRunner, OrderSyncRunnerSettings

    runner = OrderSyncRunner(
        session_factory,
        settings=OrderSyncRunnerSettings(
            enabled=False,
            loop_interval_seconds=1,
            polling_interval_seconds=1,
            reconciliation_interval_seconds=1,
            lease_seconds=30,
            snappshop_max_pages=1,
            reconciliation_page_size=10,
            tapsishop_webhook_batch_size=10,
            operation_timeout_seconds=10,
        ),
        runner_id="runner-stop",
    )
    runner.stop()
    await runner.serve_forever()

    with session_factory() as db:
        event = (
            db.query(_integration_models.IntegrationConnectorEvent)
            .filter_by(connector_id="flowhub:order-sync-runner", event_name="order_sync_runner_heartbeat")
            .order_by(_integration_models.IntegrationConnectorEvent.created_at.desc())
            .first()
        )
        assert event.metadata_json["state"] == "stopped"


def _settings():
    from app.flowhub.orders.runner import OrderSyncRunnerSettings

    return OrderSyncRunnerSettings(
        enabled=True,
        loop_interval_seconds=1,
        polling_interval_seconds=1,
        reconciliation_interval_seconds=1,
        lease_seconds=30,
        snappshop_max_pages=1,
        reconciliation_page_size=10,
        tapsishop_webhook_batch_size=10,
        operation_timeout_seconds=10,
    )


def _seed_channel(db, channel_id: str, connector_type: str, *, enabled: bool, settings: dict) -> None:
    now = datetime.utcnow()
    db.add(_integration_models.IntegrationConnectorInstance(
        id=channel_id,
        connector_type=connector_type,
        name=channel_id,
        version="1.0.0",
        enabled=enabled,
        read_only=True,
        status="configured" if enabled else "disabled",
        created_at=now,
        updated_at=now,
    ))
    for key, value in settings.items():
        db.add(_integration_models.IntegrationConnectorSetting(
            connector_id=channel_id,
            key=key,
            value_json=value,
            secret=key in {"token", "secret", "key", "webhook_token"},
            configured=True,
            updated_at=now,
        ))
    db.commit()


def _seed_receipt(db, channel_id: str) -> None:
    request_id = f"req-{uuid.uuid4().hex}"
    db.add(_webhook_models.WebhookReceipt(
        channel_id=channel_id,
        provider="tapsishop",
        provider_event_id=request_id,
        payload_hash=uuid.uuid4().hex.ljust(64, "0")[:64],
        payload_summary_json={"requestId": request_id, "orderId": "T-1", "changeType": 1, "itemCount": 1},
        normalized_event_json={
            "requestId": request_id,
            "orderId": "T-1",
            "changeType": 1,
            "changeTypeLabel": "deducted_due_to_purchase",
            "occurredAt": "2026-07-11T11:01:00Z",
            "orderDetail": {"orderId": "T-1", "orderNumber": "T-1", "status": "1"},
            "items": [{"orderItemId": "tap-item-1", "productId": "tap-prod-1", "sku": None, "quantity": 1, "price": 9000}],
        },
        acknowledged_at=datetime.utcnow(),
        processing_state="queued",
    ))
    db.commit()
