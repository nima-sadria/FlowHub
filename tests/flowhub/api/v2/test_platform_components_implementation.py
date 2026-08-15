"""Platform component implementation tests."""

from __future__ import annotations

import asyncio
import os
import pathlib
import hmac
from hashlib import sha256

import pytest

os.environ.setdefault("FLOWHUB_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FLOWHUB_JWT_SECRET", "test-platform-components-jwt-secret!")

from app.flowhub.auth import models as _auth_models  # noqa: F401
from app.flowhub.data_layer import models as _dl_models  # noqa: F401
from app.flowhub.integration_platform import models as _ip_models  # noqa: F401
from app.flowhub.logging_platform import models as _logging_models  # noqa: F401
from app.flowhub.orders import models as _order_models  # noqa: F401
from app.flowhub.pricing_matrix import models as _pricing_matrix_models  # noqa: F401
from app.flowhub.setup import models as _setup_models  # noqa: F401
from app.flowhub.source_acquisition import models as _source_acquisition_models  # noqa: F401
from app.flowhub.source_workspace import models as _source_workspace_models  # noqa: F401
from app.flowhub.unified_workspace import models as _unified_workspace_models  # noqa: F401


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
    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.auth.password import hash_password

    user = FlowHubUser(username="platformadmin", hashed_password=hash_password("password123"), role="admin")
    db.add(user)
    db.commit()
    response = client.post("/api/auth/login", json={"username": "platformadmin", "password": "password123"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture()
def viewer_headers(client, db):
    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.auth.password import hash_password

    user = FlowHubUser(username="platformviewer", hashed_password=hash_password("password123"), role="viewer")
    db.add(user)
    db.commit()
    response = client.post("/api/auth/login", json={"username": "platformviewer", "password": "password123"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _create_linked_nextcloud_source(client, auth_headers, db, connector_id):
    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.source_workspace.service import SourceWorkspaceService

    created = client.post(
        "/api/v2/integration-platform/connectors",
        headers=auth_headers,
        json={
            "connector_type": "nextcloud",
            "id": connector_id,
            "name": "Linked Nextcloud",
            "settings": {
                "url": "https://cloud.example.test",
                "username": "platform-owner",
                "spreadsheet_path": "/identity.xlsx",
            },
        },
    )
    assert created.status_code == 201
    owner = db.query(FlowHubUser).filter_by(username="platformadmin").one()
    return SourceWorkspaceService(db).create_source(
        name="Linked Source",
        source_kind="external",
        external_source_id=connector_id,
        worksheet_mode="all",
        worksheet_name=None,
        data_start_row=2,
        user=owner,
    )


def test_FLOWHUB_007_migration_creates_platform_component_tables(tmp_path, monkeypatch):
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
        "error_code": "write_blocked_FLOWHUB",
        "message": "Write operations are disabled in FlowHub.",
        "capability_advertised": True,
        "authorization_granted": False,
        "execution_attempted": False,
        "correlation_id": write.json()["correlation_id"],
    }


def test_digikala_is_coming_soon_on_every_public_integration_platform_path(db, client, auth_headers):
    """The retained backend definition must not create a second configurable UI/API path."""
    from app.flowhub.integration_platform.models import IntegrationConnectorInstance
    from app.flowhub.integration_platform.registry import registry

    # The internal foundation is intentionally retained for future conformance
    # work, including its OAuth declaration.  Public API projections must not
    # expose it as an actionable capability.
    internal = registry.get_definition("digikala")
    assert internal is not None
    assert internal.connector.capabilities.oauth is True
    assert internal.settings_schema

    canonical_definition = client.get(
        "/api/v2/integration-platform/registry/digikala",
        headers=auth_headers,
    )
    assert canonical_definition.status_code == 200
    public = canonical_definition.json()
    assert public["status"] == "coming_soon"
    assert public["availability"] == "coming_soon"
    assert public["actionable"] is False
    assert public["implementation_status"] == "IMPLEMENTED_UNVERIFIED"
    assert not any(public["capabilities"].values())
    assert public["settings_schema"] == []
    assert public["secret_fields"] == []
    assert public["diagnostic_checks"] == []

    legacy_definition = client.get(
        "/api/v2/integrations/registry/digikala",
        headers=auth_headers,
    )
    assert legacy_definition.status_code == 200
    legacy_public = legacy_definition.json()
    assert legacy_public["availability"] == "coming_soon"
    assert legacy_public["actionable"] is False
    assert not any(legacy_public["connector"]["capabilities"].values())
    assert legacy_public["settings_schema"] == []

    instance = IntegrationConnectorInstance(
        id="digikala:retained-foundation",
        connector_type="digikala",
        name="Digikala",
        version="1.0.0",
        enabled=True,
        read_only=True,
        status="healthy",
    )
    db.add(instance)
    db.commit()

    canonical_instance = client.get(
        "/api/v2/integration-platform/connectors/digikala:retained-foundation/health",
        headers=auth_headers,
    )
    assert canonical_instance.status_code == 200
    assert canonical_instance.json()["status"] == "coming_soon"
    assert canonical_instance.json()["error_code"] == "channel_coming_soon"

    canonical_instances = client.get(
        "/api/v2/integration-platform/connectors",
        headers=auth_headers,
    )
    assert canonical_instances.status_code == 200
    canonical_item = next(
        item
        for item in canonical_instances.json()["items"]
        if item["id"] == "digikala:retained-foundation"
    )
    assert canonical_item["status"] == "coming_soon"
    assert canonical_item["availability"] == "coming_soon"
    assert canonical_item["actionable"] is False
    assert not any(canonical_item["capabilities"].values())

    legacy_instance = client.get(
        "/api/v2/integrations/connectors/digikala:retained-foundation",
        headers=auth_headers,
    )
    assert legacy_instance.status_code == 200
    legacy_instance_body = legacy_instance.json()
    assert legacy_instance_body["availability"] == "coming_soon"
    assert legacy_instance_body["actionable"] is False
    assert legacy_instance_body["connector"]["identity"]["enabled"] is False
    assert not any(legacy_instance_body["connector"]["capabilities"].values())
    assert legacy_instance_body["settings"] == []

    blocked = [
        ("post", "/api/v2/integration-platform/connectors", {"connector_type": "digikala", "id": "digikala:new", "name": "Digikala"}),
        ("post", "/api/v2/integrations/connectors", {"connector_type": "digikala", "id": "digikala:legacy-new", "name": "Digikala"}),
        ("put", "/api/v2/integration-platform/connectors/digikala:retained-foundation", {"name": "Changed"}),
        ("get", "/api/v2/integration-platform/connectors/digikala:retained-foundation/settings", None),
        ("get", "/api/v2/integrations/connectors/digikala:retained-foundation/settings", None),
        ("put", "/api/v2/integration-platform/connectors/digikala:retained-foundation/settings", {"settings": {}}),
        ("patch", "/api/v2/integrations/connectors/digikala:retained-foundation/settings", {"settings": []}),
        ("patch", "/api/v2/integration-platform/connectors/digikala:retained-foundation/enable", None),
        ("patch", "/api/v2/integration-platform/connectors/digikala:retained-foundation/disable", None),
        ("delete", "/api/v2/integration-platform/connectors/digikala:retained-foundation", None),
        ("post", "/api/v2/integration-platform/connectors/digikala:retained-foundation/test", None),
        ("post", "/api/v2/integration-platform/connectors/digikala:retained-foundation/detect-capabilities", None),
        ("post", "/api/v2/integration-platform/connectors/digikala:retained-foundation/diagnostics/run", None),
        ("put", "/api/v2/integration-platform/connectors/digikala:retained-foundation/polling", {"enabled": True}),
        ("post", "/api/v2/integration-platform/connectors/digikala:retained-foundation/write-test", {"operation": "write_prices"}),
    ]
    for method, url, body in blocked:
        response = (
            getattr(client, method)(url, headers=auth_headers, json=body)
            if body is not None
            else getattr(client, method)(url, headers=auth_headers)
        )
        assert response.status_code == 409, (method, url, response.text)
        assert response.json()["detail"]["code"] == "CHANNEL_COMING_SOON"

    all_diagnostics = client.post(
        "/api/v2/integration-platform/diagnostics/run",
        headers=auth_headers,
    )
    assert all_diagnostics.status_code == 200
    assert all(check["target"] != "digikala" for check in all_diagnostics.json()["checks"])

    db.expire_all()
    persisted = db.get(IntegrationConnectorInstance, "digikala:retained-foundation")
    assert persisted is not None
    assert persisted.name == "Digikala"
    assert persisted.enabled is True
    assert db.get(IntegrationConnectorInstance, "digikala:new") is None
    assert db.get(IntegrationConnectorInstance, "digikala:legacy-new") is None


def test_internal_connector_metadata_is_hidden_from_all_public_setting_contracts(db):
    from app.flowhub.integration_platform.models import (
        IntegrationConnectorInstance,
        IntegrationConnectorSetting,
    )
    from app.flowhub.integration_platform.service import IntegrationPlatformService

    connector = IntegrationConnectorInstance(
        id="woocommerce:internal-metadata",
        connector_type="woocommerce",
        name="Owner Store",
        version="1.0.0",
        enabled=True,
        read_only=True,
        status="configured",
    )
    connector.settings.extend([
        IntegrationConnectorSetting(
            key="url",
            value_json="https://store.example.test",
            secret=False,
            configured=True,
        ),
        IntegrationConnectorSetting(
            key="_flowhub_display_name_custom",
            value_json=True,
            secret=False,
            configured=True,
        ),
    ])
    db.add(connector)
    db.commit()

    service = IntegrationPlatformService(db)
    contract = service.get_settings_contract(connector.id)
    assert contract["settings"] == {"url": "https://store.example.test"}
    assert [item.key for item in service.get_settings(connector.id)] == ["url"]
    assert [item.key for item in service.get_instance(connector.id).settings] == ["url"]
    summary = next(
        item for item in service.settings_summary() if item.connector_id == connector.id
    )
    assert [item.key for item in summary.settings] == ["url"]


def test_order_sync_status_exposes_exact_alias_custom_name_provenance(db):
    from app.flowhub.api.v2.orders import get_order_sync_status
    from app.flowhub.integration_platform.models import (
        IntegrationConnectorInstance,
        IntegrationConnectorSetting,
    )
    from app.flowhub.orders.service import OrderSyncService

    connector = IntegrationConnectorInstance(
        id="woocommerce:orders-custom",
        connector_type="woocommerce",
        name="ووکامرس",
        version="1.0.0",
        enabled=True,
        read_only=True,
        status="configured",
    )
    connector.settings.append(
        IntegrationConnectorSetting(
            key="_flowhub_display_name_custom",
            value_json=True,
            secret=False,
            configured=True,
        )
    )
    db.add(connector)
    technolife = IntegrationConnectorInstance(
        id="technolife:orders",
        connector_type="technolife",
        name="Technolife",
        version="1.0.0",
        enabled=True,
        read_only=True,
        status="configured",
    )
    db.add(technolife)
    db.commit()

    result = asyncio.run(get_order_sync_status(None, OrderSyncService(db)))
    item = next(row for row in result["items"] if row["channelId"] == connector.id)
    assert item["displayName"] == "ووکامرس"
    assert item["displayNameCustom"] is True
    technolife_item = next(
        row for row in result["items"] if row["channelId"] == technolife.id
    )
    assert technolife_item["displayName"] == "Technolife"
    assert technolife_item["displayNameCustom"] is False


def test_canonical_nextcloud_connector_rejects_credential_url(client, auth_headers):
    unsafe_url = "https://user:embedded-secret@cloud.example.test"
    response = client.post(
        "/api/v2/integration-platform/connectors",
        headers=auth_headers,
        json={
            "connector_type": "nextcloud",
            "id": "nextcloud:unsafe-url",
            "name": "Nextcloud",
            "settings": {"url": unsafe_url, "username": "user"},
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "CREDENTIALS_IN_URL_NOT_ALLOWED"
    assert unsafe_url not in response.text
    assert "embedded-secret" not in response.text


def test_canonical_nextcloud_settings_write_requires_commerce_source_api(
    client,
    auth_headers,
    db,
):
    from app.flowhub.source_workspace.models import SourceProfile

    connector_id = "nextcloud:fenced-settings"
    source = _create_linked_nextcloud_source(
        client,
        auth_headers,
        db,
        connector_id,
    )
    before = client.get(
        f"/api/v2/integration-platform/connectors/{connector_id}/settings",
        headers=auth_headers,
    ).json()
    previous_version = source["version"]

    response = client.put(
        f"/api/v2/integration-platform/connectors/{connector_id}/settings",
        headers=auth_headers,
        json={
            "settings": {
                "url": "https://replacement.example.test",
                "username": "replacement-owner",
                "spreadsheet_path": "/replacement.xlsx",
            }
        },
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "SOURCE_SETTINGS_WRITE_REQUIRES_SOURCE_API"
    assert detail["sourceId"] == connector_id
    assert "Commerce Source settings API" in detail["message"]
    after = client.get(
        f"/api/v2/integration-platform/connectors/{connector_id}/settings",
        headers=auth_headers,
    ).json()
    assert after["settings"] == before["settings"]
    assert after["secrets"] == before["secrets"]
    db.expire_all()
    assert db.get(SourceProfile, source["id"]).version == previous_version


def test_canonical_nextcloud_instance_settings_update_is_fenced_before_mutation(
    client,
    auth_headers,
    db,
):
    from app.flowhub.source_workspace.models import SourceProfile

    connector_id = "nextcloud:fenced-instance"
    source = _create_linked_nextcloud_source(
        client,
        auth_headers,
        db,
        connector_id,
    )
    before = client.get(
        f"/api/v2/integration-platform/connectors/{connector_id}",
        headers=auth_headers,
    ).json()
    before_settings = client.get(
        f"/api/v2/integration-platform/connectors/{connector_id}/settings",
        headers=auth_headers,
    ).json()
    previous_version = source["version"]

    response = client.put(
        f"/api/v2/integration-platform/connectors/{connector_id}",
        headers=auth_headers,
        json={
            "name": "Must not persist",
            "settings": {"spreadsheet_path": "/replacement.xlsx"},
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == (
        "SOURCE_SETTINGS_WRITE_REQUIRES_SOURCE_API"
    )
    after = client.get(
        f"/api/v2/integration-platform/connectors/{connector_id}",
        headers=auth_headers,
    ).json()
    assert after["name"] == before["name"]
    after_settings = client.get(
        f"/api/v2/integration-platform/connectors/{connector_id}/settings",
        headers=auth_headers,
    ).json()
    assert after_settings["settings"] == before_settings["settings"]
    assert after_settings["secrets"] == before_settings["secrets"]
    db.expire_all()
    assert db.get(SourceProfile, source["id"]).version == previous_version


def test_canonical_nextcloud_delete_requires_source_lifecycle_api(
    client,
    auth_headers,
    db,
):
    from app.flowhub.source_workspace.models import SourceProfile

    connector_id = "nextcloud:fenced-delete"
    source = _create_linked_nextcloud_source(
        client,
        auth_headers,
        db,
        connector_id,
    )
    previous_version = source["version"]

    response = client.delete(
        f"/api/v2/integration-platform/connectors/{connector_id}",
        headers=auth_headers,
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "SOURCE_LIFECYCLE_REQUIRES_SOURCE_API"
    assert detail["sourceId"] == connector_id
    assert "Source lifecycle API" in detail["message"]
    assert client.get(
        f"/api/v2/integration-platform/connectors/{connector_id}",
        headers=auth_headers,
    ).status_code == 200
    db.expire_all()
    profile = db.get(SourceProfile, source["id"])
    assert profile is not None
    assert profile.status == "active"
    assert profile.version == previous_version


def test_integration_platform_diagnostics_polling_webhook_are_safe(client, auth_headers):
    client.post(
        "/api/v2/integration-platform/connectors",
        headers=auth_headers,
        json={
            "connector_type": "nextcloud",
            "id": "nextcloud:test",
            "name": "Test Nextcloud",
            "settings": {"webhook_secret": "hook-secret"},
        },
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

    payload = b'{"event":"changed","token":"must-redact"}'
    signature = hmac.new(b"hook-secret", payload, sha256).hexdigest()
    webhook = client.post(
        "/api/v2/integration-platform/webhooks/nextcloud/nextcloud:test",
        content=payload,
        headers={"X-FlowHub-Signature": f"sha256={signature}"},
    )
    assert webhook.status_code == 200
    assert webhook.json()["accepted"] is True


def test_protected_platform_endpoints_reject_viewers(client, auth_headers, viewer_headers):
    client.post(
        "/api/v2/integration-platform/connectors",
        headers=auth_headers,
        json={"connector_type": "woocommerce", "id": "woocommerce:protected", "name": "Protected"},
    )

    protected_calls = [
        ("post", "/api/v2/integration-platform/connectors", {"connector_type": "nextcloud", "id": "nextcloud:viewer", "name": "Viewer"}),
        ("put", "/api/v2/integration-platform/connectors/woocommerce:protected/settings", {"settings": {"url": "https://example.com"}}),
        ("post", "/api/v2/integration-platform/connectors/woocommerce:protected/diagnostics/run", {}),
        ("put", "/api/v2/integration-platform/connectors/woocommerce:protected/polling", {"enabled": True}),
        ("post", "/api/v2/integration-platform/connectors/woocommerce:protected/write-test", {"operation": "write_prices"}),
        ("get", "/api/v2/logging/export", None),
        ("put", "/api/v2/logging/retention", {"policies": [{"category": "operational", "retention_days": 30}]}),
    ]
    for method, url, body in protected_calls:
        response = getattr(client, method)(url, headers=viewer_headers, json=body) if body is not None else getattr(client, method)(url, headers=viewer_headers)
        assert response.status_code == 403


def test_secret_like_settings_keys_are_always_masked(client, auth_headers):
    client.post(
        "/api/v2/integration-platform/connectors",
        headers=auth_headers,
        json={"connector_type": "woocommerce", "id": "woocommerce:secrets", "name": "Secrets"},
    )
    secret_values = {
        "password": "pw-value",
        "secret": "secret-value",
        "token": "token-value",
        "api_key": "api-key-value",
        "consumer_key": "consumer-key-value",
        "consumer_secret": "consumer-secret-value",
        "webhook_secret": "webhook-secret-value",
        "bearer": "bearer-value",
        "authorization": "authorization-value",
    }
    response = client.put(
        "/api/v2/integration-platform/connectors/woocommerce:secrets/settings",
        headers=auth_headers,
        json={"settings": secret_values},
    )
    assert response.status_code == 200
    settings = client.get("/api/v2/integration-platform/connectors/woocommerce:secrets/settings", headers=auth_headers)
    body = settings.json()
    assert body["settings"] == {}
    assert set(secret_values).issubset(body["secrets"])
    for value in secret_values.values():
        assert value not in str(body)


def test_webhook_rejects_when_secret_missing_or_signature_invalid(client, auth_headers):
    client.post(
        "/api/v2/integration-platform/connectors",
        headers=auth_headers,
        json={"connector_type": "woocommerce", "id": "woocommerce:webhook", "name": "Webhook"},
    )
    missing = client.post(
        "/api/v2/integration-platform/webhooks/woocommerce/woocommerce:webhook",
        json={"event": "changed"},
    )
    assert missing.status_code == 403

    client.put(
        "/api/v2/integration-platform/connectors/woocommerce:webhook/settings",
        headers=auth_headers,
        json={"settings": {"webhook_secret": "hook-secret"}},
    )
    invalid = client.post(
        "/api/v2/integration-platform/webhooks/woocommerce/woocommerce:webhook",
        json={"event": "changed"},
        headers={"X-FlowHub-Signature": "sha256=bad"},
    )
    assert invalid.status_code == 403


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


def test_frontend_logging_rejects_unbounded_batches_and_entries(client, auth_headers):
    batch = client.post(
        "/api/v2/logging/frontend",
        headers=auth_headers,
        json={
            "logs": [
                {"category": "UI Events", "message": f"event-{index}"}
                for index in range(101)
            ]
        },
    )
    assert batch.status_code == 422
    assert "at most 100" in batch.json()["detail"]

    oversized = client.post(
        "/api/v2/logging/frontend",
        headers=auth_headers,
        json={
            "logs": [
                {
                    "category": "Unexpected Exceptions",
                    "message": "x" * (64 * 1024),
                }
            ]
        },
    )
    assert oversized.status_code == 200
    assert oversized.json()["accepted"] == 0
    assert oversized.json()["rejections"] == [
        {"index": 0, "reason": "log_too_large"}
    ]


def test_logging_redacts_secret_like_message_and_exception_strings(client, auth_headers):
    secret_messages = [
        "password=pw-value",
        "token token-value",
        "api_key=api-key-value",
        "secret=secret-value",
        "consumer_secret=consumer-secret-value",
    ]
    response = client.post(
        "/api/v2/logging/frontend",
        headers=auth_headers,
        json={
            "logs": [
                {
                    "severity": "error",
                    "category": "Unexpected Exceptions",
                    "component": "Settings",
                    "message": message,
                    "exception_summary": message,
                    "correlation_id": f"corr_redact_{index}",
                }
                for index, message in enumerate(secret_messages)
            ]
        },
    )
    assert response.status_code == 200
    logs = client.get("/api/v2/logging/logs?severity=error&page_size=20", headers=auth_headers)
    body = logs.json()
    assert "[REDACTED]" in str(body)
    for message in secret_messages:
        assert message not in str(body)


def test_backend_log_ingestion_is_disabled_until_internal_auth_exists(client, auth_headers):
    response = client.post(
        "/api/v2/logging/backend",
        headers=auth_headers,
        json={"logs": [{"severity": "info", "message": "internal"}]},
    )
    assert response.status_code == 403


def test_direct_call_and_write_safety_audit_for_FLOWHUB_v2_routes():
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
