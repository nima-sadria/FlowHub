"""Tests for /api/v2/activity endpoint (BU5)."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("FLOWHUB_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FLOWHUB_JWT_SECRET", "test-bu5-activity-jwt-secret-32bytes!")

from app.flowhub.auth import models as _auth_models  # noqa: F401
from app.flowhub.setup import models as _setup_models  # noqa: F401

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
    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.auth.password import hash_password

    user = FlowHubUser(username="activityadmin", hashed_password=hash_password("pass1234"), role="admin")
    db.add(user)
    db.commit()

    r = client.post("/api/auth/login", json={"username": "activityadmin", "password": "pass1234"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


# -- Tests ---------------------------------------------------------------------

class TestActivityEndpoint:
    def test_requires_auth(self, client):
        r = client.get("/api/v2/activity")
        assert r.status_code == 401

    def test_returns_paginated_shape(self, client, auth_headers):
        r = client.get("/api/v2/activity", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "pageSize" in data

    def test_login_event_is_recorded(self, client, auth_headers, db):
        """Login creates an audit record which should appear in activity log."""
        r = client.get("/api/v2/activity", headers=auth_headers)
        assert r.status_code == 200
        events = r.json()["items"]
        actions = [e["action"] for e in events]
        assert "login_success" in actions

    def test_event_shape(self, client, auth_headers):
        r = client.get("/api/v2/activity", headers=auth_headers)
        assert r.status_code == 200
        events = r.json()["items"]
        if events:
            e = events[0]
            assert "id" in e
            assert "timestamp" in e
            assert "kind" in e
            assert "level" in e
            assert "category" in e
            assert "actor" in e
            assert "action" in e
            assert "detail" in e

    def test_pagination_page_size(self, client, auth_headers):
        r = client.get("/api/v2/activity?pageSize=1", headers=auth_headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data["items"]) <= 1

    def test_newest_first_ordering(self, client, auth_headers, db):
        """Create additional audit events and verify newest comes first."""
        from app.flowhub.auth.repository import create_audit_event
        create_audit_event(db, username="activityadmin", event="preview_started", ip_address="api")
        create_audit_event(db, username="activityadmin", event="preview_completed", ip_address="0 changes")

        r = client.get("/api/v2/activity?pageSize=5", headers=auth_headers)
        assert r.status_code == 200
        items = r.json()["items"]
        # First item should be the most recently created
        assert items[0]["action"] == "preview_completed"

    def test_filters_categories_users_and_hides_routine_debug_by_default(
        self, client, auth_headers, db
    ):
        from app.flowhub.auth.repository import create_audit_event

        create_audit_event(
            db,
            username="activityadmin",
            event="token_refreshed",
            ip_address="api",
        )
        create_audit_event(
            db,
            username="operator",
            event="preview_failed",
            ip_address="source:fixture",
        )

        default = client.get("/api/v2/activity?pageSize=100", headers=auth_headers)
        assert default.status_code == 200
        assert "token_refreshed" not in {
            item["action"] for item in default.json()["items"]
        }

        filtered = client.get(
            "/api/v2/activity?category=products&severity=error&username=operator",
            headers=auth_headers,
        )
        assert filtered.status_code == 200
        assert filtered.json()["total"] == 1
        assert filtered.json()["items"][0]["category"] == "products"
        assert filtered.json()["items"][0]["level"] == "error"

        routine = client.get(
            "/api/v2/activity?includeDebug=true&severity=debug",
            headers=auth_headers,
        )
        assert routine.status_code == 200
        assert [item["action"] for item in routine.json()["items"]] == [
            "token_refreshed"
        ]

    def test_includes_unified_business_audit_without_mutating_it(
        self, client, auth_headers, db
    ):
        from app.flowhub.auth.models import FlowHubUser
        from app.flowhub.unified_workspace.models import UnifiedAuditEntry

        user = db.query(FlowHubUser).filter_by(username="activityadmin").one()
        row = UnifiedAuditEntry(
            id="audit-activity-1",
            correlation_id="corr-activity-1",
            event_type="apply_completed",
            user_id=user.id,
            metadata_checksum="0" * 64,
            request_metadata_json={},
            metadata_json={},
        )
        db.add(row)
        db.commit()

        response = client.get(
            "/api/v2/activity?category=apply&severity=success",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["total"] == 1
        item = response.json()["items"][0]
        assert item["action"] == "apply_completed"
        assert item["category"] == "apply"
        assert item["actor"] == "activityadmin"
        assert db.query(UnifiedAuditEntry).filter_by(id=row.id).count() == 1
