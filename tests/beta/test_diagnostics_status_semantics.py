from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("FLOWHUB_DATABASE_URL", "sqlite:///:memory:")

from app.flowhub.auth import models as _auth_models  # noqa: F401
from app.flowhub.data_layer import models as _data_layer_models  # noqa: F401
from app.flowhub.data_layer.models import DlConnectorHealth, DlProductCache
from app.flowhub.database import FlowHubBase
from app.flowhub.diagnostics.channel_health import ChannelHealthReporter
from app.flowhub.integration_platform import models as _integration_models  # noqa: F401
from app.flowhub.integration_platform.models import (
    IntegrationConnectorInstance,
    IntegrationConnectorSetting,
    IntegrationPollingPolicy,
)
from app.flowhub.orders import models as _order_models  # noqa: F401
from app.flowhub.product_pricing import models as _price_models  # noqa: F401
from app.flowhub.webhooks import models as _webhook_models  # noqa: F401
from app.flowhub.webhooks.models import WebhookReceipt


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    FlowHubBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        FlowHubBase.metadata.drop_all(engine)
        engine.dispose()


def test_never_checked_is_neutral_and_exposes_complete_evidence_contract(db):
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_product_read(db, "woocommerce:primary", datetime.utcnow())

    item = _item(db, "woocommerce:primary")

    assert item["state"] == "NOT_CHECKED"
    assert item["status"] == "Not checked"
    assert item["reason_code"] == "credentials_not_checked"
    assert item["recommended_action"] == "Run the connection test to verify credentials."
    assert item["dimensions"]["credentials"]["state"] == "NOT_CHECKED"
    assert item["dimensions"]["externalApi"]["reason_code"] == "external_api_not_checked"
    assert item["state"] not in {"HEALTHY", "WARNING"}
    required = {
        "state",
        "reason_code",
        "checked_at",
        "evidence_source",
        "is_actionable",
        "recommended_action",
    }
    assert required.issubset(item)
    assert all(required.issubset(dimension) for dimension in item["dimensions"].values())


def test_failed_credentials_are_a_verified_actionable_error(db):
    now = datetime.utcnow()
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_health(db, "woocommerce:primary", "unhealthy", now, error_class="authentication")
    _seed_product_read(db, "woocommerce:primary", now)

    item = _item(db, "woocommerce:primary")

    assert item["state"] == "ERROR"
    assert item["dimensions"]["credentials"]["reason_code"] == "credential_verification_failed"
    assert item["dimensions"]["credentials"]["is_actionable"] is True


def test_unsupported_optional_capabilities_are_not_applicable_and_do_not_lower_health(db):
    now = datetime.utcnow()
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_health(db, "woocommerce:primary", "healthy", now, last_success_at=now)
    _seed_product_read(db, "woocommerce:primary", now)

    item = _item(db, "woocommerce:primary")

    assert item["state"] == "HEALTHY"
    for key in ("lastOrderSync", "webhookReceipt", "webhookProcessing", "queueDeadLetter", "tokenRefresh", "polling"):
        assert item["dimensions"][key]["state"] == "NOT_APPLICABLE"


def test_unsupported_external_api_probe_is_not_applicable(db):
    _seed_channel(db, "digikala:main", "digikala", settings={})

    external = _item(db, "digikala:main")["dimensions"]["externalApi"]

    assert external["state"] == "NOT_APPLICABLE"
    assert external["reason_code"] == "external_api_probe_not_applicable"
    assert external["is_actionable"] is False


def test_fresh_and_stale_product_sync_have_evidence_based_states(db):
    now = datetime.utcnow()
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_health(db, "woocommerce:primary", "healthy", now, last_success_at=now)
    cache = _seed_product_read(db, "woocommerce:primary", now)

    assert _item(db, "woocommerce:primary")["dimensions"]["lastProductSync"]["state"] == "HEALTHY"

    cache.last_successful_read = now - timedelta(days=4)
    db.commit()
    stale = _item(db, "woocommerce:primary")["dimensions"]["lastProductSync"]
    assert stale["state"] == "WARNING"
    assert stale["reason_code"] == "product_sync_stale"
    assert stale["freshness_threshold_hours"] == 24
    assert "within 24 hours" in stale["message"]


def test_required_order_sync_without_success_is_warning_but_woocommerce_is_not_applicable(db):
    now = datetime.utcnow()
    _seed_channel(db, "snappshop:main", "snappshop")
    _seed_polling_policy(db, "snappshop:main", enabled=True)
    _seed_health(db, "snappshop:main", "healthy", now, last_success_at=now)
    _seed_product_read(db, "snappshop:main", now)

    snapp = _item(db, "snappshop:main")
    assert snapp["dimensions"]["lastOrderSync"]["state"] == "WARNING"
    assert snapp["dimensions"]["lastOrderSync"]["reason_code"] == "order_sync_never_succeeded"
    assert snapp["dimensions"]["polling"]["reason_code"] == "polling_never_succeeded"

    _seed_channel(db, "woocommerce:primary", "woocommerce")
    woo = _item(db, "woocommerce:primary")
    assert woo["dimensions"]["lastOrderSync"]["state"] == "NOT_APPLICABLE"


def test_unused_order_sync_is_not_applicable_and_absent_polling_policy_is_disabled(db):
    _seed_channel(db, "snappshop:main", "snappshop")

    item = _item(db, "snappshop:main")

    assert item["dimensions"]["lastOrderSync"]["state"] == "NOT_APPLICABLE"
    assert item["dimensions"]["lastOrderSync"]["reason_code"] == "order_sync_not_applicable"
    assert item["dimensions"]["polling"]["state"] == "DISABLED"
    assert item["dimensions"]["polling"]["reason_code"] == "polling_disabled"


def test_webhook_and_polling_intentionally_disabled_are_neutral(db, monkeypatch):
    _seed_channel(db, "tapsishop:main", "tapsishop", settings={"token": None})
    tapsi = _item(db, "tapsishop:main")
    assert tapsi["dimensions"]["webhookReceipt"]["state"] == "DISABLED"
    assert tapsi["dimensions"]["webhookReceipt"]["reason_code"] == "webhook_disabled"

    monkeypatch.setenv("FLOWHUB_ORDER_SYNC_ENABLED", "false")
    _seed_channel(db, "snappshop:main", "snappshop")
    _seed_polling_policy(db, "snappshop:main", enabled=True)
    snapp = _item(db, "snappshop:main")
    assert snapp["dimensions"]["polling"]["state"] == "DISABLED"
    assert snapp["dimensions"]["lastOrderSync"]["state"] == "DISABLED"


def test_historical_webhook_receipts_do_not_reenable_a_disabled_webhook(db):
    now = datetime.utcnow()
    _seed_channel(db, "tapsishop:main", "tapsishop", settings={"token": None})
    db.add(WebhookReceipt(
        channel_id="tapsishop:main",
        provider="tapsishop",
        provider_event_id="historical-disabled-webhook",
        payload_hash="a" * 64,
        payload_summary_json={},
        normalized_event_json={},
        received_at=now - timedelta(days=1),
        processing_state="processed",
        processed_at=now - timedelta(days=1),
    ))
    db.commit()

    item = _item(db, "tapsishop:main")

    assert item["dimensions"]["webhookReceipt"]["state"] == "DISABLED"
    assert item["dimensions"]["webhookProcessing"]["state"] == "DISABLED"
    assert item["dimensions"]["lastOrderSync"]["state"] == "NOT_APPLICABLE"


def test_globally_disabled_channel_overrides_historical_health(db):
    now = datetime.utcnow()
    _seed_channel(db, "woocommerce:primary", "woocommerce", enabled=False)
    _seed_health(db, "woocommerce:primary", "healthy", now, last_success_at=now)

    item = _item(db, "woocommerce:primary")

    assert item["state"] == "DISABLED"
    assert item["status"] == "Disabled"


def test_disabled_channels_do_not_lower_a_healthy_active_summary(db):
    now = datetime.utcnow()
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_health(db, "woocommerce:primary", "healthy", now, last_success_at=now)
    _seed_product_read(db, "woocommerce:primary", now)

    summary = ChannelHealthReporter(db).report()["summary"]

    assert summary["overall_state"] == "HEALTHY"
    assert summary["overall"] == "Operational"
    assert summary["state_counts"]["DISABLED"] >= 1


def _seed_channel(
    db,
    channel_id: str,
    connector_type: str,
    *,
    enabled: bool = True,
    settings: dict | None = None,
) -> None:
    defaults = {
        "woocommerce": {"url": "https://store.example.invalid", "key": None, "secret": None},
        "snappshop": {"token": None, "agent_identifier": "agent", "vendor_id": "vendor-1"},
        "tapsishop": {"token": None},
    }
    values = defaults.get(connector_type, {}) if settings is None else settings
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
    for key, value in values.items():
        db.add(IntegrationConnectorSetting(
            connector_id=channel_id,
            key=key,
            value_json=value,
            secret=key in {"token", "secret", "key", "webhook_token"},
            configured=True,
            updated_at=now,
        ))
    db.commit()


def _seed_health(
    db,
    channel_id: str,
    status: str,
    checked_at: datetime,
    *,
    last_success_at: datetime | None = None,
    error_class: str | None = None,
) -> None:
    db.add(DlConnectorHealth(
        connector_id=channel_id,
        connector_type=channel_id.split(":", 1)[0],
        status=status,
        checked_at=checked_at,
        last_success_at=last_success_at,
        error_class=error_class,
    ))
    db.commit()


def _seed_polling_policy(db, channel_id: str, *, enabled: bool) -> None:
    db.add(IntegrationPollingPolicy(
        connector_id=channel_id,
        enabled=enabled,
        interval_seconds=900,
        jitter_seconds=60,
        updated_at=datetime.utcnow(),
    ))
    db.commit()


def _seed_product_read(db, channel_id: str, at: datetime) -> DlProductCache:
    row = DlProductCache(
        connector_id=channel_id,
        product_id=f"p-{uuid.uuid4().hex}",
        name="Synthetic product",
        last_successful_read=at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _item(db, channel_id: str) -> dict:
    return next(item for item in ChannelHealthReporter(db).report()["items"] if item["channelId"] == channel_id)
