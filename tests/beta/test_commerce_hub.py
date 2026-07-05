from __future__ import annotations

import os

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
    from app.flowhub.auth.password import hash_password

    user = FlowHubUser(username="commerceadmin", hashed_password=hash_password("password123"), role="admin")
    db.add(user)
    db.commit()
    response = client.post("/api/auth/login", json={"username": "commerceadmin", "password": "password123"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


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


def test_snapp_tapsi_registry_placeholders_are_read_only():
    from app.flowhub.integration_platform.registry import registry

    for provider in ("snappshop", "tapsishop"):
        definition = registry.get_definition(provider)
        assert definition is not None
        assert definition.connector.identity.read_only is True
        assert definition.connector.capabilities.read_products is True
        assert definition.connector.capabilities.write_prices is False
        assert definition.connector.capabilities.write_inventory is False


def test_placeholder_connection_test_does_not_call_external_system(client, auth_headers):
    response = client.post("/api/v2/commerce/channels/snappshop:main/test", headers=auth_headers, json={})

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["external_call_performed"] is False
    assert data["read_only"] is True
    assert data["runtime_write_blocked"] is True
    assert data["write_blocked"] is True


def test_channel_detail_health_and_capabilities(client, auth_headers):
    detail = client.get("/api/v2/commerce/channels/woocommerce:primary", headers=auth_headers)
    health = client.get("/api/v2/commerce/channels/woocommerce:primary/health", headers=auth_headers)
    capabilities = client.get("/api/v2/commerce/channels/woocommerce:primary/capabilities", headers=auth_headers)

    assert detail.status_code == 200
    assert detail.json()["name"] == "WooCommerce"
    assert detail.json()["read_only"] is True
    assert detail.json()["write_blocked"] is True
    assert health.status_code == 200
    assert health.json()["runtime_write_blocked"] is True
    assert capabilities.status_code == 200
    assert capabilities.json()["capability_authorizes_write"] is False
    assert capabilities.json()["runtime_write_blocked"] is True


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
    assert data["runtime_write_blocked"] is True
    assert data["secrets"]["api_key"]["status"] == "configured"

    detail = client.get("/api/v2/commerce/channels/snappshop:main", headers=auth_headers)
    assert detail.status_code == 200
    assert "snapp-secret-value" not in detail.text
    assert detail.json()["credential_status"] == "configured"


def test_commerce_routes_do_not_expose_write_execution(client):
    paths = [route.path.lower() for route in client.app.routes if hasattr(route, "path")]
    commerce_paths = " ".join(path for path in paths if "/api/v2/commerce" in path)
    assert "apply" not in commerce_paths
    assert "scheduler" not in commerce_paths
    assert "pricing" not in commerce_paths
    assert "write" not in commerce_paths
