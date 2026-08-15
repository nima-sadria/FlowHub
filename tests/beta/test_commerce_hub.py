from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from io import BytesIO
from threading import Barrier

import pytest

from tests.beta_source_http import install_nextcloud_download

os.environ.setdefault("FLOWHUB_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FLOWHUB_JWT_SECRET", "test-commerce-hub-jwt-secret-32bytes!")

from app.flowhub.auth import models as _auth_models  # noqa: F401
from app.flowhub.data_layer import models as _data_layer_models  # noqa: F401
from app.flowhub.integration_platform import models as _integration_platform_models  # noqa: F401
from app.flowhub.setup import models as _setup_models  # noqa: F401
from app.flowhub.source_acquisition import models as _source_acquisition_models  # noqa: F401
from app.flowhub.source_workspace import models as _source_workspace_models  # noqa: F401
from app.flowhub.unified_workspace import models as _unified_workspace_models  # noqa: F401
from app.flowhub.pricing_matrix import models as _pricing_matrix_models  # noqa: F401


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

    by_provider = {item["provider"]: item for item in data["items"]}
    assert by_provider["woocommerce"]["type"] == "Channel"
    assert by_provider["woocommerce"]["read_only"] is True
    assert by_provider["woocommerce"]["access_mode"] == "read_only"
    assert by_provider["woocommerce"]["write_pipeline_eligible"] is False
    assert by_provider["snappshop"]["placeholder"] is False
    assert by_provider["snappshop"]["write_blocked"] is True
    assert by_provider["tapsishop"]["placeholder"] is False
    assert by_provider["tapsishop"]["write_blocked"] is True


def test_commerce_sources_do_not_list_marketplace_channels(client, auth_headers):
    response = client.get("/api/v2/commerce/sources", headers=auth_headers)

    assert response.status_code == 200
    names = {item["name"] for item in response.json()["items"]}
    assert {"Nextcloud", "Excel / CSV", "Google Sheets", "ERP / API Import"}.issubset(names)
    assert "Snapp Shop" not in names
    assert "Tapsi Shop" not in names


def test_commerce_type_routes_mark_current_and_future_channels_read_only(client, auth_headers):
    source_response = client.get("/api/v2/commerce/source-types", headers=auth_headers)
    channel_response = client.get("/api/v2/commerce/channel-types", headers=auth_headers)

    assert source_response.status_code == 200
    assert channel_response.status_code == 200

    source_types = {item["provider"]: item for item in source_response.json()["items"]}
    channel_types = {item["provider"]: item for item in channel_response.json()["items"]}

    assert source_types["nextcloud"]["implemented"] is True
    assert source_types["csv"]["implemented"] is True
    assert source_types["csv"]["placeholder"] is False
    assert source_types["csv"]["read_only"] is True
    assert channel_types["woocommerce"]["implemented"] is True
    assert channel_types["snappshop"]["implemented"] is True
    assert channel_types["snappshop"]["placeholder"] is False
    assert channel_types["snappshop"]["read_only"] is True
    assert channel_types["snappshop"]["write_blocked"] is True
    assert channel_types["tapsishop"]["implemented"] is True
    assert channel_types["tapsishop"]["placeholder"] is False
    assert channel_types["tapsishop"]["read_only"] is True
    assert channel_types["tapsishop"]["write_blocked"] is True
    assert channel_types["technolife"]["implemented"] is True
    assert channel_types["technolife"]["placeholder"] is False
    assert channel_types["technolife"]["read_only"] is True
    assert channel_types["technolife"]["write_blocked"] is True
    assert channel_types["digikala"]["implemented"] is True
    assert channel_types["digikala"]["implementation_status"] == "IMPLEMENTED_UNVERIFIED"
    assert channel_types["digikala"]["placeholder"] is True
    assert channel_types["digikala"]["status"] == "coming_soon"
    assert channel_types["digikala"]["availability"] == "coming_soon"
    assert channel_types["digikala"]["operational_available"] is False
    assert channel_types["digikala"]["actionable"] is False
    assert channel_types["digikala"]["settings_available"] is False
    assert not any(channel_types["digikala"]["capabilities"].values())
    assert channel_types["digikala"]["read_only"] is True
    assert channel_types["digikala"]["write_blocked"] is True
    for provider in ("shopify",):
        assert channel_types[provider]["implemented"] is False
        assert channel_types[provider]["placeholder"] is True
        assert channel_types[provider]["read_only"] is True
        assert channel_types[provider]["write_blocked"] is True


def test_marketplace_registries_are_implemented_and_read_only():
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
    assert tapsi.connector.capabilities.read_orders is True
    assert tapsi.connector.capabilities.write_prices is True
    assert tapsi.connector.capabilities.write_inventory is True
    assert tapsi.connector.capabilities.webhook is True

    technolife = registry.get_definition("technolife")
    assert technolife is not None
    assert technolife.connector.identity.read_only is True
    assert technolife.connector.capabilities.read_products is True
    assert technolife.connector.capabilities.read_orders is True
    assert technolife.connector.capabilities.write_prices is True
    assert technolife.connector.capabilities.write_inventory is True
    required_secrets = {
        field.key
        for field in technolife.settings_schema
        if field.required and field.secret
    }
    assert required_secrets == {"api_key", "encryption_secret"}

    digikala = registry.get_definition("digikala")
    assert digikala is not None
    assert digikala.connector.identity.name == "Digikala"
    assert digikala.connector.identity.read_only is True
    assert digikala.connector.capabilities.oauth is True
    assert digikala.connector.capabilities.read_products is False
    assert digikala.connector.capabilities.read_orders is False
    assert digikala.connector.capabilities.write_prices is False
    assert digikala.connector.capabilities.write_inventory is False
    assert {field.key for field in digikala.settings_schema} == {
        "base_url", "request_timeout", "access_token", "refresh_token"
    }
    assert {
        field.key for field in digikala.settings_schema if field.required and field.secret
    } == {"access_token"}


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
    channel_state = client.get(
        "/api/v2/commerce/channels/woocommerce:primary", headers=auth_headers
    ).json()
    assert channel_state["health"]["status"] == "healthy"
    assert channel_state["last_health_check"]
    assert channel_state["credentials_verified"] is True


def test_woocommerce_configuration_rejects_non_absolute_store_url(client, auth_headers):
    response = client.put(
        "/api/v2/commerce/channels/woocommerce:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {"url": "store.example.test"},
            "secrets": {"key": "ck_secret", "secret": "cs_secret"},
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "WooCommerce Store URL must be an absolute HTTP or HTTPS URL."
    assert "ck_secret" not in response.text
    assert "cs_secret" not in response.text


def test_woocommerce_connection_test_maps_legacy_invalid_url_without_external_call(
    client, auth_headers, db, monkeypatch
):
    from app.flowhub.setup.service import AppConfigService

    AppConfigService(db).set_many(
        {
            "woocommerce.url": "store.example.test",
            "woocommerce.key": "ck_legacy_secret",
            "woocommerce.secret": "cs_legacy_secret",
        }
    )

    async def fail_ping(_credentials):
        raise AssertionError("invalid URLs must not reach the external client")

    monkeypatch.setattr("app.flowhub.commerce.service.ping_woocommerce", fail_ping)

    response = client.post(
        "/api/v2/commerce/channels/woocommerce:primary/test",
        headers=auth_headers,
        json={},
    )

    assert response.status_code == 200
    assert "ck_legacy_secret" not in response.text
    assert "cs_legacy_secret" not in response.text
    data = response.json()
    assert data["ok"] is False
    assert data["code"] == "CHANNEL_INVALID_URL"
    assert data["error_class"] == "invalid_url"
    assert data["external_call_performed"] is False
    assert data["message"] == "WooCommerce Store URL must be an absolute HTTP or HTTPS URL."
    channel_state = client.get(
        "/api/v2/commerce/channels/woocommerce:primary", headers=auth_headers
    ).json()
    assert channel_state["health"]["status"] == "unhealthy"
    assert channel_state["health"]["error_code"] == "invalid_url"
    assert channel_state["last_health_check"]


def test_woocommerce_connection_test_maps_httpx_configuration_error_without_500(
    client, auth_headers, monkeypatch
):
    import httpx

    save = client.put(
        "/api/v2/commerce/channels/woocommerce:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {"url": "https://store.example.test"},
            "secrets": {"key": "ck_safe_secret", "secret": "cs_safe_secret"},
        },
    )
    assert save.status_code == 200

    async def fake_acquire(_connector_id, _operation):
        return None

    class FailingAsyncClient:
        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *_args, **_kwargs):
            raise httpx.UnsupportedProtocol("Request URL includes sensitive configuration")

    monkeypatch.setattr(
        "app.connectors.destinations.woocommerce.rest_client.acquire_connector_rate_limit",
        fake_acquire,
    )
    monkeypatch.setattr(
        "app.connectors.destinations.woocommerce.rest_client.httpx.AsyncClient",
        FailingAsyncClient,
    )

    response = client.post(
        "/api/v2/commerce/channels/woocommerce:primary/test",
        headers=auth_headers,
        json={},
    )

    assert response.status_code == 200
    assert "sensitive configuration" not in response.text
    assert "ck_safe_secret" not in response.text
    assert "cs_safe_secret" not in response.text
    data = response.json()
    assert data["ok"] is False
    assert data["code"] == "CHANNEL_UPSTREAM_ERROR"
    assert data["external_call_performed"] is True
    channel_state = client.get(
        "/api/v2/commerce/channels/woocommerce:primary", headers=auth_headers
    ).json()
    assert channel_state["health"]["status"] == "unhealthy"
    assert channel_state["last_health_check"]


def test_snappshop_connection_test_uses_selected_vendor_and_persists_safe_evidence(
    client, auth_headers, db, monkeypatch
):
    from app.flowhub.integration_platform.models import (
        IntegrationConnectorHealthSnapshot,
    )

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
            FakeResponse(
                {
                    "status": True,
                    "data": {
                        "id": "vendor-1",
                        "title": "Vendor",
                        "status": "unexpected_readable_status",
                    },
                }
            ),
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
    assert data["vendor_status"] == "UNEXPECTED_READABLE_STATUS"
    assert data["message"] == (
        "Connection verified. Vendor status reported by SnappShop: "
        "UNEXPECTED_READABLE_STATUS."
    )
    assert request_calls[0]["url"] == (
        "https://apix.snappshop.ir/automation/v1/vendors/vendor-1"
    )
    assert request_calls[0]["headers"]["Authorization"] == "Bearer snapp-secret-value"
    assert request_calls[0]["headers"]["User-Agent"] == "flowhub-agent"
    assert len(request_calls) == 1
    channel_state = client.get(
        "/api/v2/commerce/channels/snappshop:main", headers=auth_headers
    ).json()
    assert channel_state["health"]["status"] == "healthy"
    assert channel_state["last_health_check"]
    assert channel_state["credentials_verified"] is True
    snapshot = (
        db.query(IntegrationConnectorHealthSnapshot)
        .filter_by(connector_id="snappshop:main")
        .order_by(IntegrationConnectorHealthSnapshot.id.desc())
        .first()
    )
    assert snapshot is not None
    assert snapshot.status == "healthy"
    assert snapshot.details_json == {
        "endpoint_class": "selected_vendor",
        "endpoint_path_template": "/vendors/{vendor_id}",
        "http_status": 200,
        "latency_ms": data["latency_ms"],
        "correlation_id": data["correlation_id"],
        "provider_request_attempted": True,
        "provider_status": "UNEXPECTED_READABLE_STATUS",
    }
    persisted = f"{snapshot.message} {snapshot.details_json}"
    assert "snapp-secret-value" not in persisted
    assert "Authorization" not in persisted
    assert "Bearer" not in persisted


@pytest.mark.parametrize(
    ("http_status", "expected_class", "expected_status"),
    [
        (401, "authentication_failed", "authentication_failed"),
        (403, "authorization_failed", "error"),
        (404, "not_found", "error"),
        (503, "upstream_unavailable", "error"),
    ],
)
def test_snappshop_selected_vendor_failures_keep_provider_classification(
    client,
    auth_headers,
    db,
    monkeypatch,
    http_status,
    expected_class,
    expected_status,
):
    from app.flowhub.integration_platform.models import (
        IntegrationConnectorHealthSnapshot,
    )

    saved = client.put(
        "/api/v2/commerce/channels/snappshop:main/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {
                "agent_identifier": "flowhub-agent",
                "vendor_id": "vendor-1",
            },
            "secrets": {"token": "snapp-failure-secret"},
        },
    )
    assert saved.status_code == 200

    class FakeResponse:
        headers = {}

        def __init__(self):
            self.status_code = http_status

        def json(self):
            return {"status": False, "message": "sensitive provider detail"}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def request(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(
        "app.flowhub.channels.snappshop.httpx.AsyncClient", FakeAsyncClient
    )

    response = client.post(
        "/api/v2/commerce/channels/snappshop:main/test",
        headers=auth_headers,
        json={},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["ok"] is False
    assert result["status"] == expected_status
    assert result["error_class"] in {
        expected_class,
        expected_class.removesuffix("_failed"),
    }
    assert result["http_status"] == http_status
    assert "snapp-failure-secret" not in response.text
    snapshot = (
        db.query(IntegrationConnectorHealthSnapshot)
        .filter_by(connector_id="snappshop:main")
        .order_by(IntegrationConnectorHealthSnapshot.id.desc())
        .first()
    )
    assert snapshot is not None
    assert snapshot.status == "unhealthy"
    assert snapshot.details_json["endpoint_path_template"] == "/vendors/{vendor_id}"
    assert snapshot.details_json["http_status"] == http_status
    assert snapshot.details_json["provider_request_attempted"] is True
    assert "snapp-failure-secret" not in str(snapshot.details_json)
    assert "sensitive provider detail" not in snapshot.message


def test_shopify_placeholder_connection_test_does_not_call_external_system(client, auth_headers, monkeypatch):
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

    response = client.post("/api/v2/commerce/channels/shopify:main/test", headers=auth_headers, json={})

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


def test_tapsishop_connection_test_performs_vendor_probe_without_secret_leakage(client, auth_headers, monkeypatch):
    request_calls: list[dict] = []

    class FakeResponse:
        status_code = 200
        headers = {}

        def json(self):
            return {
                "success": True,
                "data": {
                    "vendorId": 42,
                    "vendorName": "Vendor",
                    "storeName": "Store",
                    "storeLink": "https://store.example.test",
                    "storeNumber": "S-42",
                },
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def request(self, method, url, *, headers=None, json=None):
            request_calls.append({"method": method, "url": url, "headers": headers, "json": json})
            return FakeResponse()

    monkeypatch.setattr("app.flowhub.channels.tapsishop.httpx.AsyncClient", FakeAsyncClient)

    save = client.put(
        "/api/v2/commerce/channels/tapsishop:main/settings",
        headers=auth_headers,
        json={
            "display_name": "Tapsi Shop",
            "enabled": True,
            "settings": {
                "base_url": "https://vendorgw.tapsi.shop/Web/Hub/vendors/v1",
                "request_timeout": "10",
                "selected_vendor_id": "42",
                "token_refresh_enabled": "true",
            },
            "secrets": {
                "token": "tapsi-secret-value",
                "webhook_token": "tapsi-webhook-secret",
            },
        },
    )
    assert save.status_code == 200
    assert "tapsi-secret-value" not in save.text
    assert "tapsi-webhook-secret" not in save.text

    response = client.post("/api/v2/commerce/channels/tapsishop:main/test", headers=auth_headers, json={})

    assert response.status_code == 200
    assert "tapsi-secret-value" not in response.text
    assert "tapsi-webhook-secret" not in response.text
    data = response.json()
    assert data["ok"] is True
    assert data["connected"] is True
    assert data["authenticated"] is True
    assert data["external_call_performed"] is True
    assert data["read_only"] is True
    assert data["runtime_write_blocked"] is True
    assert request_calls == [{
        "method": "GET",
            "url": "https://vendorgw.tapsi.shop/Web/Hub/vendors/v1/vendor-information",
                "headers": {
                    "Accept": "text/plain",
                    "Content-Type": "application/json",
                    "TapsiShop.Hub.Authorization": "tapsi-secret-value",
                },
        "json": None,
    }]
    channel_state = client.get(
        "/api/v2/commerce/channels/tapsishop:main", headers=auth_headers
    ).json()
    assert channel_state["health"]["status"] == "healthy"
    assert channel_state["last_health_check"]
    assert channel_state["credentials_verified"] is True


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

    async def fake_preflight(*_args):
        return None

    async def fake_browse(self, path="/"):
        calls.append(f"browse:{path}")
        return {"path": "/", "directories": [], "files": [], "read_only": True, "write_blocked": True}

    async def fake_info(self, path):
        calls.append(f"info:{path}")
        return {"name": "prices.xlsx", "path": path, "type": "file", "extension": ".xlsx", "supported": True}

    monkeypatch.setattr("app.flowhub.integrations.nextcloud.NextcloudClient.browse_directory", fake_browse)
    monkeypatch.setattr("app.flowhub.integrations.nextcloud.NextcloudClient.get_resource_info", fake_info)
    monkeypatch.setattr("app.connectors.common.source_http.SourceHttpClient.preflight", fake_preflight)

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

    response = client.post(
        "/api/v2/commerce/sources/nextcloud:primary/test",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {"url": "https://example.com/nextcloud/remote.php/dav/files/woo/"},
            "secrets": {"password": "app-password-secret"},
        },
    )

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


@pytest.mark.parametrize(
    ("source_error", "expected_code", "expected_message"),
    [
        (
            "unsafe_destination",
            "unsafe_destination",
            "network safety policy",
        ),
        (
            "connect_timeout",
            "timeout",
            "did not respond in time",
        ),
    ],
)
def test_nextcloud_test_connection_reports_acquisition_preflight_failures(
    client,
    auth_headers,
    monkeypatch,
    source_error,
    expected_code,
    expected_message,
):
    from app.connectors.common.source_http import SourceHttpError

    async def fake_browse(self, path="/"):
        return {"path": path, "directories": [], "files": [], "read_only": True, "write_blocked": True}

    async def fake_info(self, path):
        return {"name": "prices.xlsx", "path": path, "type": "file", "extension": ".xlsx", "supported": True}

    async def blocked_preflight(*_args):
        raise SourceHttpError(source_error)

    monkeypatch.setattr("app.flowhub.integrations.nextcloud.NextcloudClient.browse_directory", fake_browse)
    monkeypatch.setattr("app.flowhub.integrations.nextcloud.NextcloudClient.get_resource_info", fake_info)
    monkeypatch.setattr("app.connectors.common.source_http.SourceHttpClient.preflight", blocked_preflight)

    response = client.post(
        "/api/v2/commerce/sources/nextcloud:primary/test",
        headers=auth_headers,
        json={
            "settings": {
                "url": "https://nextcloud.internal",
                "username": "woo",
                "spreadsheet_path": "/prices.xlsx",
            },
            "secrets": {"password": "app-password-secret"},
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["code"] == expected_code
    assert data["webdav_reachable"] is True
    assert data["spreadsheet_found"] is True
    assert expected_message in data["message"]


def test_nextcloud_test_connection_uses_draft_credentials_without_persisting_them(
    client, auth_headers, db, monkeypatch
):
    from app.flowhub.setup.service import AppConfigService

    observed: dict[str, str] = {}

    async def fake_preflight(*_args):
        return None

    async def fake_browse(self, path="/"):
        observed.update(
            url=self._creds.url,
            username=self._creds.username,
            password=self._creds.password,
        )
        return {"path": path, "directories": [], "files": [], "read_only": True, "write_blocked": True}

    async def fake_info(self, path):
        return {"name": "draft.xlsx", "path": path, "type": "file", "extension": ".xlsx", "supported": True}

    monkeypatch.setattr("app.flowhub.integrations.nextcloud.NextcloudClient.browse_directory", fake_browse)
    monkeypatch.setattr("app.flowhub.integrations.nextcloud.NextcloudClient.get_resource_info", fake_info)
    monkeypatch.setattr("app.connectors.common.source_http.SourceHttpClient.preflight", fake_preflight)

    stored = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {
                "url": "https://stored.example.test",
                "username": "stored-user",
                "spreadsheet_path": "/stored.xlsx",
            },
            "secrets": {"password": "stored-password"},
        },
    )
    assert stored.status_code == 200

    response = client.post(
        "/api/v2/commerce/sources/nextcloud:primary/test",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {
                "url": "https://draft.example.test",
                "username": "draft-user",
                "spreadsheet_path": "/draft.xlsx",
            },
            "secrets": {"password": "draft-password"},
        },
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["configuration_matches_saved"] is False
    assert "draft-password" not in response.text
    assert observed == {
        "url": "https://draft.example.test",
        "username": "draft-user",
        "password": "draft-password",
    }
    config = AppConfigService(db)
    assert config.get("nextcloud.url") == "https://stored.example.test"
    assert config.get("nextcloud.username") == "stored-user"
    assert config.get("nextcloud.password") == "stored-password"

    from app.flowhub.data_layer.models import DlConnectorHealth

    assert (
        db.query(DlConnectorHealth)
        .filter(DlConnectorHealth.connector_id == "nextcloud:primary")
        .one_or_none()
        is None
    )

    stored_test = client.post(
        "/api/v2/commerce/sources/nextcloud:primary/test",
        headers=auth_headers,
        json={},
    )
    assert stored_test.status_code == 200
    assert stored_test.json()["ok"] is True
    assert stored_test.json()["configuration_matches_saved"] is True
    health = (
        db.query(DlConnectorHealth)
        .filter(DlConnectorHealth.connector_id == "nextcloud:primary")
        .one()
    )
    assert health.status == "healthy"

    reopened = client.get(
        "/api/v2/commerce/sources/nextcloud:primary/configuration",
        headers=auth_headers,
    )
    assert reopened.status_code == 200
    assert reopened.json()["last_test"]["status"] == "healthy"


def test_disabled_nextcloud_source_does_not_probe_or_claim_healthy(
    client, auth_headers, monkeypatch
):
    """A disabled persisted Source cannot acquire fresh provider evidence."""

    calls = 0

    async def fail_browse(self, path="/"):
        nonlocal calls
        calls += 1
        raise AssertionError("disabled source must not call Nextcloud")

    monkeypatch.setattr(
        "app.flowhub.integrations.nextcloud.NextcloudClient.browse_directory",
        fail_browse,
    )
    saved = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": False,
            "settings": {
                "url": "https://stored.example.test",
                "username": "stored-user",
            },
            "secrets": {"password": "stored-app-password"},
        },
    )
    assert saved.status_code == 200
    assert "stored-app-password" not in saved.text

    tested = client.post(
        "/api/v2/commerce/sources/nextcloud:primary/test",
        headers=auth_headers,
        json={},
    )

    assert tested.status_code == 200
    assert tested.json() | {"correlation_id": "redacted"} == {
        "read_only": True,
        "runtime_write_blocked": True,
        "write_blocked": True,
        "correlation_id": "redacted",
        "ok": False,
        "connected": False,
        "authenticated": False,
        "status": "disabled",
        "code": "SOURCE_DISABLED",
        "error_class": "disabled",
        "http_status": None,
        "latency_ms": None,
        "checked_at": tested.json()["checked_at"],
        "message": "Nextcloud Source is disabled. Enable it before testing the saved connection.",
        "webdav_reachable": False,
        "spreadsheet_found": None,
        "normalized_base_url": "",
        "normalized_webdav_url": "",
        "external_call_performed": False,
        "configuration_matches_saved": True,
    }
    assert calls == 0
    assert "stored-app-password" not in tested.text

    browsed = client.post(
        "/api/v2/commerce/sources/nextcloud:primary/browse",
        headers=auth_headers,
        json={"path": "/"},
    )
    assert browsed.status_code == 409
    assert browsed.json() == {
        "detail": {
            "code": "SOURCE_DISABLED",
            "message": "Nextcloud Source is disabled. Enable it before browsing files.",
        }
    }
    assert calls == 0
    assert "stored-app-password" not in browsed.text

    source = client.get(
        "/api/v2/commerce/sources/nextcloud:primary", headers=auth_headers
    )
    assert source.status_code == 200
    assert source.json()["enabled"] is False
    assert source.json()["status"] == "disabled"
    assert source.json()["health"]["status"] == "unknown"

    configuration = client.get(
        "/api/v2/commerce/sources/nextcloud:primary/configuration",
        headers=auth_headers,
    )
    assert configuration.status_code == 200
    assert configuration.json()["connection_configured"] is True
    assert configuration.json()["enabled"] is False

    reenabled = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {
                "url": "https://stored.example.test",
                "username": "stored-user",
            },
            "secrets": {"password": ""},
        },
    )
    assert reenabled.status_code == 200
    restored = client.get(
        "/api/v2/commerce/sources/nextcloud:primary", headers=auth_headers
    )
    assert restored.status_code == 200
    assert restored.json()["enabled"] is True
    assert restored.json()["status"] != "archived"
    assert calls == 0


def test_archived_nextcloud_lifecycle_is_serialized_and_blocks_all_provider_operations(
    client, auth_headers, db, monkeypatch
):
    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.commerce.service import CommerceHubService
    from app.flowhub.source_workspace.models import SourceProfile

    saved = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {
                "url": "https://stored.example.test",
                "username": "stored-user",
                "spreadsheet_path": "/Prices.xlsx",
            },
            "secrets": {"password": "stored-app-password"},
        },
    )
    assert saved.status_code == 200
    owner = db.query(FlowHubUser).one()
    archived_at = datetime(2026, 8, 13, 8, 30, 0)
    db.add(
        SourceProfile(
            id=str(uuid.uuid4()),
            name="Historical Nextcloud prices",
            source_kind="external",
            external_source_id="nextcloud:primary",
            worksheet_mode="selected",
            worksheet_name="Prices",
            data_start_row=2,
            status="archived",
            archived_at=archived_at,
            version=4,
            owner_user_id=owner.id,
            created_at=archived_at,
            updated_at=archived_at,
        )
    )
    db.commit()

    calls = 0

    async def should_not_call_provider(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("archived Source reached provider I/O")

    monkeypatch.setattr(
        CommerceHubService,
        "_test_nextcloud_source_connection",
        should_not_call_provider,
    )

    listed = client.get("/api/v2/commerce/sources", headers=auth_headers)
    source = next(item for item in listed.json()["items"] if item["id"] == "nextcloud:primary")
    assert source["status"] == "archived"
    assert source["lifecycle_status"] == "archived"
    assert source["archived_at"] == "2026-08-13T08:30:00Z"

    configuration = client.get(
        "/api/v2/commerce/sources/nextcloud:primary/configuration",
        headers=auth_headers,
    )
    assert configuration.status_code == 200
    assert configuration.json()["lifecycle_status"] == "archived"

    for method, path, body in (
        ("post", "/api/v2/commerce/sources/nextcloud:primary/test", {}),
        ("post", "/api/v2/commerce/sources/nextcloud:primary/browse", {"path": "/"}),
        ("post", "/api/v2/commerce/sources/nextcloud:primary/read", {}),
        ("put", "/api/v2/commerce/sources/nextcloud:primary/settings", {"enabled": True}),
    ):
        response = getattr(client, method)(path, headers=auth_headers, json=body)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "SOURCE_ARCHIVED"
    assert calls == 0

    diagnostics = client.get("/api/v2/diagnostics/status", headers=auth_headers)
    assert diagnostics.status_code == 200
    diagnostic_source = next(
        item for item in diagnostics.json()["connectors"]
        if item["id"] == "nextcloud:primary"
    )
    assert diagnostic_source["source_lifecycle_status"] == "archived"
    assert diagnostic_source["source_archived_at"] == "2026-08-13T08:30:00Z"
    assert diagnostics.json()["external_call_performed"] is False


def test_archived_nextcloud_allows_fresh_independent_replacement_source(
    client, auth_headers, db, monkeypatch
):
    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.integration_platform.models import (
        IntegrationConnectorInstance,
        IntegrationConnectorSetting,
    )
    from app.flowhub.integrations.nextcloud import NextcloudClient
    from app.flowhub.setup.service import AppConfigService
    from app.flowhub.sources.spreadsheet_source import SpreadsheetSourceReadService
    from app.flowhub.source_workspace.models import SourceProfile

    legacy = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {
                "url": "https://historical.example.test",
                "username": "historical-user",
                "spreadsheet_path": "/Historical.xlsx",
            },
            "secrets": {"password": "historical-secret"},
        },
    )
    assert legacy.status_code == 200
    owner = db.query(FlowHubUser).one()
    historical = SourceProfile(
        id=str(uuid.uuid4()),
        name="Historical Nextcloud prices",
        source_kind="external",
        external_source_id="nextcloud:primary",
        worksheet_mode="all",
        worksheet_name=None,
        data_start_row=2,
        status="archived",
        archived_at=datetime(2026, 8, 13, 8, 30, 0),
        version=4,
        owner_user_id=owner.id,
    )
    db.add(historical)
    db.commit()

    async def no_provider_io(*_args, **_kwargs):
        raise AssertionError("saving a replacement Source must not call Nextcloud")

    monkeypatch.setattr(NextcloudClient, "browse_directory", no_provider_io)

    # This is the exact legacy Add Source target and remains correctly blocked.
    blocked = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={"enabled": True},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "SOURCE_ARCHIVED"

    replacement = client.post(
        "/api/v2/commerce/sources",
        headers=auth_headers,
        json={
            "source_type_id": "nextcloud:primary",
            "configuration": {
                "display_name": "Current Nextcloud prices",
                "enabled": True,
                "settings": {
                    "url": "https://current.example.test",
                    "username": "current-user",
                    "spreadsheet_path": "/Current.xlsx",
                    "worksheet_mode": "all",
                    "worksheet_name": "",
                },
                "secrets": {"password": "current-secret"},
            },
        },
    )
    assert replacement.status_code == 201
    replacement_id = replacement.json()["source_id"]
    assert replacement_id.startswith("nextcloud:")
    assert replacement_id != "nextcloud:primary"
    assert replacement.json()["credentials_returned"] is False
    assert replacement.json()["external_call_performed"] is False

    profile = client.post(
        "/api/v2/sources",
        headers=auth_headers,
        json={
            "name": "Current Nextcloud prices",
            "source_kind": "external",
            "external_source_id": replacement_id,
            "worksheet_mode": "all",
            "worksheet_name": None,
            "data_start_row": 2,
        },
    )
    assert profile.status_code == 201
    assert profile.json()["externalSourceId"] == replacement_id

    blank_secret_save = client.put(
        f"/api/v2/commerce/sources/{replacement_id}/settings",
        headers=auth_headers,
        json={
            "display_name": "Current Nextcloud prices",
            "enabled": True,
            "settings": {
                "url": "https://current.example.test",
                "username": "current-user",
                "spreadsheet_path": "/Current.xlsx",
                "worksheet_mode": "all",
                "worksheet_name": "",
            },
            "secrets": {},
        },
    )
    assert blank_secret_save.status_code == 200

    exercised: dict[str, str] = {}

    async def successful_browse(nextcloud, _path):
        exercised["url"] = nextcloud._creds.url
        exercised["username"] = nextcloud._creds.username
        exercised["password"] = nextcloud._creds.password
        return {"directories": [], "files": [], "path": "/"}

    async def successful_info(_nextcloud, _path):
        return {"type": "file", "supported": True}

    async def successful_preflight(_http, _url):
        return None

    monkeypatch.setattr(NextcloudClient, "browse_directory", successful_browse)
    monkeypatch.setattr(NextcloudClient, "get_resource_info", successful_info)
    monkeypatch.setattr(
        "app.connectors.common.source_http.SourceHttpClient.preflight",
        successful_preflight,
    )
    tested = client.post(
        f"/api/v2/commerce/sources/{replacement_id}/test",
        headers=auth_headers,
        json={},
    )
    assert tested.status_code == 200
    assert tested.json()["ok"] is True
    assert exercised == {
        "url": "https://current.example.test",
        "username": "current-user",
        "password": "current-secret",
    }

    db.expire_all()
    old_connector = db.get(IntegrationConnectorInstance, "nextcloud:primary")
    new_connector = db.get(IntegrationConnectorInstance, replacement_id)
    assert old_connector is not None and old_connector.enabled is False
    assert new_connector is not None and new_connector.enabled is True
    old_secret = db.query(IntegrationConnectorSetting).filter_by(
        connector_id="nextcloud:primary", key="password"
    ).one()
    new_secret = db.query(IntegrationConnectorSetting).filter_by(
        connector_id=replacement_id, key="password"
    ).one()
    assert old_secret.value_json is None
    assert old_secret.configured is True
    assert new_secret.value_json is None
    assert new_secret.configured is True
    config = AppConfigService(db)
    assert config.get("nextcloud.password") == "historical-secret"
    assert (
        config.get(f"connector_secret.{replacement_id}.password")
        == "current-secret"
    )
    replacement_reader = SpreadsheetSourceReadService(
        db, connector_id=replacement_id
    )
    assert replacement_reader._connector_setting("url") == "https://current.example.test"
    assert replacement_reader._connector_setting("password") == "current-secret"

    listed = client.get("/api/v2/commerce/sources", headers=auth_headers)
    assert listed.status_code == 200
    by_id = {item["id"]: item for item in listed.json()["items"]}
    assert by_id["nextcloud:primary"]["lifecycle_status"] == "archived"
    assert by_id[replacement_id]["lifecycle_status"] == "active"

    duplicate_binding = client.post(
        "/api/v2/sources",
        headers=auth_headers,
        json={
            "name": "Duplicate binding",
            "source_kind": "external",
            "external_source_id": "nextcloud:primary",
            "worksheet_mode": "all",
            "worksheet_name": None,
            "data_start_row": 2,
        },
    )
    assert duplicate_binding.status_code == 409
    assert duplicate_binding.json()["detail"]["code"] == "SOURCE_CONNECTOR_ALREADY_BOUND"
    assert duplicate_binding.json()["detail"]["lifecycle_status"] == "archived"


def test_nextcloud_connection_is_configured_before_later_source_setup_is_complete(
    client, auth_headers
):
    saved = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {
                "url": "https://stored.example.test",
                "username": "stored-user",
            },
            "secrets": {"password": "stored-app-password"},
        },
    )
    assert saved.status_code == 200

    source = client.get(
        "/api/v2/commerce/sources/nextcloud:primary", headers=auth_headers
    )
    assert source.status_code == 200
    data = source.json()
    assert data["enabled"] is True
    assert data["credential_status"] == "configured"
    assert data["status"] == "configured"
    assert data["configuration_state"] == "setup_required"


def test_nextcloud_source_settings_roll_back_connection_changes_when_currency_is_invalid(
    client, auth_headers, db
):
    """A late monetary validation error cannot partially replace Source config."""
    from app.flowhub.integration_platform.models import IntegrationConnectorInstance
    from app.flowhub.setup.service import AppConfigService

    initial = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {
                "url": "https://original.example.test",
                "username": "original-user",
            },
            "secrets": {"password": "original-app-password"},
        },
    )
    assert initial.status_code == 200

    rejected = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": False,
            "settings": {
                "url": "https://replacement.example.test",
                "username": "replacement-user",
            },
            "secrets": {"password": "replacement-app-password"},
            "currency": "IRR",
        },
    )

    assert rejected.status_code == 422
    assert "replacement-app-password" not in rejected.text

    config = AppConfigService(db)
    assert config.get("nextcloud.url") == "https://original.example.test"
    assert config.get("nextcloud.username") == "original-user"
    assert config.get("nextcloud.password") == "original-app-password"
    instance = db.get(IntegrationConnectorInstance, "nextcloud:primary")
    assert instance is not None
    assert instance.enabled is True

    reopened = client.get(
        "/api/v2/commerce/sources/nextcloud:primary/configuration",
        headers=auth_headers,
    )
    assert reopened.status_code == 200
    assert reopened.json()["enabled"] is True
    assert reopened.json()["settings"]["url"] == "https://original.example.test"
    assert reopened.json()["settings"]["username"] == "original-user"
    assert reopened.json()["secrets"]["password"]["status"] == "configured"


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
    assert data["code"] == "PUBLIC_SHARE_NOT_SUPPORTED"
    assert data["error_class"] == "invalid_url"
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
            "settings": {
                "url": "https://softpple.business",
                "username": "woo",
                "spreadsheet_path": "/prices.xlsx",
            },
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


def test_nextcloud_source_settings_allow_credentials_before_spreadsheet_selection(
    client, auth_headers, db
):
    from app.flowhub.setup.service import AppConfigService

    initial = client.get("/api/v2/commerce/sources", headers=auth_headers)
    assert initial.status_code == 200
    initial_source = next(
        item for item in initial.json()["items"] if item["id"] == "nextcloud:primary"
    )
    assert initial_source["connection_configured"] is False
    assert initial_source["configuration_state"] == "not_configured"
    assert initial_source["status"] == "not_configured"
    assert "enabled" not in initial_source

    initial_detail = client.get(
        "/api/v2/commerce/sources/nextcloud:primary", headers=auth_headers
    )
    assert initial_detail.status_code == 200
    assert initial_detail.json()["connection_configured"] is False
    assert initial_detail.json()["configuration_state"] == "not_configured"
    assert initial_detail.json()["status"] == "not_configured"
    assert "enabled" not in initial_detail.json()

    initial_configuration = client.get(
        "/api/v2/commerce/sources/nextcloud:primary/configuration",
        headers=auth_headers,
    )
    assert initial_configuration.status_code == 200
    assert initial_configuration.json()["connection_configured"] is False
    assert initial_configuration.json()["configuration_state"] == "not_configured"
    assert initial_configuration.json()["enabled"] is None

    response = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {"url": "https://softpple.business", "username": "woo"},
            "secrets": {"password": "app-password-secret"},
        },
    )

    assert response.status_code == 200
    assert "app-password-secret" not in response.text
    config = AppConfigService(db)
    assert config.get("nextcloud.url") == "https://softpple.business"
    assert config.get("nextcloud.username") == "woo"
    assert config.get("nextcloud.password") == "app-password-secret"
    assert config.get("nextcloud.spreadsheet_path") in (None, "")
    detail = client.get("/api/v2/commerce/sources/nextcloud:primary", headers=auth_headers)
    assert detail.status_code == 200
    # The credentials are saved, but the Source remains incomplete until a
    # spreadsheet is selected. These persisted states must remain distinct.
    assert detail.json()["credential_status"] == "configured"
    assert detail.json()["connection_configured"] is True
    assert detail.json()["configuration_state"] == "setup_required"

    configured_connection = client.get(
        "/api/v2/commerce/sources/nextcloud:primary/configuration",
        headers=auth_headers,
    )
    assert configured_connection.status_code == 200
    assert configured_connection.json()["enabled"] is True

    completed = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {
                "url": "https://softpple.business",
                "username": "woo",
                "spreadsheet_path": "/Reports/prices.xlsx",
            },
            "secrets": {"password": ""},
            "currency": "IRR",
            "currency_unit": "RIAL",
        },
    )
    assert completed.status_code == 200

    listed_incomplete = client.get("/api/v2/commerce/sources", headers=auth_headers)
    assert listed_incomplete.status_code == 200
    incomplete_source = next(
        item
        for item in listed_incomplete.json()["items"]
        if item["id"] == "nextcloud:primary"
    )
    assert incomplete_source["configuration_state"] == "setup_required"

    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.source_workspace.service import SourceWorkspaceService

    user = db.query(FlowHubUser).one()
    workspace = SourceWorkspaceService(db)
    managed = workspace.create_source(
        name="Nextcloud",
        source_kind="external",
        external_source_id="nextcloud:primary",
        worksheet_mode="all",
        worksheet_name=None,
        data_start_row=2,
        user=user,
        currency="IRR",
        currency_unit="RIAL",
    )
    workspace.save_mapping(
        source_id=managed["id"],
        expected_source_version=managed["version"],
        worksheet_mode="all",
        worksheet_name=None,
        data_start_row=2,
        source_fields=[
            {
                "field": "name",
                "reference_type": "column_letter",
                "reference_value": "A",
                "required": True,
            },
            {
                "field": "source_key",
                "reference_type": "column_letter",
                "reference_value": "B",
                "required": True,
            },
        ],
        channel_mappings=[
            {
                "channel_id": "woocommerce:primary",
                "fields": [
                    {
                        "field": "external_id",
                        "reference_type": "column_letter",
                        "reference_value": "B",
                    }
                ],
            }
        ],
        value_policy={},
        identity_authority={
            "type": "external_system",
            "system_identifier": "woocommerce",
            "display_label": "WooCommerce",
        },
        user=user,
    )

    listed = client.get("/api/v2/commerce/sources", headers=auth_headers)
    assert listed.status_code == 200
    configured_source = next(
        item for item in listed.json()["items"] if item["id"] == "nextcloud:primary"
    )
    assert configured_source["connection_configured"] is True
    assert configured_source["configuration_state"] == "configured"


def test_nextcloud_policies_and_currency_persist_before_later_spreadsheet_selection(
    client, auth_headers, db
):
    from app.flowhub.setup.service import AppConfigService

    policy_save = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {
                "url": "https://softpple.business",
                "username": "woo",
                "worksheet_mode": "selected",
                "worksheet_name": "Prices",
            },
            "secrets": {"password": "app-password-secret"},
            "currency": "IRR",
            "currency_unit": "TOMAN",
        },
    )

    assert policy_save.status_code == 200
    assert "app-password-secret" not in policy_save.text
    reopened = client.get(
        "/api/v2/commerce/sources/nextcloud:primary/configuration",
        headers=auth_headers,
    )
    assert reopened.status_code == 200
    policy = reopened.json()
    assert policy["settings"].get("spreadsheet_path") in (None, "")
    assert policy["settings"]["worksheet_mode"] == "selected"
    assert policy["settings"]["worksheet_name"] == "Prices"
    assert policy["currency_profile"]["status"] == "resolved"
    assert policy["currency_profile"]["currency"] == "IRR"
    assert policy["currency_profile"]["unit"] == "TOMAN"
    assert policy["secrets"]["password"]["status"] == "configured"
    assert policy["credentials_returned"] is False

    file_save = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {
                "url": "https://softpple.business",
                "username": "woo",
                "spreadsheet_path": "/Reports/prices.xlsx",
            },
            "secrets": {"password": ""},
        },
    )

    assert file_save.status_code == 200
    config = AppConfigService(db)
    assert config.get("nextcloud.spreadsheet_path") == "/Reports/prices.xlsx"
    assert config.get("nextcloud.worksheet_mode") == "selected"
    assert config.get("nextcloud.worksheet_name") == "Prices"
    after_file = client.get(
        "/api/v2/commerce/sources/nextcloud:primary/configuration",
        headers=auth_headers,
    )
    assert after_file.status_code == 200
    persisted = after_file.json()
    assert persisted["settings"]["spreadsheet_path"] == "/Reports/prices.xlsx"
    assert persisted["settings"]["worksheet_mode"] == "selected"
    assert persisted["settings"]["worksheet_name"] == "Prices"
    assert persisted["currency_profile"]["currency"] == "IRR"
    assert persisted["currency_profile"]["unit"] == "TOMAN"
    assert persisted["secrets"]["password"]["status"] == "configured"
    assert persisted["credentials_returned"] is False


def test_nextcloud_source_configuration_returns_editable_values_without_secrets(client, auth_headers, db):
    from app.flowhub.setup.service import AppConfigService

    AppConfigService(db).set_many(
        {
            "nextcloud.url": "https://softpple.business",
            "nextcloud.username": "wrong-user",
            "nextcloud.password": "wrong-secret",
        },
        updated_by="test",
    )

    response = client.get(
        "/api/v2/commerce/sources/nextcloud:primary/configuration",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["configured"] is False
    assert data["connection_configured"] is True
    assert data["settings"]["url"] == "https://softpple.business"
    assert data["settings"]["username"] == "wrong-user"
    assert data["settings"].get("spreadsheet_path") in (None, "")
    assert data["secrets"]["password"]["status"] == "configured"
    assert data["credentials_returned"] is False
    assert data["last_test"] == {
        "status": "unknown",
        "message": "No health check has been recorded.",
        "latency_ms": None,
        "error_code": None,
        "checked_at": None,
    }
    assert "wrong-secret" not in response.text


def test_nextcloud_source_save_with_blank_secret_preserves_stored_credential(
    client, auth_headers, db
):
    from app.flowhub.setup.service import AppConfigService

    first = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "display_name": "Original catalog",
            "description": "Daily owner workbook",
            "enabled": True,
            "settings": {
                "url": "https://stored.example.test",
                "username": "stored-user",
            },
            "secrets": {"password": "stored-app-password"},
        },
    )
    assert first.status_code == 200
    assert first.json()["connection_configured"] is True
    assert first.json()["configured"] is False
    assert first.json()["credentials_returned"] is False

    edited = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "display_name": "Edited catalog",
            "description": "",
            "enabled": True,
            "settings": {
                "url": "https://edited.example.test",
                "username": "edited-user",
            },
            "secrets": {"password": ""},
        },
    )

    assert edited.status_code == 200
    assert "stored-app-password" not in edited.text
    assert edited.json()["connection_configured"] is True
    config = AppConfigService(db)
    assert config.get("nextcloud.password") == "stored-app-password"

    reopened = client.get(
        "/api/v2/commerce/sources/nextcloud:primary/configuration",
        headers=auth_headers,
    )
    assert reopened.status_code == 200
    data = reopened.json()
    assert data["display_name"] == "Edited catalog"
    assert data["settings"]["url"] == "https://edited.example.test"
    assert data["settings"]["username"] == "edited-user"
    assert data["settings"]["description"] == ""
    assert data["secrets"]["password"]["status"] == "configured"
    assert data["connection_configured"] is True
    assert data["enabled"] is True
    assert data["credentials_returned"] is False
    assert "stored-app-password" not in reopened.text


def test_nextcloud_source_replaces_secret_only_when_settings_are_saved(
    client, auth_headers, db, monkeypatch
):
    from app.flowhub.setup.service import AppConfigService

    async def fake_browse(self, path="/"):
        return {"path": path, "directories": [], "files": [], "read_only": True, "write_blocked": True}

    monkeypatch.setattr(
        "app.flowhub.integrations.nextcloud.NextcloudClient.browse_directory",
        fake_browse,
    )
    stored = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {
                "url": "https://stored.example.test",
                "username": "stored-user",
            },
            "secrets": {"password": "stored-app-password"},
        },
    )
    assert stored.status_code == 200

    draft = {
        "enabled": True,
        "settings": {
            "url": "https://draft.example.test",
            "username": "draft-user",
        },
        "secrets": {"password": "replacement-app-password"},
    }
    tested = client.post(
        "/api/v2/commerce/sources/nextcloud:primary/test",
        headers=auth_headers,
        json=draft,
    )
    assert tested.status_code == 200
    assert tested.json()["ok"] is True
    config = AppConfigService(db)
    assert config.get("nextcloud.password") == "stored-app-password"

    saved = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json=draft,
    )
    assert saved.status_code == 200
    assert saved.json()["connection_configured"] is True
    assert config.get("nextcloud.password") == "replacement-app-password"
    assert "replacement-app-password" not in saved.text

    reopened = client.get(
        "/api/v2/commerce/sources/nextcloud:primary/configuration",
        headers=auth_headers,
    )
    assert reopened.status_code == 200
    assert reopened.json()["last_test"] == {
        "status": "unknown",
        "message": "No health check has been recorded.",
        "latency_ms": None,
        "error_code": None,
        "checked_at": None,
    }


def test_nextcloud_test_connection_returns_stable_safe_failure_codes(
    client, auth_headers, monkeypatch
):
    from app.flowhub.integrations.errors import IntegrationError

    saved = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {
                "url": "https://stored.example.test",
                "username": "stored-user",
            },
            "secrets": {"password": "stored-app-password"},
        },
    )
    assert saved.status_code == 200

    async def unexpected_browse(self, path="/"):
        raise RuntimeError("implementation detail")

    monkeypatch.setattr(
        "app.flowhub.integrations.nextcloud.NextcloudClient.browse_directory",
        unexpected_browse,
    )
    unexpected = client.post(
        "/api/v2/commerce/sources/nextcloud:primary/test",
        headers=auth_headers,
        json={},
    )
    assert unexpected.status_code == 200
    assert unexpected.json()["code"] == "connection_failed"
    assert unexpected.json()["error_class"] == "connection_failed"
    assert "RuntimeError" not in unexpected.text

    cases = (
        ("authentication_failed", 401, "Authentication failed."),
        ("permission_denied", 403, "Nextcloud rejected access to the WebDAV path."),
        ("resource_not_found", 404, "The configured WebDAV path was not found."),
        ("timeout", None, "The Nextcloud server did not respond in time."),
        (
            "unsafe_destination",
            None,
            "The configured source destination is blocked by the Source network safety policy.",
        ),
        ("dns_resolution_failed", None, "The Nextcloud server hostname could not be resolved."),
        ("tls_error", None, "A secure connection to the Nextcloud server could not be established."),
        ("network_unreachable", None, "The Nextcloud server could not be reached."),
    )
    for code, http_status, message in cases:
        async def fail_browse(self, path="/", *, failure_code=code, failure_status=http_status):
            raise IntegrationError(
                "Nextcloud",
                "/redacted-webdav-path",
                "redacted upstream failure",
                status_code=failure_status,
                code=failure_code,
            )

        monkeypatch.setattr(
            "app.flowhub.integrations.nextcloud.NextcloudClient.browse_directory",
            fail_browse,
        )
        response = client.post(
            "/api/v2/commerce/sources/nextcloud:primary/test",
            headers=auth_headers,
            json={},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is False
        assert data["code"] == code
        assert data["error_class"] == code
        assert data["message"] == message
        assert "stored-app-password" not in response.text

    configuration = client.get(
        "/api/v2/commerce/sources/nextcloud:primary/configuration",
        headers=auth_headers,
    )
    assert configuration.status_code == 200
    last_test = configuration.json()["last_test"]
    assert last_test["status"] == "unhealthy"
    assert last_test["message"] == "The Nextcloud server could not be reached."
    assert last_test["error_code"] == "network_unreachable"
    assert last_test["latency_ms"] is not None
    assert last_test["checked_at"]


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


def test_nextcloud_workbook_can_be_saved_before_worksheet_selection(
    client, auth_headers
):
    response = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {
                "url": "https://softpple.business",
                "username": "woo",
                "spreadsheet_path": "/Reports/prices.xlsx",
                "worksheet_mode": "selected",
                "worksheet_name": "",
            },
            "secrets": {"password": "app-password-secret"},
        },
    )

    assert response.status_code == 200
    assert "app-password-secret" not in response.text
    saved = response.json()
    assert saved["connection_configured"] is True
    assert saved["configured"] is False
    assert saved["configuration_state"] == "setup_required"

    reopened = client.get(
        "/api/v2/commerce/sources/nextcloud:primary/configuration",
        headers=auth_headers,
    )
    assert reopened.status_code == 200
    body = reopened.json()
    assert body["settings"]["spreadsheet_path"] == "/Reports/prices.xlsx"
    assert body["settings"]["worksheet_mode"] == "selected"
    assert body["settings"]["worksheet_name"] == ""
    assert body["secrets"]["password"]["status"] == "configured"
    assert body["configured"] is False
    assert body["configuration_state"] == "setup_required"


def test_nextcloud_manual_read_now_uses_mapping_and_never_writes(
    client, auth_headers, db, monkeypatch
):
    from app.connectors.destinations.woocommerce.write_adapter import WooCommercePriceWriteAdapter
    from app.flowhub.integrations.nextcloud import NextcloudClient
    from app.flowhub.source_acquisition.models import (
        SourceObservationDataset,
        SourceObservationWorksheetDataset,
    )

    async def fake_download(self, path):
        assert path == "/Reports/prices.xlsx"
        return _xlsx_custom(
            headers=["Name", "Stock", "SKU", "Price", "Product ID"],
            rows=[["Mapped Product", "12", "SKU-101", "125.00", "101"]],
        ), {"etag": "etag-read"}

    async def fail_write(*args, **kwargs):
        raise AssertionError("Manual source read must not write to WooCommerce")

    install_nextcloud_download(monkeypatch, fake_download)
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
    dataset = db.query(SourceObservationDataset).one()
    assert dataset.row_count == 3
    assert dataset.worksheet_count == 1
    worksheet = db.query(SourceObservationWorksheetDataset).one()
    assert worksheet.dataset_id == dataset.id
    assert worksheet.worksheet_name == "Sheet1"
    assert worksheet.worksheet_order == 1
    assert worksheet.rows_json == [
        ["Name", "Stock", "SKU", "Price", "Product ID"],
        [None, None, None, None, None],
        ["Mapped Product", "12", "SKU-101", "125.00", "101"],
    ]


def test_explicit_source_profile_read_retains_dataset_when_legacy_parser_finds_no_rows(
    client, auth_headers, db, monkeypatch
):
    import asyncio

    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.source_acquisition.models import (
        SourceObservationDataset,
        SourceObservationWorksheetDataset,
    )
    from app.flowhub.source_workspace.service import SourceWorkspaceService
    from app.flowhub.sources.spreadsheet_source import SpreadsheetSourceReadService

    async def fake_download(self, path):
        assert path == "/Reports/identity.xlsx"
        return _xlsx_custom(
            headers=["Website Product ID"],
            rows=[],
        ), {"etag": "etag-identity"}

    install_nextcloud_download(monkeypatch, fake_download)
    reader = SpreadsheetSourceReadService(db)
    assert reader.configured_resource_scope() is None
    saved = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {
                "url": "https://softpple.business",
                "username": "woo",
                "spreadsheet_path": "/Reports/identity.xlsx",
            },
            "secrets": {"password": "app-password-secret"},
        },
    )
    assert saved.status_code == 200
    assert reader.configured_resource_scope() == "webdav:/Reports/identity.xlsx"
    user = db.query(FlowHubUser).one()
    source = SourceWorkspaceService(db).create_source(
        name="Identity workbook",
        source_kind="external",
        external_source_id="nextcloud:primary",
        worksheet_mode="all",
        worksheet_name=None,
        data_start_row=2,
        user=user,
    )

    result = asyncio.run(
        reader.read_nextcloud_spreadsheet(
            triggered_by="test",
            triggered_by_id=user.id,
            manual=True,
            capture_raw_worksheets=False,
            source_profile_id=source["id"],
        )
    )

    assert result.rows == []
    assert result.worksheets is None
    assert result.stats["total_rows"] == 0
    dataset = db.query(SourceObservationDataset).one()
    assert result.dataset_id == dataset.id
    worksheet = db.query(SourceObservationWorksheetDataset).one()
    assert worksheet.rows_json == [
        ["Website Product ID"],
        [None],
    ]


def test_nextcloud_source_read_rate_limit_is_enforced(client, auth_headers, monkeypatch):
    from app.flowhub.integrations.nextcloud import NextcloudClient

    downloads = 0

    async def fake_download(self, path):
        nonlocal downloads
        downloads += 1
        return _xlsx_custom(
            headers=["Name", "Product ID", "Price", "SKU"],
            rows=[["Limited Product", "101", "125.00", "SKU-101"]],
        ), {"etag": "etag-limit"}

    install_nextcloud_download(monkeypatch, fake_download)
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
    detail = second.json()["detail"]
    assert detail["code"] == "SOURCE_READ_LIMIT_REACHED"
    assert detail["limit"] == 1
    assert detail["usage"] == 1
    assert detail["reset_at"]
    assert detail["retry_after_seconds"] > 0
    assert second.headers["Retry-After"] == str(detail["retry_after_seconds"])
    assert downloads == 1


def test_nextcloud_read_preflight_failure_does_not_consume_a_remote_read(
    client, auth_headers, db
):
    from app.flowhub.data_layer.models import DlSourceReadReservation

    saved = client.put(
        "/api/v2/commerce/sources/nextcloud:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {
                "url": "https://softpple.business",
                "username": "woo",
                # A connection can be saved before a workbook is selected.
                "source_read_policy": {
                    "enabled": True,
                    "max_reads_per_24h": 1,
                    "manual_read_allowed": True,
                },
            },
            "secrets": {"password": "app-password-secret"},
        },
    )
    assert saved.status_code == 200

    response = client.post(
        "/api/v2/commerce/sources/nextcloud:primary/read", headers=auth_headers
    )

    assert response.status_code == 422
    assert db.query(DlSourceReadReservation).count() == 0


def test_detect_worksheets_reuses_the_new_snapshot_without_double_counting(
    client, auth_headers, db, monkeypatch
):
    import asyncio

    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.data_layer.models import DlSourceReadReservation
    from app.flowhub.source_acquisition.models import SourceObservationDataset
    from app.flowhub.source_workspace.service import SourceWorkspaceService
    from app.flowhub.sources.spreadsheet_source import SpreadsheetSourceReadService

    downloads = 0

    async def fake_download(self, path):
        nonlocal downloads
        downloads += 1
        assert path == "/Reports/prices.xlsx"
        return _xlsx_custom(
            headers=["Name", "Product ID", "Price"],
            rows=[["Snapshot product", "101", "125.00"]],
        ), {"etag": "etag-snapshot"}

    install_nextcloud_download(monkeypatch, fake_download)
    saved = client.put(
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
                    "max_reads_per_24h": 2,
                    "manual_read_allowed": True,
                },
            },
            "secrets": {"password": "app-password-secret"},
        },
    )
    assert saved.status_code == 200
    user = db.query(FlowHubUser).one()
    workspace = SourceWorkspaceService(db)
    source = workspace.create_source(
        name="Workbook",
        source_kind="external",
        external_source_id="nextcloud:primary",
        worksheet_mode="all",
        worksheet_name=None,
        data_start_row=1,
        user=user,
    )

    imported = asyncio.run(
        SpreadsheetSourceReadService(db).read_nextcloud_spreadsheet(
            triggered_by="test",
            triggered_by_id=user.id,
            manual=True,
            capture_raw_worksheets=True,
            source_profile_id=source["id"],
        )
    )
    detected = asyncio.run(workspace.list_source_worksheets(source["id"], user))

    assert downloads == 1
    assert db.query(DlSourceReadReservation).count() == 1
    dataset = db.query(SourceObservationDataset).one()
    assert imported.dataset_id == dataset.id
    assert imported.observation_id == dataset.observation_id
    assert detected["items"] == [{"name": "Sheet1", "rowCount": None}]
    assert detected["worksheetDiscovery"]["metadataSource"] == "snapshot"
    assert detected["worksheetDiscovery"]["remoteReadUsed"] is False
    assert detected["readQuota"]["usage"] == 1
    assert detected["readQuota"]["remaining"] == 1


def test_failed_outbound_source_read_consumes_reserved_quota(client, auth_headers, db, monkeypatch):
    from app.flowhub.data_layer.models import DlSourceReadReservation
    from app.flowhub.integration_platform.models import IntegrationConnectorEvent
    from app.flowhub.integrations.errors import IntegrationError
    from app.flowhub.integrations.nextcloud import NextcloudClient

    async def fail_download(self, path):
        raise IntegrationError("nextcloud", path, "WebDAV unavailable", status_code=502)

    install_nextcloud_download(monkeypatch, fail_download)
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
            SpreadsheetSourceReadService(session).reserve_read_slot(
                actor, manual=True, source_id="source-profile-primary"
            )
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


def test_source_profile_read_quotas_are_independent_and_shared(db):
    from fastapi import HTTPException

    from app.flowhub.setup.service import AppConfigService
    from app.flowhub.sources.spreadsheet_source import SpreadsheetSourceReadService

    AppConfigService(db).set(
        "nextcloud.source_read_policy",
        '{"enabled":true,"max_reads_per_24h":10,"manual_read_allowed":true}',
        updated_by="test",
    )
    reader = SpreadsheetSourceReadService(db)
    for index in range(10):
        reader.reserve_read_slot(f"owner-{index}", manual=False, source_id="source-profile-a")
    assert reader.read_policy_state(source_id="source-profile-a")["reads_used_last_24h"] == 10
    with pytest.raises(HTTPException) as limited:
        reader.reserve_read_slot("owner-over-limit", manual=True, source_id="source-profile-a")
    assert limited.value.status_code == 429
    reader.reserve_read_slot("owner-b", manual=True, source_id="source-profile-b")
    assert reader.read_policy_state(source_id="source-profile-b")["reads_used_last_24h"] == 1


def test_discovery_allowance_is_separate_from_acquisition_allowance(db):
    from app.flowhub.setup.service import AppConfigService
    from app.flowhub.sources.spreadsheet_source import SpreadsheetSourceReadService

    AppConfigService(db).set_many(
        {
            "nextcloud.source_read_policy": '{"enabled":true,"max_reads_per_24h":1,"manual_read_allowed":true}',
            "nextcloud.worksheet_discovery_policy": '{"enabled":true,"max_refreshes_per_24h":2}',
        },
        updated_by="test",
    )
    reader = SpreadsheetSourceReadService(db)
    reader.reserve_discovery_slot("owner", source_id="source-profile-primary")
    assert reader.discovery_quota_contract(source_id="source-profile-primary")["usage"] == 1
    assert reader.read_quota_contract(source_id="source-profile-primary")["usage"] == 0
    reader.reserve_read_slot("owner", manual=True, source_id="source-profile-primary")
    assert reader.read_quota_contract(source_id="source-profile-primary")["usage"] == 1
    assert reader.discovery_quota_contract(source_id="source-profile-primary")["usage"] == 1


def test_concurrent_discovery_refreshes_cannot_exceed_atomic_allowance(tmp_path):
    from fastapi import HTTPException
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.flowhub.database import FlowHubBase
    from app.flowhub.data_layer.models import DlSourceDiscoveryReservation
    from app.flowhub.setup.service import AppConfigService
    from app.flowhub.sources.spreadsheet_source import SpreadsheetSourceReadService

    engine = create_engine(
        f"sqlite:///{tmp_path / 'discovery-quota.db'}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    FlowHubBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    setup_session = Session()
    AppConfigService(setup_session).set(
        "nextcloud.worksheet_discovery_policy",
        '{"enabled":true,"max_refreshes_per_24h":1}',
        updated_by="test",
    )
    setup_session.close()
    barrier = Barrier(2)

    def reserve(actor: str) -> int:
        session = Session()
        try:
            barrier.wait()
            SpreadsheetSourceReadService(session).reserve_discovery_slot(actor, source_id="source-profile-primary")
            return 200
        except HTTPException as exc:
            return exc.status_code
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = sorted(executor.map(reserve, ["admin-a", "admin-b"]))

    check_session = Session()
    assert results == [200, 429]
    assert check_session.query(DlSourceDiscoveryReservation).count() == 1
    check_session.close()
    engine.dispose()


def test_source_read_allowance_resets_after_24_hours(db):
    from app.flowhub.data_layer.models import DlSourceReadReservation
    from app.flowhub.setup.service import AppConfigService
    from app.flowhub.sources.spreadsheet_source import SpreadsheetSourceReadService

    AppConfigService(db).set(
        "nextcloud.source_read_policy",
        '{"enabled":true,"max_reads_per_24h":1,"manual_read_allowed":true}',
        updated_by="test",
    )
    reader = SpreadsheetSourceReadService(db)
    reader.reserve_read_slot("owner", manual=True, source_id="source-profile-primary")
    reservation = db.query(DlSourceReadReservation).one()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    reservation.reserved_at = now - timedelta(hours=24, seconds=1)
    db.commit()

    state = reader.read_policy_state(source_id="source-profile-primary", now=now)

    assert state["reads_used_last_24h"] == 0
    assert state["reads_remaining"] == 1
    assert state["reset_at"] is None


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

    install_nextcloud_download(monkeypatch, fake_download)
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
    assert detail.json()["provider"] == "woocommerce"
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
    assert simple.images == [{
        "type": "image",
        "url": "https://store.example.test/simple.jpg",
        "position": 0,
        "source": "woocommerce",
    }]
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
    from app.flowhub.data_layer.models import DlProductCache, DlRefreshJob

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

    refresh = db.query(DlRefreshJob).filter_by(
        connector_id="woocommerce:primary", entity_type="products"
    ).one()
    assert refresh.status == "partial_failed"
    assert refresh.meta["error_category"] == "authentication_failed"

    # Re-opened Channel and Diagnostics surfaces must retain the failure
    # evidence rather than presenting the one stored product as a healthy sync.
    channel = client.get(
        "/api/v2/commerce/channels/woocommerce:primary", headers=auth_headers
    ).json()
    assert channel["cache_refresh_status"] == "partial_failed"
    assert channel["product_sync_error_category"] == "authentication_failed"
    assert channel["configuration_state"] == "error"
    diagnostics = client.get(
        "/api/v2/diagnostics/channels/health", headers=auth_headers
    ).json()
    diagnostic = next(
        item
        for item in diagnostics["items"]
        if item["channelId"] == "woocommerce:primary"
    )
    assert diagnostic["productReadStatus"] == "partial_failed"
    assert diagnostic["lastSyncErrorCategory"] == "authentication_failed"
    assert diagnostic["dimensions"]["productCache"]["state"] == "WARNING"


def test_woocommerce_cache_refresh_reports_full_failure_reason_after_reload(
    client, auth_headers, db, monkeypatch
):
    from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
    from app.flowhub.data_layer.models import DlProductCache, DlRefreshJob

    _configure_woocommerce_channel(client, auth_headers)

    async def fail_first_page(*_args, **_kwargs):
        raise ConnectorError(
            code=ConnectorErrorCode.TIMEOUT,
            message="Timed out while reading key=ck_live_secret secret=cs_live_secret",
            provider="woocommerce",
        )

    monkeypatch.setattr(
        "app.connectors.read.woocommerce.list_products_paged", fail_first_page
    )
    response = client.post(
        "/api/v2/commerce/channels/woocommerce:primary/refresh-cache",
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert db.query(DlProductCache).count() == 0
    assert "ck_live_secret" not in response.text
    assert "cs_live_secret" not in response.text
    refresh = db.query(DlRefreshJob).filter_by(
        connector_id="woocommerce:primary", entity_type="products"
    ).one()
    assert refresh.status == "failed"
    assert refresh.meta["error_category"] == "timeout"

    channel = client.get(
        "/api/v2/commerce/channels/woocommerce:primary", headers=auth_headers
    ).json()
    assert channel["cache_refresh_status"] == "failed"
    assert channel["product_sync_error_category"] == "timeout"
    assert channel["configuration_state"] == "error"
    diagnostics = client.get(
        "/api/v2/diagnostics/channels/health", headers=auth_headers
    ).json()
    diagnostic = next(
        item
        for item in diagnostics["items"]
        if item["channelId"] == "woocommerce:primary"
    )
    assert diagnostic["productReadStatus"] == "failed"
    assert diagnostic["lastSyncErrorCategory"] == "timeout"
    assert diagnostic["dimensions"]["productCache"]["state"] == "ERROR"


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


def test_snappshop_can_be_write_enabled_only_through_protected_pipeline(client, auth_headers):
    response = client.put(
        "/api/v2/commerce/channels/snappshop:main/settings",
        headers=auth_headers,
        json={
            "access_mode": "write_enabled",
            "settings": {
                "agent_identifier": "flowhub-agent",
                "vendor_id": "vendor-1",
            },
            "secrets": {"token": "snapp-write-token"},
        },
    )

    assert response.status_code == 200
    assert "snapp-write-token" not in response.text
    data = response.json()
    assert data["access_mode"] == "write_enabled"
    assert data["read_only"] is False
    assert data["write_pipeline_eligible"] is True
    assert data["runtime_write_blocked"] is True


def test_snappshop_credentials_can_be_saved_before_vendor_selection(client, auth_headers):
    response = client.put(
        "/api/v2/commerce/channels/snappshop:main/settings",
        headers=auth_headers,
        json={
            "access_mode": "read_only",
            "settings": {"agent_identifier": "flowhub-agent"},
            "secrets": {"token": "snapp-read-token"},
        },
    )

    assert response.status_code == 200
    assert "snapp-read-token" not in response.text
    detail = client.get(
        "/api/v2/commerce/channels/snappshop:main",
        headers=auth_headers,
    )
    assert detail.status_code == 200
    assert detail.json()["credentials_configured"] is True
    assert detail.json()["vendor_selected"] is False
    assert detail.json()["credential_status"] == "not_configured"


def test_tapsishop_can_be_write_enabled_only_through_protected_pipeline(
    client,
    auth_headers,
):
    response = client.put(
        "/api/v2/commerce/channels/tapsishop:main/settings",
        headers=auth_headers,
        json={
            "access_mode": "write_enabled",
            "settings": {"base_url": "https://vendorgw.tapsi.shop/Web/Hub/vendors/v1"},
            "secrets": {"token": "tapsi-write-token"},
        },
    )

    assert response.status_code == 200
    assert "tapsi-write-token" not in response.text
    data = response.json()
    assert data["access_mode"] == "write_enabled"
    assert data["read_only"] is False
    assert data["write_pipeline_eligible"] is True
    assert data["runtime_write_blocked"] is True


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


def test_tapsishop_channel_settings_mask_separate_outbound_and_webhook_tokens(client, auth_headers):
    response = client.put(
        "/api/v2/commerce/channels/tapsishop:main/settings",
        headers=auth_headers,
        json={
            "settings": {"selected_vendor_id": "42"},
            "secrets": {
                "token": "tapsi-secret-value",
                "webhook_token": "tapsi-webhook-secret",
            },
        },
    )

    assert response.status_code == 200
    assert "tapsi-secret-value" not in response.text
    assert "tapsi-webhook-secret" not in response.text
    data = response.json()
    assert data["read_only"] is True
    assert data["access_mode"] == "read_only"
    assert data["write_pipeline_eligible"] is False
    assert data["runtime_write_blocked"] is True
    assert data["secrets"]["token"]["status"] == "configured"
    assert data["secrets"]["webhook_token"]["status"] == "configured"

    detail = client.get("/api/v2/commerce/channels/tapsishop:main", headers=auth_headers)
    assert detail.status_code == 200
    assert "tapsi-secret-value" not in detail.text
    assert "tapsi-webhook-secret" not in detail.text
    assert detail.json()["credential_status"] == "configured"


def test_marketplace_configuration_metadata_is_sanitized_and_blank_secret_keeps_existing(client, auth_headers, db):
    secret_value = "snapp-secret-value"
    saved = client.put(
        "/api/v2/commerce/channels/snappshop:main/settings",
        headers=auth_headers,
        json={
            "display_name": "Primary SnappShop",
            "enabled": True,
            "access_mode": "read_only",
            "settings": {
                "base_url": "https://apix.snappshop.ir/automation/v1",
                "agent_identifier": "flowhub-agent",
                "agent_header_name": "User-Agent",
                "request_timeout": "20",
                "vendor_id": "vendor-1",
            },
            "secrets": {"token": secret_value},
        },
    )
    assert saved.status_code == 200

    configuration = client.get(
        "/api/v2/commerce/channels/snappshop:main/configuration", headers=auth_headers
    )
    assert configuration.status_code == 200
    data = configuration.json()
    assert data["configured"] is True
    assert data["enabled"] is True
    assert data["access_mode"] == "read_only"
    assert data["settings"]["agent_identifier"] == "flowhub-agent"
    assert data["token_configured"] is True
    assert data["credentials_returned"] is False
    assert secret_value not in configuration.text

    updated = client.put(
        "/api/v2/commerce/channels/snappshop:main/settings",
        headers=auth_headers,
        json={
            "display_name": "Primary SnappShop",
            "enabled": True,
            "access_mode": "read_only",
            "settings": {"agent_identifier": "flowhub-agent-2", "vendor_id": "vendor-1"},
            "secrets": {"token": ""},
        },
    )
    assert updated.status_code == 200
    assert updated.json()["secrets"]["token"]["status"] == "configured"
    assert client.get(
        "/api/v2/commerce/channels/snappshop:main/configuration", headers=auth_headers
    ).json()["token_configured"] is True

    from app.flowhub.integration_platform.models import IntegrationConnectorEvent
    audit = db.query(IntegrationConnectorEvent).filter_by(
        connector_id="snappshop:main", event_name="channel_configuration_changed"
    ).order_by(IntegrationConnectorEvent.id.desc()).first()
    assert audit is not None
    assert audit.metadata_json["actor"].startswith("commerceadmin_")
    assert audit.metadata_json["channel_id"] == "snappshop:main"
    assert set(audit.metadata_json["changed_fields"]).issuperset({
        "agent_identifier", "vendor_id", "enabled", "access_mode"
    })
    assert audit.created_at is not None
    assert secret_value not in str(audit.metadata_json)
    assert secret_value not in audit.message


def test_channel_system_names_are_english_but_owner_custom_names_are_preserved(
    client, auth_headers, db
):
    from app.flowhub.integration_platform.models import IntegrationConnectorInstance

    listed = client.get("/api/v2/commerce/channels", headers=auth_headers)
    assert listed.status_code == 200
    names = {item["provider"]: item["name"] for item in listed.json()["items"]}
    assert names["woocommerce"] == "WooCommerce"
    assert names["snappshop"] == "SnappShop"
    assert names["tapsishop"] == "TapsiShop"
    assert names["technolife"] == "Technolife"

    created = client.put(
        "/api/v2/commerce/channels/woocommerce:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {"url": "https://shop.example.test"},
            "secrets": {"key": "consumer-key", "secret": "consumer-secret"},
        },
    )
    assert created.status_code == 200

    canonical_save = client.put(
        "/api/v2/commerce/channels/woocommerce:primary/settings",
        headers=auth_headers,
        json={
            "display_name": "WooCommerce",
            "enabled": True,
            "settings": {"url": "https://shop.example.test"},
            "secrets": {"key": "", "secret": ""},
        },
    )
    assert canonical_save.status_code == 200
    canonical_configuration = client.get(
        "/api/v2/commerce/channels/woocommerce:primary/configuration",
        headers=auth_headers,
    ).json()
    assert canonical_configuration["display_name"] == "WooCommerce"
    assert canonical_configuration["display_name_custom"] is False

    # Simulate an instance created before display-name provenance existed.
    legacy_instance = db.get(IntegrationConnectorInstance, "woocommerce:primary")
    assert legacy_instance is not None
    legacy_instance.name = "ووکامرس"
    db.commit()
    configuration = client.get(
        "/api/v2/commerce/channels/woocommerce:primary/configuration",
        headers=auth_headers,
    ).json()
    assert configuration["display_name"] == "WooCommerce"
    assert configuration["display_name_custom"] is False

    explicitly_saved_alias = client.put(
        "/api/v2/commerce/channels/woocommerce:primary/settings",
        headers=auth_headers,
        json={
            "display_name": "ووکامرس",
            "enabled": True,
            "settings": {"url": "https://shop.example.test"},
            "secrets": {"key": "", "secret": ""},
        },
    )
    assert explicitly_saved_alias.status_code == 200
    assert "_flowhub_display_name_custom" not in explicitly_saved_alias.json()["settings"]
    configuration = client.get(
        "/api/v2/commerce/channels/woocommerce:primary/configuration",
        headers=auth_headers,
    ).json()
    assert configuration["display_name"] == "ووکامرس"
    assert configuration["display_name_custom"] is True
    assert "_flowhub_display_name_custom" not in configuration["settings"]
    db.expire_all()
    persisted = db.get(IntegrationConnectorInstance, "woocommerce:primary")
    assert persisted is not None
    marker = next(
        item
        for item in persisted.settings
        if item.key == "_flowhub_display_name_custom"
    )
    assert marker.value_json is True
    assert marker.secret is False
    assert marker.configured is True

    order_sync_status = client.get(
        "/api/v2/orders/sync-status", headers=auth_headers
    )
    assert order_sync_status.status_code == 200
    woo_order_status = next(
        item
        for item in order_sync_status.json()["items"]
        if item["channelId"] == "woocommerce:primary"
    )
    assert woo_order_status["displayName"] == "ووکامرس"
    assert woo_order_status["displayNameCustom"] is True

    custom_name = "فروشگاه تهران"
    customized = client.put(
        "/api/v2/commerce/channels/woocommerce:primary/settings",
        headers=auth_headers,
        json={
            "display_name": custom_name,
            "enabled": True,
            "settings": {"url": "https://shop.example.test"},
            "secrets": {"key": "", "secret": ""},
        },
    )
    assert customized.status_code == 200
    channel = client.get(
        "/api/v2/commerce/channels/woocommerce:primary", headers=auth_headers
    ).json()
    assert channel["name"] == custom_name
    assert channel["display_name_custom"] is True


def test_channel_draft_credentials_are_tested_but_replaced_only_on_save(
    client, auth_headers, db, monkeypatch
):
    from app.flowhub.data_layer.health_service import ConnectorHealthService
    from app.flowhub.data_layer.models import DlConnectorHealth
    from app.flowhub.setup.models import FlowHubAppConfig

    saved = client.put(
        "/api/v2/commerce/channels/woocommerce:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {"url": "https://saved.example.test"},
            "secrets": {"key": "saved-key", "secret": "saved-secret"},
        },
    )
    assert saved.status_code == 200
    ConnectorHealthService(db).upsert(
        connector_id="woocommerce:primary",
        connector_type="woocommerce",
        status="unhealthy",
        detail="Saved connector evidence.",
        error_class="authentication_failed",
    )

    observed = {}

    async def successful_probe(credentials):
        observed["url"] = credentials.url
        observed["key"] = credentials.key
        observed["secret"] = credentials.secret
        return {"http_status": 200, "records_checked": 1}

    monkeypatch.setattr(
        "app.flowhub.commerce.service.ping_woocommerce", successful_probe
    )
    tested = client.post(
        "/api/v2/commerce/channels/woocommerce:primary/test",
        headers=auth_headers,
        json={
            "settings": {"url": "https://draft.example.test"},
            "secrets": {"key": "draft-key", "secret": "draft-secret"},
        },
    )
    assert tested.status_code == 200
    assert tested.json()["ok"] is True
    assert tested.json()["configuration_matches_saved"] is False
    assert observed == {
        "url": "https://draft.example.test",
        "key": "draft-key",
        "secret": "draft-secret",
    }
    assert db.get(FlowHubAppConfig, "woocommerce.url").value == "https://saved.example.test"
    assert db.get(FlowHubAppConfig, "woocommerce.key").value == "saved-key"
    assert db.get(FlowHubAppConfig, "woocommerce.secret").value == "saved-secret"
    db.expire_all()
    health = db.query(DlConnectorHealth).filter_by(
        connector_id="woocommerce:primary"
    ).one()
    assert health.status == "unhealthy"
    assert health.detail == "Saved connector evidence."

    tested_saved = client.post(
        "/api/v2/commerce/channels/woocommerce:primary/test",
        headers=auth_headers,
        json={},
    )
    assert tested_saved.status_code == 200
    assert tested_saved.json()["ok"] is True
    assert tested_saved.json()["configuration_matches_saved"] is True
    db.expire_all()
    health = db.query(DlConnectorHealth).filter_by(
        connector_id="woocommerce:primary"
    ).one()
    assert health.status == "healthy"
    assert "Connected to WooCommerce" in health.detail

    replaced = client.put(
        "/api/v2/commerce/channels/woocommerce:primary/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {"url": "https://draft.example.test"},
            "secrets": {"key": "draft-key", "secret": "draft-secret"},
        },
    )
    assert replaced.status_code == 200
    db.expire_all()
    assert db.get(FlowHubAppConfig, "woocommerce.key").value == "draft-key"
    assert db.get(FlowHubAppConfig, "woocommerce.secret").value == "draft-secret"


def test_tapsishop_test_connection_never_refreshes_or_replaces_saved_token(
    client, auth_headers, db, monkeypatch
):
    from app.flowhub.setup.models import FlowHubAppConfig

    saved = client.put(
        "/api/v2/commerce/channels/tapsishop:main/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {"token_refresh_enabled": True},
            "secrets": {"token": "saved-tapsi-token"},
        },
    )
    assert saved.status_code == 200

    requested_urls = []

    class FakeResponse:
        headers = {}

        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def request(self, method, url, **kwargs):
            requested_urls.append(url)
            if url.endswith("/refresh-token"):
                return FakeResponse(200, {"success": True, "data": {"token": "rotated-token"}})
            return FakeResponse(401, {"success": False})

    monkeypatch.setattr(
        "app.flowhub.channels.tapsishop.httpx.AsyncClient",
        lambda **kwargs: FakeAsyncClient(),
    )
    tested = client.post(
        "/api/v2/commerce/channels/tapsishop:main/test",
        headers=auth_headers,
        json={},
    )

    assert tested.status_code == 200
    assert tested.json()["ok"] is False
    assert all(not url.endswith("/refresh-token") for url in requested_urls)
    db.expire_all()
    assert db.get(FlowHubAppConfig, "tapsishop.token").value == "saved-tapsi-token"


def test_tapsishop_configuration_reports_separate_secret_states_and_webhook_path(client, auth_headers):
    response = client.put(
        "/api/v2/commerce/channels/tapsishop:main/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {"request_timeout": 15, "selected_vendor_id": "42"},
            "secrets": {"token": "outbound-only"},
        },
    )
    assert response.status_code == 200

    configuration = client.get(
        "/api/v2/commerce/channels/tapsishop:main/configuration", headers=auth_headers
    )
    data = configuration.json()
    assert data["token_configured"] is True
    assert data["webhook_token_configured"] is False
    assert data["settings"]["token_refresh_enabled"] is False
    assert data["settings"]["revoke_current_token"] is False
    assert data["webhook_path"] == "/api/v2/webhooks/tapsishop/tapsishop:main"
    assert "outbound-only" not in configuration.text


def test_marketplace_configuration_requires_admin_and_valid_required_fields(client, auth_headers, db):
    from app.flowhub.auth.jwt_service import create_access_token
    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.auth.password import hash_password

    viewer = FlowHubUser(username=f"viewer_{uuid.uuid4().hex}", hashed_password=hash_password("password123"), role="viewer")
    db.add(viewer)
    db.commit()
    db.refresh(viewer)
    viewer_headers = {"Authorization": f"Bearer {create_access_token(viewer.id, viewer.username, viewer.role)}"}

    assert client.get(
        "/api/v2/commerce/channels/snappshop:main/configuration", headers=viewer_headers
    ).status_code == 403
    assert client.put(
        "/api/v2/commerce/channels/snappshop:main/settings",
        headers=viewer_headers,
        json={"settings": {"agent_identifier": "agent"}, "secrets": {"token": "secret"}},
    ).status_code == 403
    invalid = client.put(
        "/api/v2/commerce/channels/snappshop:main/settings",
        headers=auth_headers,
        json={"settings": {"base_url": "not-a-url"}, "secrets": {}},
    )
    assert invalid.status_code == 422
    assert client.get("/api/v2/commerce/channels/snappshop:main", headers=auth_headers).json()["credential_status"] == "not_configured"


def test_technolife_configuration_requires_and_masks_both_documented_secrets(
    client, auth_headers
):
    import base64

    encryption_secret = base64.b64encode(b"0123456789abcdef").decode("ascii")
    missing_secret = client.put(
        "/api/v2/commerce/channels/technolife:main/settings",
        headers=auth_headers,
        json={"enabled": True, "settings": {}, "secrets": {"api_key": "api-key"}},
    )
    assert missing_secret.status_code == 422

    response = client.put(
        "/api/v2/commerce/channels/technolife:main/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "access_mode": "write_enabled",
            "settings": {},
            "secrets": {
                "api_key": "api-key",
                "encryption_secret": encryption_secret,
            },
        },
    )
    assert response.status_code == 200
    assert "api-key" not in response.text
    assert encryption_secret not in response.text

    configuration = client.get(
        "/api/v2/commerce/channels/technolife:main/configuration",
        headers=auth_headers,
    ).json()
    assert configuration["configured"] is True
    assert configuration["access_mode"] == "write_enabled"
    assert configuration["secrets"]["api_key"]["status"] == "configured"
    assert configuration["secrets"]["encryption_secret"]["status"] == "configured"
    assert configuration["credentials_returned"] is False


def test_technolife_connection_test_persists_verified_health(
    client, auth_headers, monkeypatch
):
    import base64

    from app.flowhub.channels.contracts import ChannelHealth

    encryption_secret = base64.b64encode(b"0123456789abcdef").decode("ascii")
    save = client.put(
        "/api/v2/commerce/channels/technolife:main/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {},
            "secrets": {
                "api_key": "technolife-api-key",
                "encryption_secret": encryption_secret,
            },
        },
    )
    assert save.status_code == 200

    async def healthy_connection(_self):
        return ChannelHealth(
            status="healthy",
            checked_at="2026-08-10T12:00:00Z",
            latency_ms=14.5,
        )

    monkeypatch.setattr(
        "app.flowhub.channels.technolife.TechnolifeConnector.test_connection",
        healthy_connection,
    )

    response = client.post(
        "/api/v2/commerce/channels/technolife:main/test",
        headers=auth_headers,
        json={},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert "technolife-api-key" not in response.text
    assert encryption_secret not in response.text
    channel_state = client.get(
        "/api/v2/commerce/channels/technolife:main", headers=auth_headers
    ).json()
    assert channel_state["health"]["status"] == "healthy"
    assert channel_state["health"]["latency_ms"] == 14.5
    assert channel_state["last_health_check"]
    assert channel_state["credentials_verified"] is True


@pytest.mark.parametrize(
    ("channel_id", "settings", "secrets", "connector_path"),
    (
        (
            "snappshop:main",
            {
                "agent_identifier": "panel-agent",
                "vendor_id": "panel-vendor",
                "request_timeout": "30",
            },
            {"token": "panel-snapp-token"},
            "app.flowhub.channels.snappshop.SnappShopConnector.get_vendor_information",
        ),
        (
            "technolife:main",
            {"request_timeout": "30"},
            {"api_key": "panel-technolife-key", "encryption_secret": "MDEyMzQ1Njc4OWFiY2RlZg=="},
            "app.flowhub.channels.technolife.TechnolifeConnector.test_connection",
        ),
    ),
)
def test_reopened_configuration_string_timeout_test_updates_saved_health(
    client, auth_headers, monkeypatch, channel_id, settings, secrets, connector_path
):
    """The form serializes timeout as text; it still represents saved config."""

    assert client.put(
        f"/api/v2/commerce/channels/{channel_id}/settings",
        headers=auth_headers,
        json={"enabled": True, "settings": settings, "secrets": secrets},
    ).status_code == 200

    if channel_id == "snappshop:main":
        from app.flowhub.channels.contracts import ChannelVendor

        async def healthy_connection(_self):
            return ChannelVendor(
                channel_id=channel_id,
                connector_type="snappshop",
                name="Panel vendor",
                vendor_id="panel-vendor",
                metadata={"status": "active"},
            )
    else:
        from app.flowhub.channels.contracts import ChannelHealth

        async def healthy_connection(_self):
            return ChannelHealth(
                status="healthy",
                checked_at="2026-08-10T12:00:00Z",
                latency_ms=12.0,
            )

    monkeypatch.setattr(connector_path, healthy_connection)
    reopened = client.get(
        f"/api/v2/commerce/channels/{channel_id}/configuration", headers=auth_headers
    ).json()
    form_payload = {
        "settings": {
            **reopened["settings"],
            # CommerceHub stores inputs as strings before POSTing Test.
            "request_timeout": str(reopened["settings"]["request_timeout"]),
        },
        "secrets": {},
    }
    tested = client.post(
        f"/api/v2/commerce/channels/{channel_id}/test",
        headers=auth_headers,
        json=form_payload,
    )
    assert tested.status_code == 200
    assert tested.json()["ok"] is True
    state = client.get(f"/api/v2/commerce/channels/{channel_id}", headers=auth_headers).json()
    assert state["health"]["status"] == "healthy"
    assert state["credentials_verified"] is True


def test_latest_failed_connection_is_not_presented_as_verified_and_keeps_error_category(
    client, auth_headers, monkeypatch
):
    import base64

    from app.flowhub.channels.contracts import (
        ChannelHealth,
        ConnectorError,
        ConnectorErrorCategory,
    )

    encryption_secret = base64.b64encode(b"0123456789abcdef").decode("ascii")
    save = client.put(
        "/api/v2/commerce/channels/technolife:main/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {},
            "secrets": {
                "api_key": "safe-test-api-key",
                "encryption_secret": encryption_secret,
            },
        },
    )
    assert save.status_code == 200

    async def healthy_connection(_self):
        return ChannelHealth(status="healthy", latency_ms=10)

    monkeypatch.setattr(
        "app.flowhub.channels.technolife.TechnolifeConnector.test_connection",
        healthy_connection,
    )
    assert client.post(
        "/api/v2/commerce/channels/technolife:main/test",
        headers=auth_headers,
        json={},
    ).json()["ok"] is True

    async def rate_limited_connection(_self):
        return ChannelHealth(
            status="unhealthy",
            latency_ms=12,
            error=ConnectorError(
                category=ConnectorErrorCategory.RATE_LIMIT,
                message="Technolife rate limit was reached.",
                connector_type="technolife",
                channel_id="technolife:main",
                http_status=429,
            ),
        )

    monkeypatch.setattr(
        "app.flowhub.channels.technolife.TechnolifeConnector.test_connection",
        rate_limited_connection,
    )
    failed = client.post(
        "/api/v2/commerce/channels/technolife:main/test",
        headers=auth_headers,
        json={},
    )
    assert failed.status_code == 200
    assert failed.json()["error_class"] == "rate_limit"

    state = client.get(
        "/api/v2/commerce/channels/technolife:main", headers=auth_headers
    ).json()
    assert state["health"]["status"] == "unhealthy"
    assert state["health"]["error_code"] == "rate_limited"
    assert state["credentials_verified"] is False
    assert state["configuration_state"] == "error"


@pytest.mark.parametrize(
    ("channel_id", "settings", "secrets", "preserved_config_keys"),
    [
        (
            "snappshop:main",
            {
                "base_url": "https://stored.snappshop.example/v1",
                "agent_identifier": "stored-agent",
                "agent_header_name": "Stored-Agent",
                "request_timeout": 17,
                "vendor_id": "stored-vendor",
            },
            {"token": "stored-snapp-token"},
            {
                "snappshop.base_url": "https://stored.snappshop.example/v1",
                "snappshop.agent_identifier": "stored-agent",
                "snappshop.agent_header_name": "Stored-Agent",
                "snappshop.vendor_id": "stored-vendor",
            },
        ),
        (
            "tapsishop:main",
            {
                "base_url": "https://vendorgw.tapsi.shop/Web/Hub/vendors/v1",
                "request_timeout": 17,
                "selected_vendor_id": "stored-vendor",
                "token_refresh_enabled": True,
                "token_refresh_name": "Stored Refresh",
                "revoke_current_token": True,
            },
            {"token": "stored-tapsi-token", "webhook_token": "stored-webhook-token"},
            {
                "tapsishop.base_url": "https://vendorgw.tapsi.shop/Web/Hub/vendors/v1",
                "tapsishop.selected_vendor_id": "stored-vendor",
                "tapsishop.token_refresh_enabled": "true",
                "tapsishop.token_refresh_name": "Stored Refresh",
                "tapsishop.revoke_current_token": "true",
            },
        ),
        (
            "technolife:main",
            {
                "base_url": "https://seller-api.technolife.com",
                "request_timeout": 17,
            },
            {
                "api_key": "stored-technolife-key",
                "encryption_secret": "MDEyMzQ1Njc4OWFiY2RlZg==",
            },
            {"technolife.base_url": "https://seller-api.technolife.com"},
        ),
    ],
)
def test_marketplace_partial_settings_save_preserves_omitted_nonsecret_values(
    client, auth_headers, db, channel_id, settings, secrets, preserved_config_keys
):
    from app.flowhub.setup.service import AppConfigService

    first_save = client.put(
        f"/api/v2/commerce/channels/{channel_id}/settings",
        headers=auth_headers,
        json={"enabled": True, "settings": settings, "secrets": secrets},
    )
    assert first_save.status_code == 200

    partial_save = client.put(
        f"/api/v2/commerce/channels/{channel_id}/settings",
        headers=auth_headers,
        json={"settings": {"request_timeout": 23}, "secrets": {}},
    )
    assert partial_save.status_code == 200

    config = AppConfigService(db)
    assert config.get(f"{channel_id.split(':', 1)[0]}.request_timeout") == "23"
    for key, expected in preserved_config_keys.items():
        assert config.get(key) == expected


def test_digikala_is_coming_soon_and_all_operational_actions_are_non_actionable(
    client, auth_headers, monkeypatch
):
    class FailingAsyncClient:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Coming Soon must not construct a Digikala HTTP client")

    monkeypatch.setattr(
        "app.flowhub.channels.digikala.httpx.AsyncClient", FailingAsyncClient
    )

    channel = client.get(
        "/api/v2/commerce/channels/digikala:main", headers=auth_headers
    )
    assert channel.status_code == 200
    state = channel.json()
    assert state["implemented"] is True
    assert state["implementation_status"] == "IMPLEMENTED_UNVERIFIED"
    assert state["placeholder"] is True
    assert state["status"] == "coming_soon"
    assert state["availability"] == "coming_soon"
    assert state["operational_available"] is False
    assert state["actionable"] is False
    assert state["settings_available"] is False
    assert state["configuration_state"] == "coming_soon"
    assert state["credentials_verified"] is False
    assert state["health"]["error_code"] == "coming_soon"
    assert not any(state["capabilities"].values())
    assert state["capabilities_summary"] == ["Planned channel unavailable in 1.0.0"]

    test = client.post(
        "/api/v2/commerce/channels/digikala:main/test",
        headers=auth_headers,
        json={"secrets": {"access_token": "must-not-be-used"}},
    )
    assert test.status_code == 200
    assert test.json()["status"] == "coming_soon"
    assert test.json()["code"] == "CHANNEL_COMING_SOON"
    assert test.json()["external_call_performed"] is False
    assert "must-not-be-used" not in test.text

    configuration = client.get(
        "/api/v2/commerce/channels/digikala:main/configuration",
        headers=auth_headers,
    )
    save = client.put(
        "/api/v2/commerce/channels/digikala:main/settings",
        headers=auth_headers,
        json={"secrets": {"access_token": "must-not-be-persisted"}},
    )
    refresh = client.post(
        "/api/v2/commerce/channels/digikala:main/refresh-cache",
        headers=auth_headers,
    )
    for response in (configuration, save, refresh):
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "CHANNEL_COMING_SOON"
        assert "must-not-be-persisted" not in response.text


def test_snappshop_unsaved_credentials_can_test_and_return_vendor_choices(client, auth_headers, monkeypatch):
    class FakeResponse:
        status_code = 200
        headers = {}

        def json(self):
            return {"status": True, "data": [{"id": "vendor-1", "title": "Primary Vendor"}]}

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def request(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.flowhub.channels.snappshop.httpx.AsyncClient", lambda **kwargs: FakeAsyncClient())
    response = client.post(
        "/api/v2/commerce/channels/snappshop:main/test",
        headers=auth_headers,
        json={
            "settings": {"agent_identifier": "flowhub-agent", "request_timeout": 5},
            "secrets": {"token": "unsaved-secret"},
        },
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["vendors"] == [{
        "id": "vendor-1",
        "name": "Primary Vendor",
        "title": "Primary Vendor",
        "title_en": None,
        "status": None,
        "store_url": None,
        "reference_code": "vendor-1",
    }]
    assert response.json()["suggested_vendor_id"] == "vendor-1"
    assert "unsaved-secret" not in response.text


def test_snappshop_refresh_cache_fetches_all_pages_and_products_api_filters_local_cache(
    client, auth_headers, db, monkeypatch
):
    from app.flowhub.data_layer.health_service import ConnectorHealthService
    from app.flowhub.data_layer.models import DlConnectorHealth

    save = client.put(
        "/api/v2/commerce/channels/snappshop:main/settings",
        headers=auth_headers,
        json={
            "display_name": "SnappShop",
            "enabled": True,
            "access_mode": "read_only",
            "settings": {"agent_identifier": "flowhub-agent", "vendor_id": "vendor-1", "request_timeout": 29},
            "secrets": {"token": "snapp-secret"},
        },
    )
    assert save.status_code == 200
    ConnectorHealthService(db).upsert(
        "snappshop:main",
        "snappshop",
        "unhealthy",
        detail="Independent connection failure evidence.",
        error_class="authorization_failed",
    )
    connection_health = db.query(DlConnectorHealth).filter_by(
        connector_id="snappshop:main"
    ).one()
    health_checked_at = connection_health.checked_at
    health_last_success_at = connection_health.last_success_at

    class FakeResponse:
        status_code = 200
        headers = {}

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    class FakeAsyncClient:
        responses = [
            FakeResponse({
                "status": True,
                "data": [{"id": "p-1", "sku": "SKU-1", "title": "Product One", "price": 1000, "stock": 4, "active": True}],
                "meta": {"pagination": {"total": 2, "count": 1, "per_page": 20, "current_page": 1, "total_pages": 2, "links": {"next": "https://apix.snappshop.ir/automation/v1/vendors/vendor-1/products?page=2"}}},
            }),
            FakeResponse({
                "status": True,
                "data": [{"id": "p-2", "sku": "SKU-2", "title": "Product Two", "price": 2000, "stock": 0, "active": True}],
                "meta": {"pagination": {"total": 2, "count": 1, "per_page": 20, "current_page": 2, "total_pages": 2, "links": {"next": None}}},
            }),
        ]
        requests = []

        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def request(self, method, url, *, headers=None, params=None, json=None):
            self.requests.append({"method": method, "url": url, "headers": headers, "params": params})
            return self.responses.pop(0)

    monkeypatch.setattr("app.flowhub.channels.snappshop.httpx.AsyncClient", FakeAsyncClient)

    refresh = client.post(
        "/api/v2/commerce/channels/snappshop:main/refresh-cache",
        headers=auth_headers,
    )

    assert refresh.status_code == 200
    result = refresh.json()
    assert result["ok"] is True
    assert result["pages_read"] == 2
    assert result["products_received"] == 2
    assert result["products_stored"] == 2
    assert result["external_write"] is False
    assert [item["params"] for item in FakeAsyncClient.requests] == [{"page": 1}, {"page": 2}]

    products = client.get(
        "/api/v2/products?channelId=snappshop:main&page=1&pageSize=20",
        headers=auth_headers,
    )
    assert products.status_code == 200
    assert products.json()["total"] == 2
    assert {item["connectorId"] for item in products.json()["items"]} == {"snappshop:main"}
    assert {item["currency"] for item in products.json()["items"]} == {"TMN"}
    db.expire_all()
    connection_health = db.query(DlConnectorHealth).filter_by(
        connector_id="snappshop:main"
    ).one()
    assert connection_health.status == "unhealthy"
    assert connection_health.checked_at == health_checked_at
    assert connection_health.last_success_at == health_last_success_at
    assert connection_health.detail == "Independent connection failure evidence."


def test_successful_snappshop_configuration_commits_state_and_sanitized_audit(
    client, auth_headers, db
):
    from app.flowhub.integration_platform.models import IntegrationConnectorEvent, IntegrationConnectorInstance
    from app.flowhub.setup.models import FlowHubAppConfig

    token = "successful-snapp-token"
    response = client.put(
        "/api/v2/commerce/channels/snappshop:main/settings",
        headers=auth_headers,
        json={
            "display_name": "Primary SnappShop",
            "enabled": True,
            "access_mode": "read_only",
            "settings": {
                "base_url": "https://apix.snappshop.ir/automation/v1",
                "agent_identifier": "flowhub-agent",
                "agent_header_name": "Agent-User",
                "request_timeout": 22,
                "vendor_id": "vendor-22",
            },
            "secrets": {"token": token},
        },
    )

    assert response.status_code == 200
    assert token not in response.text
    db.expire_all()
    assert db.get(FlowHubAppConfig, "snappshop.token").value == token
    assert db.get(FlowHubAppConfig, "snappshop.agent_identifier").value == "flowhub-agent"
    assert db.get(FlowHubAppConfig, "snappshop.vendor_id").value == "vendor-22"
    instance = db.get(IntegrationConnectorInstance, "snappshop:main")
    assert instance.name == "Primary SnappShop"
    assert instance.enabled is True
    assert instance.read_only is True
    settings = {item.key: item.value_json for item in instance.settings if not item.secret}
    assert settings["base_url"] == "https://apix.snappshop.ir/automation/v1"
    assert settings["agent_identifier"] == "flowhub-agent"
    assert settings["agent_header_name"] == "Agent-User"
    assert settings["request_timeout"] == 22
    assert settings["vendor_id"] == "vendor-22"
    audit = db.query(IntegrationConnectorEvent).filter_by(
        connector_id="snappshop:main", event_name="channel_configuration_changed"
    ).one()
    assert audit.metadata_json["actor"].startswith("commerceadmin_")
    assert audit.metadata_json["channel_id"] == "snappshop:main"
    assert set(audit.metadata_json["changed_fields"]).issuperset({
        "base_url", "agent_identifier", "agent_header_name", "request_timeout",
        "vendor_id", "enabled", "access_mode",
    })
    assert audit.created_at is not None
    assert token not in str(audit.metadata_json)
    assert "Authorization" not in str(audit.metadata_json)


def test_successful_tapsishop_configuration_commits_state_and_sanitized_audit(
    client, auth_headers, db
):
    from app.flowhub.integration_platform.models import IntegrationConnectorEvent, IntegrationConnectorInstance
    from app.flowhub.setup.models import FlowHubAppConfig

    outbound_token = "successful-outbound-token"
    webhook_token = "successful-webhook-token"
    response = client.put(
        "/api/v2/commerce/channels/tapsishop:main/settings",
        headers=auth_headers,
        json={
            "display_name": "Primary TapsiShop",
            "enabled": True,
            "access_mode": "read_only",
            "settings": {
                "base_url": "https://vendorgw.tapsi.shop/Web/Hub/vendors/v1",
                "request_timeout": 25,
                "selected_vendor_id": "store-42",
                "token_refresh_enabled": True,
                "token_refresh_name": "FlowHub Refresh",
                "revoke_current_token": False,
            },
            "secrets": {"token": outbound_token, "webhook_token": webhook_token},
        },
    )

    assert response.status_code == 200
    assert outbound_token not in response.text
    assert webhook_token not in response.text
    db.expire_all()
    assert db.get(FlowHubAppConfig, "tapsishop.token").value == outbound_token
    assert db.get(FlowHubAppConfig, "tapsishop.webhook_token").value == webhook_token
    instance = db.get(IntegrationConnectorInstance, "tapsishop:main")
    assert instance.name == "Primary TapsiShop"
    assert instance.enabled is True
    assert instance.read_only is True
    settings = {item.key: item.value_json for item in instance.settings if not item.secret}
    assert settings["request_timeout"] == 25
    assert settings["selected_vendor_id"] == "store-42"
    assert settings["token_refresh_enabled"] is True
    assert settings["revoke_current_token"] is False
    audit = db.query(IntegrationConnectorEvent).filter_by(
        connector_id="tapsishop:main", event_name="channel_configuration_changed"
    ).one()
    assert audit.metadata_json["actor"].startswith("commerceadmin_")
    assert audit.metadata_json["channel_id"] == "tapsishop:main"
    assert set(audit.metadata_json["changed_fields"]).issuperset({
        "selected_vendor_id", "token_refresh_enabled", "revoke_current_token", "enabled", "access_mode"
    })
    assert audit.created_at is not None
    assert outbound_token not in str(audit.metadata_json)
    assert webhook_token not in str(audit.metadata_json)
    assert "Authorization" not in str(audit.metadata_json)
    configuration = client.get(
        "/api/v2/commerce/channels/tapsishop:main/configuration", headers=auth_headers
    ).json()
    assert configuration["settings"]["token_refresh_enabled"] is True
    assert configuration["settings"]["revoke_current_token"] is False


def test_snappshop_configuration_rolls_back_after_credential_staging_failure(
    client, auth_headers, db_engine, monkeypatch
):
    from fastapi import HTTPException
    from sqlalchemy.orm import sessionmaker

    from app.flowhub.integration_platform.models import (
        IntegrationConnectorEvent,
        IntegrationConnectorInstance,
    )
    from app.flowhub.integration_platform.service import IntegrationPlatformService
    from app.flowhub.setup.models import FlowHubAppConfig

    old_payload = {
        "display_name": "Old SnappShop",
        "enabled": False,
        "access_mode": "read_only",
        "settings": {
            "base_url": "https://old.snappshop.example/v1",
            "agent_identifier": "old-agent",
            "agent_header_name": "User-Agent",
            "request_timeout": 10,
            "vendor_id": "old-vendor",
        },
        "secrets": {"token": "old-snapp-token"},
    }
    assert client.put(
        "/api/v2/commerce/channels/snappshop:main/settings",
        headers=auth_headers,
        json=old_payload,
    ).status_code == 200

    def fail_settings(*args, **kwargs):
        raise HTTPException(500, "simulated connector settings failure")

    monkeypatch.setattr(IntegrationPlatformService, "stage_settings_contract", fail_settings)
    response = client.put(
        "/api/v2/commerce/channels/snappshop:main/settings",
        headers=auth_headers,
        json={
            "display_name": "New SnappShop",
            "enabled": True,
            "access_mode": "read_only",
            "settings": {
                "base_url": "https://new.snappshop.example/v1",
                "agent_identifier": "new-agent",
                "agent_header_name": "Agent-User",
                "request_timeout": 20,
                "vendor_id": "new-vendor",
            },
            "secrets": {"token": "new-snapp-token"},
        },
    )
    assert response.status_code == 500

    session = sessionmaker(bind=db_engine)()
    try:
        assert session.get(FlowHubAppConfig, "snappshop.token").value == "old-snapp-token"
        assert session.get(FlowHubAppConfig, "snappshop.base_url").value == "https://old.snappshop.example/v1"
        assert session.get(FlowHubAppConfig, "snappshop.vendor_id").value == "old-vendor"
        instance = session.get(IntegrationConnectorInstance, "snappshop:main")
        assert instance.name == "Old SnappShop"
        assert instance.enabled is False
        settings = {item.key: item.value_json for item in instance.settings if not item.secret}
        assert settings["agent_identifier"] == "old-agent"
        assert settings["vendor_id"] == "old-vendor"
        assert session.query(IntegrationConnectorEvent).filter_by(
            connector_id="snappshop:main", event_name="channel_configuration_changed"
        ).count() == 1
        assert session.query(IntegrationConnectorEvent).filter_by(
            connector_id="snappshop:main"
        ).count() == 2
    finally:
        session.close()


def test_woocommerce_configuration_rolls_back_after_credential_staging_failure(
    client, auth_headers, db_engine, monkeypatch
):
    """Woo AppConfig and write-only marker must commit together or not at all."""

    from fastapi import HTTPException
    from sqlalchemy.orm import sessionmaker

    from app.flowhub.integration_platform.models import IntegrationConnectorInstance
    from app.flowhub.integration_platform.service import IntegrationPlatformService
    from app.flowhub.setup.models import FlowHubAppConfig

    old_payload = {
        "enabled": True,
        "settings": {"url": "https://old.woocommerce.example.test"},
        "secrets": {"key": "old-woocommerce-key", "secret": "old-woocommerce-secret"},
    }
    assert client.put(
        "/api/v2/commerce/channels/woocommerce:primary/settings",
        headers=auth_headers,
        json=old_payload,
    ).status_code == 200

    def fail_settings(*args, **kwargs):
        raise HTTPException(500, "simulated connector settings failure")

    monkeypatch.setattr(IntegrationPlatformService, "stage_settings_contract", fail_settings)
    response = client.put(
        "/api/v2/commerce/channels/woocommerce:primary/settings",
        headers=auth_headers,
        json={
            "enabled": False,
            "settings": {"url": "https://new.woocommerce.example.test"},
            "secrets": {"key": "new-woocommerce-key", "secret": "new-woocommerce-secret"},
        },
    )
    assert response.status_code == 500

    session = sessionmaker(bind=db_engine)()
    try:
        assert session.get(FlowHubAppConfig, "woocommerce.url").value == old_payload["settings"]["url"]
        assert session.get(FlowHubAppConfig, "woocommerce.key").value == old_payload["secrets"]["key"]
        assert session.get(FlowHubAppConfig, "woocommerce.secret").value == old_payload["secrets"]["secret"]
        instance = session.get(IntegrationConnectorInstance, "woocommerce:primary")
        assert instance is not None
        assert instance.enabled is True
    finally:
        session.close()


def test_first_marketplace_configuration_failure_leaves_no_state(
    client, auth_headers, db_engine, monkeypatch
):
    from fastapi import HTTPException
    from sqlalchemy.orm import sessionmaker

    from app.flowhub.integration_platform.models import IntegrationConnectorEvent, IntegrationConnectorInstance
    from app.flowhub.integration_platform.service import IntegrationPlatformService
    from app.flowhub.setup.models import FlowHubAppConfig

    def fail_settings(*args, **kwargs):
        raise HTTPException(500, "simulated connector settings failure")

    monkeypatch.setattr(IntegrationPlatformService, "stage_settings_contract", fail_settings)
    response = client.put(
        "/api/v2/commerce/channels/snappshop:main/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": {"agent_identifier": "first-agent", "vendor_id": "first-vendor"},
            "secrets": {"token": "first-token"},
        },
    )
    assert response.status_code == 500

    session = sessionmaker(bind=db_engine)()
    try:
        assert session.get(FlowHubAppConfig, "snappshop.token") is None
        assert session.get(FlowHubAppConfig, "snappshop.agent_identifier") is None
        assert session.get(IntegrationConnectorInstance, "snappshop:main") is None
        assert session.query(IntegrationConnectorEvent).filter_by(
            connector_id="snappshop:main"
        ).count() == 0
    finally:
        session.close()


def test_tapsishop_configuration_rolls_back_both_secrets_and_refresh_state(
    client, auth_headers, db_engine, monkeypatch
):
    from fastapi import HTTPException
    from sqlalchemy.orm import sessionmaker

    from app.flowhub.integration_platform.models import IntegrationConnectorEvent, IntegrationConnectorInstance
    from app.flowhub.integration_platform.service import IntegrationPlatformService
    from app.flowhub.setup.models import FlowHubAppConfig

    assert client.put(
        "/api/v2/commerce/channels/tapsishop:main/settings",
        headers=auth_headers,
        json={
            "display_name": "Old TapsiShop",
            "enabled": False,
            "access_mode": "read_only",
            "settings": {
                "request_timeout": 10,
                "selected_vendor_id": "old-store",
                "token_refresh_enabled": False,
                "token_refresh_name": "Old Refresh",
                "revoke_current_token": False,
            },
            "secrets": {"token": "old-tapsi-token", "webhook_token": "old-webhook-token"},
        },
    ).status_code == 200

    def fail_settings(*args, **kwargs):
        raise HTTPException(500, "simulated connector settings failure")

    monkeypatch.setattr(IntegrationPlatformService, "stage_settings_contract", fail_settings)
    response = client.put(
        "/api/v2/commerce/channels/tapsishop:main/settings",
        headers=auth_headers,
        json={
            "display_name": "New TapsiShop",
            "enabled": True,
            "access_mode": "read_only",
            "settings": {
                "request_timeout": 20,
                "selected_vendor_id": "new-store",
                "token_refresh_enabled": True,
                "token_refresh_name": "New Refresh",
                "revoke_current_token": True,
            },
            "secrets": {"token": "new-tapsi-token", "webhook_token": "new-webhook-token"},
        },
    )
    assert response.status_code == 500

    session = sessionmaker(bind=db_engine)()
    try:
        assert session.get(FlowHubAppConfig, "tapsishop.token").value == "old-tapsi-token"
        assert session.get(FlowHubAppConfig, "tapsishop.webhook_token").value == "old-webhook-token"
        assert session.get(FlowHubAppConfig, "tapsishop.token_refresh_enabled").value == "false"
        instance = session.get(IntegrationConnectorInstance, "tapsishop:main")
        assert instance.name == "Old TapsiShop"
        assert instance.enabled is False
        settings = {item.key: item.value_json for item in instance.settings if not item.secret}
        assert settings["selected_vendor_id"] == "old-store"
        assert settings["token_refresh_enabled"] is False
        assert session.query(IntegrationConnectorEvent).filter_by(
            connector_id="tapsishop:main", event_name="channel_configuration_changed"
        ).count() == 1
        assert session.query(IntegrationConnectorEvent).filter_by(
            connector_id="tapsishop:main"
        ).count() == 2
    finally:
        session.close()


def test_marketplace_configuration_rolls_back_when_actor_audit_fails(
    client, auth_headers, db_engine, monkeypatch
):
    from fastapi import HTTPException
    from sqlalchemy.orm import sessionmaker

    from app.flowhub.integration_platform.models import IntegrationConnectorEvent, IntegrationConnectorInstance
    from app.flowhub.integration_platform.service import IntegrationPlatformService
    from app.flowhub.setup.models import FlowHubAppConfig

    assert client.put(
        "/api/v2/commerce/channels/snappshop:main/settings",
        headers=auth_headers,
        json={
            "display_name": "Audited SnappShop",
            "enabled": False,
            "settings": {"agent_identifier": "old-agent", "vendor_id": "old-vendor"},
            "secrets": {"token": "old-audited-token"},
        },
    ).status_code == 200
    original_record_event = IntegrationPlatformService.record_event

    def fail_actor_audit(self, **kwargs):
        if kwargs.get("event_name") == "channel_configuration_changed":
            raise HTTPException(500, "simulated audit failure")
        return original_record_event(self, **kwargs)

    monkeypatch.setattr(IntegrationPlatformService, "record_event", fail_actor_audit)
    response = client.put(
        "/api/v2/commerce/channels/snappshop:main/settings",
        headers=auth_headers,
        json={
            "display_name": "Unaudited SnappShop",
            "enabled": True,
            "settings": {"agent_identifier": "new-agent", "vendor_id": "new-vendor"},
            "secrets": {"token": "new-unaudited-token"},
        },
    )
    assert response.status_code == 500

    session = sessionmaker(bind=db_engine)()
    try:
        assert session.get(FlowHubAppConfig, "snappshop.token").value == "old-audited-token"
        instance = session.get(IntegrationConnectorInstance, "snappshop:main")
        assert instance.name == "Audited SnappShop"
        assert instance.enabled is False
        settings = {item.key: item.value_json for item in instance.settings if not item.secret}
        assert settings["agent_identifier"] == "old-agent"
        assert settings["vendor_id"] == "old-vendor"
        assert session.query(IntegrationConnectorEvent).filter_by(
            connector_id="snappshop:main", event_name="channel_configuration_changed"
        ).count() == 1
        assert session.query(IntegrationConnectorEvent).filter_by(
            connector_id="snappshop:main"
        ).count() == 2
    finally:
        session.close()


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

    install_nextcloud_download(monkeypatch, fail_download)
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

    # The acquisition boundary deliberately normalizes upstream transport
    # failures to its stable gateway response instead of reflecting raw status.
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["code"] == "upstream_rejected"
    assert detail["message"] == "Source acquisition failed."
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


_MARKETPLACE_SECRET_LIFECYCLE_CASES = (
    (
        "woocommerce:primary",
        {"url": "https://store.example.test"},
        {"key": "wc-initial-key", "secret": "wc-initial-secret"},
        {"key": "wc-replacement-key", "secret": "wc-replacement-secret"},
    ),
    (
        "tapsishop:main",
        {
            "base_url": "https://vendorgw.tapsi.shop/Web/Hub/vendors/v1",
            "request_timeout": 17,
            "selected_vendor_id": "tapsi-store-17",
        },
        {"token": "tapsi-initial-token", "webhook_token": "tapsi-initial-webhook"},
        {
            "token": "tapsi-replacement-token",
            "webhook_token": "tapsi-replacement-webhook",
        },
    ),
    (
        "technolife:main",
        {"base_url": "https://seller-api.technolife.com", "request_timeout": 17},
        {
            "api_key": "technolife-initial-key",
            "encryption_secret": "MDEyMzQ1Njc4OWFiY2RlZg==",
        },
        {
            "api_key": "technolife-replacement-key",
            "encryption_secret": "YWJjZGVmZ2hpamtsbW5vcA==",
        },
    ),
)


_CHANNEL_HEALTH_INVALIDATION_CASES = (
    *_MARKETPLACE_SECRET_LIFECYCLE_CASES,
    (
        "snappshop:main",
        {
            "base_url": "https://apix.snappshop.ir/automation/v1",
            "agent_identifier": "flowhub-health-agent",
            "agent_header_name": "User-Agent",
            "vendor_id": "health-vendor",
        },
        {"token": "snapp-health-initial-token"},
        {"token": "snapp-health-replacement-token"},
    ),
)


@pytest.mark.parametrize(
    ("channel_id", "settings", "initial_secrets", "replacement_secrets"),
    _MARKETPLACE_SECRET_LIFECYCLE_CASES,
)
def test_marketplace_secret_replacement_requires_save_and_stays_write_only_after_reload(
    client,
    auth_headers,
    db,
    channel_id,
    settings,
    initial_secrets,
    replacement_secrets,
):
    """Blank secret submissions preserve credentials; replacements persist only on Save."""

    from app.flowhub.setup.service import AppConfigService

    provider = channel_id.split(":", 1)[0]
    initial_save = client.put(
        f"/api/v2/commerce/channels/{channel_id}/settings",
        headers=auth_headers,
        json={
            "enabled": True,
            "settings": dict(settings),
            "secrets": dict(initial_secrets),
        },
    )
    assert initial_save.status_code == 200
    assert all(value not in initial_save.text for value in initial_secrets.values())

    first_reload = client.get(
        f"/api/v2/commerce/channels/{channel_id}/configuration",
        headers=auth_headers,
    )
    assert first_reload.status_code == 200
    assert first_reload.json()["enabled"] is True
    for key, value in initial_secrets.items():
        assert first_reload.json()["secrets"][key]["status"] == "configured"
        assert value not in first_reload.text

    blank_save = client.put(
        f"/api/v2/commerce/channels/{channel_id}/settings",
        headers=auth_headers,
        json={"secrets": {key: "" for key in initial_secrets}},
    )
    assert blank_save.status_code == 200
    config = AppConfigService(db)
    for key, value in initial_secrets.items():
        assert config.get(f"{provider}.{key}") == value

    blank_reload = client.get(
        f"/api/v2/commerce/channels/{channel_id}/configuration",
        headers=auth_headers,
    )
    assert blank_reload.status_code == 200
    for key, value in initial_secrets.items():
        assert blank_reload.json()["secrets"][key]["status"] == "configured"
        assert value not in blank_reload.text

    replacement_save = client.put(
        f"/api/v2/commerce/channels/{channel_id}/settings",
        headers=auth_headers,
        json={"secrets": dict(replacement_secrets)},
    )
    assert replacement_save.status_code == 200
    assert all(value not in replacement_save.text for value in replacement_secrets.values())
    for key, value in replacement_secrets.items():
        assert config.get(f"{provider}.{key}") == value

    replaced_reload = client.get(
        f"/api/v2/commerce/channels/{channel_id}/configuration",
        headers=auth_headers,
    )
    assert replaced_reload.status_code == 200
    for key, value in replacement_secrets.items():
        assert replaced_reload.json()["secrets"][key]["status"] == "configured"
        assert value not in replaced_reload.text
        assert initial_secrets[key] not in replaced_reload.text


@pytest.mark.parametrize(
    "changed_channel_id",
    [case[0] for case in _MARKETPLACE_SECRET_LIFECYCLE_CASES],
)
def test_marketplace_secret_save_does_not_overwrite_another_provider(
    client, auth_headers, db, changed_channel_id
):
    """Provider-specific AppConfig keys prevent one channel from replacing another's secret."""

    from app.flowhub.setup.service import AppConfigService

    by_channel = {
        channel_id: (settings, initial_secrets, replacement_secrets)
        for channel_id, settings, initial_secrets, replacement_secrets
        in _MARKETPLACE_SECRET_LIFECYCLE_CASES
    }
    for channel_id, (settings, initial_secrets, _replacement_secrets) in by_channel.items():
        saved = client.put(
            f"/api/v2/commerce/channels/{channel_id}/settings",
            headers=auth_headers,
            json={
                "enabled": True,
                "settings": dict(settings),
                "secrets": dict(initial_secrets),
            },
        )
        assert saved.status_code == 200

    _settings, _initial, replacements = by_channel[changed_channel_id]
    replaced = client.put(
        f"/api/v2/commerce/channels/{changed_channel_id}/settings",
        headers=auth_headers,
        json={"secrets": dict(replacements)},
    )
    assert replaced.status_code == 200

    config = AppConfigService(db)
    all_secret_values = {
        value
        for _channel_id, _settings, initial_secrets, replacement_secrets
        in _MARKETPLACE_SECRET_LIFECYCLE_CASES
        for value in (*initial_secrets.values(), *replacement_secrets.values())
    }
    for channel_id, (_settings, initial_secrets, replacement_secrets) in by_channel.items():
        provider = channel_id.split(":", 1)[0]
        expected = replacement_secrets if channel_id == changed_channel_id else initial_secrets
        for key, value in expected.items():
            assert config.get(f"{provider}.{key}") == value

        reload = client.get(
            f"/api/v2/commerce/channels/{channel_id}/configuration",
            headers=auth_headers,
        )
        assert reload.status_code == 200
        assert all(value not in reload.text for value in all_secret_values)
        for key in expected:
            assert reload.json()["secrets"][key]["status"] == "configured"


@pytest.mark.parametrize(
    ("channel_id", "settings", "initial_secrets", "replacement_secrets"),
    _CHANNEL_HEALTH_INVALIDATION_CASES,
)
def test_connection_setting_replacement_invalidates_health_but_blank_secret_save_preserves_it(
    client,
    auth_headers,
    db,
    channel_id,
    settings,
    initial_secrets,
    replacement_secrets,
):
    """Healthy evidence is tied to the saved connection identity, not merely its age."""

    from app.flowhub.data_layer.health_service import ConnectorHealthService
    from app.flowhub.data_layer.models import DlConnectorHealth

    assert client.put(
        f"/api/v2/commerce/channels/{channel_id}/settings",
        headers=auth_headers,
        json={"enabled": True, "settings": dict(settings), "secrets": dict(initial_secrets)},
    ).status_code == 200
    ConnectorHealthService(db).upsert(
        connector_id=channel_id,
        connector_type=channel_id.split(":", 1)[0],
        status="healthy",
        detail="Saved configuration was verified.",
    )

    # A blank write-only field means keep the saved credential, so the probe
    # remains evidence for the same configuration.
    assert client.put(
        f"/api/v2/commerce/channels/{channel_id}/settings",
        headers=auth_headers,
        json={"display_name": "Verified channel", "secrets": {key: "" for key in initial_secrets}},
    ).status_code == 200
    db.expire_all()
    preserved = client.get(
        f"/api/v2/commerce/channels/{channel_id}", headers=auth_headers
    ).json()
    assert preserved["status"] == "healthy"
    assert preserved["credentials_verified"] is True

    # Replacing an actual credential is a Save, but the old successful test
    # must no longer be presented as verification for the new credential.
    assert client.put(
        f"/api/v2/commerce/channels/{channel_id}/settings",
        headers=auth_headers,
        json={"secrets": dict(replacement_secrets)},
    ).status_code == 200
    db.expire_all()
    assert db.query(DlConnectorHealth).filter_by(connector_id=channel_id).one_or_none() is None
    invalidated = client.get(
        f"/api/v2/commerce/channels/{channel_id}", headers=auth_headers
    ).json()
    assert invalidated["status"] == "configured"
    assert invalidated["configuration_state"] == "configured"
    assert invalidated["credentials_verified"] is False
    assert invalidated["health"]["status"] == "unknown"


@pytest.mark.parametrize(
    ("channel_id", "settings", "secrets"),
    (
        (
            "snappshop:main",
            {"agent_identifier": "timeout-agent", "vendor_id": "timeout-vendor", "request_timeout": 15},
            {"token": "snapp-timeout-token"},
        ),
        (
            "tapsishop:main",
            {"selected_vendor_id": "timeout-vendor", "request_timeout": 15},
            {"token": "tapsi-timeout-token"},
        ),
        (
            "technolife:main",
            {"request_timeout": 15},
            {"api_key": "technolife-timeout-key", "encryption_secret": "MDEyMzQ1Njc4OWFiY2RlZg=="},
        ),
    ),
)
def test_test_connection_timeout_change_invalidates_prior_health_evidence(
    client, auth_headers, db, channel_id, settings, secrets
):
    from app.flowhub.data_layer.health_service import ConnectorHealthService
    from app.flowhub.data_layer.models import DlConnectorHealth

    assert client.put(
        f"/api/v2/commerce/channels/{channel_id}/settings",
        headers=auth_headers,
        json={"enabled": True, "settings": settings, "secrets": secrets},
    ).status_code == 200
    ConnectorHealthService(db).upsert(
        connector_id=channel_id,
        connector_type=channel_id.split(":", 1)[0],
        status="healthy",
        detail="Saved timeout configuration was verified.",
    )

    assert client.put(
        f"/api/v2/commerce/channels/{channel_id}/settings",
        headers=auth_headers,
        json={"settings": {"request_timeout": 30}},
    ).status_code == 200
    db.expire_all()
    assert db.query(DlConnectorHealth).filter_by(connector_id=channel_id).one_or_none() is None
    state = client.get(f"/api/v2/commerce/channels/{channel_id}", headers=auth_headers).json()
    assert state["credentials_verified"] is False
    assert state["health"]["status"] == "unknown"


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
