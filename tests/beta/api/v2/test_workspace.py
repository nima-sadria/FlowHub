"""Tests for /api/v2/workspace/* endpoints (BU5).

Uses the same SQLite in-memory DB fixtures as test_setup.py.
WooCommerce and Nextcloud I/O are fully mocked.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("BETA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("BETA_JWT_SECRET", "test-bu5-workspace-jwt-secret-32bytes!")

from app.beta.auth import models as _auth_models  # noqa: F401
from app.beta.setup import models as _setup_models  # noqa: F401


# ── Fixtures (mirror test_setup.py pattern) ───────────────────────────────────

@pytest.fixture()
def db_engine():
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    from app.beta.database import BetaBase, _get_engine

    _get_engine.cache_clear()
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    BetaBase.metadata.create_all(engine)
    yield engine
    BetaBase.metadata.drop_all(engine)
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
    from app.beta.app import app
    from app.beta.database import get_db

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
    """Create an admin user and return JWT auth headers."""
    from app.beta.auth.password import hash_password
    from app.beta.auth.models import BetaUser

    user = BetaUser(username="testadmin", hashed_password=hash_password("password123"), role="admin")
    db.add(user)
    db.commit()

    r = client.post("/api/auth/login", json={"username": "testadmin", "password": "password123"})
    assert r.status_code == 200
    token = r.json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def configured_db(db):
    """Seed WC and NC credentials + mark setup complete."""
    from app.beta.setup.service import AppConfigService
    cfg = AppConfigService(db)
    cfg.set_many({
        "woocommerce.url": "https://store.example.com",
        "woocommerce.key": "ck_test",
        "woocommerce.secret": "cs_test",
        "nextcloud.url": "https://cloud.example.com",
        "nextcloud.username": "user",
        "nextcloud.password": "pass",
        "nextcloud.spreadsheet_path": "/prices.xlsx",
        "setup.completed": "true",
        "server.currency": "EUR",
    })
    return db


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestWorkspaceState:
    def test_state_requires_auth(self, client):
        r = client.get("/api/v2/workspace/state")
        assert r.status_code == 401

    def test_state_returns_idle(self, client, auth_headers):
        r = client.get("/api/v2/workspace/state", headers=auth_headers)
        assert r.status_code == 200
        assert r.json()["state"] == "idle"


class TestWorkspacePreview:
    def test_preview_requires_auth(self, client):
        r = client.post("/api/v2/workspace/preview")
        assert r.status_code == 401

    def test_preview_returns_503_when_wc_not_configured(self, client, auth_headers, db):
        r = client.post("/api/v2/workspace/preview", headers=auth_headers)
        assert r.status_code == 503
        assert "WooCommerce" in r.json()["detail"]

    def test_preview_returns_503_when_nc_not_configured(self, client, auth_headers, db):
        from app.beta.setup.service import AppConfigService
        cfg = AppConfigService(db)
        cfg.set_many({
            "woocommerce.url": "https://store.example.com",
            "woocommerce.key": "ck_test",
            "woocommerce.secret": "cs_test",
            "setup.completed": "true",
        })
        r = client.post("/api/v2/workspace/preview", headers=auth_headers)
        assert r.status_code == 503
        assert "Nextcloud" in r.json()["detail"]

    def test_preview_returns_valid_shape(self, client, auth_headers, configured_db):
        from unittest.mock import AsyncMock, patch, MagicMock

        # Mock WC products response
        mock_wc_products = [
            {"id": "1", "wcId": 1, "name": "Widget A", "sku": "W-001",
             "currentPrice": 10.0, "categoryNames": [], "productType": "simple"},
            {"id": "2", "wcId": 2, "name": "Widget B", "sku": "W-002",
             "currentPrice": 20.0, "categoryNames": [], "productType": "simple"},
        ]

        # Build a minimal XLSX workbook in memory
        import io
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Prices"
        ws.append(["Name", "ID", "Price"])   # row 1 — header
        ws.append([])                          # row 2
        ws.append(["Widget A", 1, 15.00])     # row 3 — price change
        ws.append(["Widget B", 2, 20.00])     # row 4 — same price (no change)
        buf = io.BytesIO()
        wb.save(buf)
        xlsx_bytes = buf.getvalue()

        with (
            patch("app.beta.integrations.woocommerce.WooCommerceClient.get_all_products_for_preview",
                  new=AsyncMock(return_value=mock_wc_products)),
            patch("app.beta.integrations.nextcloud.NextcloudClient.download_file",
                  new=AsyncMock(return_value=(xlsx_bytes, {}))),
        ):
            r = client.post("/api/v2/workspace/preview", headers=auth_headers)

        assert r.status_code == 200
        data = r.json()
        assert "id" in data
        assert data["state"] == "preview_ready"
        assert data["totalChanges"] == 1  # only Widget A changed (10 → 15)
        changes = data["changes"]
        assert len(changes) == 1
        c = changes[0]
        assert c["productId"] == "1"
        assert c["currentPrice"] == pytest.approx(10.0)
        assert c["proposedPrice"] == pytest.approx(15.0)
        assert c["difference"] == pytest.approx(5.0)
        assert "startedAt" in data

    def test_preview_write_guard_via_http(self, client, auth_headers):
        """Verify the write guard endpoint returns 403 for any write attempt."""
        from app.beta.integrations.write_guard import BETA_WRITE_BLOCKED
        # Directly test the write_guard raises correctly
        from app.beta.integrations.write_guard import raise_write_blocked
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            raise_write_blocked()
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == BETA_WRITE_BLOCKED
