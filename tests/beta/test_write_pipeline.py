from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
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
    _set_preview(db, user=user)
    token = create_access_token(user.id, user.username, user.role)
    return {"Authorization": f"Bearer {token}"}


def _payload(**overrides):
    body = {
        "previewId": "preview-test",
        "selectedRowIds": ["preview-test:Sheet1:3"],
    }
    body.update(overrides)
    return body


def _source(preview_id: str, *, row: int = 3):
    return {
        "previewId": preview_id,
        "sourceId": "nextcloud:primary",
        "sourceType": "nextcloud_spreadsheet",
        "sourceSnapshotId": 1,
        "sourceSnapshotVersion": 1,
        "sourceFilePath": "/prices.xlsx",
        "worksheet": "Sheet1",
        "rowNumber": row,
        "productId": "101",
        "sku": "SKU-101",
        "productName": "Test Product",
        "rawPrice": "110.00",
    }


def _change(
    *,
    product_id: str = "101",
    product_name: str = "Test Product",
    sku: str = "SKU-101",
    current_price: float = 100.0,
    proposed_price: float = 110.0,
    row: int = 3,
    **extras,
):
    return {
        "productId": product_id,
        "productName": product_name,
        "sku": sku,
        "currentPrice": current_price,
        "proposedPrice": proposed_price,
        "currency": "EUR",
        "status": "valid_change",
        "validationStatus": "valid_change",
        "eligible_for_dry_run": True,
        "source": {**_source("preview-test", row=row), "productId": product_id, "sku": sku},
        "validationWarnings": [],
        **extras,
    }


def _set_preview(
    db,
    *,
    user=None,
    changes: list[dict] | None = None,
    row_errors: dict[int, list[str]] | None = None,
    preview_id: str = "preview-test",
    summary: dict | None = None,
):
    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.data_layer.models import DlProductCache, DlSourceSnapshot, DlWorkspacePreview
    from app.flowhub.workspace.preview_store import WorkspacePreviewStore

    user = user or db.query(FlowHubUser).first()
    source_snapshot = db.query(DlSourceSnapshot).filter(DlSourceSnapshot.file_path == "/prices.xlsx").one_or_none()
    if source_snapshot is None:
        source_snapshot = DlSourceSnapshot(
            connector_id="nextcloud:primary",
            file_path="/prices.xlsx",
            integrity_hash="a" * 64,
            version_seq=1,
            sheet_names=["Sheet1"],
            snapshotted_at=datetime.utcnow(),
        )
        db.add(source_snapshot)
        db.commit()
        db.refresh(source_snapshot)
    existing = db.get(DlWorkspacePreview, preview_id)
    if existing is not None:
        db.delete(existing)
        db.commit()

    changes = changes or [_change()]
    for change in changes:
        cached = (
            db.query(DlProductCache)
            .filter(DlProductCache.connector_id == "woocommerce:primary")
            .filter(DlProductCache.product_id == str(change["productId"]))
            .one_or_none()
        )
        if cached is None:
            cached = DlProductCache(
                connector_id="woocommerce:primary",
                product_id=str(change["productId"]),
                exists=True,
            )
            db.add(cached)
        cached.regular_price = str(change["currentPrice"])
        cached.price = str(change["currentPrice"])
        cached.product_type = str(change.get("itemType") or "simple")
        cached.parent_id = change.get("parentProductId")
    db.commit()
    errors_by_row = row_errors or {}
    rows = []
    for change in changes:
        source = dict(change["source"])
        source.update({
            "previewId": preview_id,
            "sourceSnapshotId": source_snapshot.id,
            "sourceSnapshotVersion": source_snapshot.version_seq,
        })
        change = {**change, "source": source}
        row_number = int(source["rowNumber"])
        errors = list(errors_by_row.get(row_number, []))
        eligible = not errors and change.get("eligible_for_dry_run") is True
        rows.append({
            "id": f"{preview_id}:Sheet1:{row_number}",
            "source": source,
            "matchedProduct": {
                "channelId": "woocommerce:primary",
                "productId": change["productId"],
                "productType": change.get("itemType", "simple"),
                "itemType": change.get("itemType", "simple"),
                "parentProductId": change.get("parentProductId"),
                "variationId": change.get("variationId"),
                "sku": change.get("sku", ""),
                "name": change.get("productName", ""),
                "currentPrice": change["currentPrice"],
                "effectivePrice": change["currentPrice"],
                "categoryNames": [],
            },
            "currentPrice": change["currentPrice"],
            "proposedPrice": change["proposedPrice"],
            "difference": change["proposedPrice"] - change["currentPrice"],
            "changePct": 10.0,
            "status": "error" if errors else change.get("status", "valid_change"),
            "changeType": "price_changed",
            "errors": errors,
            "warnings": change.get("validationWarnings", []),
            "eligible_for_dry_run": eligible,
            "dry_run_change": change if eligible else None,
        })
    summary = summary or {
        "total_rows": 3,
        "valid_changes": len(changes),
        "warning_rows": 0,
        "unchanged_rows": 1,
        "error_rows": 1,
    }
    WorkspacePreviewStore(db).create(
        preview_id=preview_id,
        source_id="nextcloud:primary",
        source_snapshot=source_snapshot,
        owner=user,
        rows=rows,
        summary=summary,
    )
    return [row["id"] for row in rows]


def _enable_woocommerce_write(client, auth_headers):
    response = client.put(
        "/api/v2/commerce/channels/woocommerce:primary/settings",
        headers=auth_headers,
        json={"access_mode": "write_enabled"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["access_mode"] == "write_enabled"
    assert data["read_only"] is False
    assert data["write_pipeline_eligible"] is True
    assert data["runtime_write_blocked"] is True
    return data


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
    assert data["safetySummary"]["eligible_rows"] == 1
    assert data["safetySummary"]["skipped_rows"] == 1
    assert data["safetySummary"]["blocked_rows"] == 1
    assert data["safetySummary"]["estimated_affected_products"] == 1

    events = client.get(f"/api/v2/write-pipeline/batches/{data['id']}/events", headers=auth_headers)
    assert events.status_code == 200
    assert events.json()[0]["eventType"] == "dry_run_created_from_preview"
    assert events.json()[0]["metadata"]["selected_row_ids"] == ["preview-test:Sheet1:3"]
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


def test_read_only_channel_blocks_write_pipeline_execution(client, auth_headers, monkeypatch):
    from app.connectors.destinations.woocommerce.write_adapter import WooCommercePriceWriteAdapter

    calls = {"count": 0}

    async def fake_execute(_adapter, item, _context):
        calls["count"] += 1
        return {"provider": "woocommerce", "product_id": item.channel_product_id, "regular_price": "110.00"}

    monkeypatch.setattr(WooCommercePriceWriteAdapter, "execute_item", fake_execute)
    created = client.post("/api/v2/write-pipeline/dry-run", headers=auth_headers, json=_payload()).json()
    client.post(
        f"/api/v2/write-pipeline/batches/{created['id']}/approve",
        headers=auth_headers,
        json={"reason": "operator approved"},
    )

    response = client.post(f"/api/v2/write-pipeline/batches/{created['id']}/execute", headers=auth_headers)

    assert response.status_code == 403
    assert "channel_write_access_disabled" in response.text
    assert calls["count"] == 0


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

    _enable_woocommerce_write(client, auth_headers)
    applied = client.post(f"/api/v2/write-pipeline/batches/{created['id']}/execute", headers=auth_headers)
    assert applied.status_code == 200
    assert applied.json()["status"] == "applied"
    assert calls["count"] == 1
    assert applied.json()["resultSummary"]["total_attempted"] == 1


def test_write_enabled_access_mode_does_not_auto_apply(client, auth_headers, monkeypatch):
    from app.connectors.destinations.woocommerce.write_adapter import WooCommercePriceWriteAdapter

    calls = {"count": 0}

    async def fail_if_called(*_args, **_kwargs):
        calls["count"] += 1
        raise AssertionError("access mode must not execute")

    monkeypatch.setattr(WooCommercePriceWriteAdapter, "execute_item", fail_if_called)
    _enable_woocommerce_write(client, auth_headers)

    created = client.post("/api/v2/write-pipeline/dry-run", headers=auth_headers, json=_payload())
    assert created.status_code == 201
    assert created.json()["status"] == "dry_run_ready"

    approved = client.post(
        f"/api/v2/write-pipeline/batches/{created.json()['id']}/approve",
        headers=auth_headers,
        json={"reason": "operator approved"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert approved.json()["executedAt"] is None
    assert calls["count"] == 0


def test_non_woocommerce_channels_are_blocked(client, auth_headers):
    response = client.post(
        "/api/v2/write-pipeline/dry-run",
        headers=auth_headers,
        json=_payload(channelId="snappshop:main"),
    )

    assert response.status_code == 403
    assert "unsupported_channel_write" in response.text


def test_dry_run_requires_workspace_preview_provenance(client, auth_headers):
    body = _payload()
    body.pop("previewId")

    response = client.post("/api/v2/write-pipeline/dry-run", headers=auth_headers, json=body)

    assert response.status_code == 422


def test_missing_preview_is_rejected_and_audited(client, auth_headers, db):
    from app.flowhub.integration_platform.models import IntegrationConnectorEvent

    response = client.post(
        "/api/v2/write-pipeline/dry-run",
        headers=auth_headers,
        json={"previewId": "missing-preview", "selectedRowIds": ["missing:row"]},
    )

    assert response.status_code == 404
    assert "PREVIEW_NOT_FOUND" in response.text
    event = db.query(IntegrationConnectorEvent).filter(IntegrationConnectorEvent.event_name == "dry_run_rejected").one()
    assert event.metadata_json["reason"] == "PREVIEW_NOT_FOUND"
    assert event.metadata_json["execution_attempted"] is False


def test_dry_run_rejects_changes_without_matching_preview_source(client, auth_headers):
    body = _payload()
    body["selectedRowIds"] = ["preview-test:Sheet1:999"]

    response = client.post("/api/v2/write-pipeline/dry-run", headers=auth_headers, json=body)

    assert response.status_code == 422
    assert "PREVIEW_ROW_NOT_FOUND" in response.text


def test_arbitrary_client_row_cannot_enter_dry_run(client, auth_headers):
    body = _payload()
    body["changes"] = [_change(product_id="999", proposed_price=120.0)]

    response = client.post("/api/v2/write-pipeline/dry-run", headers=auth_headers, json=body)

    assert response.status_code == 422
    assert "DRY_RUN_REQUEST_FIELDS_INVALID" in response.text


def test_expired_preview_is_rejected(client, auth_headers, db):
    from app.flowhub.data_layer.models import DlWorkspacePreview

    preview = db.get(DlWorkspacePreview, "preview-test")
    preview.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()

    response = client.post("/api/v2/write-pipeline/dry-run", headers=auth_headers, json=_payload())

    assert response.status_code == 409
    assert "PREVIEW_EXPIRED" in response.text


def test_preview_row_with_error_cannot_enter_dry_run(client, auth_headers, db):
    _set_preview(db, row_errors={3: ["invalid_price"]})

    response = client.post("/api/v2/write-pipeline/dry-run", headers=auth_headers, json=_payload())

    assert response.status_code == 422
    assert "PREVIEW_ROW_NOT_ELIGIBLE" in response.text


def test_only_selected_preview_rows_enter_dry_run(client, auth_headers, db):
    row_ids = _set_preview(
        db,
        changes=[_change(), _change(product_id="102", product_name="Second", sku="SKU-102", row=4)],
        summary={"total_rows": 2, "valid_changes": 2, "warning_rows": 0, "unchanged_rows": 0, "error_rows": 0},
    )

    response = client.post(
        "/api/v2/write-pipeline/dry-run",
        headers=auth_headers,
        json={"previewId": "preview-test", "selectedRowIds": [row_ids[1]]},
    )

    assert response.status_code == 201
    assert response.json()["itemCount"] == 1
    assert response.json()["items"][0]["productId"] == "102"


def test_duplicate_selected_row_ids_are_rejected(client, auth_headers):
    row_id = _payload()["selectedRowIds"][0]

    response = client.post(
        "/api/v2/write-pipeline/dry-run",
        headers=auth_headers,
        json={"previewId": "preview-test", "selectedRowIds": [row_id, row_id]},
    )

    assert response.status_code == 422
    assert "PREVIEW_ROW_NOT_ELIGIBLE" in response.text


def test_preview_ownership_is_enforced(client, auth_headers, db):
    from app.flowhub.auth.jwt_service import create_access_token
    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.auth.password import hash_password

    other = FlowHubUser(username="other_admin", hashed_password=hash_password("password123"), role="admin")
    db.add(other)
    db.commit()
    db.refresh(other)
    other_headers = {"Authorization": f"Bearer {create_access_token(other.id, other.username, other.role)}"}

    response = client.post("/api/v2/write-pipeline/dry-run", headers=other_headers, json=_payload())

    assert response.status_code == 403
    assert "PREVIEW_OWNERSHIP_MISMATCH" in response.text


def test_preview_row_tampering_is_detected(client, auth_headers, db):
    from app.flowhub.data_layer.models import DlWorkspacePreview

    preview = db.get(DlWorkspacePreview, "preview-test")
    rows = list(preview.rows_json)
    rows[0] = {**rows[0], "proposedPrice": 999.0}
    preview.rows_json = rows
    db.commit()

    response = client.post("/api/v2/write-pipeline/dry-run", headers=auth_headers, json=_payload())

    assert response.status_code == 409
    assert "PREVIEW_HASH_MISMATCH" in response.text


def test_changed_source_snapshot_invalidates_preview(client, auth_headers, db):
    from app.flowhub.data_layer.models import DlSourceSnapshot

    source = db.query(DlSourceSnapshot).filter(DlSourceSnapshot.file_path == "/prices.xlsx").one()
    source.integrity_hash = "b" * 64
    db.commit()

    response = client.post("/api/v2/write-pipeline/dry-run", headers=auth_headers, json=_payload())

    assert response.status_code == 409
    assert "PREVIEW_HASH_MISMATCH" in response.text


def test_changed_cached_product_price_invalidates_preview(client, auth_headers, db):
    from app.flowhub.data_layer.models import DlProductCache

    product = (
        db.query(DlProductCache)
        .filter(DlProductCache.connector_id == "woocommerce:primary")
        .filter(DlProductCache.product_id == "101")
        .one()
    )
    product.regular_price = "105.00"
    product.price = "105.00"
    db.commit()

    response = client.post("/api/v2/write-pipeline/dry-run", headers=auth_headers, json=_payload())

    assert response.status_code == 409
    assert "PREVIEW_HASH_MISMATCH" in response.text


def test_stock_fields_are_blocked(client, auth_headers):
    body = _payload()
    body["stock_quantity"] = 5

    response = client.post("/api/v2/write-pipeline/dry-run", headers=auth_headers, json=body)

    assert response.status_code == 403
    assert "stock_writes_disabled" in response.text


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


def test_non_numeric_woocommerce_product_id_is_rejected(client, auth_headers, db):
    _set_preview(db, changes=[_change(product_id="prod-101")])

    response = client.post("/api/v2/write-pipeline/dry-run", headers=auth_headers, json=_payload())

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
    _enable_woocommerce_write(client, auth_headers)

    response = client.post(f"/api/v2/write-pipeline/batches/{created['id']}/execute", headers=auth_headers)

    assert response.status_code == 200
    assert calls["count"] == 1


def test_manual_apply_acquires_write_limiter_before_adapter_execution(client, auth_headers, monkeypatch):
    from app.connectors.destinations.woocommerce.write_adapter import WooCommercePriceWriteAdapter

    order: list[str] = []

    async def fake_acquire(self, connector_id, operation, *, connector_type=None):
        from app.flowhub.rate_limit import RateLimitAcquireResult

        order.append(f"limiter:{connector_id}:{operation}:{connector_type}")
        return RateLimitAcquireResult(
            connector_id=connector_id,
            operation=operation,
            rpm=30,
            delay_seconds=0,
            delayed=False,
            queue_length=0,
            estimated_delay_ms=0,
            requests_completed=1,
            requests_delayed=0,
            throttle_events=0,
            average_request_duration_ms=0,
            last_throttle_at=None,
            last_connector_delay_ms=0,
        )

    async def fake_execute(_adapter, item, _context):
        order.append(f"adapter:{item.channel_product_id}")
        return {"provider": "woocommerce", "product_id": item.channel_product_id, "regular_price": "110.00"}

    monkeypatch.setattr("app.flowhub.rate_limit.service.RateLimitService.acquire", fake_acquire)
    monkeypatch.setattr(WooCommercePriceWriteAdapter, "execute_item", fake_execute)
    created = client.post("/api/v2/write-pipeline/dry-run", headers=auth_headers, json=_payload()).json()
    client.post(f"/api/v2/write-pipeline/batches/{created['id']}/approve", headers=auth_headers, json={})
    _enable_woocommerce_write(client, auth_headers)

    response = client.post(f"/api/v2/write-pipeline/batches/{created['id']}/execute", headers=auth_headers)

    assert response.status_code == 200
    assert order == ["limiter:woocommerce:primary:write:woocommerce", "adapter:101"]


def test_woocommerce_rest_put_does_not_take_second_write_limiter_token():
    src = Path("app/connectors/destinations/woocommerce/rest_client.py").read_text(encoding="utf-8")
    put_body = src.split("async def _put(", 1)[1].split("async def list_products", 1)[0]

    assert 'acquire_connector_rate_limit("woocommerce:primary", "write")' not in put_body


@pytest.mark.asyncio
async def test_woocommerce_variation_price_update_uses_variation_endpoint(monkeypatch):
    from app.connectors.destinations.woocommerce import rest_client
    from app.connectors.destinations.woocommerce.auth import WooCommerceCredentials

    captured = {}

    async def fake_put(_creds, path, payload):
        captured["path"] = path
        captured["payload"] = payload
        return {"id": 201, "regular_price": payload["regular_price"]}

    monkeypatch.setattr(rest_client, "_put", fake_put)

    result = await rest_client.update_product_price(
        WooCommerceCredentials(url="https://store.example.test", key="ck", secret="cs"),
        201,
        132.0,
        parent_product_id=100,
    )

    assert captured == {
        "path": "/products/100/variations/201",
        "payload": {"regular_price": "132.00"},
    }
    assert result["variation_id"] == 201
    assert result["parent_product_id"] == 100
    assert result["stock_update"] is False


def test_variation_dry_run_requires_parent_product_id(client, auth_headers, db):
    _set_preview(db, changes=[_change(
        product_id="201",
        product_name="Parent Hoodie - Blue / XL",
        sku="VAR-201",
        itemType="variation",
        variationId="201",
        parentProductId=None,
    )])

    response = client.post("/api/v2/write-pipeline/dry-run", headers=auth_headers, json=_payload())

    assert response.status_code == 422
    assert "parent product ID" in response.text


def test_woocommerce_adapter_is_registered_for_price_updates_only():
    from app.flowhub.write_pipeline.registry import default_write_adapter_registry

    registry = default_write_adapter_registry()

    assert registry.get("woocommerce:primary", "price_update") is not None
    assert registry.get("woocommerce:primary", "stock_update") is None
    assert registry.get("snappshop:main", "price_update") is None
    assert registry.get("tapsishop:main", "price_update") is None
    assert registry.get("digikala:main", "price_update") is None
    assert registry.get("technolife:main", "price_update") is None
    assert registry.get("shopify:main", "price_update") is None


def test_apply_records_read_back_verification_and_audit_metadata(client, auth_headers, monkeypatch):
    from app.connectors.destinations.woocommerce.write_adapter import WooCommercePriceWriteAdapter

    async def fake_execute(_adapter, item, _context):
        return {"provider": "woocommerce", "product_id": item.channel_product_id, "regular_price": "110.00"}

    async def fake_verify(_adapter, item, _context):
        return {
            "provider": "woocommerce",
            "verified": True,
            "observed_price": 110.0,
            "expected_price": item.proposed_price,
            "verification_error": None,
        }

    monkeypatch.setattr(WooCommercePriceWriteAdapter, "execute_item", fake_execute)
    monkeypatch.setattr(WooCommercePriceWriteAdapter, "verify_item", fake_verify)
    created = client.post("/api/v2/write-pipeline/dry-run", headers=auth_headers, json=_payload()).json()
    client.post(f"/api/v2/write-pipeline/batches/{created['id']}/approve", headers=auth_headers, json={"reason": "ok"})
    _enable_woocommerce_write(client, auth_headers)

    response = client.post(f"/api/v2/write-pipeline/batches/{created['id']}/execute", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["items"][0]["verification"]["verified"] is True
    assert data["resultSummary"]["verified_count"] == 1
    events = client.get(f"/api/v2/write-pipeline/batches/{created['id']}/events", headers=auth_headers).json()
    applied_event = [item for item in events if item["eventType"] == "item_applied"][0]
    assert applied_event["metadata"]["source"]["sourceFilePath"] == "/prices.xlsx"
    assert applied_event["metadata"]["product_id"] == "101"
    assert applied_event["metadata"]["verification"]["verified"] is True
    assert applied_event["correlationId"].startswith("corr_")


def test_apply_records_variation_audit_metadata(client, auth_headers, db, monkeypatch):
    from app.connectors.destinations.woocommerce.write_adapter import WooCommercePriceWriteAdapter

    _set_preview(db, changes=[_change(
        product_id="201",
        product_name="Parent Hoodie - Blue / XL",
        sku="VAR-201",
        current_price=120.0,
        proposed_price=132.0,
        row=7,
        itemType="variation",
        variationId="201",
        parentProductId="100",
        parentProductName="Parent Hoodie",
        variationAttributes=[{"name": "Color", "value": "Blue"}, {"name": "Size", "value": "XL"}],
    )])

    async def fake_execute(_adapter, item, _context):
        assert item.channel_product_id == "201"
        assert item.pre_write_snapshot_json["item_type"] == "variation"
        return {
            "provider": "woocommerce",
            "product_id": item.channel_product_id,
            "variation_id": 201,
            "parent_product_id": 100,
            "regular_price": "132.00",
            "stock_update": False,
        }

    async def fake_verify(_adapter, item, _context):
        return {
            "provider": "woocommerce",
            "verified": True,
            "observed_price": 132.0,
            "expected_price": item.proposed_price,
            "verification_error": None,
        }

    monkeypatch.setattr(WooCommercePriceWriteAdapter, "execute_item", fake_execute)
    monkeypatch.setattr(WooCommercePriceWriteAdapter, "verify_item", fake_verify)
    created = client.post(
        "/api/v2/write-pipeline/dry-run",
        headers=auth_headers,
        json={"previewId": "preview-test", "selectedRowIds": ["preview-test:Sheet1:7"]},
    ).json()
    assert created["items"][0]["itemType"] == "variation"
    assert created["items"][0]["variationId"] == "201"
    client.post(f"/api/v2/write-pipeline/batches/{created['id']}/approve", headers=auth_headers, json={"reason": "ok"})
    _enable_woocommerce_write(client, auth_headers)

    response = client.post(f"/api/v2/write-pipeline/batches/{created['id']}/execute", headers=auth_headers)

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["itemType"] == "variation"
    assert item["parentProductId"] == "100"
    assert item["variationAttributes"][0] == {"name": "Color", "value": "Blue"}
    events = client.get(f"/api/v2/write-pipeline/batches/{created['id']}/events", headers=auth_headers).json()
    applied_event = [event for event in events if event["eventType"] == "item_applied"][0]
    assert applied_event["metadata"]["item_type"] == "variation"
    assert applied_event["metadata"]["parent_product_id"] == "100"
    assert applied_event["metadata"]["variation_id"] == "201"
    assert applied_event["metadata"]["variation_attributes"][1] == {"name": "Size", "value": "XL"}


def test_partial_failure_is_recorded_with_safe_provider_error(client, auth_headers, db, monkeypatch):
    from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
    from app.connectors.destinations.woocommerce.write_adapter import WooCommercePriceWriteAdapter

    selected_ids = _set_preview(
        db,
        changes=[_change(), _change(product_id="102", product_name="Second Product", sku="SKU-102", row=4)],
        summary={"total_rows": 2, "valid_changes": 2, "warning_rows": 0, "unchanged_rows": 0, "error_rows": 0},
    )

    async def fake_execute(_adapter, item, _context):
        if item.channel_product_id == "102":
            raise ConnectorError(
                code=ConnectorErrorCode.AUTH_FAILED,
                message="consumer_secret=cs_live_secret failed",
                provider="woocommerce",
                http_status=401,
            )
        return {"provider": "woocommerce", "product_id": item.channel_product_id, "regular_price": "110.00"}

    async def fake_verify(_adapter, item, _context):
        return {"verified": True, "observed_price": 110.0, "expected_price": item.proposed_price}

    monkeypatch.setattr(WooCommercePriceWriteAdapter, "execute_item", fake_execute)
    monkeypatch.setattr(WooCommercePriceWriteAdapter, "verify_item", fake_verify)
    created = client.post(
        "/api/v2/write-pipeline/dry-run",
        headers=auth_headers,
        json={"previewId": "preview-test", "selectedRowIds": selected_ids},
    ).json()
    client.post(f"/api/v2/write-pipeline/batches/{created['id']}/approve", headers=auth_headers, json={})
    _enable_woocommerce_write(client, auth_headers)

    response = client.post(f"/api/v2/write-pipeline/batches/{created['id']}/execute", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["status"] == "partially_failed"
    assert response.json()["resultSummary"]["failure_count"] == 1
    assert "cs_live_secret" not in response.text
    events = client.get(f"/api/v2/write-pipeline/batches/{created['id']}/events", headers=auth_headers)
    assert "cs_live_secret" not in events.text


def test_future_channel_approved_batch_fails_closed_on_execute(client, auth_headers, db):
    from app.flowhub.write_pipeline.models import WriteBatch, WriteItem

    batch_hash = sha256("snappshop:main\nprice_update\n101|100.0000|110.0000|EUR||simple||".encode("utf-8")).hexdigest()
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
    _enable_woocommerce_write(client, auth_headers)
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
