from __future__ import annotations

import json
import os
import uuid

import pytest
from sqlalchemy.exc import SQLAlchemyError

os.environ.setdefault("FLOWHUB_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FLOWHUB_JWT_SECRET", "test-tapsishop-webhook-jwt-secret-32bytes!")

from app.flowhub.auth import models as _auth_models  # noqa: F401
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


@pytest.fixture()
def auth_headers(client, db):
    from app.flowhub.auth.jwt_service import create_access_token
    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.auth.password import hash_password

    user = FlowHubUser(username=f"webhookadmin_{uuid.uuid4().hex}", hashed_password=hash_password("password123"), role="admin")
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"Authorization": f"Bearer {create_access_token(user.id, user.username, user.role)}"}


def test_valid_tapsishop_webhook_is_durably_stored_before_success(client, db):
    _seed_tapsi_channel(db, "tapsishop:main", "hook-secret")

    response = _post_webhook(client, "tapsishop:main", _payload(), "hook-secret")

    assert response.status_code == 200
    assert response.json() == {"message": "Webhook accepted.", "succeed": True}
    receipt = _receipt(db, "tapsishop:main", "req-1")
    assert receipt.acknowledged_at is not None
    assert receipt.processing_state == "queued"
    assert receipt.payload_summary_json["requestId"] == "req-1"
    assert receipt.normalized_event_json["changeTypeLabel"] == "deducted_due_to_purchase"
    stored = json.dumps(receipt.payload_summary_json) + json.dumps(receipt.normalized_event_json)
    assert "09120000000" not in stored
    assert "1234567890" not in stored
    assert "Customer Name" not in stored
    assert "Delivery Address" not in stored


def test_invalid_and_missing_tokens_fail_without_secret_or_channel_detail(client, db):
    _seed_tapsi_channel(db, "tapsishop:main", "hook-secret")

    invalid = _post_webhook(client, "tapsishop:main", _payload(), "wrong-secret")
    missing = client.post(
        "/api/v2/webhooks/tapsishop/tapsishop:main",
        headers={"Content-Type": "application/json"},
        json=_payload(),
    )

    assert invalid.status_code == 403
    assert missing.status_code == 403
    assert "hook-secret" not in invalid.text
    assert "wrong-secret" not in invalid.text
    assert "tapsishop:main" not in invalid.text


def test_malformed_json_and_schema_fail_without_success_ack(client, db):
    _seed_tapsi_channel(db, "tapsishop:main", "hook-secret")

    malformed = client.post(
        "/api/v2/webhooks/tapsishop/tapsishop:main",
        headers={"Content-Type": "application/json", "TapsiShop.Hub.Webhook-Authorization": "hook-secret"},
        content=b"{not-json",
    )
    schema = _post_webhook(client, "tapsishop:main", {"requestId": "req-bad"}, "hook-secret")

    assert malformed.status_code == 400
    assert malformed.json().get("succeed") is not True
    assert schema.status_code == 422
    assert schema.json().get("succeed") is not True


def test_duplicate_request_id_acknowledges_without_duplicate_receipt(client, db):
    _seed_tapsi_channel(db, "tapsishop:main", "hook-secret")

    first = _post_webhook(client, "tapsishop:main", _payload(), "hook-secret")
    second = _post_webhook(client, "tapsishop:main", _payload(), "hook-secret")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == {"message": "Webhook already accepted.", "succeed": True}
    assert db.query(_webhook_models.WebhookReceipt).filter_by(channel_id="tapsishop:main", provider_event_id="req-1").count() == 1


def test_same_request_id_on_different_channel_is_independent(client, db):
    _seed_tapsi_channel(db, "tapsishop:main", "hook-secret")
    _seed_tapsi_channel(db, "tapsishop:second", "other-secret")

    first = _post_webhook(client, "tapsishop:main", _payload(), "hook-secret")
    second = _post_webhook(client, "tapsishop:second", _payload(), "other-secret")

    assert first.status_code == 200
    assert second.status_code == 200
    assert db.query(_webhook_models.WebhookReceipt).filter_by(provider_event_id="req-1").count() == 2


def test_storage_failure_does_not_return_success_ack(client, db, monkeypatch):
    _seed_tapsi_channel(db, "tapsishop:main", "hook-secret")

    def fail_accept(self, channel_id, payload, raw_body):
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr("app.flowhub.webhooks.service.WebhookIngestionService.accept_tapsishop", fail_accept)
    response = _post_webhook(client, "tapsishop:main", _payload(), "hook-secret")

    assert response.status_code == 503
    assert response.json()["succeed"] is False


def test_personal_data_and_tokens_are_absent_from_events(client, db):
    _seed_tapsi_channel(db, "tapsishop:main", "hook-secret")

    response = _post_webhook(client, "tapsishop:main", _payload(), "hook-secret")

    assert response.status_code == 200
    event_text = json.dumps([event.metadata_json for event in db.query(_integration_platform_models.IntegrationConnectorEvent).all()])
    assert "hook-secret" not in event_text
    assert "09120000000" not in event_text
    assert "1234567890" not in event_text
    assert "Delivery Address" not in event_text


def test_repeated_delivery_after_success_receipt_remains_tapsishop_compatible(client, db):
    _seed_tapsi_channel(db, "tapsishop:main", "hook-secret")

    _post_webhook(client, "tapsishop:main", _payload(), "hook-secret")
    repeated = _post_webhook(client, "tapsishop:main", _payload(), "hook-secret")

    assert repeated.status_code == 200
    assert repeated.json()["succeed"] is True


def test_retry_dead_letter_metrics_and_admin_replay(client, db, auth_headers):
    from app.flowhub.webhooks.service import MAX_PROCESSING_ATTEMPTS, WebhookIngestionService

    _seed_tapsi_channel(db, "tapsishop:main", "hook-secret")
    _post_webhook(client, "tapsishop:main", _payload(), "hook-secret")
    receipt = _receipt(db, "tapsishop:main", "req-1")
    service = WebhookIngestionService(db)

    first = service.process_receipt(receipt.id, error_category="timeout", error_message="temporary upstream timeout")
    assert first["processing_state"] == "retry_scheduled"
    for _ in range(MAX_PROCESSING_ATTEMPTS - 1):
        final = service.process_receipt(receipt.id, error_category="timeout", error_message="temporary upstream timeout")
    assert final["processing_state"] == "dead_letter"
    assert db.query(_webhook_models.WebhookDeadLetter).filter_by(receipt_id=receipt.id).count() == 1

    metrics = client.get("/api/v2/webhooks/metrics", headers=auth_headers)
    assert metrics.status_code == 200
    assert metrics.json()["dead_letter"] == 1

    replay = client.post(f"/api/v2/webhooks/{receipt.id}/replay", headers=auth_headers)
    assert replay.status_code == 200
    assert replay.json()["processing_state"] == "queued"
    db.expire_all()
    processed = service.process_receipt(receipt.id)
    assert processed["processing_state"] == "processed"


def _seed_tapsi_channel(db, channel_id: str, webhook_token: str) -> None:
    from datetime import datetime
    from app.flowhub.integration_platform.models import IntegrationConnectorInstance, IntegrationConnectorSetting

    db.add(IntegrationConnectorInstance(
        id=channel_id,
        connector_type="tapsishop",
        name=channel_id,
        version="1.0.0",
        enabled=True,
        read_only=False,
        status="configured",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    ))
    db.add(IntegrationConnectorSetting(
        connector_id=channel_id,
        key="webhook_token",
        value_json=webhook_token,
        secret=True,
        configured=True,
        updated_at=datetime.utcnow(),
    ))
    db.commit()


def _post_webhook(client, channel_id: str, payload: dict, token: str):
    return client.post(
        f"/api/v2/webhooks/tapsishop/{channel_id}",
        headers={"Content-Type": "application/json", "TapsiShop.Hub.Webhook-Authorization": token},
        json=payload,
    )


def _payload(request_id: str = "req-1") -> dict:
    return {
        "requestId": request_id,
        "orderId": "order-1",
        "changeType": 1,
        "timestamp": "2026-07-11T10:00:00Z",
        "orderDetail": {
            "orderId": "order-1",
            "orderNumber": "ORD-1",
            "customerName": "Customer Name",
            "customerPhone": "09120000000",
            "nationalCode": "1234567890",
            "deliveryAddress": "Delivery Address",
        },
        "items": [
            {
                "orderItemId": "item-1",
                "productId": "product-1",
                "sku": "SKU-1",
                "quantity": 2,
                "price": 1000000,
            }
        ],
    }


def _receipt(db, channel_id: str, request_id: str):
    return db.query(_webhook_models.WebhookReceipt).filter_by(channel_id=channel_id, provider_event_id=request_id).one()
