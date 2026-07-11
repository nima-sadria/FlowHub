from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Barrier

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
    assert by_name["Snapp Shop"]["placeholder"] is False
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
    assert channel_types["snappshop"]["implemented"] is True
    assert channel_types["snappshop"]["placeholder"] is False
    assert channel_types["snappshop"]["read_only"] is True
    assert channel_types["snappshop"]["write_blocked"] is True
    for provider in ("tapsishop", "digikala", "technolife", "shopify"):
        assert channel_types[provider]["placeholder"] is True
        assert channel_types[provider]["read_only"] is True
        assert channel_types[provider]["write_blocked"] is True


def test_snapp_registry_is_implemented_and_tapsi_placeholder_is_read_only():
    from app.flowhub.integration_platform.registry import registry

    snapp = registry.get_definition("snappshop")
    assert snapp is not None
    assert snapp.connector.identity.read_only is True
    assert snapp.connector.capabilities.read_products is True
    assert snapp.connector.capabilities.read_orders is True
    assert snapp.connector.capabilities.write_prices is True
    assert snapp.connector.capabilities.write_inventory is True

    tapsi = registry.get_definition("tapsishop")
    assert tapsi is not None
    assert tapsi.connector.identity.read_only is True
    assert tapsi.connector.capabilities.read_products is True
    assert tapsi.connector.capabilities.write_prices is False
    assert tapsi.connector.capabilities.write_inventory is False


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


def test_snappshop_connection_test_performs_vendor_probe_without_secret_leakage(client, auth_headers, monkeypatch):
    request_calls: list[dict] = []

    class FakeResponse:
        status_code = 200
        headers = {}

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class FakeAsyncClient:
        responses = [
            FakeResponse({"status": True, "data": [{"id": "vendor-1", "title": "Vendor"}]}),
            FakeResponse({"status": True, "data": {"id": "vendor-1", "title": "Vendor"}}),
        ]

        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def request(self, method, url, *, headers=None, params=None, json=None):
            request_calls.append({"method": method, "url": url, "headers": headers, "params": params, "json": json})
            return self.responses.pop(0)

    monkeypatch.setattr("app.flowhub.channels.snappshop.httpx.AsyncClient", FakeAsyncClient)

    save = client.put(
        "/api/v2/commerce/channels/snappshop:main/settings",
        headers=auth_headers,
        json={
            "display_name": "Snapp Shop",
            "enabled": True,
            "settings": {
                "base_url": "https://apix.snappshop.ir/automation/v1",
                "agent_identifier": "flowhub-agent",
                "agent_header_name": "User-Agent",
                "vendor_id": "vendor-1",
            },
            "secrets": {"token": "snapp-secret-value"},
        },
    )
    assert save.status_code == 200
    assert "snapp-secret-value" not in save.text

    response = client.post("/api/v2/commerce/channels/snappshop:main/test", headers=auth_headers, json={})

    assert response.status_code == 200
    assert "snapp-secret-value" not in response.text
    data = response.json()
    assert data["ok"] is True
    assert data["connected"] is True
    assert data["authenticated"] is True
    assert data["external_call_performed"] is True
    assert data["read_only"] is True
    assert data["runtime_write_blocked"] is True
    assert request_calls[0]["url"] == "https://apix.snappshop.ir/automation/v1/vendors"
    assert request_calls[0]["headers"]["Authorization"] == "Bearer snapp-secret-value"
    assert request_calls[0]["headers"]["User-Agent"] == "flowhub-agent"
    assert request_calls[1]["url"] == "https://apix.snappshop.ir/automation/v1/vendors/vendor-1"


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

    response = client.post("/api/v2/commerce/channels/tapsishop:main/test", headers=auth_headers, json={})

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


@pytest.mark.parametrize(
    "url",
    [
        "https://user@nextcloud.example.test",
        "https://user:password@nextcloud.example.test",
        "https://user%40example.test:token@nextcloud.example.test/remote.php/dav/files/user",
    ],
)
def test_nextcloud_source_rejects_credential_bearing_urls_without_exposure(client, auth_headers, caplog, url):
    response = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "settings": {"url": url, "username": "user", "spreadsheet_path": "/prices.xlsx"},
            "secrets": {"password": "separate-app-password"},
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "code": "CREDENTIALS_IN_URL_NOT_ALLOWED",
        "message": "Credentials must not be embedded in the Nextcloud URL. Use the separate username and app-password fields.",
    }
    assert url not in response.text
    assert "separate-app-password" not in response.text
    assert url not in caplog.text
    assert "separate-app-password" not in caplog.text


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


def test_nextcloud_test_connection_rejects_stored_credential_url_before_webdav(client, auth_headers, db, monkeypatch):
    from app.flowhub.setup.service import AppConfigService

    async def fail_browse(self, path="/"):
        raise AssertionError("credential-bearing URL must fail before WebDAV")

    monkeypatch.setattr("app.flowhub.integrations.nextcloud.NextcloudClient.browse_directory", fail_browse)
    unsafe_url = "https://woo:embedded-secret@softpple.business"
    AppConfigService(db).set_many(
        {
            "nextcloud.url": unsafe_url,
            "nextcloud.username": "woo",
            "nextcloud.password": "separate-app-password",
        },
        updated_by="test",
    )

    response = client.post("/api/v2/commerce/sources/nextcloud:primary/test", headers=auth_headers, json={})

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["code"] == "CREDENTIALS_IN_URL_NOT_ALLOWED"
    assert data["external_call_performed"] is False
    assert data["normalized_base_url"] == ""
    assert data["normalized_webdav_url"] == ""
    assert unsafe_url not in response.text
    assert "embedded-secret" not in response.text


def test_nextcloud_read_rejects_legacy_credential_url_before_download(client, auth_headers, db, monkeypatch):
    from app.flowhub.setup.service import AppConfigService

    async def fail_download(self, path):
        raise AssertionError("credential-bearing URL must fail before source download")

    monkeypatch.setattr("app.flowhub.integrations.nextcloud.NextcloudClient.download_file", fail_download)
    save = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {
                "url": "https://softpple.business",
                "username": "woo",
                "spreadsheet_path": "/Reports/prices.xlsx",
            },
            "secrets": {"password": "separate-app-password"},
        },
    )
    assert save.status_code == 200
    unsafe_url = "https://woo:embedded-secret@softpple.business"
    AppConfigService(db).set_many({"nextcloud.url": unsafe_url}, updated_by="legacy-test")

    response = client.post("/api/v2/commerce/sources/nextcloud:primary/read", headers=auth_headers, json={})

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "CREDENTIALS_IN_URL_NOT_ALLOWED"
    assert unsafe_url not in response.text
    assert "embedded-secret" not in response.text


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


def test_nextcloud_source_mapping_and_read_policy_are_saved(client, auth_headers, db):
    from app.flowhub.setup.service import AppConfigService

    response = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {
                "url": "https://softpple.business/remote.php/dav/files/woo/",
                "spreadsheet_path": "/Reports/prices.xlsx",
                "source_mapping": {
                    "id": {"enabled": True, "column": "E"},
                    "price": {"enabled": True, "column": "D"},
                    "stock": {"enabled": True, "column": "B"},
                },
                "source_read_policy": {
                    "enabled": True,
                    "max_reads_per_24h": 7,
                    "manual_read_allowed": True,
                },
                "worksheet_mode": "selected",
                "worksheet_name": "Prices",
            },
            "secrets": {"password": "app-password-secret"},
        },
    )

    assert response.status_code == 200
    assert "app-password-secret" not in response.text
    cfg = AppConfigService(db)
    assert cfg.get("nextcloud.url") == "https://softpple.business"
    assert cfg.get("nextcloud.username") == "woo"
    assert '"column": "E"' in cfg.get("nextcloud.source_mapping")
    assert '"max_reads_per_24h": 7' in cfg.get("nextcloud.source_read_policy")
    assert cfg.get("nextcloud.worksheet_mode") == "selected"
    assert cfg.get("nextcloud.worksheet_name") == "Prices"

    detail = client.get("/api/v2/commerce/sources/nextcloud:primary", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["read_policy"]["max_reads_per_24h"] == 7


@pytest.mark.parametrize(
    "settings,message",
    [
        (
            {"source_mapping": {"id": {"enabled": True, "column": ""}}},
            "id column is required when enabled.",
        ),
        (
            {
                "source_mapping": {
                    "id": {"enabled": True, "column": "B"},
                    "price": {"enabled": True, "column": "B"},
                    "stock": {"enabled": False, "column": "D"},
                }
            },
            "Duplicate enabled source mapping column",
        ),
        (
            {"worksheet_mode": "selected", "worksheet_name": ""},
            "worksheet_name is required",
        ),
    ],
)
def test_nextcloud_source_mapping_validation_rejects_invalid_settings(client, auth_headers, settings, message):
    response = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {"url": "https://softpple.business", "username": "woo", **settings},
            "secrets": {"password": "app-password-secret"},
        },
    )

    assert response.status_code == 422
    assert message in response.text
    assert "app-password-secret" not in response.text


def test_nextcloud_manual_read_now_uses_mapping_and_never_writes(client, auth_headers, monkeypatch):
    from app.connectors.destinations.woocommerce.write_adapter import WooCommercePriceWriteAdapter
    from app.flowhub.integrations.nextcloud import NextcloudClient

    async def fake_download(self, path):
        assert path == "/Reports/prices.xlsx"
        return _xlsx_custom(
            headers=["Name", "Stock", "SKU", "Price", "Product ID"],
            rows=[["Mapped Product", "12", "SKU-101", "125.00", "101"]],
        ), {"etag": "etag-read"}

    async def fail_write(*args, **kwargs):
        raise AssertionError("Manual source read must not write to WooCommerce")

    monkeypatch.setattr(NextcloudClient, "download_file", fake_download)
    monkeypatch.setattr(WooCommercePriceWriteAdapter, "execute_item", fail_write)

    save = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {
                "url": "https://softpple.business",
                "username": "woo",
                "spreadsheet_path": "/Reports/prices.xlsx",
                "source_mapping": {
                    "id": {"enabled": True, "column": "E"},
                    "price": {"enabled": True, "column": "D"},
                    "stock": {"enabled": True, "column": "B"},
                },
            },
            "secrets": {"password": "app-password-secret"},
        },
    )
    assert save.status_code == 200

    response = client.post("/api/v2/commerce/sources/nextcloud:primary/read", headers=auth_headers, json={})

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["rows_read"] == 1
    assert data["valid_rows"] == 1
    assert data["external_call_performed"] is True
    assert data["source_write"] is False
    assert data["write_blocked"] is True
    assert data["reads_remaining"] == 9


def test_nextcloud_source_read_rate_limit_is_enforced(client, auth_headers, monkeypatch):
    from app.flowhub.integrations.nextcloud import NextcloudClient

    async def fake_download(self, path):
        return _xlsx_custom(
            headers=["Name", "Product ID", "Price", "SKU"],
            rows=[["Limited Product", "101", "125.00", "SKU-101"]],
        ), {"etag": "etag-limit"}

    monkeypatch.setattr(NextcloudClient, "download_file", fake_download)
    save = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {
                "url": "https://softpple.business",
                "username": "woo",
                "spreadsheet_path": "/Reports/prices.xlsx",
                "source_read_policy": {
                    "enabled": True,
                    "max_reads_per_24h": 1,
                    "manual_read_allowed": True,
                },
            },
            "secrets": {"password": "app-password-secret"},
        },
    )
    assert save.status_code == 200

    first = client.post("/api/v2/commerce/sources/nextcloud:primary/read", headers=auth_headers, json={})
    second = client.post("/api/v2/commerce/sources/nextcloud:primary/read", headers=auth_headers, json={})

    assert first.status_code == 200
    assert first.json()["reads_remaining"] == 0
    assert second.status_code == 429
    assert "Source read limit exceeded" in second.text


def test_failed_outbound_source_read_consumes_reserved_quota(client, auth_headers, db, monkeypatch):
    from app.flowhub.data_layer.models import DlSourceReadReservation
    from app.flowhub.integration_platform.models import IntegrationConnectorEvent
    from app.flowhub.integrations.errors import IntegrationError
    from app.flowhub.integrations.nextcloud import NextcloudClient

    async def fail_download(self, path):
        raise IntegrationError("nextcloud", path, "WebDAV unavailable", status_code=502)

    monkeypatch.setattr(NextcloudClient, "download_file", fail_download)
    save = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {
                "url": "https://softpple.business",
                "username": "woo",
                "spreadsheet_path": "/Reports/prices.xlsx",
                "source_read_policy": {"enabled": True, "max_reads_per_24h": 1, "manual_read_allowed": True},
            },
            "secrets": {"password": "app-password-secret"},
        },
    )
    assert save.status_code == 200

    failed = client.post("/api/v2/commerce/sources/nextcloud:primary/read", headers=auth_headers)
    limited = client.post("/api/v2/commerce/sources/nextcloud:primary/read", headers=auth_headers)

    assert failed.status_code == 502
    assert limited.status_code == 429
    reservations = db.query(DlSourceReadReservation).all()
    assert len(reservations) == 1
    assert reservations[0].status == "failed"
    events = {
        row.event_name: row
        for row in db.query(IntegrationConnectorEvent)
        .filter(IntegrationConnectorEvent.event_name.in_({"source_read_reserved", "source_read_reservation_finalized"}))
        .all()
    }
    assert events["source_read_reserved"].metadata_json["reservation_status"] == "reserved"
    assert events["source_read_reservation_finalized"].metadata_json["reservation_status"] == "failed"


def test_concurrent_source_reads_cannot_exceed_atomic_quota(tmp_path):
    from fastapi import HTTPException
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.flowhub.database import FlowHubBase
    from app.flowhub.setup.service import AppConfigService
    from app.flowhub.sources.spreadsheet_source import SpreadsheetSourceReadService
    from app.flowhub.data_layer.models import DlSourceReadReservation

    engine = create_engine(
        f"sqlite:///{tmp_path / 'source-quota.db'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    FlowHubBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    setup_session = Session()
    AppConfigService(setup_session).set_many(
        {"nextcloud.source_read_policy": '{"enabled":true,"max_reads_per_24h":1,"manual_read_allowed":true}'},
        updated_by="test",
    )
    setup_session.close()
    barrier = Barrier(2)

    def reserve(actor: str) -> int:
        session = Session()
        try:
            barrier.wait()
            SpreadsheetSourceReadService(session).reserve_read_slot(actor, manual=True)
            return 200
        except HTTPException as exc:
            return exc.status_code
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = sorted(executor.map(reserve, ["admin-a", "admin-b"]))

    check_session = Session()
    assert results == [200, 429]
    assert check_session.query(DlSourceReadReservation).count() == 1
    check_session.close()
    engine.dispose()


def test_duplicate_rows_are_errors_and_manual_read_counts_reconcile(client, auth_headers, monkeypatch):
    from app.flowhub.integrations.nextcloud import NextcloudClient

    async def fake_download(self, path):
        return _xlsx_custom(
            headers=["Name", "Product ID", "Price", "SKU"],
            rows=[
                ["A", "101", "110", "DUP-SKU"],
                ["B", "101", "111", "SKU-B"],
                ["C", "102", "112", "DUP-SKU"],
                ["D", "103", "bad", "SKU-D"],
                ["E", "104", "114", "SKU-E"],
            ],
        ), {"etag": "etag-duplicates"}

    monkeypatch.setattr(NextcloudClient, "download_file", fake_download)
    save = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {
                "url": "https://softpple.business",
                "username": "woo",
                "spreadsheet_path": "/Reports/prices.xlsx",
            },
            "secrets": {"password": "app-password-secret"},
        },
    )
    assert save.status_code == 200

    response = client.post("/api/v2/commerce/sources/nextcloud:primary/read", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["rows_read"] == 5
    assert data["valid_rows"] == 1
    assert data["warning_rows"] == 0
    assert data["error_rows"] == 4
    assert data["duplicate_rows"] == 3
    assert data["valid_rows"] + data["warning_rows"] + data["error_rows"] == data["rows_read"]


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


def test_woocommerce_cache_refresh_populates_variations_and_upserts_without_writes(
    client, auth_headers, db, monkeypatch
):
    from app.flowhub.data_layer.models import DlProductCache

    _configure_woocommerce_channel(client, auth_headers)
    catalog_price = {"simple": "10.00"}
    write_calls: list[tuple] = []

    async def fake_list_products(_creds, *, page, per_page, **_kwargs):
        assert per_page == 100
        assert page == 1
        return [
            {
                "id": 101,
                "name": "Simple product",
                "type": "simple",
                "sku": "SIMPLE-101",
                "regular_price": catalog_price["simple"],
                "sale_price": "",
                "price": catalog_price["simple"],
                "stock_quantity": 5,
                "stock_status": "instock",
                "manage_stock": True,
                "backorders": "no",
                "categories": [{"id": 7, "name": "Catalog"}],
                "images": [{"src": "https://store.example.test/simple.jpg"}],
                "status": "publish",
                "date_modified_gmt": "2026-07-10T08:00:00",
            },
            {
                "id": 200,
                "name": "Variable parent",
                "type": "variable",
                "sku": "PARENT-200",
                "regular_price": "",
                "sale_price": "",
                "price": "",
                "stock_quantity": None,
                "stock_status": "instock",
                "manage_stock": False,
                "backorders": "no",
                "categories": [{"id": 8, "name": "Variable"}],
                "images": [{"src": "https://store.example.test/parent.jpg"}],
                "status": "publish",
                "date_modified_gmt": "2026-07-10T08:00:00",
            },
        ], 2, 1

    async def fake_list_variations(_creds, product_id, *, page, per_page):
        assert product_id == 200
        assert page == 1
        assert per_page == 100
        return [{
            "id": 201,
            "sku": "VAR-201",
            "regular_price": "20.00",
            "sale_price": "18.00",
            "price": "18.00",
            "stock_quantity": 3,
            "stock_status": "instock",
            "manage_stock": True,
            "backorders": "no",
            "attributes": [{"name": "Color", "option": "Blue"}],
            "image": {"src": "https://store.example.test/variation.jpg"},
            "status": "publish",
            "date_modified_gmt": "2026-07-10T08:05:00",
        }]

    async def fail_if_write_called(*args, **kwargs):
        write_calls.append((args, kwargs))
        raise AssertionError("WooCommerce writes are forbidden during cache refresh")

    monkeypatch.setattr("app.connectors.read.woocommerce.list_products_paged", fake_list_products)
    monkeypatch.setattr("app.connectors.read.woocommerce.list_variations", fake_list_variations)
    monkeypatch.setattr("app.connectors.destinations.woocommerce.rest_client._put", fail_if_write_called)

    first = client.post(
        "/api/v2/commerce/channels/woocommerce:primary/refresh-cache",
        headers=auth_headers,
    )

    assert first.status_code == 200
    assert first.json() == {
        **first.json(),
        "ok": True,
        "status": "completed",
        "products_read": 2,
        "variable_products_read": 1,
        "variations_read": 1,
        "cache_rows_upserted": 3,
        "warnings": [],
        "errors": [],
        "read_only": True,
        "external_write": False,
        "stock_write": False,
        "source_write": False,
        "dry_run_created": False,
        "approval_created": False,
        "apply_executed": False,
        "credentials_returned": False,
    }
    rows = db.query(DlProductCache).order_by(DlProductCache.product_id).all()
    assert [row.product_id for row in rows] == ["101", "200", "201"]
    simple, parent, variation = rows
    assert simple.product_type == "simple"
    assert simple.regular_price == "10.00"
    assert simple.stock_qty == 5
    assert simple.categories == [{"id": 7, "name": "Catalog"}]
    assert simple.images == [{"src": "https://store.example.test/simple.jpg"}]
    assert simple.channel_id == "woocommerce:primary"
    assert parent.product_type == "variable"
    assert variation.product_type == "variation"
    assert variation.parent_id == "200"
    assert variation.sku == "VAR-201"
    assert variation.regular_price == "20.00"
    assert variation.sale_price == "18.00"
    assert variation.price == "18.00"
    assert variation.raw_data["attributes"] == [{"name": "Color", "option": "Blue"}]
    assert variation.last_successful_read is not None
    assert write_calls == []

    catalog_price["simple"] = "12.50"
    second = client.post(
        "/api/v2/commerce/channels/woocommerce:primary/refresh-cache",
        headers=auth_headers,
    )

    assert second.status_code == 200
    assert second.json()["cache_rows_upserted"] == 3
    assert db.query(DlProductCache).count() == 3
    db.expire_all()
    updated = db.query(DlProductCache).filter_by(product_id="101").one()
    assert updated.regular_price == "12.50"
    assert updated.price == "12.50"
    assert write_calls == []

    channels = client.get("/api/v2/commerce/channels", headers=auth_headers).json()["items"]
    woo = next(item for item in channels if item["id"] == "woocommerce:primary")
    assert woo["cached_products"] == 2
    assert woo["cached_variations"] == 1
    assert woo["cache_refresh_status"] == "completed"
    assert woo["last_cache_refresh"]


def test_woocommerce_cache_refresh_reports_partial_page_failure_safely(
    client, auth_headers, db, monkeypatch
):
    from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
    from app.flowhub.data_layer.models import DlProductCache

    _configure_woocommerce_channel(client, auth_headers)

    async def fake_list_products(_creds, *, page, **_kwargs):
        if page == 1:
            return [{
                "id": 101,
                "name": "First page product",
                "type": "simple",
                "regular_price": "10.00",
                "price": "10.00",
            }], 2, 2
        raise ConnectorError(
            code=ConnectorErrorCode.AUTH_FAILED,
            message="Authentication failed for key=ck_live_secret secret=cs_live_secret",
            provider="woocommerce",
            http_status=401,
        )

    monkeypatch.setattr("app.connectors.read.woocommerce.list_products_paged", fake_list_products)

    response = client.post(
        "/api/v2/commerce/channels/woocommerce:primary/refresh-cache",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["status"] == "partial_failed"
    assert data["products_read"] == 1
    assert data["cache_rows_upserted"] == 1
    assert db.query(DlProductCache).count() == 1
    assert "Authentication failed" in data["errors"][0]
    assert "ck_live_secret" not in response.text
    assert "cs_live_secret" not in response.text
    assert data["credentials_returned"] is False


def test_woocommerce_cache_refresh_blocks_disabled_channels_before_outbound_calls(client, auth_headers, monkeypatch):
    _configure_woocommerce_channel(client, auth_headers)
    outbound_calls = 0

    async def fake_list_products(*_args, **_kwargs):
        nonlocal outbound_calls
        outbound_calls += 1
        raise AssertionError("disabled channel must not perform WooCommerce reads")

    disable = client.put(
        "/api/v2/commerce/channels/woocommerce:primary/settings",
        headers=auth_headers,
        json={"enabled": False},
    )
    assert disable.status_code == 200

    monkeypatch.setattr("app.connectors.read.woocommerce.list_products_paged", fake_list_products)
    response = client.post(
        "/api/v2/commerce/channels/woocommerce:primary/refresh-cache",
        headers=auth_headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "CHANNEL_DISABLED",
        "message": "WooCommerce channel is disabled.",
    }
    assert outbound_calls == 0


def test_woocommerce_cache_refresh_requires_credentials_and_admin(client, auth_headers, db):
    from app.flowhub.auth.jwt_service import create_access_token
    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.auth.password import hash_password

    enable_without_credentials = client.put(
        "/api/v2/commerce/channels/woocommerce:primary/settings",
        headers=auth_headers,
        json={"display_name": "WooCommerce", "enabled": True, "settings": {}},
    )
    assert enable_without_credentials.status_code == 200

    missing = client.post("/api/v2/commerce/channels/woocommerce:primary/refresh-cache", headers=auth_headers)
    assert missing.status_code == 200
    assert missing.json()["ok"] is False
    assert missing.json()["status"] == "failed"
    assert missing.json()["errors"] == ["connector_not_configured"]

    viewer = FlowHubUser(
        username=f"cacheviewer_{uuid.uuid4().hex}",
        hashed_password=hash_password("password123"),
        role="viewer",
    )
    db.add(viewer)
    db.commit()
    db.refresh(viewer)
    viewer_headers = {
        "Authorization": f"Bearer {create_access_token(viewer.id, viewer.username, viewer.role)}"
    }
    forbidden = client.post(
        "/api/v2/commerce/channels/woocommerce:primary/refresh-cache",
        headers=viewer_headers,
    )
    assert forbidden.status_code == 403


def test_woocommerce_variation_fetch_retries_transient_500(monkeypatch):
    import asyncio
    import httpx

    from app.connectors.destinations.woocommerce.auth import WooCommerceCredentials
    from app.connectors.destinations.woocommerce.rest_client import list_variations

    calls = 0
    sleeps: list[float] = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, *, params, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(500, request=httpx.Request("GET", url), json={"message": "retry"})
            return httpx.Response(200, request=httpx.Request("GET", url), json=[{"id": 201}])

    async def fake_sleep(delay: float):
        sleeps.append(delay)

    async def fake_acquire(*_args, **_kwargs):
        return None

    monkeypatch.setattr("app.connectors.destinations.woocommerce.rest_client.httpx.AsyncClient", lambda **_kwargs: FakeClient())
    monkeypatch.setattr("app.connectors.destinations.woocommerce.rest_client.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("app.connectors.destinations.woocommerce.rest_client.acquire_connector_rate_limit", fake_acquire)

    result = asyncio.run(
        list_variations(
            WooCommerceCredentials(url="https://store.example.test", key="ck_test", secret="cs_test"),
            200,
            page=1,
            per_page=100,
        )
    )

    assert result == [{"id": 201}]
    assert calls == 2
    assert sleeps == [1.0]


def test_woocommerce_variation_fetch_retries_429_retry_after(monkeypatch):
    import asyncio
    import httpx

    from app.connectors.destinations.woocommerce.auth import WooCommerceCredentials
    from app.connectors.destinations.woocommerce.rest_client import list_variations

    calls = 0
    sleeps: list[float] = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, *, params, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(
                    429,
                    request=httpx.Request("GET", url),
                    json={"message": "rate limited"},
                    headers={"Retry-After": "7"},
                )
            return httpx.Response(200, request=httpx.Request("GET", url), json=[{"id": 202}])

    async def fake_sleep(delay: float):
        sleeps.append(delay)

    async def fake_acquire(*_args, **_kwargs):
        return None

    monkeypatch.setattr("app.connectors.destinations.woocommerce.rest_client.httpx.AsyncClient", lambda **_kwargs: FakeClient())
    monkeypatch.setattr("app.connectors.destinations.woocommerce.rest_client.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("app.connectors.destinations.woocommerce.rest_client.acquire_connector_rate_limit", fake_acquire)

    result = asyncio.run(
        list_variations(
            WooCommerceCredentials(url="https://store.example.test", key="ck_test", secret="cs_test"),
            200,
            page=1,
            per_page=100,
        )
    )

    assert result == [{"id": 202}]
    assert calls == 2
    assert sleeps == [7.0]


def test_woocommerce_cache_refresh_reports_variation_failure_safely(client, auth_headers, db, monkeypatch):
    from app.connectors.common.errors import ConnectorError, ConnectorErrorCode

    _configure_woocommerce_channel(client, auth_headers)

    async def fake_list_products(_creds, *, page, per_page, **_kwargs):
        assert page == 1
        assert per_page == 100
        return [
            {
                "id": 200,
                "name": "Variable parent",
                "type": "variable",
                "sku": "PARENT-200",
                "regular_price": "",
                "sale_price": "",
                "price": "",
                "stock_quantity": None,
                "stock_status": "instock",
                "manage_stock": False,
                "backorders": "no",
                "categories": [],
                "images": [],
                "status": "publish",
                "date_modified_gmt": "2026-07-10T08:00:00",
            },
        ], 1, 1

    async def fake_list_variations(_creds, product_id, *, page, per_page):
        raise ConnectorError(
            code=ConnectorErrorCode.PROVIDER_ERROR,
            message="Variation fetch failed for key=ck_live_secret secret=cs_live_secret",
            provider="woocommerce",
            http_status=500,
        )

    monkeypatch.setattr("app.connectors.read.woocommerce.list_products_paged", fake_list_products)
    monkeypatch.setattr("app.connectors.read.woocommerce.list_variations", fake_list_variations)

    response = client.post(
        "/api/v2/commerce/channels/woocommerce:primary/refresh-cache",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["status"] == "failed"
    assert data["products_read"] == 1
    assert data["cache_rows_upserted"] == 0
    assert data["errors"] == ["The external service returned an invalid or unavailable response."]
    assert "ck_live_secret" not in response.text
    assert "cs_live_secret" not in response.text


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


def test_non_woocommerce_channel_cannot_be_write_enabled(client, auth_headers):
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
            "settings": {"agent_identifier": "flowhub-agent", "vendor_id": "vendor-1"},
            "secrets": {"token": "snapp-secret-value"},
        },
    )

    assert response.status_code == 200
    assert "snapp-secret-value" not in response.text
    data = response.json()
    assert data["read_only"] is True
    assert data["access_mode"] == "read_only"
    assert data["write_pipeline_eligible"] is False
    assert data["runtime_write_blocked"] is True
    assert data["secrets"]["token"]["status"] == "configured"

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


def _xlsx_custom(headers: list[str], rows: list[list[object]]) -> bytes:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(headers)
    ws.append(["" for _ in headers])
    for row in rows:
        ws.append(row)
    stream = BytesIO()
    wb.save(stream)
    return stream.getvalue()


def test_nextcloud_browse_html_error_returns_safe_structured_payload(client, auth_headers, monkeypatch):
    from app.flowhub.integrations.errors import IntegrationError

    async def fail_browse(self, path="/"):
        raise IntegrationError(
            "nextcloud",
            "/remote.php/dav/files/woo/",
            "<!DOCTYPE html><html><body>proxy error password=app-password-secret</body></html>",
            status_code=502,
        )

    monkeypatch.setattr("app.flowhub.integrations.nextcloud.NextcloudClient.browse_directory", fail_browse)
    response = client.post(
        "/api/v2/commerce/sources/nextcloud:primary/browse",
        headers=auth_headers,
        json={
            "path": "/",
            "settings": {"url": "https://nextcloud.example.test", "username": "woo"},
            "secrets": {"password": "app-password-secret"},
        },
    )

    assert response.status_code == 502
    assert response.json() == {
        "code": "SOURCE_UPSTREAM_ERROR",
        "message": "The external service returned an invalid or unavailable response.",
        "source": "nextcloud",
        "http_status": 502,
    }
    assert "<html" not in response.text.lower()
    assert "app-password-secret" not in response.text


def test_nextcloud_source_read_html_error_returns_safe_structured_payload(client, auth_headers, monkeypatch):
    from app.flowhub.integrations.errors import IntegrationError
    from app.flowhub.integrations.nextcloud import NextcloudClient

    async def fail_download(self, path):
        raise IntegrationError(
            "nextcloud",
            path,
            "<html><body>gateway timeout token=private-token</body></html>",
            status_code=504,
        )

    monkeypatch.setattr(NextcloudClient, "download_file", fail_download)
    save = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {"url": "https://nextcloud.example.test", "username": "woo", "spreadsheet_path": "/Prices.xlsx"},
            "secrets": {"password": "app-password-secret"},
        },
    )
    assert save.status_code == 200

    response = client.post("/api/v2/commerce/sources/nextcloud:primary/read", headers=auth_headers)

    assert response.status_code == 504
    assert response.json()["code"] == "SOURCE_UPSTREAM_ERROR"
    assert response.json()["message"] == "The external service returned an invalid or unavailable response."
    assert "<html" not in response.text.lower()
    assert "private-token" not in response.text


def test_woocommerce_cache_refresh_html_error_returns_safe_result(client, auth_headers, monkeypatch):
    from app.connectors.common.errors import ConnectorError, ConnectorErrorCode

    _configure_woocommerce_channel(client, auth_headers)

    async def fail_list_products(*_args, **_kwargs):
        raise ConnectorError(
            code=ConnectorErrorCode.PROVIDER_ERROR,
            message="<!DOCTYPE html><html><body>upstream secret=cs_live_secret</body></html>",
            provider="woocommerce",
            http_status=503,
        )

    monkeypatch.setattr("app.connectors.read.woocommerce.list_products_paged", fail_list_products)
    response = client.post("/api/v2/commerce/channels/woocommerce:primary/refresh-cache", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["error"]["code"] == "CHANNEL_UPSTREAM_ERROR"
    assert data["error"]["message"] == "The external service returned an invalid or unavailable response."
    assert "<html" not in response.text.lower()
    assert "cs_live_secret" not in response.text


def _configure_woocommerce_channel(client, auth_headers) -> None:
    response = client.put(
        "/api/v2/commerce/channels/woocommerce:primary/settings",
        headers=auth_headers,
        json={
            "display_name": "WooCommerce",
            "enabled": True,
            "settings": {"url": "https://store.example.test"},
            "secrets": {"key": "ck_live_secret", "secret": "cs_live_secret"},
        },
    )
    assert response.status_code == 200
    assert "ck_live_secret" not in response.text
    assert "cs_live_secret" not in response.text
