"""Pricing Matrix configuration API contract tests."""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("FLOWHUB_JWT_SECRET", "pricing-matrix-api-test-secret-32-bytes")

from app.flowhub.auth import models as _auth_models  # noqa: F401
from app.flowhub.pricing_matrix import models as _pricing_models  # noqa: F401
from app.flowhub.setup import models as _setup_models  # noqa: F401
from app.flowhub.unified_workspace import models as _workspace_models  # noqa: F401


@pytest.fixture()
def db_engine():
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
    session = sessionmaker(bind=db_engine)()
    yield session
    session.close()


@pytest.fixture()
def client(db_engine):
    from fastapi.testclient import TestClient

    from app.flowhub.app import app
    from app.flowhub.database import get_db

    Session = sessionmaker(bind=db_engine)

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def admin_headers(client, db):
    from app.flowhub.auth.jwt_service import create_access_token
    from app.flowhub.auth.models import FlowHubUser

    user = FlowHubUser(username=f"pm_admin_{uuid.uuid4().hex}", hashed_password="unused", role="admin")
    db.add(user)
    db.commit()
    return {"Authorization": f"Bearer {create_access_token(user.id, user.username, user.role)}"}


@pytest.fixture()
def viewer_headers(client, db):
    from app.flowhub.auth.jwt_service import create_access_token
    from app.flowhub.auth.models import FlowHubUser

    user = FlowHubUser(username=f"pm_viewer_{uuid.uuid4().hex}", hashed_password="unused", role="viewer")
    db.add(user)
    db.commit()
    return {"Authorization": f"Bearer {create_access_token(user.id, user.username, user.role)}"}


@pytest.fixture()
def seeded_channel(db):
    from app.flowhub.unified_workspace.services import UnifiedWorkspaceService

    UnifiedWorkspaceService(db)._seed_channels()
    db.commit()
    return "woocommerce:primary"


@pytest.fixture()
def canonical_product(db):
    from app.flowhub.unified_workspace.models import CanonicalProduct

    product = CanonicalProduct(
        id=str(uuid.uuid4()),
        name="Pricing Matrix Product",
        sku="PM-1",
        product_type="simple",
        status="active",
    )
    db.add(product)
    db.commit()
    return product.id


def _policy_payload(**overrides):
    payload = {
        "name": "API policy",
        "computation_currency": "EUR",
        "round_order": "surcharge_then_round",
        "max_quote_age_days": 30,
        "min_quote_count": 1,
        "evaluation_timezone": "UTC",
        "rules": [{"rate_mode": "percent_bp", "rate_value": 1000, "round_step_minor": 100}],
    }
    payload.update(overrides)
    return payload


def _activate(client, headers, channel_id, policy_id, head_version=0):
    return client.post(
        f"/api/v2/pricing-matrix/channels/{channel_id}/activate",
        headers=headers,
        json={
            "policy_revision_id": policy_id,
            "expected_head_version": head_version,
            "reason": "Release approved",
        },
    )


def test_policy_create_read_list_and_strict_validation(client, admin_headers):
    response = client.post("/api/v2/pricing-matrix/policies", headers=admin_headers, json=_policy_payload())
    assert response.status_code == 201
    policy = response.json()
    assert policy["revisionNumber"] == 1
    assert policy["createdAt"].endswith("+00:00") or "T" in policy["createdAt"]
    assert policy["rules"][0]["rateValue"] == 1000

    detail = client.get(f"/api/v2/pricing-matrix/policies/{policy['id']}", headers=admin_headers)
    assert detail.status_code == 200
    assert detail.json()["checksum"] == policy["checksum"]
    assert client.get("/api/v2/pricing-matrix/policies", headers=admin_headers).json()["items"][0]["id"] == policy["id"]

    invalid = client.post(
        "/api/v2/pricing-matrix/policies",
        headers=admin_headers,
        json={**_policy_payload(), "unexpected": True},
    )
    assert invalid.status_code == 422


def test_product_group_revisions_are_immutable_and_validate_members(
    client, admin_headers, canonical_product
):
    response = client.post(
        "/api/v2/pricing-matrix/product-groups",
        headers=admin_headers,
        json={"name": "Featured", "canonical_product_ids": [canonical_product]},
    )
    assert response.status_code == 201
    group = response.json()
    assert group["canonicalProductIds"] == [canonical_product]
    assert isinstance(group["createdAt"], str)
    assert client.get(
        f"/api/v2/pricing-matrix/product-groups/{group['id']}", headers=admin_headers
    ).json()["checksum"] == group["checksum"]

    missing = client.post(
        "/api/v2/pricing-matrix/product-groups",
        headers=admin_headers,
        json={"name": "Missing", "canonical_product_ids": [str(uuid.uuid4())]},
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "canonical_product_not_found"


def test_channel_activation_lifecycle_and_deactivation_contract(
    client, admin_headers, seeded_channel
):
    policy = client.post("/api/v2/pricing-matrix/policies", headers=admin_headers, json=_policy_payload()).json()
    unit = client.put(
        f"/api/v2/pricing-matrix/units/channel/{seeded_channel}",
        headers=admin_headers,
        json={"currency": "EUR", "unit": "EUR", "connector_config_version": "test-v1"},
    )
    assert unit.status_code == 200

    activated = _activate(client, admin_headers, seeded_channel, policy["id"])
    assert activated.status_code == 200
    assert activated.json()["status"] == "active"
    assert isinstance(activated.json()["updatedAt"], str)

    events = client.get(
        f"/api/v2/pricing-matrix/channels/{seeded_channel}/lifecycle-events", headers=admin_headers
    )
    assert events.status_code == 200
    assert events.json()["items"][0]["eventKind"] == "activate"
    assert isinstance(events.json()["items"][0]["occurredAt"], str)

    deactivated = client.post(
        f"/api/v2/pricing-matrix/channels/{seeded_channel}/deactivate",
        headers=admin_headers,
        json={"expected_head_version": 1, "reason": "Maintenance"},
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["status"] == "inactive"

    repeated = client.post(
        f"/api/v2/pricing-matrix/channels/{seeded_channel}/deactivate",
        headers=admin_headers,
        json={"expected_head_version": 2, "reason": "Again"},
    )
    assert repeated.status_code == 422
    assert repeated.json()["detail"]["code"] == "pricing_policy_not_activated"


def test_simultaneous_activation_attempts_use_one_authoritative_head_version(
    client, admin_headers, seeded_channel
):
    policy = client.post("/api/v2/pricing-matrix/policies", headers=admin_headers, json=_policy_payload()).json()
    client.put(
        f"/api/v2/pricing-matrix/units/channel/{seeded_channel}",
        headers=admin_headers,
        json={"currency": "EUR", "unit": "EUR"},
    )
    # Two operators read the same initial Head before either writes.
    operator_a_version = client.get(
        f"/api/v2/pricing-matrix/channels/{seeded_channel}/head", headers=admin_headers
    ).json()["headVersion"]
    operator_b_version = operator_a_version

    first = _activate(client, admin_headers, seeded_channel, policy["id"], operator_a_version)
    second = _activate(client, admin_headers, seeded_channel, policy["id"], operator_b_version)

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "pricing_policy_head_conflict"
    events = client.get(
        f"/api/v2/pricing-matrix/channels/{seeded_channel}/lifecycle-events", headers=admin_headers
    ).json()["items"]
    assert [event["eventKind"] for event in events] == ["activate"]


def test_stale_deactivation_is_rejected_then_succeeds_after_head_refetch(
    client, admin_headers, seeded_channel
):
    first_policy = client.post("/api/v2/pricing-matrix/policies", headers=admin_headers, json=_policy_payload()).json()
    replacement_policy = client.post(
        "/api/v2/pricing-matrix/policies",
        headers=admin_headers,
        json=_policy_payload(name="Replacement policy"),
    ).json()
    client.put(
        f"/api/v2/pricing-matrix/units/channel/{seeded_channel}",
        headers=admin_headers,
        json={"currency": "EUR", "unit": "EUR"},
    )
    assert _activate(client, admin_headers, seeded_channel, first_policy["id"], 0).status_code == 200

    # One actor activates a replacement while another holds the stale Head.
    stale_version = 1
    assert _activate(client, admin_headers, seeded_channel, replacement_policy["id"], stale_version).status_code == 200
    stale_deactivation = client.post(
        f"/api/v2/pricing-matrix/channels/{seeded_channel}/deactivate",
        headers=admin_headers,
        json={"expected_head_version": stale_version, "reason": "Stale pause"},
    )
    assert stale_deactivation.status_code == 409
    assert stale_deactivation.json()["detail"]["code"] == "pricing_policy_head_conflict"

    fresh_head = client.get(
        f"/api/v2/pricing-matrix/channels/{seeded_channel}/head", headers=admin_headers
    ).json()
    retry = client.post(
        f"/api/v2/pricing-matrix/channels/{seeded_channel}/deactivate",
        headers=admin_headers,
        json={"expected_head_version": fresh_head["headVersion"], "reason": "Refetched pause"},
    )
    assert retry.status_code == 200
    assert retry.json()["status"] == "inactive"


def test_lifecycle_mutation_requires_a_preseeded_head(client, admin_headers, seeded_channel):
    response = client.post(
        f"/api/v2/pricing-matrix/channels/{seeded_channel}/deactivate",
        headers=admin_headers,
        json={"expected_head_version": 0, "reason": "No head"},
    )
    # An inactive Channel is rejected before a lifecycle event can be appended.
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "pricing_policy_not_activated"


def test_viewer_can_read_but_cannot_change_pricing_matrix(client, admin_headers, viewer_headers):
    assert client.get("/api/v2/pricing-matrix/policies", headers=viewer_headers).status_code == 200
    assert (
        client.post("/api/v2/pricing-matrix/policies", headers=viewer_headers, json=_policy_payload()).status_code
        == 403
    )
    assert client.post("/api/v2/pricing-matrix/policies", json=_policy_payload()).status_code == 401
