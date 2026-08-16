from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import uuid

import pytest
from sqlalchemy.exc import SQLAlchemyError

os.environ.setdefault("FLOWHUB_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FLOWHUB_JWT_SECRET", "test-woocommerce-webhook-jwt-secret-32bytes!")

from app.flowhub.auth import models as _auth_models  # noqa: F401
from app.flowhub.business_observability import models as _business_observability_models  # noqa: F401
from app.flowhub.integration_platform import models as _integration_platform_models  # noqa: F401
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


def test_valid_woocommerce_webhook_is_durably_stored_before_success(client, db):
    _seed_woocommerce_channel(db, "woocommerce:primary", "hook-secret")

    response = _post_webhook(client, "woocommerce:primary", _payload(), "hook-secret", topic="product.updated")

    assert response.status_code == 200
    assert response.json() == {"message": "Webhook accepted.", "succeed": True}
    receipt = _receipt(db, "woocommerce:primary", "wh-1:dl-1")
    assert receipt.acknowledged_at is not None
    assert receipt.processing_state == "queued"
    assert receipt.provider == "woocommerce"
    assert receipt.normalized_event_json["topic"] == "product.updated"
    assert receipt.normalized_event_json["wc_product_id"] == "123"
    assert receipt.normalized_event_json["sku"] == "SKU-1"


def test_invalid_and_missing_signature_fail_without_receipt(client, db):
    _seed_woocommerce_channel(db, "woocommerce:primary", "hook-secret")

    invalid = _post_webhook(client, "woocommerce:primary", _payload(), "wrong-secret", topic="product.updated")
    missing = client.post(
        "/api/v2/webhooks/woocommerce/woocommerce:primary",
        headers={
            "Content-Type": "application/json",
            "X-WC-Webhook-Topic": "product.updated",
            "X-WC-Webhook-ID": "wh-1",
            "X-WC-Webhook-Delivery-ID": "dl-1",
        },
        content=json.dumps(_payload()).encode("utf-8"),
    )

    assert invalid.status_code == 403
    assert missing.status_code == 403
    assert "hook-secret" not in invalid.text
    assert "wrong-secret" not in invalid.text
    assert db.query(_webhook_models.WebhookReceipt).filter_by(channel_id="woocommerce:primary").count() == 0


def test_malformed_base64_signature_is_rejected(client, db):
    _seed_woocommerce_channel(db, "woocommerce:primary", "hook-secret")

    response = client.post(
        "/api/v2/webhooks/woocommerce/woocommerce:primary",
        headers={
            "Content-Type": "application/json",
            "X-WC-Webhook-Topic": "product.updated",
            "X-WC-Webhook-Signature": "not-valid-base64!!!",
            "X-WC-Webhook-ID": "wh-1",
            "X-WC-Webhook-Delivery-ID": "dl-1",
        },
        content=json.dumps(_payload()).encode("utf-8"),
    )

    assert response.status_code == 403
    assert db.query(_webhook_models.WebhookReceipt).count() == 0


def test_unsupported_topic_is_rejected_without_receipt(client, db):
    _seed_woocommerce_channel(db, "woocommerce:primary", "hook-secret")

    response = _post_webhook(client, "woocommerce:primary", _payload(), "hook-secret", topic="order.created")

    assert response.status_code == 400
    assert db.query(_webhook_models.WebhookReceipt).count() == 0


def test_missing_delivery_identity_headers_are_rejected(client, db):
    _seed_woocommerce_channel(db, "woocommerce:primary", "hook-secret")
    raw_body = json.dumps(_payload()).encode("utf-8")
    signature = _sign(raw_body, "hook-secret")

    response = client.post(
        "/api/v2/webhooks/woocommerce/woocommerce:primary",
        headers={
            "Content-Type": "application/json",
            "X-WC-Webhook-Topic": "product.updated",
            "X-WC-Webhook-Signature": signature,
        },
        content=raw_body,
    )

    assert response.status_code == 400
    assert db.query(_webhook_models.WebhookReceipt).count() == 0


def test_malformed_json_fails_without_success_ack(client, db):
    _seed_woocommerce_channel(db, "woocommerce:primary", "hook-secret")
    raw_body = b"{not-json"
    signature = _sign(raw_body, "hook-secret")

    response = client.post(
        "/api/v2/webhooks/woocommerce/woocommerce:primary",
        headers={
            "Content-Type": "application/json",
            "X-WC-Webhook-Topic": "product.updated",
            "X-WC-Webhook-Signature": signature,
            "X-WC-Webhook-ID": "wh-1",
            "X-WC-Webhook-Delivery-ID": "dl-1",
        },
        content=raw_body,
    )

    assert response.status_code == 400
    assert response.json().get("succeed") is not True


def test_duplicate_delivery_acknowledges_without_duplicate_receipt(client, db):
    _seed_woocommerce_channel(db, "woocommerce:primary", "hook-secret")

    first = _post_webhook(client, "woocommerce:primary", _payload(), "hook-secret", topic="product.updated")
    second = _post_webhook(client, "woocommerce:primary", _payload(), "hook-secret", topic="product.updated")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == {"message": "Webhook already accepted.", "succeed": True}
    assert db.query(_webhook_models.WebhookReceipt).filter_by(
        channel_id="woocommerce:primary", provider_event_id="wh-1:dl-1"
    ).count() == 1


def test_different_delivery_id_is_independent_receipt(client, db):
    _seed_woocommerce_channel(db, "woocommerce:primary", "hook-secret")

    first = _post_webhook(client, "woocommerce:primary", _payload(), "hook-secret", topic="product.updated", delivery_id="dl-1")
    second = _post_webhook(client, "woocommerce:primary", _payload(), "hook-secret", topic="product.updated", delivery_id="dl-2")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["message"] == "Webhook accepted."
    assert db.query(_webhook_models.WebhookReceipt).filter_by(channel_id="woocommerce:primary").count() == 2


def test_missing_channel_and_disabled_channel_are_rejected(client, db):
    missing = _post_webhook(client, "woocommerce:unknown", _payload(), "hook-secret", topic="product.updated")
    assert missing.status_code == 404

    _seed_woocommerce_channel(db, "woocommerce:primary", "hook-secret", enabled=False)
    disabled = _post_webhook(client, "woocommerce:primary", _payload(), "hook-secret", topic="product.updated")
    assert disabled.status_code == 404


def test_non_woocommerce_channel_type_is_rejected(client, db):
    from datetime import datetime, timezone

    from app.flowhub.integration_platform.models import IntegrationConnectorInstance

    db.add(IntegrationConnectorInstance(
        id="tapsishop:main",
        connector_type="tapsishop",
        name="tapsishop:main",
        version="1.0.0",
        enabled=True,
        read_only=False,
        status="configured",
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
    ))
    db.commit()

    response = _post_webhook(client, "tapsishop:main", _payload(), "hook-secret", topic="product.updated")
    assert response.status_code == 404


def test_oversized_payload_is_rejected(client, db):
    _seed_woocommerce_channel(db, "woocommerce:primary", "hook-secret")
    from app.flowhub.webhooks.service import MAX_WOOCOMMERCE_WEBHOOK_BYTES

    huge_payload = {**_payload(), "description": "x" * (MAX_WOOCOMMERCE_WEBHOOK_BYTES + 1024)}
    raw_body = json.dumps(huge_payload).encode("utf-8")
    signature = _sign(raw_body, "hook-secret")

    response = client.post(
        "/api/v2/webhooks/woocommerce/woocommerce:primary",
        headers={
            "Content-Type": "application/json",
            "Content-Length": str(len(raw_body)),
            "X-WC-Webhook-Topic": "product.updated",
            "X-WC-Webhook-Signature": signature,
            "X-WC-Webhook-ID": "wh-1",
            "X-WC-Webhook-Delivery-ID": "dl-1",
        },
        content=raw_body,
    )

    assert response.status_code == 413
    assert db.query(_webhook_models.WebhookReceipt).count() == 0


def test_storage_failure_does_not_return_success_ack(client, db, monkeypatch):
    _seed_woocommerce_channel(db, "woocommerce:primary", "hook-secret")

    def fail_accept(self, channel_id, topic, payload, raw_body, *, webhook_id, delivery_id):
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr("app.flowhub.webhooks.service.WebhookIngestionService.accept_woocommerce_event", fail_accept)
    response = _post_webhook(client, "woocommerce:primary", _payload(), "hook-secret", topic="product.updated")

    assert response.status_code == 503
    assert response.json()["succeed"] is False


def test_product_deleted_and_created_topics_are_accepted(client, db):
    _seed_woocommerce_channel(db, "woocommerce:primary", "hook-secret")

    created = _post_webhook(client, "woocommerce:primary", _payload(), "hook-secret", topic="product.created", delivery_id="dl-created")
    deleted = _post_webhook(client, "woocommerce:primary", _payload(), "hook-secret", topic="product.deleted", delivery_id="dl-deleted")

    assert created.status_code == 200
    assert deleted.status_code == 200


def test_business_events_are_emitted_for_received_and_duplicate(client, db):
    from app.flowhub.business_observability.models import BusinessEvent

    _seed_woocommerce_channel(db, "woocommerce:primary", "hook-secret")

    _post_webhook(client, "woocommerce:primary", _payload(), "hook-secret", topic="product.updated")
    _post_webhook(client, "woocommerce:primary", _payload(), "hook-secret", topic="product.updated")

    event_types = {row.event_type for row in db.query(BusinessEvent).all()}
    assert "woocommerce_webhook_received" in event_types
    assert "woocommerce_webhook_duplicate" in event_types
    for row in db.query(BusinessEvent).all():
        assert row.domain == "channels"


def _seed_woocommerce_channel(db, channel_id: str, webhook_secret: str, *, enabled: bool = True) -> None:
    from datetime import datetime, timezone

    from app.flowhub.integration_platform.models import IntegrationConnectorInstance, IntegrationConnectorSetting
    from app.flowhub.setup.models import FlowHubAppConfig
    from app.flowhub.setup.service import AppConfigService

    FlowHubAppConfig.__table__.create(bind=db.get_bind(), checkfirst=True)

    db.add(IntegrationConnectorInstance(
        id=channel_id,
        connector_type="woocommerce",
        name=channel_id,
        version="1.0.0",
        enabled=enabled,
        read_only=False,
        status="configured",
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
    ))
    db.add(IntegrationConnectorSetting(
        connector_id=channel_id,
        key="webhook_secret",
        value_json=None,
        secret=True,
        configured=True,
        updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
    ))
    db.flush()
    AppConfigService(db).set(
        "woocommerce.webhook_secret",
        webhook_secret,
        updated_by="test",
    )


def _sign(raw_body: bytes, secret: str) -> str:
    return base64.b64encode(hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()).decode("ascii")


def _post_webhook(
    client,
    channel_id: str,
    payload: dict,
    secret: str,
    *,
    topic: str,
    webhook_id: str = "wh-1",
    delivery_id: str = "dl-1",
):
    raw_body = json.dumps(payload).encode("utf-8")
    signature = _sign(raw_body, secret)
    return client.post(
        f"/api/v2/webhooks/woocommerce/{channel_id}",
        headers={
            "Content-Type": "application/json",
            "X-WC-Webhook-Topic": topic,
            "X-WC-Webhook-Signature": signature,
            "X-WC-Webhook-ID": webhook_id,
            "X-WC-Webhook-Delivery-ID": delivery_id,
        },
        content=raw_body,
    )


def _payload() -> dict:
    return {
        "id": 123,
        "sku": "SKU-1",
        "name": "Test Product",
        "status": "publish",
        "type": "simple",
        "price": "100000",
        "stock_quantity": 5,
    }


def _receipt(db, channel_id: str, provider_event_id: str):
    return db.query(_webhook_models.WebhookReceipt).filter_by(
        channel_id=channel_id, provider="woocommerce", provider_event_id=provider_event_id
    ).one()
