"""Tests for /api/v2/setup/* endpoints (BU4).

All tests use an in-memory SQLite database via the auth conftest fixtures.
The BetaAppConfig model is imported at module level so it registers with
BetaBase.metadata before db_engine calls create_all().
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("BETA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("BETA_JWT_SECRET", "test-bu4-jwt-secret-32-bytes-min!")

# Import auth models (conftest already does this, but be explicit)
from app.beta.integration_platform import models as _ip_models  # noqa: F401 - registers ip_* tables
from app.beta.auth import models as _auth_models  # noqa: F401 â€” registers BetaBase tables
# Import setup model so BetaAppConfig is registered with BetaBase.metadata
from app.beta.setup import models as _setup_models  # noqa: F401 â€” registers beta_app_config
from app.beta.api.v2 import setup as setup_api
from app.beta.setup.service import AppConfigService


# â”€â”€ Fixtures â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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


# â”€â”€ GET /api/v2/setup/status â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestSetupStatus:
    def test_returns_200(self, client):
        r = client.get("/api/v2/setup/status")
        assert r.status_code == 200

    def test_not_completed_on_fresh_db(self, client):
        r = client.get("/api/v2/setup/status")
        assert r.json()["completed"] is False

    def test_completed_after_marking(self, db, client):
        svc = AppConfigService(db)
        svc.mark_setup_complete("test")
        db.commit()
        r = client.get("/api/v2/setup/status")
        assert r.json()["completed"] is True


# â”€â”€ POST /api/v2/setup/server-profile â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestSetupServerProfile:
    def test_saves_profile(self, client, db):
        r = client.post("/api/v2/setup/server-profile", json={
            "domain": "test.example.com",
            "port": 8085,
            "environment": "beta",
            "timezone": "UTC",
            "currency": "USD",
        })
        assert r.status_code == 200
        assert r.json()["ok"] is True
        svc = AppConfigService(db)
        assert svc.get("server.domain") == "test.example.com"
        assert svc.get("server.timezone") == "UTC"

    def test_rejects_invalid_timezone(self, client):
        r = client.post("/api/v2/setup/server-profile", json={
            "domain": "test.example.com",
            "port": 8085,
            "environment": "beta",
            "timezone": "Not/ATimezone",
            "currency": "USD",
        })
        assert r.status_code == 422

    def test_rejects_invalid_currency(self, client):
        r = client.post("/api/v2/setup/server-profile", json={
            "domain": "test.example.com",
            "port": 8085,
            "environment": "beta",
            "timezone": "UTC",
            "currency": "notvalid",
        })
        assert r.status_code == 422

    def test_locked_after_setup_complete(self, db, client):
        AppConfigService(db).mark_setup_complete("test")
        db.commit()
        r = client.post("/api/v2/setup/server-profile", json={
            "domain": "x.com", "port": 8085, "environment": "beta",
            "timezone": "UTC", "currency": "USD",
        })
        assert r.status_code == 409


# â”€â”€ POST /api/v2/setup/database â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestSetupDatabase:
    def test_returns_connected(self, client):
        r = client.post("/api/v2/setup/database")
        assert r.status_code == 200
        data = r.json()
        assert data["connected"] is True

    def test_reports_up_to_date_when_current_revision_matches_latest(self, client, monkeypatch):
        monkeypatch.setattr(setup_api, "_get_current_beta_revision", lambda db: "beta_007")
        monkeypatch.setattr(setup_api, "_get_latest_beta_revision", lambda: "beta_007")
        r = client.post("/api/v2/setup/database")
        assert r.status_code == 200
        data = r.json()
        assert data["current_revision"] == "beta_007"
        assert data["latest_revision"] == "beta_007"
        assert data["is_current"] is True
        assert data["migrations_current"] is True

    def test_reports_needs_update_when_current_revision_is_behind(self, client, monkeypatch):
        monkeypatch.setattr(setup_api, "_get_current_beta_revision", lambda db: "beta_006")
        monkeypatch.setattr(setup_api, "_get_latest_beta_revision", lambda: "beta_007")
        r = client.post("/api/v2/setup/database")
        assert r.status_code == 200
        data = r.json()
        assert data["current_revision"] == "beta_006"
        assert data["latest_revision"] == "beta_007"
        assert data["is_current"] is False
        assert data["migrations_current"] is False

    def test_reports_unable_to_verify_when_latest_revision_is_unknown(self, client, monkeypatch):
        monkeypatch.setattr(setup_api, "_get_current_beta_revision", lambda db: "beta_007")
        monkeypatch.setattr(setup_api, "_get_latest_beta_revision", lambda: None)
        r = client.post("/api/v2/setup/database")
        assert r.status_code == 200
        data = r.json()
        assert data["current_revision"] == "beta_007"
        assert data["latest_revision"] is None
        assert data["is_current"] is None
        assert data["migrations_current"] is False

    def test_locked_after_setup_complete(self, db, client):
        AppConfigService(db).mark_setup_complete("test")
        db.commit()
        r = client.post("/api/v2/setup/database")
        assert r.status_code == 409


# â”€â”€ POST /api/v2/setup/admin â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestSetupAdmin:
    def test_creates_admin_and_returns_tokens(self, client):
        r = client.post("/api/v2/setup/admin", json={
            "username": "admin",
            "password": "securepassword123",
        })
        assert r.status_code == 200
        data = r.json()
        assert "token" in data
        assert "refresh_token" in data
        assert data["username"] == "admin"

    def test_rejects_short_password(self, client):
        r = client.post("/api/v2/setup/admin", json={
            "username": "admin",
            "password": "short",
        })
        assert r.status_code == 422

    def test_rejects_short_username(self, client):
        r = client.post("/api/v2/setup/admin", json={
            "username": "ab",
            "password": "validpassword123",
        })
        assert r.status_code == 422

    def test_rejects_second_admin(self, client):
        client.post("/api/v2/setup/admin", json={
            "username": "admin",
            "password": "securepassword123",
        })
        r = client.post("/api/v2/setup/admin", json={
            "username": "admin2",
            "password": "securepassword456",
        })
        assert r.status_code == 409

    def test_locked_after_setup_complete(self, db, client):
        AppConfigService(db).mark_setup_complete("test")
        db.commit()
        r = client.post("/api/v2/setup/admin", json={
            "username": "admin",
            "password": "securepassword123",
        })
        assert r.status_code == 409


# â”€â”€ POST /api/v2/setup/complete â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestSetupComplete:
    def test_requires_admin_to_exist(self, client):
        # No admin created yet â€” should be rejected
        r = client.post("/api/v2/setup/complete")
        assert r.status_code == 422

    def test_completes_after_admin_created(self, client, db):
        client.post("/api/v2/setup/admin", json={
            "username": "admin",
            "password": "securepassword123",
        })
        r = client.post("/api/v2/setup/complete")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        # Verify status flips
        r2 = client.get("/api/v2/setup/status")
        assert r2.json()["completed"] is True

    def test_locked_after_completion(self, client):
        client.post("/api/v2/setup/admin", json={
            "username": "admin",
            "password": "securepassword123",
        })
        client.post("/api/v2/setup/complete")
        r = client.post("/api/v2/setup/complete")
        assert r.status_code == 409


class TestSetupIntegrationsRemoved:
    """Connector configuration belongs to Settings -> Integrations, not setup."""

    def test_woocommerce_setup_route_removed(self, client):
        r = client.post("/api/v2/setup" + "/integrations/woocommerce", json={
            "url": "https://mystore.example.com",
            "key": "ck_testkey123",
            "secret": "cs_testsecret456",
        })
        assert r.status_code in {404, 405}

    def test_nextcloud_setup_route_removed(self, client):
        r = client.post("/api/v2/setup" + "/integrations/nextcloud", json={
            "url": "https://cloud.example.com",
            "username": "myuser",
            "password": "apppassword123",
            "spreadsheet_path": "/prices/products.xlsx",
        })
        assert r.status_code in {404, 405}


# â”€â”€ AppConfigService unit tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TestAppConfigService:
    def test_get_returns_none_for_missing_key(self, db):
        svc = AppConfigService(db)
        assert svc.get("no.such.key") is None

    def test_set_and_get(self, db):
        svc = AppConfigService(db)
        svc.set("test.key", "hello")
        assert svc.get("test.key") == "hello"

    def test_set_many(self, db):
        svc = AppConfigService(db)
        svc.set_many({"a.one": "1", "a.two": "2"})
        assert svc.get("a.one") == "1"
        assert svc.get("a.two") == "2"

    def test_update_existing_key(self, db):
        svc = AppConfigService(db)
        svc.set("key", "v1")
        svc.set("key", "v2")
        assert svc.get("key") == "v2"

    def test_is_setup_completed_false_by_default(self, db):
        svc = AppConfigService(db)
        assert svc.is_setup_completed() is False

    def test_mark_setup_complete(self, db):
        svc = AppConfigService(db)
        svc.mark_setup_complete()
        assert svc.is_setup_completed() is True

    def test_get_safe_masks_secrets(self, db):
        svc = AppConfigService(db)
        svc.set("woocommerce.key", "ck_supersecretkey")
        svc.set("woocommerce.secret", "cs_supersecret")
        svc.set("nextcloud.password", "mypass")
        svc.set("server.domain", "example.com")
        safe = svc.get_safe()
        assert safe["woocommerce.key"] == "[REDACTED]"
        assert safe["woocommerce.secret"] == "[REDACTED]"
        assert safe["nextcloud.password"] == "[REDACTED]"
        assert safe["server.domain"] == "example.com"
