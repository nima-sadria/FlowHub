"""Integration Platform wiring readiness tests."""

from __future__ import annotations

import os
import pathlib

import pytest

os.environ.setdefault("FLOWHUB_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FLOWHUB_JWT_SECRET", "test-ip-wiring-jwt-secret-32bytes!")

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

    user = FlowHubUser(username="ipadmin", hashed_password=hash_password("password123"), role="admin")
    db.add(user)
    db.commit()
    response = client.post("/api/auth/login", json={"username": "ipadmin", "password": "password123"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_migration_creates_integration_platform_tables(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    db_path = tmp_path / "FLOWHUB.sqlite"
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", f"sqlite:///{db_path}")
    cfg = Config("alembic_flowhub.ini")
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    tables = set(inspect(engine).get_table_names())
    assert {
        "ip_connector_instances",
        "ip_connector_settings",
        "ip_connector_health_snapshots",
        "ip_connector_events",
    }.issubset(tables)
    engine.dispose()


def test_canonical_capability_schema_baseline():
    from app.flowhub.integration_platform.contracts import ConnectorCapabilities, ConnectorHealthStatus
    from app.flowhub.integration_platform.registry import registry

    caps = ConnectorCapabilities().model_dump()
    assert set(caps) == {
        "read_products",
        "read_categories",
        "read_inventory",
        "read_orders",
        "write_prices",
        "write_inventory",
        "webhook",
        "polling",
        "oauth",
        "api_key",
        "supports_modified_since",
        "supports_delta_sync",
        "supports_updated_after",
        "supports_pagination",
        "supports_batch_read",
    }
    statuses = {item.value for item in ConnectorHealthStatus}
    assert statuses == {
        "healthy",
        "warning",
        "error",
        "disabled",
        "degraded",
        "authentication_failed",
        "rate_limited",
        "timeout",
    }
    woo = registry.get_definition("woocommerce")
    assert woo is not None
    assert woo.connector.capabilities.write_prices is True
    assert woo.connector.capability_authorizes_write is False


def test_direct_call_audit_for_active_FLOWHUB_v2_routes():
    root = pathlib.Path("app/flowhub/api/v2")
    forbidden = (
        "app.flowhub.integrations.woocommerce",
        "app.flowhub.integrations.nextcloud",
        "app.services.woocommerce",
        "app.services.nextcloud",
        "app.connectors.destinations.woocommerce",
        "app.connectors.sources.nextcloud",
        "import httpx",
        "from httpx",
        "httpx.",
    )
    offenders: list[str] = []
    for path in root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                offenders.append(f"{path}:{token}")
    assert offenders == []


def test_legacy_connector_mutations_require_admin(client, auth_headers, db):
    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.auth.password import hash_password

    viewer = FlowHubUser(username="integrationviewer", hashed_password=hash_password("password123"), role="viewer")
    db.add(viewer)
    db.commit()
    login = client.post("/api/auth/login", json={"username": "integrationviewer", "password": "password123"})
    viewer_headers = {"Authorization": f"Bearer {login.json()['token']}"}
    create_body = {"connector_type": "nextcloud", "id": "nextcloud:blocked", "name": "Blocked"}

    assert client.post("/api/v2/integrations/connectors", headers=viewer_headers, json=create_body).status_code == 403
    assert client.post("/api/v2/integrations/connectors", headers=auth_headers, json=create_body).status_code == 201
    response = client.patch(
        "/api/v2/integrations/connectors/nextcloud:blocked/settings",
        headers=viewer_headers,
        json={"settings": [{"key": "url", "value": "https://cloud.example.test"}]},
    )
    assert response.status_code == 403


def test_products_route_reads_data_layer_records(client, auth_headers, db):
    from app.flowhub.data_layer.product_service import ProductReadModelService
    from app.flowhub.setup.service import AppConfigService

    AppConfigService(db).set_many(
        {
            "woocommerce.url": "https://store.example.com",
            "woocommerce.key": "ck",
            "woocommerce.secret": "cs",
            "server.currency": "EUR",
        }
    )
    ProductReadModelService(db).upsert(
        "woocommerce:primary",
        "42",
        {
            "external_id": 42,
            "name": "Widget",
            "sku": "W-1",
            "price": "12.50",
            "categories": [{"id": 3, "name": "Tools"}],
            "product_type": "simple",
            "status": "publish",
        },
    )

    response = client.get("/api/v2/products", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["items"][0]["name"] == "Widget"
    assert data["items"][0]["currentPrice"] == 12.5
    assert data["runtime_write_blocked"] is True


def _seed_product(
    db,
    *,
    product_id: str,
    name: str,
    sku: str,
    category_id: int,
    category_name: str,
    product_type: str,
) -> None:
    from app.flowhub.data_layer.product_service import ProductReadModelService

    ProductReadModelService(db).upsert(
        "woocommerce:primary",
        product_id,
        {
            "external_id": int(product_id),
            "name": name,
            "sku": sku,
            "price": "10.00",
            "categories": [{"id": category_id, "name": category_name}],
            "product_type": product_type,
            "status": "publish",
        },
    )


def _configure_woocommerce(db) -> None:
    from app.flowhub.setup.service import AppConfigService

    AppConfigService(db).set_many(
        {
            "woocommerce.url": "https://store.example.com",
            "woocommerce.key": "ck",
            "woocommerce.secret": "cs",
        }
    )


def test_products_route_filters_by_category_id(client, auth_headers, db):
    _configure_woocommerce(db)
    _seed_product(
        db,
        product_id="101",
        name="Hammer",
        sku="HAM-1",
        category_id=7,
        category_name="Tools",
        product_type="simple",
    )
    _seed_product(
        db,
        product_id="102",
        name="Notebook",
        sku="N-1",
        category_id=8,
        category_name="Stationery",
        product_type="simple",
    )

    response = client.get("/api/v2/products?categoryId=7", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "Hammer"


def test_products_route_filters_by_product_type(client, auth_headers, db):
    _configure_woocommerce(db)
    _seed_product(
        db,
        product_id="201",
        name="Simple mug",
        sku="MUG-S",
        category_id=4,
        category_name="Home",
        product_type="simple",
    )
    _seed_product(
        db,
        product_id="202",
        name="Variable hoodie",
        sku="HOOD-V",
        category_id=4,
        category_name="Home",
        product_type="variable",
    )

    response = client.get("/api/v2/products?productType=variable", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["productType"] == "variable"


def test_products_route_preserves_search_filter(client, auth_headers, db):
    _configure_woocommerce(db)
    _seed_product(
        db,
        product_id="301",
        name="Blue Bottle",
        sku="BOT-BLUE",
        category_id=5,
        category_name="Drinkware",
        product_type="simple",
    )
    _seed_product(
        db,
        product_id="302",
        name="Red Cup",
        sku="CUP-RED",
        category_id=5,
        category_name="Drinkware",
        product_type="simple",
    )

    response = client.get("/api/v2/products?search=BLUE", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["sku"] == "BOT-BLUE"


def test_products_route_preserves_pagination(client, auth_headers, db):
    _configure_woocommerce(db)
    for product_id, name in [("401", "Alpha"), ("402", "Bravo"), ("403", "Charlie")]:
        _seed_product(
            db,
            product_id=product_id,
            name=name,
            sku=f"SKU-{product_id}",
            category_id=6,
            category_name="Sorted",
            product_type="simple",
        )

    response = client.get("/api/v2/products?page=2&pageSize=1", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert data["page"] == 2
    assert data["pageSize"] == 1
    assert [item["name"] for item in data["items"]] == ["Bravo"]


def test_sources_route_reads_integration_platform_and_data_layer(client, auth_headers, db):
    from app.flowhub.data_layer.snapshot_service import SourceSnapshotService
    from app.flowhub.setup.service import AppConfigService

    AppConfigService(db).set_many(
        {
            "nextcloud.url": "https://cloud.example.com",
            "nextcloud.username": "user",
            "nextcloud.password": "pass",
            "nextcloud.spreadsheet_path": "/prices.xlsx",
        }
    )
    SourceSnapshotService(db).upsert("nextcloud:primary", "/prices.xlsx", etag="abc", parsed_row_count=10)
    response = client.get("/api/v2/sources", headers=auth_headers)
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["connector_id"] == "nextcloud:primary"
    assert item["status"] == "active"
    assert item["lastSynced"] is not None


def test_workspace_routes_are_read_only(client, auth_headers, db):
    response = client.get("/api/v2/workspace", headers=auth_headers)
    assert response.status_code == 200
    summary = response.json()
    assert summary["runtime_write_blocked"] is True
    assert summary["apply_available"] is False
    assert summary["scheduler_available"] is False
    assert summary["pricing_automation_available"] is False

    preview = client.post("/api/v2/workspace/preview", headers=auth_headers)
    assert preview.status_code == 422
    assert "Missing required setting" in preview.text


def test_diagnostics_run_uses_records_only(client, auth_headers, db):
    response = client.post("/api/v2/diagnostics/run", headers=auth_headers, json={"target": "woocommerce"})
    assert response.status_code == 200
    data = response.json()
    assert data["summary"].endswith("records only.")
    assert all(check["details"]["external_call_performed"] is False for check in data["checks"])


def test_settings_secret_masking_and_telemetry(client, auth_headers):
    created = client.post(
        "/api/v2/integrations/connectors",
        headers=auth_headers,
        json={"connector_type": "woocommerce", "id": "wc-main", "name": "Main store"},
    )
    assert created.status_code == 201
    updated = client.patch(
        "/api/v2/integrations/connectors/wc-main/settings",
        headers=auth_headers,
        json={"settings": [{"key": "secret", "value": "cs_secret", "secret": True}]},
    )
    assert updated.status_code == 200
    assert "cs_secret" not in updated.text
    settings = client.get("/api/v2/config", headers=auth_headers)
    assert settings.status_code == 200
    assert "configured" in settings.text
    assert "cs_secret" not in settings.text
    telemetry = client.get("/api/v2/integrations/telemetry", headers=auth_headers)
    assert telemetry.status_code == 200
    assert telemetry.json()["total"] >= 1


def test_write_safety_no_execution_routes(client, auth_headers):
    paths = [route.path.lower() for route in client.app.routes if hasattr(route, "path")]
    joined = " ".join(path for path in paths if "/api/v2/integrations" in path or "/api/v2/workspace" in path)
    assert "apply" not in joined
    assert "scheduler" not in joined
    assert "pricing" not in joined
    assert "execute" not in joined
