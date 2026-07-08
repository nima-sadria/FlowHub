from __future__ import annotations

import os
import uuid
from hashlib import sha256
from pathlib import Path

import pytest

os.environ.setdefault("FLOWHUB_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FLOWHUB_JWT_SECRET", "test-write-pipeline-jwt-secret-32bytes!")

from app.flowhub.auth import models as _auth_models  # noqa: F401
from app.flowhub.data_layer import models as _data_layer_models  # noqa: F401
from app.flowhub.integration_platform import models as _integration_platform_models  # noqa: F401
from app.flowhub.setup import models as _setup_models  # noqa: F401
from app.flowhub.write_pipeline import models as _write_pipeline_models  # noqa: F401


@pytest.fixture()
def db_engine():
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    from app.flowhub.database import FlowHubBase, _get_engine

    _get_engine.cache_clear()
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    FlowHubBase.metadata.create_all(engine)
    yield engine
    FlowHubBase.metadata.drop_all(engine)
    engine.dispose()
    _get_engine.cache_clear()


@pytest.fixture()
def db(db_engine):
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def client(db_engine):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app.flowhub.app import app
    from app.flowhub.database import get_db

    Session = sessionmaker(bind=db_engine)

    def _override_get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(client, db):
    from app.flowhub.auth.jwt_service import create_access_token
    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.auth.password import hash_password

    username = f"writeadmin_{uuid.uuid4().hex}"
    user = FlowHubUser(username=username, hashed_password=hash_password("password123"), role="admin")
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id, user.username, user.role)
    return {"Authorization": f"Bearer {token}"}


def _payload(**overrides):
    body = {
        "previewId": "preview-test",
        "channelId": "woocommerce:primary",
        "operationType": "price_update",
        "changes": [
            {
                "productId": "101",
                "productName": "Test Product",
                "sku": "SKU-101",
                "currentPrice": 100.0,
                "proposedPrice": 110.0,
                "currency": "EUR",
            }
        ],
    }
    body.update(overrides)
    return body


def test_dry_run_creates_batch_without_marketplace_write(client, auth_headers):
    response = client.post("/api/v2/write-pipeline/dry-run", headers=auth_headers, json=_payload())

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "dry_run_ready"
    assert data["channelId"] == "woocommerce:primary"
    assert data["operationType"] == "price_update"
    assert data["safetySummary"]["automatic_apply"] is False
    assert data["safetySummary"]["scheduler_started"] is False
    assert data["safetySummary"]["stock_update_allowed"] is False

    events = client.get(f"/api/v2/write-pipeline/batches/{data['id']}/events", headers=auth_headers)
    assert events.status_code == 200
    assert events.json()[0]["metadata"]["execution_attempted"] is False


def test_approval_does_not_execute(client, auth_headers, monkeypatch):
    from app.connectors.destinations.woocommerce.write_adapter import WooCommercePriceWriteAdapter

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("approval must not execute")

    monkeypatch.setattr(WooCommercePriceWriteAdapter, "execute_item", fail_if_called)
    created = client.post("/api/v2/write-pipeline/dry-run", headers=auth_headers, json=_payload()).json()

    approved = client.post(
        f"/api/v2/write-pipeline/batches/{created['id']}/approve",
        headers=auth_headers,
        json={"reason": "operator approved"},
    )

    assert approved.status_code == 200
    data = approved.json()
    assert data["status"] == "approved"
    assert data["executedAt"] is None

    events = client.get(f"/api/v2/write-pipeline/batches/{created['id']}/events", headers=auth_headers)
    approval_event = [item for item in events.json() if item["eventType"] == "approved"][0]
    assert approval_event["metadata"]["execution_attempted"] is False


def test_execution_requires_second_action_after_approval(client, auth_headers, monkeypatch):
    from app.connectors.destinations.woocommerce.write_adapter import WooCommercePriceWriteAdapter

    calls = {"count": 0}

    async def fake_execute(_adapter, item, _context):
        calls["count"] += 1
        return {"provider": "woocommerce", "product_id": item.channel_product_id, "regular_price": "110.00"}

    monkeypatch.setattr(WooCommercePriceWriteAdapter, "execute_item", fake_execute)
    created = client.post("/api/v2/write-pipeline/dry-run", headers=auth_headers, json=_payload()).json()

    blocked = client.post(f"/api/v2/write-pipeline/batches/{created['id']}/execute", headers=auth_headers)
    assert blocked.status_code == 409
    assert calls["count"] == 0

    approved = client.post(
        f"/api/v2/write-pipeline/batches/{created['id']}/approve",
        headers=auth_headers,
        json={},
    )
    assert approved.status_code == 200
    assert calls["count"] == 0

    applied = client.post(f"/api/v2/write-pipeline/batches/{created['id']}/execute", headers=auth_headers)
    assert applied.status_code == 200
    assert applied.json()["status"] == "applied"
    assert calls["count"] == 1


def test_non_woocommerce_channels_are_blocked(client, auth_headers):
    response = client.post(
        "/api/v2/write-pipeline/dry-run",
        headers=auth_headers,
        json=_payload(channelId="snappshop:main"),
    )

    assert response.status_code == 403
    assert "unsupported_channel_write" in response.text


def test_stock_fields_are_blocked(client, auth_headers):
    body = _payload()
    body["changes"][0]["stock_quantity"] = 5

    response = client.post("/api/v2/write-pipeline/dry-run", headers=auth_headers, json=body)

    assert response.status_code == 403
    assert "Stock updates are blocked" in response.text


def test_stock_operation_is_blocked(client, auth_headers):
    response = client.post(
        "/api/v2/write-pipeline/dry-run",
        headers=auth_headers,
        json=_payload(operationType="stock_update"),
    )

    assert response.status_code == 403
    assert "stock_writes_disabled" in response.text


def test_automatic_apply_controls_are_blocked(client, auth_headers):
    response = client.post(
        "/api/v2/write-pipeline/dry-run",
        headers=auth_headers,
        json=_payload(automaticApply=True),
    )

    assert response.status_code == 403
    assert "automatic_apply_disabled" in response.text


def test_non_numeric_woocommerce_product_id_is_rejected(client, auth_headers):
    body = _payload()
    body["changes"][0]["productId"] = "prod-101"

    response = client.post("/api/v2/write-pipeline/dry-run", headers=auth_headers, json=body)

    assert response.status_code == 422
    assert "product ID must be numeric" in response.text


def test_no_scheduler_or_generic_connector_write_api_exposed(client):
    paths = [route.path.lower() for route in client.app.routes if hasattr(route, "path")]
    write_paths = " ".join(path for path in paths if "/api/v2/write-pipeline" in path)
    integration_paths = " ".join(path for path in paths if "/api/v2/integration-platform" in path)

    assert "scheduler" not in write_paths
    assert "stock" not in write_paths
    assert "snapp" not in write_paths
    assert "tapsi" not in write_paths
    assert "/connectors/{connector_id}/write" not in integration_paths


def test_write_pipeline_service_has_no_woocommerce_connector_import_or_execution_method():
    src = Path("app/flowhub/write_pipeline/service.py").read_text(encoding="utf-8")

    assert "WooCommerceConnector" not in src
    assert "_execute_woocommerce_price_update" not in src
    assert "app.connectors.destinations.woocommerce.connector" not in src


def test_execution_dispatches_through_adapter_registry(client, auth_headers, monkeypatch):
    from app.connectors.destinations.woocommerce.write_adapter import WooCommercePriceWriteAdapter

    calls = {"count": 0}

    async def fake_execute(_adapter, item, _context):
        calls["count"] += 1
        return {"provider": "woocommerce", "product_id": item.channel_product_id, "regular_price": "110.00"}

    monkeypatch.setattr(WooCommercePriceWriteAdapter, "execute_item", fake_execute)
    created = client.post("/api/v2/write-pipeline/dry-run", headers=auth_headers, json=_payload()).json()
    client.post(f"/api/v2/write-pipeline/batches/{created['id']}/approve", headers=auth_headers, json={})

    response = client.post(f"/api/v2/write-pipeline/batches/{created['id']}/execute", headers=auth_headers)

    assert response.status_code == 200
    assert calls["count"] == 1


def test_woocommerce_adapter_is_registered_for_price_updates_only():
    from app.flowhub.write_pipeline.registry import default_write_adapter_registry

    registry = default_write_adapter_registry()

    assert registry.get("woocommerce:primary", "price_update") is not None
    assert registry.get("woocommerce:primary", "stock_update") is None
    assert registry.get("snappshop:main", "price_update") is None
    assert registry.get("tapsishop:main", "price_update") is None


def test_future_channel_approved_batch_fails_closed_on_execute(client, auth_headers, db):
    from app.flowhub.write_pipeline.models import WriteBatch, WriteItem

    batch_hash = sha256("snappshop:main\nprice_update\n101|100.0000|110.0000|EUR".encode("utf-8")).hexdigest()
    batch = WriteBatch(
        id="wb_snapp_closed",
        channel_id="snappshop:main",
        channel_type="snappshop",
        operation_type="price_update",
        status="approved",
        batch_hash=batch_hash,
        item_count=1,
        currency="EUR",
        created_by="test",
        approved_by="test",
        safety_summary_json={},
    )
    db.add(batch)
    db.add(
        WriteItem(
            batch_id=batch.id,
            channel_product_id="101",
            sku="SKU-101",
            product_name="Test Product",
            current_price=100.0,
            proposed_price=110.0,
            delta_amount=10.0,
            delta_percent=10.0,
            currency="EUR",
            pre_write_snapshot_json={},
            status="pending",
        )
    )
    db.commit()

    response = client.post(f"/api/v2/write-pipeline/batches/{batch.id}/execute", headers=auth_headers)

    assert response.status_code == 403
    assert "unsupported_channel_write" in response.text


def test_provider_result_is_sanitized_from_events_and_items(client, auth_headers, monkeypatch):
    from app.connectors.destinations.woocommerce.write_adapter import WooCommercePriceWriteAdapter

    async def fake_execute(_adapter, item, _context):
        return {
            "provider": "woocommerce",
            "product_id": item.channel_product_id,
            "regular_price": "110.00",
            "secret": "do-not-log",
            "token": "do-not-log-token",
        }

    monkeypatch.setattr(WooCommercePriceWriteAdapter, "execute_item", fake_execute)
    created = client.post("/api/v2/write-pipeline/dry-run", headers=auth_headers, json=_payload()).json()
    client.post(f"/api/v2/write-pipeline/batches/{created['id']}/approve", headers=auth_headers, json={})
    response = client.post(f"/api/v2/write-pipeline/batches/{created['id']}/execute", headers=auth_headers)

    assert response.status_code == 200
    assert "do-not-log" not in response.text

    events = client.get(f"/api/v2/write-pipeline/batches/{created['id']}/events", headers=auth_headers)
    assert "do-not-log" not in events.text


def test_production_app_does_not_expose_legacy_stock_or_write_routes(client):
    paths = {route.path.lower() for route in client.app.routes if hasattr(route, "path")}

    assert "/api/emergency/{batch_id}/apply" not in paths
    assert "/api/sync/{job_id}/confirm" not in paths
    assert not any(path.startswith("/api/emergency") for path in paths)
    assert not any("/stock" in path for path in paths)


def test_production_entrypoint_targets_flowhub_app():
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    installer = Path("installer/install.sh").read_text(encoding="utf-8")
    compose_template = Path("installer/templates/docker-compose.template.yml").read_text(encoding="utf-8")

    assert 'CMD ["uvicorn", "app.flowhub.app:app"' in dockerfile
    assert "grep -q 'app.flowhub.app:app'" in installer
    assert "app.main:app" not in dockerfile
    assert "app.main:app" not in compose_template
