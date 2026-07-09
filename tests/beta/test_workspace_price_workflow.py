from __future__ import annotations

import os
import uuid
from datetime import datetime
from io import BytesIO

import pytest

os.environ.setdefault("FLOWHUB_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FLOWHUB_JWT_SECRET", "test-workspace-workflow-jwt-secret-32bytes!")

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

    username = f"workspaceadmin_{uuid.uuid4().hex}"
    user = FlowHubUser(username=username, hashed_password=hash_password("password123"), role="admin")
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id, user.username, user.role)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def configured_db(db):
    from app.flowhub.setup.service import AppConfigService

    AppConfigService(db).set_many(
        {
            "woocommerce.url": "https://store.example.test",
            "woocommerce.key": "ck_test",
            "woocommerce.secret": "cs_test",
            "nextcloud.url": "https://cloud.example.test",
            "nextcloud.username": "user",
            "nextcloud.password": "pass",
            "nextcloud.spreadsheet_path": "/prices.xlsx",
            "server.currency": "EUR",
            "setup.completed": "true",
        }
    )
    return db


def test_nextcloud_spreadsheet_import_success_generates_preview_and_dry_run(
    client, auth_headers, configured_db, monkeypatch
):
    from app.flowhub.integrations.nextcloud import NextcloudClient

    _cache_product(configured_db, "101", "Test Product", "SKU-101", "100.00")

    async def fake_download(self, path):
        assert path == "/prices.xlsx"
        return _xlsx([["Test Product", 101, "110.00", "SKU-101"]]), {"etag": "etag-1", "last_modified": "now"}

    monkeypatch.setattr(NextcloudClient, "download_file", fake_download)

    preview = client.post("/api/v2/workspace/preview", headers=auth_headers)
    assert preview.status_code == 200
    data = preview.json()
    assert data["external_call_performed"] is True
    assert data["summary"]["total_rows"] == 1
    assert data["summary"]["valid_changes"] == 1
    row = data["rows"][0]
    assert row["source"]["sourceId"] == "nextcloud:primary"
    assert row["source"]["sourceFilePath"] == "/prices.xlsx"
    assert row["source"]["worksheet"] == "Sheet1"
    assert row["source"]["rowNumber"] == 3
    assert row["source"]["productId"] == "101"
    assert row["source"]["sku"] == "SKU-101"
    assert row["source"]["productName"] == "Test Product"
    assert row["matchedProduct"]["name"] == "Test Product"
    assert row["currentPrice"] == 100.0
    assert row["proposedPrice"] == 110.0
    assert row["difference"] == 10.0
    assert row["changePct"] == 10.0
    assert row["status"] == "valid_change"
    assert row["warnings"] == []
    assert row["errors"] == []
    assert row["eligible_for_dry_run"] is True
    assert data["changes"][0]["source"]["worksheet"] == "Sheet1"
    assert data["changes"][0]["source"]["rowNumber"] == 3

    dry_run = client.post(
        "/api/v2/write-pipeline/dry-run",
        headers=auth_headers,
        json={
            "previewId": data["id"],
            "channelId": "woocommerce:primary",
            "operationType": "price_update",
            "changes": data["changes"],
        },
    )
    assert dry_run.status_code == 201
    batch = dry_run.json()
    assert batch["status"] == "dry_run_ready"
    assert batch["sourcePreviewId"] == data["id"]
    assert batch["items"][0]["productId"] == "101"

    execute = client.post(f"/api/v2/write-pipeline/batches/{batch['id']}/execute", headers=auth_headers)
    assert execute.status_code == 409
    assert "approved Dry Run" in execute.text


def test_variation_row_matched_by_variation_id_is_eligible_for_dry_run(
    client, auth_headers, configured_db, monkeypatch
):
    from app.flowhub.integrations.nextcloud import NextcloudClient

    _cache_product(configured_db, "100", "Parent Hoodie", "PARENT-100", "0.00", product_type="variable")
    _cache_product(
        configured_db,
        "201",
        "Parent Hoodie - Blue / XL",
        "VAR-201",
        "120.00",
        product_type="variation",
        parent_id="100",
        raw_data={"attributes": [{"name": "Color", "option": "Blue"}, {"name": "Size", "option": "XL"}]},
    )

    async def fake_download(self, path):
        return _xlsx([["Parent Hoodie - Blue / XL", 201, "132.00", "VAR-201"]]), {"etag": "etag-var"}

    monkeypatch.setattr(NextcloudClient, "download_file", fake_download)

    response = client.post("/api/v2/workspace/preview", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    row = data["rows"][0]
    assert row["status"] == "valid_change"
    assert row["eligible_for_dry_run"] is True
    assert row["matchedProduct"]["itemType"] == "variation"
    assert row["matchedProduct"]["variationId"] == "201"
    assert row["matchedProduct"]["parentProductId"] == "100"
    assert row["matchedProduct"]["parentProductName"] == "Parent Hoodie"
    assert row["matchedProduct"]["variationAttributes"] == [
        {"name": "Color", "value": "Blue"},
        {"name": "Size", "value": "XL"},
    ]
    change = data["changes"][0]
    assert change["itemType"] == "variation"
    assert change["productId"] == "201"
    assert change["variationId"] == "201"
    assert change["parentProductId"] == "100"

    dry_run = client.post(
        "/api/v2/write-pipeline/dry-run",
        headers=auth_headers,
        json={
            "previewId": data["id"],
            "channelId": "woocommerce:primary",
            "operationType": "price_update",
            "previewSummary": data["summary"],
            "changes": data["changes"],
        },
    )
    assert dry_run.status_code == 201
    item = dry_run.json()["items"][0]
    assert item["itemType"] == "variation"
    assert item["variationId"] == "201"
    assert item["parentProductId"] == "100"
    assert item["variationAttributes"][0] == {"name": "Color", "value": "Blue"}


def test_variation_row_matched_by_sku_if_safe(client, auth_headers, configured_db, monkeypatch):
    from app.flowhub.integrations.nextcloud import NextcloudClient

    _cache_product(configured_db, "100", "Parent Hoodie", "PARENT-100", "0.00", product_type="variable")
    _cache_product(
        configured_db,
        "202",
        "Parent Hoodie - Red / L",
        "VAR-202",
        "100.00",
        product_type="variation",
        parent_id="100",
    )

    async def fake_download(self, path):
        return _xlsx([["Parent Hoodie - Red / L", "", "115.00", "VAR-202"]]), {"etag": "etag-var-sku"}

    monkeypatch.setattr(NextcloudClient, "download_file", fake_download)

    response = client.post("/api/v2/workspace/preview", headers=auth_headers)

    assert response.status_code == 200
    row = response.json()["rows"][0]
    assert row["matchedProduct"]["variationId"] == "202"
    assert row["eligible_for_dry_run"] is True


def test_variation_row_missing_parent_id_fails_closed(client, auth_headers, configured_db, monkeypatch):
    from app.flowhub.integrations.nextcloud import NextcloudClient

    _cache_product(
        configured_db,
        "203",
        "Orphan Variation",
        "VAR-203",
        "100.00",
        product_type="variation",
        parent_id=None,
    )

    async def fake_download(self, path):
        return _xlsx([["Orphan Variation", 203, "110.00", "VAR-203"]]), {"etag": "etag-orphan"}

    monkeypatch.setattr(NextcloudClient, "download_file", fake_download)

    response = client.post("/api/v2/workspace/preview", headers=auth_headers)

    assert response.status_code == 200
    row = response.json()["rows"][0]
    assert row["status"] == "error"
    assert "missing_variation_parent_id" in row["errors"]
    assert row["eligible_for_dry_run"] is False


def test_simple_woocommerce_price_workflow_end_to_end_with_mocked_adapter(
    client, auth_headers, configured_db, monkeypatch
):
    from app.connectors.destinations.woocommerce.write_adapter import WooCommercePriceWriteAdapter
    from app.flowhub.integrations.nextcloud import NextcloudClient

    _cache_product(configured_db, "101", "Test Product", "SKU-101", "100.00")

    async def fake_download(self, path):
        return _xlsx([["Test Product", 101, "110.00", "SKU-101"]]), {"etag": "etag-e2e", "last_modified": "now"}

    async def fake_execute(_adapter, item, _context):
        return {
            "provider": "woocommerce",
            "product_id": item.channel_product_id,
            "regular_price": f"{item.proposed_price:.2f}",
            "stock_update": False,
        }

    async def fake_verify(_adapter, item, _context):
        return {
            "provider": "woocommerce",
            "verified": True,
            "observed_price": item.proposed_price,
            "expected_price": item.proposed_price,
            "verification_error": None,
        }

    monkeypatch.setattr(NextcloudClient, "download_file", fake_download)
    monkeypatch.setattr(WooCommercePriceWriteAdapter, "execute_item", fake_execute)
    monkeypatch.setattr(WooCommercePriceWriteAdapter, "verify_item", fake_verify)

    preview = client.post("/api/v2/workspace/preview", headers=auth_headers).json()
    dry_run = client.post(
        "/api/v2/write-pipeline/dry-run",
        headers=auth_headers,
        json={
            "previewId": preview["id"],
            "channelId": "woocommerce:primary",
            "operationType": "price_update",
            "previewSummary": preview["summary"],
            "changes": preview["changes"],
        },
    ).json()
    approved = client.post(
        f"/api/v2/write-pipeline/batches/{dry_run['id']}/approve",
        headers=auth_headers,
        json={"reason": "owner approved"},
    )
    assert approved.status_code == 200

    enabled = client.put(
        "/api/v2/commerce/channels/woocommerce:primary/settings",
        headers=auth_headers,
        json={"access_mode": "write_enabled"},
    )
    assert enabled.status_code == 200

    result = client.post(f"/api/v2/write-pipeline/batches/{dry_run['id']}/execute", headers=auth_headers)

    assert result.status_code == 200
    data = result.json()
    assert data["status"] == "applied"
    assert data["items"][0]["providerResult"]["stock_update"] is False
    assert data["items"][0]["verification"]["verified"] is True
    assert data["resultSummary"]["success_count"] == 1
    assert data["resultSummary"]["verified_count"] == 1
    events = client.get(f"/api/v2/write-pipeline/batches/{dry_run['id']}/events", headers=auth_headers).json()
    assert {item["eventType"] for item in events} >= {"dry_run_created", "approved", "item_applied", "execution_finished"}


def test_workspace_preview_classifies_validation_errors_warnings_and_unchanged(
    client, auth_headers, configured_db, monkeypatch
):
    from app.flowhub.integrations.nextcloud import NextcloudClient

    _cache_product(configured_db, "101", "Duplicate Product", "SKU-101", "100.00")
    _cache_product(configured_db, "102", "Cache Name", "SKU-102", "100.00")
    _cache_product(configured_db, "103", "Same Price", "SKU-103", "100.00")
    _cache_product(configured_db, "104", "Valid Product", "SKU-104", "100.00")
    _cache_product(configured_db, "105", "Large Warning", "SKU-105", "100.00")
    _cache_product(configured_db, "106", "Invalid Price", "SKU-106", "100.00")
    _cache_product(configured_db, "107", "Variation Product", "SKU-107", "100.00", product_type="variation")
    _cache_product(configured_db, "108", "SKU Match", "DUP-SKU", "100.00")
    _cache_product(configured_db, "109", "Huge Change", "SKU-109", "100.00")

    async def fake_download(self, path):
        return _xlsx(
            [
                ["Duplicate Product", 101, "110.00", "SKU-101"],
                ["Duplicate Product", 101, "111.00", "SKU-101B"],
                ["Wrong Name", 102, "120.00", "SKU-102"],
                ["Same Price", 103, "100.00", "SKU-103"],
                ["Valid Product", 104, "112.00", "SKU-104"],
                ["Large Warning", 105, "140.00", "SKU-105"],
                ["Invalid Price", 106, "abc", "SKU-106"],
                ["Missing Product", 999, "120.00", "SKU-999"],
                ["Variation Product", 107, "120.00", "SKU-107"],
                ["SKU Match", "", "120.00", "DUP-SKU"],
                ["SKU Match", "", "121.00", "DUP-SKU"],
                ["Missing Identifier", "", "120.00", ""],
                ["Huge Change", 109, "170.00", "SKU-109"],
            ]
        ), {"etag": "etag-2"}

    monkeypatch.setattr(NextcloudClient, "download_file", fake_download)

    response = client.post("/api/v2/workspace/preview", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    rows = data["rows"]
    by_row = {item["source"]["rowNumber"]: item for item in rows}

    assert "duplicate_product_id" in by_row[3]["errors"]
    assert "product_name_mismatch" in by_row[5]["errors"]
    assert by_row[6]["status"] == "unchanged"
    assert by_row[7]["eligible_for_dry_run"] is True
    assert "large_price_change" in by_row[8]["warnings"]
    assert "invalid_or_missing_price" in by_row[9]["errors"]
    assert "missing_product" in by_row[10]["errors"]
    assert by_row[11]["status"] == "valid_change"
    assert by_row[11]["matchedProduct"]["itemType"] == "variation"
    assert by_row[11]["eligible_for_dry_run"] is True
    assert "duplicate_sku" in by_row[12]["errors"]
    assert "duplicate_sku" in by_row[13]["errors"]
    assert "missing_product_identifier" in by_row[14]["errors"]
    assert "large_price_change_blocked" in by_row[15]["errors"]
    assert data["summary"]["error_rows"] == 9
    assert data["summary"]["unchanged_rows"] == 1
    assert data["summary"]["large_changes"] == 2

    change_ids = {item["productId"] for item in data["changes"]}
    assert change_ids == {"104", "105", "107"}
    assert all("stock" not in item for item in data["changes"])


def test_rows_with_errors_are_rejected_by_write_pipeline(client, auth_headers):
    response = client.post(
        "/api/v2/write-pipeline/dry-run",
        headers=auth_headers,
        json={
            "previewId": "wp_bad",
            "changes": [
                {
                    "productId": "101",
                    "productName": "Bad",
                    "sku": "SKU-101",
                    "currentPrice": 100.0,
                    "proposedPrice": 110.0,
                    "currency": "EUR",
                    "eligible_for_dry_run": False,
                    "validationStatus": "error",
                    "source": {
                        "previewId": "wp_bad",
                        "sourceId": "nextcloud:primary",
                        "sourceType": "nextcloud_spreadsheet",
                        "sourceSnapshotId": 1,
                        "sourceSnapshotVersion": 1,
                        "sourceFilePath": "/prices.xlsx",
                        "worksheet": "Sheet1",
                        "rowNumber": 3,
                    },
                }
            ],
        },
    )
    assert response.status_code == 422
    assert "validation errors" in response.text


def test_preview_fails_safely_when_cache_is_empty(client, auth_headers, configured_db, monkeypatch):
    from app.flowhub.integrations.nextcloud import NextcloudClient

    async def fake_download(self, path):
        raise AssertionError("empty product cache must fail before source download")

    monkeypatch.setattr(NextcloudClient, "download_file", fake_download)
    response = client.post("/api/v2/workspace/preview", headers=auth_headers)
    assert response.status_code == 409
    assert "product cache is empty" in response.text


def test_preview_fails_safely_when_channel_credentials_are_missing(client, auth_headers, db, monkeypatch):
    from app.flowhub.integrations.nextcloud import NextcloudClient
    from app.flowhub.setup.service import AppConfigService

    AppConfigService(db).set_many(
        {
            "nextcloud.url": "https://cloud.example.test",
            "nextcloud.username": "user",
            "nextcloud.password": "pass",
            "nextcloud.spreadsheet_path": "/prices.xlsx",
        }
    )
    _cache_product(db, "101", "Test Product", "SKU-101", "100.00")

    async def fake_download(self, path):
        raise AssertionError("missing channel credentials must fail before source download")

    monkeypatch.setattr(NextcloudClient, "download_file", fake_download)
    response = client.post("/api/v2/workspace/preview", headers=auth_headers)

    assert response.status_code == 422
    assert "woocommerce.url" in response.text


def test_spreadsheet_normalizes_persian_digits_and_commas():
    from app.flowhub.integrations.spreadsheet import load_workbook_bytes, parse_source_price_rows

    wb = load_workbook_bytes(_xlsx([["Persian Product", "۱۰۱", "۱,۲۳۴.۵۰", "SKU-FA"]]))
    rows, duplicates = parse_source_price_rows(wb)
    assert rows[0]["product_id"] == "101"
    assert rows[0]["proposed_price"] == 1234.5
    assert duplicates["duplicate_product_ids"] == []


def _cache_product(
    db,
    product_id: str,
    name: str,
    sku: str,
    price: str,
    *,
    product_type: str = "simple",
    parent_id: str | None = "100",
    raw_data: dict | None = None,
) -> None:
    from app.flowhub.data_layer.models import DlProductCache

    db.add(
        DlProductCache(
            connector_id="woocommerce:primary",
            product_id=product_id,
            external_id=int(product_id),
            sku=sku,
            name=name,
            product_type=product_type,
            parent_id=parent_id if product_type == "variation" else None,
            regular_price=price,
            price=price,
            categories=[{"name": "Default"}],
            images=[{"src": f"https://example.test/{product_id}.jpg"}],
            freshness="fresh",
            exists=True,
            raw_data=raw_data or {},
            last_fetched_at=datetime.utcnow(),
        )
    )
    db.commit()


def _xlsx(rows: list[list[object]]) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["Name", "Product ID", "Price", "SKU"])
    ws.append(["", "", "", ""])
    for row in rows:
        ws.append(row)
    stream = BytesIO()
    wb.save(stream)
    return stream.getvalue()
