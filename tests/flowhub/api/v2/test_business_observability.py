"""Tests for /api/v2/business-events endpoints."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("FLOWHUB_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FLOWHUB_JWT_SECRET", "test-bo-api-jwt-secret-with-32-bytes!")

from app.flowhub.auth import models as _auth_models  # noqa: F401
from app.flowhub.business_observability import models as _bo_models  # noqa: F401
from app.flowhub.business_observability.service import BusinessObservabilityService


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


def _login(client, db, *, username: str, role: str) -> dict[str, str]:
    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.auth.password import hash_password

    user = FlowHubUser(username=username, hashed_password=hash_password("password123"), role=role)
    db.add(user)
    db.commit()
    response = client.post("/api/auth/login", json={"username": username, "password": "password123"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


@pytest.fixture()
def admin_headers(client, db):
    return _login(client, db, username="bo-admin", role="admin")


@pytest.fixture()
def viewer_headers(client, db):
    return _login(client, db, username="bo-viewer", role="viewer")


@pytest.fixture()
def seeded_event(db):
    service = BusinessObservabilityService(db)
    return service.emit_event(
        domain="write_pipeline",
        event_type="write_batch_partially_failed",
        severity="error",
        business_impact="partial_failure",
        reason_code="provider_error",
        reason_message="2 of 5 items failed",
        primary_scope_type="batch",
        primary_scope_id="batch-1",
        primary_scope_label="Batch 1",
        recommended_action="Review failed items",
        retryable=True,
        action_route_key="workspace.home",
        correlation_id="corr-seed",
        producer="write_pipeline.service",
    )


class TestListAndGet:
    def test_list_requires_auth(self, client):
        response = client.get("/api/v2/business-events")
        assert response.status_code == 401

    def test_list_returns_seeded_event(self, client, admin_headers, seeded_event):
        response = client.get("/api/v2/business-events", headers=admin_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == seeded_event.id
        assert body["items"][0]["status"] == "open"
        assert body["items"][0]["actionUrl"] == "/workspace"

    def test_viewer_can_list(self, client, viewer_headers, seeded_event):
        response = client.get("/api/v2/business-events", headers=viewer_headers)
        assert response.status_code == 200

    def test_get_by_id(self, client, admin_headers, seeded_event):
        response = client.get(f"/api/v2/business-events/{seeded_event.id}", headers=admin_headers)
        assert response.status_code == 200
        assert response.json()["reasonCode"] == "provider_error"

    def test_get_unknown_id_returns_404(self, client, admin_headers):
        response = client.get("/api/v2/business-events/does-not-exist", headers=admin_headers)
        assert response.status_code == 404

    def test_kpis_endpoint(self, client, admin_headers, seeded_event):
        response = client.get("/api/v2/business-events/kpis", headers=admin_headers)
        assert response.status_code == 200
        assert "openBlockingByDomain" in response.json()


class TestLifecycle:
    def test_acknowledge_requires_apply_execute_permission(self, client, viewer_headers, seeded_event):
        response = client.post(
            f"/api/v2/business-events/{seeded_event.id}/acknowledge",
            headers=viewer_headers,
            json={},
        )
        assert response.status_code == 403

    def test_admin_can_acknowledge_then_resolve(self, client, admin_headers, seeded_event):
        ack = client.post(
            f"/api/v2/business-events/{seeded_event.id}/acknowledge",
            headers=admin_headers,
            json={"note": "investigating"},
        )
        assert ack.status_code == 200
        assert ack.json()["status"] == "acknowledged"
        assert ack.json()["acknowledgedBy"] == "bo-admin"

        resolve = client.post(
            f"/api/v2/business-events/{seeded_event.id}/resolve", headers=admin_headers, json={}
        )
        assert resolve.status_code == 200
        assert resolve.json()["status"] == "resolved"

    def test_resolved_event_rejects_further_transitions(self, client, admin_headers, seeded_event):
        client.post(f"/api/v2/business-events/{seeded_event.id}/resolve", headers=admin_headers, json={})
        response = client.post(
            f"/api/v2/business-events/{seeded_event.id}/acknowledge", headers=admin_headers, json={}
        )
        assert response.status_code == 409

    def test_lifecycle_history_reflects_transitions(self, client, admin_headers, seeded_event):
        client.post(
            f"/api/v2/business-events/{seeded_event.id}/acknowledge", headers=admin_headers, json={}
        )
        client.post(f"/api/v2/business-events/{seeded_event.id}/resolve", headers=admin_headers, json={})
        response = client.get(
            f"/api/v2/business-events/{seeded_event.id}/lifecycle", headers=admin_headers
        )
        assert response.status_code == 200
        statuses = [item["toStatus"] for item in response.json()]
        assert statuses == ["acknowledged", "resolved"]
