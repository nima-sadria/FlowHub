"""Tests for /api/v2/workspace endpoints."""

from __future__ import annotations

import os
from datetime import datetime
from io import BytesIO

import pytest

os.environ.setdefault("FLOWHUB_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FLOWHUB_JWT_SECRET", "test-bu5-workspace-jwt-secret-32bytes!")

from app.flowhub.auth import models as _auth_models  # noqa: F401
from app.flowhub.data_layer import models as _dl_models  # noqa: F401
from app.flowhub.integration_platform import models as _ip_models  # noqa: F401
from app.flowhub.setup import models as _setup_models  # noqa: F401


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
    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.auth.password import hash_password

    user = FlowHubUser(username="testadmin", hashed_password=hash_password("password123"), role="admin")
    db.add(user)
    db.commit()
    response = client.post("/api/auth/login", json={"username": "testadmin", "password": "password123"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture()
def configured_db(db):
    from app.flowhub.setup.service import AppConfigService

    cfg = AppConfigService(db)
    cfg.set_many(
        {
            "woocommerce.url": "https://store.example.com",
            "woocommerce.key": "ck_test",
            "woocommerce.secret": "cs_test",
            "nextcloud.url": "https://cloud.example.com",
            "nextcloud.username": "user",
            "nextcloud.password": "pass",
            "nextcloud.spreadsheet_path": "/prices.xlsx",
            "setup.completed": "true",
            "server.currency": "EUR",
        }
    )
    return db


class TestWorkspaceState:
    def test_state_requires_auth(self, client):
        response = client.get("/api/v2/workspace/state")
        assert response.status_code == 401

    def test_state_returns_idle(self, client, auth_headers):
        response = client.get("/api/v2/workspace/state", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["state"] == "idle"


class TestWorkspacePreview:
    def test_preview_requires_auth(self, client):
        response = client.post("/api/v2/workspace/preview")
        assert response.status_code == 401

    def test_preview_fails_closed_without_live_connector_configuration(self, client, auth_headers):
        response = client.post("/api/v2/workspace/preview", headers=auth_headers)
        assert response.status_code == 422
        assert "Missing required setting: nextcloud.spreadsheet_path" in response.text

    def test_preview_returns_source_driven_rows(self, client, auth_headers, configured_db, monkeypatch):
        from app.flowhub.data_layer.models import DlProductCache
        from app.flowhub.integrations.nextcloud import NextcloudClient

        configured_db.add(
            DlProductCache(
                connector_id="woocommerce:primary",
                product_id="101",
                external_id=101,
                sku="SKU-101",
                name="Test Product",
                product_type="simple",
                regular_price="100.00",
                price="100.00",
                categories=[{"name": "Category"}],
                images=[{"src": "https://example.test/image.jpg"}],
                freshness="fresh",
                exists=True,
                last_fetched_at=datetime.utcnow(),
            )
        )
        configured_db.commit()

        async def fake_download(self, path):
            assert path == "/prices.xlsx"
            return _xlsx([["Test Product", 101, "110.00", "SKU-101"]]), {"etag": "abc", "last_modified": "today"}

        monkeypatch.setattr(NextcloudClient, "download_file", fake_download)
        response = client.post("/api/v2/workspace/preview", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "preview_ready"
        assert data["totalChanges"] == 1
        assert data["summary"]["total_rows"] == 1
        assert data["summary"]["valid_changes"] == 1
        assert data["rows"][0]["source"]["worksheet"] == "Sheet"
        assert data["rows"][0]["matchedProduct"]["productId"] == "101"
        assert data["changes"][0]["productId"] == "101"
        assert data["changes"][0]["source"]["sourceFilePath"] == "/prices.xlsx"
        assert data["runtime_write_blocked"] is True
        assert data["external_call_performed"] is True
        assert "startedAt" in data

    def test_preview_write_guard_via_http(self, client, auth_headers):
        from app.flowhub.integrations.write_guard import FLOWHUB_WRITE_BLOCKED, raise_write_blocked
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            raise_write_blocked()
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == FLOWHUB_WRITE_BLOCKED


def _xlsx(rows: list[list[object]]) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet"
    ws.append(["Name", "Product ID", "Price", "SKU"])
    ws.append(["", "", "", ""])
    for row in rows:
        ws.append(row)
    stream = BytesIO()
    wb.save(stream)
    return stream.getvalue()
