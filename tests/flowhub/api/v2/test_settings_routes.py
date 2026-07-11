"""Tests for /api/v2/settings endpoints (BU5)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("FLOWHUB_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FLOWHUB_JWT_SECRET", "test-bu5-settings-jwt-secret-32bytes!")

from app.flowhub.auth import models as _auth_models  # noqa: F401
from app.flowhub.setup import models as _setup_models  # noqa: F401
from app.flowhub.integration_platform import models as _ip_models  # noqa: F401


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


@pytest.fixture()
def auth_headers(client, db):
    from app.flowhub.auth.password import hash_password
    from app.flowhub.auth.models import FlowHubUser

    user = FlowHubUser(username="settingsadmin", hashed_password=hash_password("pass1234"), role="admin")
    db.add(user)
    db.commit()

    r = client.post("/api/auth/login", json={"username": "settingsadmin", "password": "pass1234"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture()
def viewer_headers(client, db):
    from app.flowhub.auth.password import hash_password
    from app.flowhub.auth.models import FlowHubUser

    user = FlowHubUser(username="settingsviewer", hashed_password=hash_password("pass1234"), role="viewer")
    db.add(user)
    db.commit()
    r = client.post("/api/auth/login", json={"username": "settingsviewer", "password": "pass1234"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture()
def owner_headers(client, db):
    from app.flowhub.auth.password import hash_password
    from app.flowhub.auth.models import FlowHubUser

    user = FlowHubUser(username="settingsowner", hashed_password=hash_password("pass1234"), role="owner")
    db.add(user)
    db.commit()
    r = client.post("/api/auth/login", json={"username": "settingsowner", "password": "pass1234"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


# -- GET /api/v2/settings ------------------------------------------------------

class TestGetSettings:
    def test_requires_auth(self, client):
        r = client.get("/api/v2/settings")
        assert r.status_code == 401

    def test_returns_settings_shape(self, client, auth_headers):
        r = client.get("/api/v2/settings", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "timezone" in data
        assert "currency" in data
        assert "syncIntervalMinutes" in data
        assert "wcConfigured" in data
        assert "ncConfigured" in data

    def test_secrets_not_in_response(self, client, auth_headers, db):
        from app.flowhub.setup.service import AppConfigService
        cfg = AppConfigService(db)
        cfg.set("woocommerce.key", "ck_supersecret")
        cfg.set("woocommerce.secret", "cs_supersecret")
        cfg.set("nextcloud.password", "mypassword")

        r = client.get("/api/v2/settings", headers=auth_headers)
        assert r.status_code == 200
        body_str = r.text
        assert "ck_supersecret" not in body_str
        assert "cs_supersecret" not in body_str
        assert "mypassword" not in body_str

    def test_wc_configured_true_when_credentials_set(self, client, auth_headers, db):
        from app.flowhub.setup.service import AppConfigService
        cfg = AppConfigService(db)
        cfg.set_many({
            "woocommerce.url": "https://store.example.com",
            "woocommerce.key": "ck_test",
            "woocommerce.secret": "cs_test",
        })
        r = client.get("/api/v2/settings", headers=auth_headers)
        assert r.json()["wcConfigured"] is True

    def test_nc_configured_false_when_missing_password(self, client, auth_headers, db):
        from app.flowhub.setup.service import AppConfigService
        cfg = AppConfigService(db)
        cfg.set_many({"nextcloud.url": "https://cloud.example.com", "nextcloud.username": "user"})
        # No password set
        r = client.get("/api/v2/settings", headers=auth_headers)
        assert r.json()["ncConfigured"] is False


# -- POST /api/v2/settings -----------------------------------------------------

class TestUpdateSettings:
    def test_update_timezone(self, client, auth_headers, db):
        r = client.post("/api/v2/settings", headers=auth_headers,
                        json={"timezone": "Asia/Tehran"})
        assert r.status_code == 200
        assert r.json()["ok"] is True
        from app.flowhub.setup.service import AppConfigService
        assert AppConfigService(db).get("server.timezone") == "Asia/Tehran"

    def test_update_currency(self, client, auth_headers, db):
        r = client.post("/api/v2/settings", headers=auth_headers,
                        json={"currency": "IRR"})
        assert r.status_code == 200
        from app.flowhub.setup.service import AppConfigService
        assert AppConfigService(db).get("server.currency") == "IRR"

    def test_rejects_invalid_timezone(self, client, auth_headers):
        r = client.post("/api/v2/settings", headers=auth_headers,
                        json={"timezone": "Not/ATimezone"})
        assert r.status_code == 422

    def test_rejects_invalid_currency(self, client, auth_headers):
        r = client.post("/api/v2/settings", headers=auth_headers,
                        json={"currency": "notvalid"})
        assert r.status_code == 422

    def test_rejects_empty_body(self, client, auth_headers):
        r = client.post("/api/v2/settings", headers=auth_headers, json={})
        assert r.status_code == 400

    @pytest.mark.parametrize(
        ("path", "body"),
        [
            ("/api/v2/settings", {"timezone": "UTC"}),
            ("/api/v2/settings/rate-limits", {"read_requests_per_minute": 60, "write_requests_per_minute": 30}),
            ("/api/v2/settings/woocommerce", {"url": "https://store.example.com", "key": "ck_test", "secret": "cs_test"}),
            ("/api/v2/settings/nextcloud", {"url": "https://cloud.example.com", "username": "user", "password": "app-pass", "spreadsheet_path": "/prices.xlsx"}),
        ],
    )
    def test_viewer_cannot_mutate_settings(self, client, viewer_headers, path, body):
        r = client.post(path, headers=viewer_headers, json=body)
        assert r.status_code == 403

    def test_owner_can_update_settings(self, client, owner_headers, db):
        r = client.post("/api/v2/settings", headers=owner_headers, json={"currency": "IRR"})
        assert r.status_code == 200
        from app.flowhub.setup.service import AppConfigService
        assert AppConfigService(db).get("server.currency") == "IRR"


# -- POST /api/v2/settings/woocommerce ----------------------------------------

class TestUpdateWooCommerce:
    def test_saves_credentials(self, client, auth_headers, db):
        r = client.post("/api/v2/settings/woocommerce", headers=auth_headers,
                        json={"url": "https://store.example.com", "key": "ck_k", "secret": "cs_s"})
        assert r.status_code == 200
        assert r.json()["ok"] is True
        from app.flowhub.setup.service import AppConfigService
        cfg = AppConfigService(db)
        assert cfg.get("woocommerce.url") == "https://store.example.com"
        # Secret stored but never returned
        assert cfg.get("woocommerce.key") == "ck_k"
        connectors = client.get("/api/v2/integrations/connectors", headers=auth_headers)
        assert connectors.status_code == 200
        item = connectors.json()["items"][0]
        settings = {s["key"]: s for s in item["settings"]}
        assert settings["key"]["value"] is None
        assert settings["key"]["configured"] is True

    def test_rejects_invalid_url(self, client, auth_headers):
        r = client.post("/api/v2/settings/woocommerce", headers=auth_headers,
                        json={"url": "not-a-url", "key": "ck_k", "secret": "cs_s"})
        assert r.status_code == 422


# -- POST /api/v2/settings/nextcloud ------------------------------------------

class TestUpdateNextcloud:
    def test_saves_credentials(self, client, auth_headers, db):
        r = client.post("/api/v2/settings/nextcloud", headers=auth_headers,
                        json={
                            "url": "https://cloud.example.com",
                            "username": "user",
                            "password": "apppass",
                            "spreadsheet_path": "/prices.xlsx",
                        })
        assert r.status_code == 200
        assert r.json()["ok"] is True
        from app.flowhub.setup.service import AppConfigService
        cfg = AppConfigService(db)
        assert cfg.get("nextcloud.url") == "https://cloud.example.com"
        assert cfg.get("nextcloud.spreadsheet_path") == "/prices.xlsx"
        assert "apppass" not in client.get("/api/v2/settings", headers=auth_headers).text

    @pytest.mark.parametrize(
        "url",
        [
            "https://user@cloud.example.test",
            "https://user:password@cloud.example.test",
            "https://user%40example.test:token@cloud.example.test/remote.php/dav/files/user",
        ],
    )
    def test_rejects_credential_bearing_url(self, client, auth_headers, caplog, url):
        r = client.post(
            "/api/v2/settings/nextcloud",
            headers=auth_headers,
            json={
                "url": url,
                "username": "user",
                "password": "separate-app-password",
                "spreadsheet_path": "/prices.xlsx",
            },
        )

        assert r.status_code == 422
        assert r.json()["detail"]["code"] == "CREDENTIALS_IN_URL_NOT_ALLOWED"
        assert url not in r.text
        assert "separate-app-password" not in r.text
        assert url not in caplog.text

    def test_settings_response_withholds_legacy_credential_url(self, client, auth_headers, db):
        from app.flowhub.setup.service import AppConfigService

        unsafe_url = "https://user:legacy-secret@cloud.example.test"
        AppConfigService(db).set_many(
            {
                "nextcloud.url": unsafe_url,
                "nextcloud.username": "user",
                "nextcloud.password": "separate-app-password",
            },
            updated_by="legacy-test",
        )

        response = client.get("/api/v2/settings", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["nextcloudUrl"] == ""
        assert unsafe_url not in response.text
        assert "legacy-secret" not in response.text
