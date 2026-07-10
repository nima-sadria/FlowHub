"""Role hierarchy tests for the production user-administration routes."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("FLOWHUB_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FLOWHUB_JWT_SECRET", "test-user-authorization-jwt-secret-32bytes!")

from app.flowhub.auth import models as _auth_models  # noqa: F401
from app.flowhub.data_layer import models as _data_models  # noqa: F401
from app.flowhub.integration_platform import models as _ip_models  # noqa: F401
from app.flowhub.setup import models as _setup_models  # noqa: F401


@pytest.fixture()
def db_engine():
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    from app.flowhub.database import FlowHubBase, _get_engine

    _get_engine.cache_clear()
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    FlowHubBase.metadata.create_all(engine)
    yield engine
    FlowHubBase.metadata.drop_all(engine)
    engine.dispose()
    _get_engine.cache_clear()


@pytest.fixture()
def db(db_engine):
    from sqlalchemy.orm import sessionmaker

    session = sessionmaker(bind=db_engine)()
    yield session
    session.close()


@pytest.fixture()
def client(db_engine):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker
    from app.flowhub.app import app
    from app.flowhub.database import get_db

    Session = sessionmaker(bind=db_engine)

    def override_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app, raise_server_exceptions=True) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _headers(client, db, username: str, role: str) -> dict[str, str]:
    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.auth.password import hash_password

    db.add(FlowHubUser(username=username, hashed_password=hash_password("password123"), role=role, is_active=True))
    db.commit()
    response = client.post("/api/auth/login", json={"username": username, "password": "password123"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_admin_cannot_create_or_promote_privileged_users(client, db):
    admin_headers = _headers(client, db, "admin-user", "admin")
    viewer_headers = _headers(client, db, "viewer-user", "viewer")

    create = client.post("/api/v2/users", headers=admin_headers, json={"username": "new-owner", "password": "password123", "role": "owner"})
    assert create.status_code == 403
    viewer_id = client.get("/api/v2/users", headers=admin_headers).json()["items"][1]["id"]
    promote = client.patch(f"/api/v2/users/{viewer_id}", headers=admin_headers, json={"role": "super_admin"})
    assert promote.status_code == 403
    assert client.get("/api/auth/me", headers=viewer_headers).status_code == 200


def test_admin_cannot_modify_privileged_user_or_self_escalate(client, db):
    admin_headers = _headers(client, db, "admin-user", "admin")
    _headers(client, db, "owner-user", "owner")
    users = client.get("/api/v2/users", headers=admin_headers).json()["items"]
    admin_id = next(item["id"] for item in users if item["username"] == "admin-user")
    owner_id = next(item["id"] for item in users if item["username"] == "owner-user")

    assert client.patch(f"/api/v2/users/{owner_id}", headers=admin_headers, json={"password": "new-password"}).status_code == 403
    assert client.patch(f"/api/v2/users/{admin_id}", headers=admin_headers, json={"role": "owner"}).status_code == 403


def test_owner_can_manage_privileged_users_and_role_changes_are_audited(client, db):
    owner_headers = _headers(client, db, "owner-user", "owner")
    create = client.post("/api/v2/users", headers=owner_headers, json={"username": "future-super", "password": "password123", "role": "super_admin"})
    assert create.status_code == 201
    user_id = create.json()["id"]
    update = client.patch(f"/api/v2/users/{user_id}", headers=owner_headers, json={"role": "admin"})
    assert update.status_code == 200

    from app.flowhub.auth.models import FlowHubLoginAudit
    assert db.query(FlowHubLoginAudit).filter(FlowHubLoginAudit.event == "user_role_changed").count() == 1


def test_last_active_privileged_user_cannot_be_disabled(client, db):
    owner_headers = _headers(client, db, "owner-user", "owner")
    owner_id = client.get("/api/v2/users", headers=owner_headers).json()["items"][0]["id"]
    response = client.patch(f"/api/v2/users/{owner_id}", headers=owner_headers, json={"is_active": False})
    assert response.status_code == 409
