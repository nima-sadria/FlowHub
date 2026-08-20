"""Postgres concurrency coverage for Unified Workspace Draft CAS.

save_draft()'s CAS check (draft.version != expected_version) has no DB-level
optimistic-locking column -- it is a plain application-level read-then-write
check. uq_uw_draft_revision_number is the real backstop under genuine
concurrent transactions. These tests exercise that with real threads against
real PostgreSQL (SQLite's StaticPool test setup serializes all sessions onto
one connection and cannot reproduce this).

See ADR_CHANNEL_READ_ARCHITECTURE.md for the Targeted LIGHT / DlProductCache
architecture this also verifies stays uncoupled from Draft CAS.

Mirrors the schema-per-test-module / TRUNCATE-per-test pattern used by
tests/flowhub/webhooks/test_woocommerce_webhooks_postgres.py and
tests/flowhub/read_engine/test_channel_entity_work_postgres.py.
"""

from __future__ import annotations

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("FLOWHUB_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FLOWHUB_JWT_SECRET", "unified-workspace-postgres-test-secret-32b")

# The `client` fixture below imports app.flowhub.app on its first call (inside
# a fixture function, i.e. after postgres_engine's module-scoped create_all()
# has already run). Importing it here first ensures every router's models
# (e.g. orders' channel_inventory_effects) are registered on FlowHubBase
# metadata before create_all() builds the schema -- otherwise later fixtures'
# TRUNCATE (which reflects current, now-larger metadata) fails with
# UndefinedTable for tables that were never created.
from app.flowhub.app import app as _app  # noqa: E402, F401
from app.flowhub.auth import models as _auth_models  # noqa: E402, F401
from app.flowhub.data_layer import models as _data_models  # noqa: E402, F401
from app.flowhub.integration_platform import models as _integration_models  # noqa: E402, F401
from app.flowhub.pricing_matrix import models as _pricing_matrix_models  # noqa: E402, F401
from app.flowhub.product_pricing import models as _pricing_models  # noqa: E402, F401
from app.flowhub.setup import models as _setup_models  # noqa: E402, F401
from app.flowhub.source_acquisition import models as _source_acquisition_models  # noqa: E402, F401
from app.flowhub.source_workspace import models as _source_workspace_models  # noqa: E402, F401
from app.flowhub.unified_workspace import models as _workspace_models  # noqa: E402, F401
from app.flowhub.write_pipeline import models as _write_pipeline_models  # noqa: E402, F401

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def postgres_engine():
    from app.flowhub.database import FlowHubBase

    url = os.environ.get("FLOWHUB_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("FLOWHUB_TEST_POSTGRES_URL is not configured")

    admin_engine = sa.create_engine(url, pool_pre_ping=True)
    schema = f"unified_workspace_test_{uuid.uuid4().hex}"
    with admin_engine.begin() as connection:
        database_name = str(connection.execute(sa.text("select current_database()")).scalar_one())
        if "test" not in database_name.lower():
            pytest.fail("FLOWHUB_TEST_POSTGRES_URL must target an isolated database whose name contains 'test'")
        connection.execute(sa.schema.CreateSchema(schema))

    engine = sa.create_engine(
        url,
        connect_args={"options": f"-csearch_path={schema}"},
        pool_pre_ping=True,
    )
    FlowHubBase.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(sa.schema.DropSchema(schema, cascade=True))
        admin_engine.dispose()


@pytest.fixture()
def db(postgres_engine):
    with postgres_engine.begin() as connection:
        table_names = ", ".join(f'"{table.name}"' for table in _import_base().metadata.sorted_tables)
        connection.execute(sa.text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))
    session = sessionmaker(bind=postgres_engine)()
    yield session
    session.close()


def _import_base():
    from app.flowhub.database import FlowHubBase

    return FlowHubBase


@pytest.fixture()
def client(postgres_engine):
    from fastapi.testclient import TestClient

    from app.flowhub.app import app
    from app.flowhub.database import get_db

    Session = sessionmaker(bind=postgres_engine)

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
def admin(db):
    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.auth.password import hash_password

    user = FlowHubUser(
        username=f"uw_pg_{uuid.uuid4().hex[:12]}",
        hashed_password=hash_password("password123"),
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def auth_headers(admin):
    from app.flowhub.auth.jwt_service import create_access_token

    return {"Authorization": f"Bearer {create_access_token(admin.id, admin.username, admin.role)}"}


def _seed(db) -> None:
    from app.flowhub.data_layer.models import DlProductCache
    from app.flowhub.setup.service import AppConfigService

    AppConfigService(db).set("server.currency", "EUR")
    AppConfigService(db).set("server.currency_unit", "EUR")
    db.add(
        DlProductCache(
            connector_id="woocommerce:primary",
            product_id="101",
            external_id=101,
            sku="SKU-101",
            name="Postgres Concurrency Test Product",
            product_type="simple",
            price="100",
            regular_price="100",
            stock_qty=5,
            status="publish",
            stock_status="instock",
            manage_stock=True,
            freshness="fresh",
            last_fetched_at=datetime.now(UTC).replace(tzinfo=None),
            last_successful_read=datetime.now(UTC).replace(tzinfo=None),
            exists=True,
            record_hash="woo-cache-pg-1",
        )
    )
    db.commit()


def _create_workspace(client, auth_headers) -> dict:
    response = client.post(
        "/api/v2/unified-workspaces/manual",
        headers=auth_headers,
        json={
            "name": "Postgres Concurrency Test",
            "selections": [{"connector_id": "woocommerce:primary", "product_id": "101"}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _change_payload(row: dict, target_value: str) -> dict:
    return {
        "canonical_product_id": row["canonicalProductId"],
        "listing_id": row["listingId"],
        "channel_id": row["channelId"],
        "field": "price",
        "target_value": target_value,
        "currency": "EUR",
        "unit": "EUR",
    }


def test_concurrent_draft_saves_with_the_same_expected_version_resolve_to_exactly_one_winner(
    client, auth_headers, db
):
    """Two truly concurrent Draft saves both racing against expected_version=0
    (the real scenario uq_uw_draft_revision_number backstops): exactly one
    succeeds with 201, the other gets a clean 409 DRAFT_VERSION_CONFLICT --
    never a raw 500, and never two winners."""
    _seed(db)
    workspace = _create_workspace(client, auth_headers)
    row = client.get(
        f"/api/v2/unified-workspaces/{workspace['id']}/grid", headers=auth_headers
    ).json()["items"][0]

    barrier = threading.Barrier(2)

    def save(target_value: str):
        barrier.wait(timeout=10)
        return client.post(
            f"/api/v2/unified-workspaces/{workspace['id']}/draft/revisions",
            headers=auth_headers,
            json={"expected_version": 0, "metadata": {}, "changes": [_change_payload(row, target_value)]},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, ["150", "160"]))

    statuses = sorted(response.status_code for response in results)
    assert statuses == [201, 409], [
        (response.status_code, response.text) for response in results
    ]
    conflict = next(response for response in results if response.status_code == 409)
    assert conflict.json()["detail"]["code"] == "DRAFT_VERSION_CONFLICT"

    grid = client.get(f"/api/v2/unified-workspaces/{workspace['id']}/grid", headers=auth_headers).json()
    assert grid["draftVersion"] == 1, "exactly one save advanced the Draft, not zero and not two"


def test_targeted_light_style_cache_write_does_not_invalidate_a_concurrent_draft_save(
    client, auth_headers, db
):
    """A Targeted-LIGHT-style write to DlProductCache (the Channel Read
    Architecture's canonical observation table) running concurrently with a
    Draft save must never make that save's CAS fail -- draft.version lives
    entirely in unified_workspace's own tables and must stay uncoupled from
    Channel-observation writes, confirmed by tracing every read/write of
    draft.version in services.py (only save_draft/restore_revision touch it)."""
    from app.flowhub.data_layer.models import DlProductCache

    _seed(db)
    workspace = _create_workspace(client, auth_headers)
    row = client.get(
        f"/api/v2/unified-workspaces/{workspace['id']}/grid", headers=auth_headers
    ).json()["items"][0]

    barrier = threading.Barrier(2)
    cache_engine = db.get_bind()
    CacheSession = sessionmaker(bind=cache_engine)

    def save_draft():
        barrier.wait(timeout=10)
        return client.post(
            f"/api/v2/unified-workspaces/{workspace['id']}/draft/revisions",
            headers=auth_headers,
            json={"expected_version": 0, "metadata": {}, "changes": [_change_payload(row, "150")]},
        )

    def observe_external_price_change():
        barrier.wait(timeout=10)
        session = CacheSession()
        try:
            cache = (
                session.query(DlProductCache)
                .filter_by(connector_id="woocommerce:primary", product_id="101")
                .with_for_update()
                .one()
            )
            cache.price = "225850000"
            cache.regular_price = "225850000"
            cache.last_fetched_at = datetime.now(UTC).replace(tzinfo=None)
            cache.last_successful_read = datetime.now(UTC).replace(tzinfo=None)
            session.commit()
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        draft_future = pool.submit(save_draft)
        cache_future = pool.submit(observe_external_price_change)
        draft_response = draft_future.result(timeout=15)
        cache_future.result(timeout=15)

    assert draft_response.status_code == 201, draft_response.text
    assert draft_response.json()["draftVersion"] == 1

    updated_cache = (
        db.query(DlProductCache)
        .filter_by(connector_id="woocommerce:primary", product_id="101")
        .one()
    )
    assert updated_cache.price == "225850000"


def test_two_concurrent_applies_racing_the_same_manifest_resolve_to_exactly_one_winner(
    client, auth_headers, db, monkeypatch
):
    """Two truly concurrent Apply requests for the identical manifest and
    Idempotency-Key: exactly one ApplyJob is created and dispatched; the
    other request resolves to the same job rather than erroring or
    double-dispatching. Exercises uq_uw_apply_idempotency and
    uq_uw_apply_logical_operation -- the latter now bound to
    manifest_checksum (not just selection scope) -- under real Postgres
    concurrency, which SQLite's StaticPool test setup cannot reproduce."""
    from app.flowhub.unified_workspace.connectors import ListingUpdateResult
    from app.flowhub.unified_workspace.models import ApplyJob
    from app.flowhub.write_pipeline.workspace_contracts import WriteOutcome

    _seed(db)
    workspace = _create_workspace(client, auth_headers)
    row = client.get(
        f"/api/v2/unified-workspaces/{workspace['id']}/grid", headers=auth_headers
    ).json()["items"][0]
    revision = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/draft/revisions",
        headers=auth_headers,
        json={"expected_version": 0, "metadata": {}, "changes": [_change_payload(row, "150")]},
    )
    assert revision.status_code == 201, revision.text
    review = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews",
        headers=auth_headers,
        json={"draft_revision_id": revision.json()["id"]},
    )
    assert review.status_code == 201, review.text
    review_body = review.json()
    item = review_body["items"][0]
    selection = client.put(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews/{review_body['id']}/selection",
        headers=auth_headers,
        json={"review_item_ids": [item["id"]]},
    )
    assert selection.status_code == 200, selection.text
    selection_body = selection.json()

    async def fake_apply(_self, updates, *, requested_by):
        return [
            ListingUpdateResult(
                listing_id=update.listing_id,
                outcome=WriteOutcome.VERIFIED_APPLIED,
                response={"id": "provider-1"},
                external_response_id="provider-1",
                accepted_price=update.target_price,
            )
            for update in updates
        ]

    monkeypatch.setattr(
        "app.flowhub.unified_workspace.connectors.WooCommerceWorkspaceConnector.apply_updates",
        fake_apply,
    )

    barrier = threading.Barrier(2)

    def apply_request(_index: int):
        barrier.wait(timeout=10)
        return client.post(
            f"/api/v2/unified-workspaces/{workspace['id']}/apply",
            headers={**auth_headers, "Idempotency-Key": "manifest-race-1"},
            json={
                "review_id": review_body["id"],
                "expected_selection_checksum": selection_body["selectionChecksum"],
                "manifest_id": selection_body["manifestId"],
                "expected_manifest_checksum": selection_body["manifestChecksum"],
                "confirmed": True,
            },
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(apply_request, range(2)))

    statuses = sorted(response.status_code for response in results)
    assert statuses == [202, 202], [(r.status_code, r.text) for r in results]
    job_ids = {response.json()["id"] for response in results}
    assert len(job_ids) == 1, "both requests must resolve to the same ApplyJob, never two"
    assert db.query(ApplyJob).filter_by(workspace_id=workspace["id"]).count() == 1
