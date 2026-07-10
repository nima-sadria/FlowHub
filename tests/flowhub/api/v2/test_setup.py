"""Tests for /api/v2/setup/* endpoints (BU4).

All tests use an in-memory SQLite database via the auth conftest fixtures.
The FlowHubAppConfig model is imported at module level so it registers with
FlowHubBase.metadata before db_engine calls create_all().
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("FLOWHUB_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FLOWHUB_JWT_SECRET", "test-bu4-jwt-secret-32-bytes-min!")

# Import auth models (conftest already does this, but be explicit)
from app.flowhub.integration_platform import models as _ip_models  # noqa: F401 - registers ip_* tables
from app.flowhub.auth import models as _auth_models  # noqa: F401 - registers FlowHubBase tables
# Import setup model so FlowHubAppConfig is registered with FlowHubBase.metadata
from app.flowhub.setup import models as _setup_models  # noqa: F401 - registers flowhub_app_config
from app.flowhub.api.v2 import setup as setup_api
from app.flowhub.setup.service import AppConfigService


# -- Fixtures ------------------------------------------------------------------

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


# -- GET /api/v2/setup/status --------------------------------------------------

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


# -- POST /api/v2/setup/server-profile ----------------------------------------

class TestSetupServerProfile:
    def test_saves_profile(self, client, db):
        r = client.post("/api/v2/setup/server-profile", json={
            "domain": "test.example.com",
            "port": 8085,
            "environment": "production",
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
            "environment": "production",
            "timezone": "Not/ATimezone",
            "currency": "USD",
        })
        assert r.status_code == 422

    def test_rejects_invalid_currency(self, client):
        r = client.post("/api/v2/setup/server-profile", json={
            "domain": "test.example.com",
            "port": 8085,
            "environment": "production",
            "timezone": "UTC",
            "currency": "notvalid",
        })
        assert r.status_code == 422

    def test_locked_after_setup_complete(self, db, client):
        AppConfigService(db).mark_setup_complete("test")
        db.commit()
        r = client.post("/api/v2/setup/server-profile", json={
            "domain": "x.com", "port": 8085, "environment": "production",
            "timezone": "UTC", "currency": "USD",
        })
        assert r.status_code == 409


# -- POST /api/v2/setup/database ----------------------------------------------

class TestSetupDatabase:
    def test_returns_connected(self, client):
        r = client.post("/api/v2/setup/database")
        assert r.status_code == 200
        data = r.json()
        assert data["connected"] is True

    def test_reports_up_to_date_when_current_revision_matches_latest(self, client, monkeypatch):
        monkeypatch.setattr(setup_api, "_get_current_FLOWHUB_revision", lambda db: "flowhub_007")
        monkeypatch.setattr(setup_api, "_get_latest_FLOWHUB_revision", lambda: "flowhub_007")
        r = client.post("/api/v2/setup/database")
        assert r.status_code == 200
        data = r.json()
        assert data["current_revision"] == "flowhub_007"
        assert data["latest_revision"] == "flowhub_007"
        assert data["is_current"] is True
        assert data["migrations_current"] is True

    def test_reports_needs_update_when_current_revision_is_behind(self, client, monkeypatch):
        monkeypatch.setattr(setup_api, "_get_current_FLOWHUB_revision", lambda db: "flowhub_006")
        monkeypatch.setattr(setup_api, "_get_latest_FLOWHUB_revision", lambda: "flowhub_007")
        r = client.post("/api/v2/setup/database")
        assert r.status_code == 200
        data = r.json()
        assert data["current_revision"] == "flowhub_006"
        assert data["latest_revision"] == "flowhub_007"
        assert data["is_current"] is False
        assert data["migrations_current"] is False

    def test_reports_unable_to_verify_when_latest_revision_is_unknown(self, client, monkeypatch):
        monkeypatch.setattr(setup_api, "_get_current_FLOWHUB_revision", lambda db: "flowhub_007")
        monkeypatch.setattr(setup_api, "_get_latest_FLOWHUB_revision", lambda: None)
        r = client.post("/api/v2/setup/database")
        assert r.status_code == 200
        data = r.json()
        assert data["current_revision"] == "flowhub_007"
        assert data["latest_revision"] is None
        assert data["is_current"] is None
        assert data["migrations_current"] is False

    def test_locked_after_setup_complete(self, db, client):
        AppConfigService(db).mark_setup_complete("test")
        db.commit()
        r = client.post("/api/v2/setup/database")
        assert r.status_code == 409


# -- POST /api/v2/setup/admin -------------------------------------------------

class TestSetupAdmin:
    def test_creates_initial_owner_and_returns_tokens(self, client):
        r = client.post("/api/v2/setup/admin", json={
            "username": "admin",
            "email": "admin@example.com",
            "password": "securepassword123",
        })
        assert r.status_code == 200
        data = r.json()
        assert "token" in data
        assert "refresh_token" in data
        assert data["username"] == "admin"

        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {data['token']}"})
        assert me.status_code == 200
        assert me.json()["role"] == "owner"
        assert me.json()["is_admin"] is True
        assert me.json()["is_super_admin"] is True

    def test_stores_admin_email(self, client, db):
        r = client.post("/api/v2/setup/admin", json={
            "username": "admin",
            "email": " Admin@Example.COM ",
            "password": "securepassword123",
        })
        assert r.status_code == 200
        assert AppConfigService(db).get("admin.email") == "admin@example.com"

    def test_rejects_short_password(self, client):
        r = client.post("/api/v2/setup/admin", json={
            "username": "admin",
            "email": "admin@example.com",
            "password": "short",
        })
        assert r.status_code == 422

    def test_rejects_short_username(self, client):
        r = client.post("/api/v2/setup/admin", json={
            "username": "ab",
            "email": "admin@example.com",
            "password": "validpassword123",
        })
        assert r.status_code == 422

    @pytest.mark.parametrize("email", [
        "",
        "adminexample.com",
        "admin@",
        "admin@example",
        "admin@@example.com",
        "admin @example.com",
        "admin@example..com",
        "admin@-example.com",
        "admin@example.c",
    ])
    def test_rejects_invalid_email(self, client, email):
        r = client.post("/api/v2/setup/admin", json={
            "username": "admin",
            "email": email,
            "password": "validpassword123",
        })
        assert r.status_code == 422

    def test_rejects_second_admin(self, client):
        client.post("/api/v2/setup/admin", json={
            "username": "admin",
            "email": "admin@example.com",
            "password": "securepassword123",
        })
        r = client.post("/api/v2/setup/admin", json={
            "username": "admin2",
            "email": "admin2@example.com",
            "password": "securepassword456",
        })
        assert r.status_code == 409

    def test_locked_after_setup_complete(self, db, client):
        AppConfigService(db).mark_setup_complete("test")
        db.commit()
        r = client.post("/api/v2/setup/admin", json={
            "username": "admin",
            "email": "admin@example.com",
            "password": "securepassword123",
        })
        assert r.status_code == 409


# -- POST /api/v2/setup/complete ----------------------------------------------

class TestSetupComplete:
    def test_requires_admin_to_exist(self, client):
        # No admin created yet - should be rejected
        r = client.post("/api/v2/setup/complete")
        assert r.status_code == 422

    def test_completes_after_admin_created(self, client, db):
        client.post("/api/v2/setup/admin", json={
            "username": "admin",
            "email": "admin@example.com",
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
            "email": "admin@example.com",
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


# -- AppConfigService unit tests -----------------------------------------------

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
