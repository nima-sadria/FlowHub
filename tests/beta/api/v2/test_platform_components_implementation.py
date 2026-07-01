"""Platform component implementation tests."""

from __future__ import annotations

import os
import pathlib

import pytest

os.environ.setdefault("BETA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("BETA_JWT_SECRET", "test-platform-components-jwt-secret!")

from app.beta.auth import models as _auth_models  # noqa: F401
from app.beta.data_layer import models as _dl_models  # noqa: F401
from app.beta.integration_platform import models as _ip_models  # noqa: F401
from app.beta.logging_platform import models as _logging_models  # noqa: F401
from app.beta.setup import models as _setup_models  # noqa: F401


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
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(client, db):
    from app.beta.auth.models import BetaUser
    from app.beta.auth.password import hash_password

    user = BetaUser(username="platformadmin", hashed_password=hash_password("password123"), role="admin")
    db.add(user)
    db.commit()
    response = client.post("/api/auth/login", json={"username": "platformadmin", "password": "password123"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_beta_007_migration_creates_platform_component_tables(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect

    db_path = tmp_path / "beta.sqlite"
    monkeypatch.setenv("BETA_DATABASE_URL", f"sqlite:///{db_path}")
    cfg = Config("alembic_beta.ini")
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    tables = set(inspect(engine).get_table_names())
    assert {
        "ip_connector_instances",
        "ip_connector_diagnostics",
        "ip_connector_telemetry",
        "ip_webhook_events",
        "ip_polling_policies",
        "logging_entries",
        "logging_correlations",
        "logging_request_traces",
        "logging_retention_policies",
        "logging_export_events",
        "logging_redaction_policy_versions",
    }.issubset(tables)
    engine.dispose()


def test_integration_platform_canonical_contracts_and_write_guard(client, auth_headers):
    create = client.post(
        "/api/v2/integration-platform/connectors",
        headers=auth_headers,
        json={
            "connector_type": "woocommerce",
            "id": "woocommerce:test",
            "name": "Test WooCommerce",
            "settings": {
                "url": "https://store.example.com",
                "key": "ck_test",
                "secret": "cs_test",
            },
        },
    )
    assert create.status_code == 201
    connector = create.json()
    assert connector["capabilities"]["write_prices"] is True
    assert connector["capability_authorizes_write"] is False
    assert connector["read_only"] is True

    settings = client.get("/api/v2/integration-platform/connectors/woocommerce:test/settings", headers=auth_headers)
    assert settings.status_code == 200
    body = settings.json()
    assert body["settings"]["url"] == "https://store.example.com"
    assert "key" not in body["settings"]
    assert body["secrets"]["key"]["status"] == "configured"
    assert "ck_test" not in str(body)

    write = client.post(
        "/api/v2/integration-platform/connectors/woocommerce:test/write-test",
        headers=auth_headers,
        json={"operation": "write_prices"},
    )
    assert write.status_code == 200
    assert write.json() == {
        "allowed": False,
        "status": "blocked",
        "error_code": "write_blocked_beta",
        "message": "Write operations are disabled in FlowHub Beta.",
        "capability_advertised": True,
        "authorization_granted": False,
        "execution_attempted": False,
        "correlation_id": write.json()["correlation_id"],
    }


def test_integration_platform_diagnostics_polling_webhook_are_safe(client, auth_headers):
    client.post(
        "/api/v2/integration-platform/connectors",
        headers=auth_headers,
        json={"connector_type": "nextcloud", "id": "nextcloud:test", "name": "Test Nextcloud"},
    )

    diagnostics = client.post(
        "/api/v2/integration-platform/connectors/nextcloud:test/diagnostics/run",
        headers=auth_headers,
    )
    assert diagnostics.status_code == 200
    assert diagnostics.json()["connector_id"] == "nextcloud:test"

    polling = client.put(
        "/api/v2/integration-platform/connectors/nextcloud:test/polling",
        headers=auth_headers,
        json={"enabled": True, "interval_seconds": 900},
    )
    assert polling.status_code == 200
    assert polling.json()["enabled"] is True
    assert polling.json()["scheduler_implemented"] is False

    webhook = client.post(
        "/api/v2/integration-platform/webhooks/nextcloud/nextcloud:test",
        json={"event": "changed", "token": "must-redact"},
    )
    assert webhook.status_code == 200
    assert webhook.json()["accepted"] is True


def test_logging_platform_ingestion_search_redaction_retention(client, auth_headers):
    ingest = client.post(
        "/api/v2/logging/frontend",
        headers=auth_headers,
        json={
            "logs": [
                {
                    "severity": "error",
                    "category": "API Errors",
                    "component": "ProductBrowser",
                    "module": "frontend",
                    "operation": "fetch_products",
                    "message": "Product request failed.",
                    "correlation_id": "corr_test",
                    "request_id": "req_test",
                    "result": "failed",
                    "details": {"consumer_secret": "cs_test", "status": 500},
                }
            ]
        },
    )
    assert ingest.status_code == 200
    assert ingest.json()["accepted"] == 1

    logs = client.get("/api/v2/logging/logs?severity=error", headers=auth_headers)
    assert logs.status_code == 200
    item = logs.json()["items"][0]
    assert item["correlation_id"] == "corr_test"
    assert item["severity"] == "error"

    detail = client.get(f"/api/v2/logging/logs/{item['id']}", headers=auth_headers)
    assert detail.status_code == 200
    assert detail.json()["item"]["structured"]["consumer_secret"] == "[REDACTED]"
    assert "cs_test" not in str(detail.json())

    retention = client.get("/api/v2/logging/retention", headers=auth_headers)
    assert retention.status_code == 200
    policies = {item["category"]: item["retention_days"] for item in retention.json()["policies"]}
    assert policies["operational"] == 30
    assert policies["connector_telemetry"] == 90
    assert policies["audit_security"] == 365


def test_direct_call_and_write_safety_audit_for_beta_v2_routes():
    root = pathlib.Path("app/beta/api/v2")
    forbidden = (
        "app.beta.integrations.woocommerce",
        "app.beta.integrations.nextcloud",
        "app.services.woocommerce",
        "app.services.nextcloud",
        "app.connectors.destinations.woocommerce",
        "app.connectors.sources.nextcloud",
        "import httpx",
        "from httpx",
        "httpx.",
        "batch_update_prices",
        "update_single_product",
        "write_back_to_sheet",
        "write_price_to_sheet",
    )
    offenders: list[str] = []
    for path in root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                offenders.append(f"{path}:{token}")
    assert offenders == []
