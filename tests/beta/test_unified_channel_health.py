from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timedelta

import pytest

os.environ.setdefault("FLOWHUB_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FLOWHUB_JWT_SECRET", "test-health-jwt-secret-with-at-least-32-bytes")

from app.flowhub.auth import models as _auth_models  # noqa: F401
from app.flowhub.data_layer import models as _data_layer_models  # noqa: F401
from app.flowhub.integration_platform import models as _integration_models  # noqa: F401
from app.flowhub.orders import models as _order_models  # noqa: F401
from app.flowhub.product_pricing import models as _price_models  # noqa: F401
from app.flowhub.webhooks import models as _webhook_models  # noqa: F401


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
def db(db_engine):
    from sqlalchemy.orm import sessionmaker

    session = sessionmaker(bind=db_engine)()
    yield session
    session.close()


@pytest.fixture()
def client(db_engine):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app.flowhub.app import app
    from app.flowhub.database import get_db

    Session = sessionmaker(bind=db_engine)

    def override_get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(client, db):
    from app.flowhub.auth.jwt_service import create_access_token
    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.auth.password import hash_password

    user = FlowHubUser(username=f"healthadmin_{uuid.uuid4().hex}", hashed_password=hash_password("password123"), role="admin")
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"Authorization": f"Bearer {create_access_token(user.id, user.username, user.role)}"}


def test_operational_tapsishop_health_uses_sanitized_local_evidence(db):
    from app.flowhub.diagnostics.channel_health import ChannelHealthReporter

    now = datetime.utcnow()
    _seed_channel(db, "tapsishop:main", "tapsishop", enabled=True, settings={"token": None, "webhook_token": None, "token_refresh_enabled": True})
    _seed_health(db, "tapsishop:main", "tapsishop", "healthy", now, last_success_at=now, detail="Vendor information check succeeded.")
    _seed_product_read(db, "tapsishop:main", now)
    _seed_order_sync(db, "tapsishop:main", "tapsishop", now)
    _seed_webhook(db, "tapsishop:main", "processed", now)

    item = _item(ChannelHealthReporter(db).report(), "tapsishop:main")

    assert item["status"] == "Operational"
    assert item["dimensions"]["credentials"]["status"] == "Operational"
    assert item["dimensions"]["webhookProcessing"]["status"] == "Operational"
    text = json.dumps(item).lower()
    assert "hook-secret" not in text
    assert "bearer" not in text


def test_disabled_channel_is_disabled_not_error(db):
    from app.flowhub.diagnostics.channel_health import ChannelHealthReporter

    _seed_channel(db, "snappshop:main", "snappshop", enabled=False, settings={"token": None, "agent_identifier": "agent"})
    _seed_health(db, "snappshop:main", "snappshop", "unhealthy", datetime.utcnow(), error_class="authentication")

    item = _item(ChannelHealthReporter(db).report(), "snappshop:main")

    assert item["status"] == "Disabled"
    assert item["dimensions"]["credentials"]["status"] == "Disabled"


def test_invalid_token_is_error_and_timeout_is_unable_to_check(db):
    from app.flowhub.diagnostics.channel_health import ChannelHealthReporter

    now = datetime.utcnow()
    _seed_channel(db, "snappshop:main", "snappshop", enabled=True, settings={"token": None, "agent_identifier": "agent"})
    _seed_health(db, "snappshop:main", "snappshop", "unhealthy", now, error_class="authentication")
    _seed_channel(db, "woocommerce:primary", "woocommerce", enabled=True, settings={"url": "https://store.example", "key": None, "secret": None})
    _seed_health(db, "woocommerce:primary", "woocommerce", "unknown", now, error_class="timeout", detail="probe timed out")
    _seed_product_read(db, "woocommerce:primary", now)
    _seed_order_sync(db, "woocommerce:primary", "woocommerce", now)

    payload = ChannelHealthReporter(db).report()

    snapp = _item(payload, "snappshop:main")
    woo = _item(payload, "woocommerce:primary")
    assert snapp["status"] == "Error"
    assert snapp["dimensions"]["credentials"]["status"] == "Error"
    assert woo["dimensions"]["externalApi"]["status"] == "Unable to check"


def test_malformed_response_stale_sync_delayed_webhook_and_dead_letter_are_visible(db):
    from app.flowhub.diagnostics.channel_health import ChannelHealthReporter

    now = datetime.utcnow()
    stale = now - timedelta(days=3)
    _seed_channel(db, "tapsishop:main", "tapsishop", enabled=True, settings={"token": None, "token_refresh_enabled": True})
    _seed_health(db, "tapsishop:main", "tapsishop", "unhealthy", now, error_class="unexpected_response", detail="token=secret upstream payload")
    _seed_product_read(db, "tapsishop:main", stale)
    _seed_order_sync(db, "tapsishop:main", "tapsishop", stale)
    receipt = _seed_webhook(db, "tapsishop:main", "queued", now)
    _seed_dead_letter(db, receipt.id)

    item = _item(ChannelHealthReporter(db).report(), "tapsishop:main")
    text = json.dumps(item).lower()

    assert item["status"] == "Error"
    assert item["dimensions"]["lastProductSync"]["status"] == "Warning"
    assert item["dimensions"]["webhookProcessing"]["status"] == "Warning"
    assert item["dimensions"]["queueDeadLetter"]["status"] == "Error"
    assert "secret" not in text
    assert "token=secret" not in text


def test_tapsishop_token_refresh_diagnostics_are_channel_scoped(db):
    from app.flowhub.diagnostics.channel_health import ChannelHealthReporter
    from app.flowhub.integration_platform.models import IntegrationConnectorEvent

    now = datetime.utcnow()
    _seed_channel(db, "tapsishop:main", "tapsishop", enabled=True, settings={"token": None, "token_refresh_enabled": True})
    _seed_channel(db, "tapsishop:second", "tapsishop", enabled=True, settings={"token": None, "token_refresh_enabled": True})
    _seed_health(db, "tapsishop:main", "tapsishop", "healthy", now, last_success_at=now)
    _seed_health(db, "tapsishop:second", "tapsishop", "unhealthy", now, error_class="authentication")
    db.add(IntegrationConnectorEvent(
        connector_id="tapsishop:main",
        event_name="token_refresh_succeeded",
        severity="info",
        message="token refreshed",
        metadata_json={},
        created_at=now,
    ))
    db.add(IntegrationConnectorEvent(
        connector_id="tapsishop:second",
        event_name="token_refresh_failed",
        severity="warning",
        message="token refresh failed",
        metadata_json={},
        created_at=now,
    ))
    db.commit()

    payload = ChannelHealthReporter(db).report()
    main = _item(payload, "tapsishop:main")
    second = _item(payload, "tapsishop:second")

    assert "credential_refresh_succeeded" in main["dimensions"]["tokenRefresh"]["message"]
    assert "credential_refresh_failed" not in main["dimensions"]["tokenRefresh"]["message"]
    assert "credential_refresh_failed" in second["dimensions"]["tokenRefresh"]["message"]


def test_channel_health_endpoint_and_refresh_suppress_concurrent_provider_checks(client, db, auth_headers, monkeypatch):
    from app.flowhub.diagnostics.channel_health import _REFRESH_LOCKS

    _seed_channel(db, "snappshop:main", "snappshop", enabled=True, settings={"token": None, "agent_identifier": "agent"})

    listed = client.get("/api/v2/diagnostics/channels/health", headers=auth_headers)
    assert listed.status_code == 200
    assert any(item["channelId"] == "snappshop:main" for item in listed.json()["items"])

    async def should_not_run(self, channel_id):
        raise AssertionError("provider check should be suppressed while the lock is held")

    monkeypatch.setattr("app.flowhub.commerce.service.CommerceHubService.test_channel_connection", should_not_run)

    lock = _REFRESH_LOCKS.setdefault("snappshop:main", asyncio.Lock())
    async def locked_refresh():
        await lock.acquire()
        try:
            response = client.post(
                "/api/v2/diagnostics/channels/health/refresh",
                headers=auth_headers,
                json={"channelId": "snappshop:main"},
            )
            assert response.status_code == 200
            assert response.json()["external_call_performed"] is True
        finally:
            lock.release()

    asyncio.run(locked_refresh())


def test_all_unconfigured_channels_return_normalized_disabled_health(client, auth_headers):
    response = client.get("/api/v2/diagnostics/channels/health", headers=auth_headers)

    assert response.status_code == 200
    items = response.json()["items"]
    assert {item["channelId"] for item in items}.issuperset({"woocommerce:primary", "snappshop:main", "tapsishop:main"})
    assert all(item["status"] == "Disabled" for item in items)


def test_channel_health_report_isolates_one_channel_exception(db, monkeypatch, caplog):
    from app.flowhub.diagnostics.channel_health import ChannelHealthReporter

    original = ChannelHealthReporter._channel_shape

    def fail_one(self, channel_id):
        if channel_id == "snappshop:main":
            raise RuntimeError("token=should-not-leak")
        return original(self, channel_id)

    monkeypatch.setattr(ChannelHealthReporter, "_channel_shape", fail_one)
    payload = ChannelHealthReporter(db).report()
    failed = _item(payload, "snappshop:main")

    assert failed["status"] == "Unable to check"
    assert failed["lastErrorCategory"] == "diagnostic_unavailable"
    assert "should-not-leak" not in json.dumps(payload)
    assert "should-not-leak" not in caplog.text
    assert _item(payload, "tapsishop:main")["status"] == "Disabled"


def _seed_channel(db, channel_id: str, connector_type: str, *, enabled: bool, settings: dict) -> None:
    from app.flowhub.integration_platform.models import IntegrationConnectorInstance, IntegrationConnectorSetting

    now = datetime.utcnow()
    db.add(IntegrationConnectorInstance(
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
        db.add(IntegrationConnectorSetting(
            connector_id=channel_id,
            key=key,
            value_json=value,
            secret=key in {"token", "secret", "key", "webhook_token"},
            configured=True,
            updated_at=now,
        ))
    db.commit()


def _seed_health(db, connector_id: str, connector_type: str, health_status: str, checked_at: datetime, *, last_success_at: datetime | None = None, error_class: str | None = None, detail: str = "ok") -> None:
    from app.flowhub.data_layer.models import DlConnectorHealth

    db.add(DlConnectorHealth(
        connector_id=connector_id,
        connector_type=connector_type,
        status=health_status,
        latency_ms=42,
        detail=detail,
        error_class=error_class,
        consecutive_failures=1 if error_class else 0,
        checked_at=checked_at,
        last_success_at=last_success_at,
    ))
    db.commit()


def _seed_product_read(db, connector_id: str, at: datetime) -> None:
    from app.flowhub.data_layer.models import DlProductCache

    db.add(DlProductCache(
        connector_id=connector_id,
        product_id=f"p-{uuid.uuid4().hex}",
        sku="SKU-1",
        name="Product",
        last_successful_read=at,
    ))
    db.commit()


def _seed_order_sync(db, channel_id: str, connector_type: str, at: datetime) -> None:
    from app.flowhub.orders.models import ChannelOrderRecord, OrderSyncCheckpoint

    db.add(ChannelOrderRecord(
        channel_id=channel_id,
        connector_type=connector_type,
        provider_order_id=f"order-{uuid.uuid4().hex}",
        order_number="ORD-1",
        provider_status="created",
        normalized_status="new",
        currency="IRR",
        raw_hash=uuid.uuid4().hex,
        raw_summary_json={},
        first_seen_at=at,
        last_seen_at=at,
        synchronization_state="synced",
        event_source="api",
    ))
    db.add(OrderSyncCheckpoint(
        channel_id=channel_id,
        connector_type=connector_type,
        source="events",
        cursor="cursor-1",
        last_run_at=at,
        updated_at=at,
    ))
    db.commit()


def _seed_webhook(db, channel_id: str, state: str, at: datetime):
    from app.flowhub.webhooks.models import WebhookReceipt

    receipt = WebhookReceipt(
        channel_id=channel_id,
        provider="tapsishop",
        provider_event_id=f"req-{uuid.uuid4().hex}",
        payload_hash=uuid.uuid4().hex,
        payload_summary_json={"requestId": "req"},
        normalized_event_json={"changeTypeLabel": "deducted_due_to_purchase"},
        received_at=at,
        acknowledged_at=at,
        processing_state=state,
        processed_at=at if state == "processed" else None,
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)
    return receipt


def _seed_dead_letter(db, receipt_id: int) -> None:
    from app.flowhub.webhooks.models import WebhookDeadLetter

    db.add(WebhookDeadLetter(
        receipt_id=receipt_id,
        channel_id="tapsishop:main",
        provider="tapsishop",
        provider_event_id="req-dead",
        reason="processing failed",
        error_category="timeout",
    ))
    db.commit()


def _item(payload: dict, channel_id: str) -> dict:
    return next(item for item in payload["items"] if item["channelId"] == channel_id)
