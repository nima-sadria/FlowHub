from __future__ import annotations

import os
import uuid

import pytest

os.environ.setdefault("FLOWHUB_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FLOWHUB_JWT_SECRET", "test-commerce-hub-jwt-secret-32bytes!")

from app.flowhub.auth import models as _auth_models  # noqa: F401
from app.flowhub.data_layer import models as _data_layer_models  # noqa: F401
from app.flowhub.integration_platform import models as _integration_platform_models  # noqa: F401
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
    from app.flowhub.auth.jwt_service import create_access_token
    from app.flowhub.auth.password import hash_password

    username = f"commerceadmin_{uuid.uuid4().hex}"
    user = FlowHubUser(username=username, hashed_password=hash_password("password123"), role="admin")
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id, user.username, user.role)
    return {"Authorization": f"Bearer {token}"}


def test_commerce_channels_report_read_only_write_blocked(client, auth_headers):
    response = client.get("/api/v2/commerce/channels", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["read_only"] is True
    assert data["runtime_write_blocked"] is True
    assert data["write_blocked"] is True

    by_name = {item["name"]: item for item in data["items"]}
    assert by_name["WooCommerce"]["type"] == "Channel"
    assert by_name["WooCommerce"]["read_only"] is True
    assert by_name["WooCommerce"]["access_mode"] == "read_only"
    assert by_name["WooCommerce"]["write_pipeline_eligible"] is False
    assert by_name["Snapp Shop"]["placeholder"] is True
    assert by_name["Snapp Shop"]["write_blocked"] is True
    assert by_name["Tapsi Shop"]["placeholder"] is True
    assert by_name["Tapsi Shop"]["write_blocked"] is True


def test_commerce_sources_do_not_list_marketplace_channels(client, auth_headers):
    response = client.get("/api/v2/commerce/sources", headers=auth_headers)

    assert response.status_code == 200
    names = {item["name"] for item in response.json()["items"]}
    assert {"Nextcloud", "CSV", "Google Sheets", "ERP / API Import"}.issubset(names)
    assert "Snapp Shop" not in names
    assert "Tapsi Shop" not in names


def test_commerce_type_routes_mark_future_placeholders_read_only(client, auth_headers):
    source_response = client.get("/api/v2/commerce/source-types", headers=auth_headers)
    channel_response = client.get("/api/v2/commerce/channel-types", headers=auth_headers)

    assert source_response.status_code == 200
    assert channel_response.status_code == 200

    source_types = {item["provider"]: item for item in source_response.json()["items"]}
    channel_types = {item["provider"]: item for item in channel_response.json()["items"]}

    assert source_types["nextcloud"]["implemented"] is True
    assert source_types["csv"]["placeholder"] is True
    assert source_types["csv"]["read_only"] is True
    assert channel_types["woocommerce"]["implemented"] is True
    for provider in ("snappshop", "tapsishop", "digikala", "technolife", "shopify"):
        assert channel_types[provider]["placeholder"] is True
        assert channel_types[provider]["read_only"] is True
        assert channel_types[provider]["write_blocked"] is True


def test_snapp_tapsi_registry_placeholders_are_read_only():
    from app.flowhub.integration_platform.registry import registry

    for provider in ("snappshop", "tapsishop"):
        definition = registry.get_definition(provider)
        assert definition is not None
        assert definition.connector.identity.read_only is True
        assert definition.connector.capabilities.read_products is True
        assert definition.connector.capabilities.write_prices is False
        assert definition.connector.capabilities.write_inventory is False


def test_woocommerce_connection_test_performs_read_only_api_call_without_secret_leakage(client, auth_headers, monkeypatch):
    limiter_calls: list[tuple[str, str]] = []
    request_calls: list[dict] = []

    async def fake_acquire(connector_id: str, operation: str):
        limiter_calls.append((connector_id, operation))

    class FakeResponse:
        status_code = 200
        headers = {"X-WP-Total": "1", "X-WP-TotalPages": "1"}

        def json(self):
            return [{"id": 123}]

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            self.auth = kwargs.get("auth")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, *, params, timeout):
            request_calls.append({
                "url": url,
                "params": params,
                "timeout": timeout,
                "auth": self.auth,
            })
            return FakeResponse()

    monkeypatch.setattr(
        "app.connectors.destinations.woocommerce.rest_client.acquire_connector_rate_limit",
        fake_acquire,
    )
    monkeypatch.setattr("app.connectors.destinations.woocommerce.rest_client.httpx.AsyncClient", FakeAsyncClient)

    save = client.put(
        "/api/v2/commerce/channels/woocommerce:primary/settings",
        headers=auth_headers,
        json={
            "display_name": "WooCommerce",
            "enabled": True,
            "settings": {"url": "https://store.example.test"},
            "secrets": {"key": "ck_live_secret", "secret": "cs_live_secret"},
        },
    )
    assert save.status_code == 200
    assert "ck_live_secret" not in save.text
    assert "cs_live_secret" not in save.text

    response = client.post("/api/v2/commerce/channels/woocommerce:primary/test", headers=auth_headers, json={})

    assert response.status_code == 200
    assert "ck_live_secret" not in response.text
    assert "cs_live_secret" not in response.text
    data = response.json()
    assert data["ok"] is True
    assert data["connected"] is True
    assert data["authenticated"] is True
    assert data["status"] == "connected"
    assert data["http_status"] == 200
    assert isinstance(data["latency_ms"], (int, float))
    assert data["checked_at"]
    assert data["external_call_performed"] is True
    assert data["read_only"] is True
    assert data["runtime_write_blocked"] is True
    assert data["write_blocked"] is True
    assert limiter_calls == [("woocommerce:primary", "read")]
    assert len(request_calls) == 1
    assert request_calls[0]["url"] == "https://store.example.test/wp-json/wc/v3/products"
    assert request_calls[0]["params"]["per_page"] == 1
    assert request_calls[0]["params"]["_fields"] == "id"
    assert request_calls[0]["auth"] == ("ck_live_secret", "cs_live_secret")


def test_placeholder_connection_test_does_not_call_external_system(client, auth_headers, monkeypatch):
    async def fail_acquire(*args, **kwargs):
        raise AssertionError("placeholder channels must not acquire a limiter token")

    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("placeholder channels must not create outbound HTTP clients")

    monkeypatch.setattr(
        "app.connectors.destinations.woocommerce.rest_client.acquire_connector_rate_limit",
        fail_acquire,
    )
    monkeypatch.setattr("app.connectors.destinations.woocommerce.rest_client.httpx.AsyncClient", FailingAsyncClient)

    response = client.post("/api/v2/commerce/channels/snappshop:main/test", headers=auth_headers, json={})

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["connected"] is False
    assert data["authenticated"] is False
    assert data["status"] == "placeholder"
    assert data["external_call_performed"] is False
    assert data["message"] == "Real connector is not implemented yet. No external call was performed."
    assert data["read_only"] is True
    assert data["runtime_write_blocked"] is True
    assert data["write_blocked"] is True


def test_source_placeholder_connection_test_does_not_call_external_system(client, auth_headers):
    response = client.post("/api/v2/commerce/sources/gsheets:price-list/test", headers=auth_headers, json={})

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["external_call_performed"] is False
    assert data["read_only"] is True
    assert data["runtime_write_blocked"] is True
    assert data["write_blocked"] is True


@pytest.mark.parametrize(
    "url",
    [
        "https://softpple.business",
        "https://softpple.business/",
        "https://example.com/nextcloud",
    ],
)
def test_nextcloud_source_accepts_root_base_url(client, auth_headers, url):
    response = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {
                "url": url,
                "username": "woo",
                "spreadsheet_path": "/Price Sheet.xlsx",
            },
            "secrets": {"password": "app-password-secret"},
        },
    )

    assert response.status_code == 200
    assert "app-password-secret" not in response.text
    assert response.json()["read_only"] is True
    assert response.json()["write_pipeline_eligible"] is False


@pytest.mark.parametrize(
    "url",
    [
        "https://softpple.business/remote.php/dav/files/woo",
        "https://softpple.business/remote.php/dav/files/woo/",
        "https://example.com/nextcloud/remote.php/dav/files/USERNAME/",
    ],
)
def test_nextcloud_source_accepts_webdav_files_url_as_input(client, auth_headers, url):
    response = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {
                "url": url,
                "username": url.rstrip("/").rsplit("/", 1)[-1],
                "spreadsheet_path": "/Price Sheet.xlsx",
            },
            "secrets": {"password": "app-password-secret"},
        },
    )

    assert response.status_code == 200
    assert "app-password-secret" not in response.text
    assert response.json()["read_only"] is True
    assert response.json()["write_pipeline_eligible"] is False


def test_nextcloud_source_extracts_username_from_webdav_url(client, auth_headers, db):
    from app.flowhub.setup.service import AppConfigService

    response = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {
                "url": "https://example.com/nextcloud/remote.php/dav/files/woo/",
                "spreadsheet_path": "/wooprice/Price List.xlsx",
            },
            "secrets": {"password": "app-password-secret"},
        },
    )

    assert response.status_code == 200
    cfg = AppConfigService(db)
    assert cfg.get("nextcloud.url") == "https://example.com/nextcloud"
    assert cfg.get("nextcloud.webdav_files_root_url") == "https://example.com/nextcloud/remote.php/dav/files/woo/"
    assert cfg.get("nextcloud.username") == "woo"
    assert cfg.get("nextcloud.spreadsheet_path") == "/wooprice/Price List.xlsx"


def test_nextcloud_source_rejects_webdav_username_mismatch(client, auth_headers):
    response = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "settings": {"url": "https://softpple.business/remote.php/dav/files/woo", "username": "admin"},
            "secrets": {"password": "app-password-secret"},
        },
    )

    assert response.status_code == 422
    assert "WebDAV URL username does not match configured username." in response.text


@pytest.mark.parametrize(
    ("url", "message"),
    [
        (
            "https://softpple.business/index.php/s/xxxxx",
            "Public share links are not supported. Use the Nextcloud root URL or your personal WebDAV files URL.",
        ),
        (
            "https://softpple.business/public.php/dav/files/xxxxx/",
            "Public share links are not supported. Use the Nextcloud root URL or your personal WebDAV files URL.",
        ),
        (
            "https://softpple.business/remote.php/dav/files/",
            "Use the Nextcloud root URL or the WebDAV files URL shown in Nextcloud Files settings.",
        ),
        (
            "https://softpple.business/apps/files/",
            "Use the Nextcloud root URL or the WebDAV files URL shown in Nextcloud Files settings.",
        ),
        (
            "not-a-url",
            "Use the Nextcloud root URL or the WebDAV files URL shown in Nextcloud Files settings.",
        ),
    ],
)
def test_nextcloud_source_rejects_non_root_base_urls(client, auth_headers, url, message):
    response = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "settings": {"url": url, "username": "woo", "spreadsheet_path": "/prices.xlsx"},
            "secrets": {"password": "app-password-secret"},
        },
    )

    assert response.status_code == 422
    assert message in response.text
    assert "app-password-secret" not in response.text


def test_nextcloud_webdav_browse_returns_folders_and_spreadsheets_without_secret(client, auth_headers, monkeypatch):
    from app.connectors.sources.nextcloud.webdav import DavResource

    calls: list[dict] = []

    async def fake_propfind(creds, path, depth="1"):
        calls.append({
            "url": creds.url,
            "webdav_files_root_url": creds.webdav_files_root_url,
            "username": creds.username,
            "password": creds.password,
            "path": path,
            "depth": depth,
        })
        return [
            DavResource("/remote.php/dav/files/woo/Reports/", True, last_modified="Mon, 01 Jan 2024 00:00:00 GMT"),
            DavResource("/remote.php/dav/files/woo/Reports/Subfolder/", True, last_modified="Tue, 02 Jan 2024 00:00:00 GMT"),
            DavResource("/remote.php/dav/files/woo/Reports/Q1.xlsx", False, content_length=1234, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            DavResource("/remote.php/dav/files/woo/Reports/legacy.xls", False, content_length=55),
            DavResource("/remote.php/dav/files/woo/Reports/prices.csv", False, content_length=77),
            DavResource("/remote.php/dav/files/woo/Reports/readme.txt", False, content_length=10),
        ]

    monkeypatch.setattr("app.flowhub.integrations.nextcloud.propfind_path", fake_propfind)

    response = client.post(
        "/api/v2/commerce/sources/nextcloud:primary/browse",
        headers=auth_headers,
        json={
            "path": "/Reports",
            "settings": {"url": "https://softpple.business/remote.php/dav/files/woo", "username": "woo"},
            "secrets": {"password": "app-password-secret"},
        },
    )

    assert response.status_code == 200
    assert "app-password-secret" not in response.text
    data = response.json()
    assert data["path"] == "/Reports"
    assert data["external_call_performed"] is True
    assert data["credentials_returned"] is False
    assert data["directories"][0]["name"] == "Subfolder"
    files = {item["name"]: item for item in data["files"]}
    assert set(files) == {"Q1.xlsx", "legacy.xls", "prices.csv"}
    assert files["Q1.xlsx"]["supported"] is True
    assert files["legacy.xls"]["supported"] is False
    assert files["prices.csv"]["supported"] is False
    assert calls == [{
        "url": "https://softpple.business",
        "webdav_files_root_url": "https://softpple.business/remote.php/dav/files/woo/",
        "username": "woo",
        "password": "app-password-secret",
        "path": "/Reports/",
        "depth": "1",
    }]


def test_nextcloud_webdav_browse_root_uses_webdav_files_root(client, auth_headers, monkeypatch):
    from app.connectors.sources.nextcloud.webdav import DavResource

    calls: list[dict] = []

    async def fake_propfind(creds, path, depth="1"):
        calls.append({
            "url": creds.url,
            "webdav_files_root_url": creds.webdav_files_root_url,
            "username": creds.username,
            "path": path,
            "depth": depth,
        })
        return [DavResource("/nextcloud/remote.php/dav/files/woo/", True)]

    monkeypatch.setattr("app.flowhub.integrations.nextcloud.propfind_path", fake_propfind)

    response = client.post(
        "/api/v2/commerce/sources/nextcloud:primary/browse",
        headers=auth_headers,
        json={
            "path": "/",
            "settings": {"url": "https://example.com/nextcloud/remote.php/dav/files/woo/"},
            "secrets": {"password": "app-password-secret"},
        },
    )

    assert response.status_code == 200
    assert calls == [{
        "url": "https://example.com/nextcloud",
        "webdav_files_root_url": "https://example.com/nextcloud/remote.php/dav/files/woo/",
        "username": "woo",
        "path": "/",
        "depth": "1",
    }]


def test_nextcloud_webdav_browse_rejects_path_traversal(client, auth_headers, monkeypatch):
    async def fail_propfind(*args, **kwargs):
        raise AssertionError("path traversal must fail before WebDAV")

    monkeypatch.setattr("app.flowhub.integrations.nextcloud.propfind_path", fail_propfind)

    response = client.post(
        "/api/v2/commerce/sources/nextcloud:primary/browse",
        headers=auth_headers,
        json={
            "path": "/Reports/%2e%2e/secrets",
            "settings": {"url": "https://softpple.business", "username": "woo"},
            "secrets": {"password": "app-password-secret"},
        },
    )

    assert response.status_code == 422
    assert "Invalid Nextcloud path" in response.text
    assert "app-password-secret" not in response.text


def test_nextcloud_test_connection_with_root_url_uses_webdav_and_checks_spreadsheet_path(client, auth_headers, monkeypatch):
    calls: list[str] = []

    async def fake_browse(self, path="/"):
        calls.append(f"browse:{path}")
        return {"path": "/", "directories": [], "files": [], "read_only": True, "write_blocked": True}

    async def fake_info(self, path):
        calls.append(f"info:{path}")
        return {"name": "prices.xlsx", "path": path, "type": "file", "extension": ".xlsx", "supported": True}

    monkeypatch.setattr("app.flowhub.integrations.nextcloud.NextcloudClient.browse_directory", fake_browse)
    monkeypatch.setattr("app.flowhub.integrations.nextcloud.NextcloudClient.get_resource_info", fake_info)

    save = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {"url": "https://softpple.business", "username": "woo", "spreadsheet_path": "/prices.xlsx"},
            "secrets": {"password": "app-password-secret"},
        },
    )
    assert save.status_code == 200

    response = client.post("/api/v2/commerce/sources/nextcloud:primary/test", headers=auth_headers, json={})

    assert response.status_code == 200
    assert "app-password-secret" not in response.text
    data = response.json()
    assert data["ok"] is True
    assert data["status"] == "operational"
    assert data["webdav_reachable"] is True
    assert data["spreadsheet_found"] is True
    assert data["normalized_base_url"] == "https://softpple.business"
    assert data["normalized_webdav_url"] == "https://softpple.business/remote.php/dav/files/woo/"
    assert data["message"] == "Connection successful. Spreadsheet found."
    assert data["external_call_performed"] is True
    assert data["read_only"] is True
    assert data["write_blocked"] is True
    assert calls == ["browse:/", "info:/prices.xlsx"]

    detail = client.get("/api/v2/commerce/sources/nextcloud:primary", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["health"]["status"] == "healthy"
    assert detail.json()["last_health_check"]
    assert detail.json()["credential_status"] == "configured"


def test_nextcloud_test_connection_with_webdav_url_succeeds_without_spreadsheet_path(client, auth_headers, monkeypatch):
    calls: list[str] = []

    async def fake_browse(self, path="/"):
        calls.append(f"browse:{path}")
        return {"path": "/", "directories": [], "files": [], "read_only": True, "write_blocked": True}

    async def fail_info(self, path):
        raise AssertionError("empty spreadsheet path must not be checked")

    monkeypatch.setattr("app.flowhub.integrations.nextcloud.NextcloudClient.browse_directory", fake_browse)
    monkeypatch.setattr("app.flowhub.integrations.nextcloud.NextcloudClient.get_resource_info", fail_info)

    save = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {"url": "https://example.com/nextcloud/remote.php/dav/files/woo/"},
            "secrets": {"password": "app-password-secret"},
        },
    )
    assert save.status_code == 200

    response = client.post("/api/v2/commerce/sources/nextcloud:primary/test", headers=auth_headers, json={})

    assert response.status_code == 200
    assert "app-password-secret" not in response.text
    data = response.json()
    assert data["ok"] is True
    assert data["status"] == "operational"
    assert data["webdav_reachable"] is True
    assert data["spreadsheet_found"] is None
    assert data["normalized_base_url"] == "https://example.com/nextcloud"
    assert data["normalized_webdav_url"] == "https://example.com/nextcloud/remote.php/dav/files/woo/"
    assert data["message"] == "Connection successful. Select a spreadsheet file to enable preview."
    assert calls == ["browse:/"]


def test_nextcloud_test_connection_rejects_stored_public_share_url(client, auth_headers, db, monkeypatch):
    from app.flowhub.setup.service import AppConfigService

    async def fail_browse(self, path="/"):
        raise AssertionError("invalid public share URL must fail before WebDAV")

    monkeypatch.setattr("app.flowhub.integrations.nextcloud.NextcloudClient.browse_directory", fail_browse)
    AppConfigService(db).set_many(
        {
            "nextcloud.url": "https://softpple.business/index.php/s/xxxxx",
            "nextcloud.username": "woo",
            "nextcloud.password": "app-password-secret",
        },
        updated_by="test",
    )

    response = client.post("/api/v2/commerce/sources/nextcloud:primary/test", headers=auth_headers, json={})

    assert response.status_code == 200
    assert "app-password-secret" not in response.text
    data = response.json()
    assert data["ok"] is False
    assert data["status"] == "error"
    assert data["webdav_reachable"] is False
    assert data["spreadsheet_found"] is None
    assert data["message"] == "Public share links are not supported. Use the Nextcloud root URL or your personal WebDAV files URL."


def test_nextcloud_test_connection_wrong_credentials_fail_safely(client, auth_headers, monkeypatch):
    from app.flowhub.integrations.errors import IntegrationError

    async def fake_browse(self, path="/"):
        raise IntegrationError("Nextcloud", "/remote.php/dav/files/woo/", "Authentication failed - check username and app password", status_code=401)

    monkeypatch.setattr("app.flowhub.integrations.nextcloud.NextcloudClient.browse_directory", fake_browse)

    save = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {"url": "https://softpple.business", "username": "woo"},
            "secrets": {"password": "wrong-secret"},
        },
    )
    assert save.status_code == 200

    response = client.post("/api/v2/commerce/sources/nextcloud:primary/test", headers=auth_headers, json={})

    assert response.status_code == 200
    assert "wrong-secret" not in response.text
    data = response.json()
    assert data["ok"] is False
    assert data["status"] == "error"
    assert data["webdav_reachable"] is False
    assert data["spreadsheet_found"] is None
    assert data["message"] == "Authentication failed."

    detail = client.get("/api/v2/commerce/sources/nextcloud:primary", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["health"]["status"] == "unhealthy"
    assert detail.json()["health"]["error_code"] == "authentication_failed"


def test_nextcloud_test_connection_missing_spreadsheet_fails_clearly(client, auth_headers, monkeypatch):
    from app.flowhub.integrations.errors import IntegrationError

    async def fake_browse(self, path="/"):
        return {"path": "/", "directories": [], "files": [], "read_only": True, "write_blocked": True}

    async def missing_info(self, path):
        raise IntegrationError("Nextcloud", "/remote.php/dav/files/woo/missing.xlsx", "File not found: /missing.xlsx", status_code=404)

    monkeypatch.setattr("app.flowhub.integrations.nextcloud.NextcloudClient.browse_directory", fake_browse)
    monkeypatch.setattr("app.flowhub.integrations.nextcloud.NextcloudClient.get_resource_info", missing_info)

    save = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {"url": "https://softpple.business", "username": "woo", "spreadsheet_path": "/missing.xlsx"},
            "secrets": {"password": "app-password-secret"},
        },
    )
    assert save.status_code == 200

    response = client.post("/api/v2/commerce/sources/nextcloud:primary/test", headers=auth_headers, json={})

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["status"] == "error"
    assert data["webdav_reachable"] is True
    assert data["spreadsheet_found"] is False
    assert data["message"] == "Spreadsheet not found."


def test_channel_detail_health_and_capabilities(client, auth_headers):
    detail = client.get("/api/v2/commerce/channels/woocommerce:primary", headers=auth_headers)
    health = client.get("/api/v2/commerce/channels/woocommerce:primary/health", headers=auth_headers)
    capabilities = client.get("/api/v2/commerce/channels/woocommerce:primary/capabilities", headers=auth_headers)

    assert detail.status_code == 200
    assert detail.json()["name"] == "WooCommerce"
    assert detail.json()["access_mode"] == "read_only"
    assert detail.json()["read_only"] is True
    assert detail.json()["write_blocked"] is True
    assert detail.json()["write_pipeline_eligible"] is False
    assert health.status_code == 200
    assert health.json()["runtime_write_blocked"] is True
    assert capabilities.status_code == 200
    assert capabilities.json()["capability_authorizes_write"] is False
    assert capabilities.json()["runtime_write_blocked"] is True


def test_woocommerce_access_mode_defaults_read_only_until_owner_enables(client, auth_headers):
    detail = client.get("/api/v2/commerce/channels/woocommerce:primary", headers=auth_headers)

    assert detail.status_code == 200
    assert detail.json()["access_mode"] == "read_only"
    assert detail.json()["read_only"] is True
    assert detail.json()["write_pipeline_eligible"] is False

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

    detail = client.get("/api/v2/commerce/channels/woocommerce:primary", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["access_mode"] == "write_enabled"
    assert detail.json()["read_only"] is False
    assert detail.json()["write_pipeline_eligible"] is True


def test_placeholder_channel_cannot_be_write_enabled(client, auth_headers):
    response = client.put(
        "/api/v2/commerce/channels/snappshop:main/settings",
        headers=auth_headers,
        json={"access_mode": "write_enabled"},
    )

    assert response.status_code == 403
    assert "channel_write_access_unsupported" in response.text


def test_channel_settings_preserve_credential_masking(client, auth_headers):
    response = client.put(
        "/api/v2/commerce/channels/snappshop:main/settings",
        headers=auth_headers,
        json={
            "settings": {"merchant_id": "merchant-1"},
            "secrets": {"api_key": "snapp-secret-value"},
        },
    )

    assert response.status_code == 200
    assert "snapp-secret-value" not in response.text
    data = response.json()
    assert data["read_only"] is True
    assert data["access_mode"] == "read_only"
    assert data["write_pipeline_eligible"] is False
    assert data["runtime_write_blocked"] is True
    assert data["secrets"]["api_key"]["status"] == "configured"

    detail = client.get("/api/v2/commerce/channels/snappshop:main", headers=auth_headers)
    assert detail.status_code == 200
    assert "snapp-secret-value" not in detail.text
    assert detail.json()["credential_status"] == "configured"


def test_source_settings_preserve_credential_masking(client, auth_headers):
    response = client.put(
        "/api/v2/commerce/sources/erp:api-import/settings",
        headers=auth_headers,
        json={
            "display_name": "ERP Import",
            "enabled": True,
            "settings": {"base_url": "https://erp.example.test"},
            "secrets": {"api_token": "erp-secret-value"},
        },
    )

    assert response.status_code == 200
    assert "erp-secret-value" not in response.text
    data = response.json()
    assert data["read_only"] is True
    assert data["runtime_write_blocked"] is True
    assert data["secrets"]["api_token"]["status"] == "configured"

    detail = client.get("/api/v2/commerce/sources/erp:api-import", headers=auth_headers)
    assert detail.status_code == 200
    assert "erp-secret-value" not in detail.text
    assert detail.json()["credential_status"] == "configured"


def test_commerce_routes_do_not_expose_write_execution(client):
    paths = [route.path.lower() for route in client.app.routes if hasattr(route, "path")]
    commerce_paths = " ".join(path for path in paths if "/api/v2/commerce" in path)
    assert "apply" not in commerce_paths
    assert "scheduler" not in commerce_paths
    assert "pricing" not in commerce_paths
    assert "write" not in commerce_paths
