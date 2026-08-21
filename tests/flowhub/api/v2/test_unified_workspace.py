"""FlowHub v1.2 Unified Workspace lifecycle and invariant tests."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("FLOWHUB_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FLOWHUB_JWT_SECRET", "unified-workspace-test-secret-32-bytes-long")

from app.flowhub.auth import models as _auth_models  # noqa: F401
from app.flowhub.data_layer import models as _data_models  # noqa: F401
from app.flowhub.integration_platform import models as _integration_models  # noqa: F401
from app.flowhub.pricing_matrix import models as _pricing_matrix_models  # noqa: F401
from app.flowhub.product_pricing import models as _pricing_models  # noqa: F401
from app.flowhub.setup import models as _setup_models  # noqa: F401
from app.flowhub.source_acquisition import models as _source_acquisition_models  # noqa: F401
from app.flowhub.source_workspace import models as _source_workspace_models  # noqa: F401
from app.flowhub.unified_workspace import models as _workspace_models  # noqa: F401
from app.flowhub.write_pipeline import models as _write_pipeline_models  # noqa: F401


@pytest.fixture()
def db_engine():
    from app.flowhub.database import FlowHubBase, _get_engine

    _get_engine.cache_clear()
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
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
def admin(db):
    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.auth.password import hash_password

    user = FlowHubUser(
        username=f"uw_{uuid.uuid4().hex}",
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


@pytest.fixture(autouse=True)
def authoritative_workspace_live_read(monkeypatch):
    """Default test Channel boundary: an exact targeted, no-write read.

    Tests that exercise drift or provider failure replace this connector method
    explicitly.  Apply tests receive the same evidence on their post-lock
    read, which models an unchanged Channel without bypassing Dry Run.
    """
    from app.flowhub.unified_workspace.connectors import ListingUpdateResult
    from app.flowhub.write_pipeline.workspace_contracts import WriteOutcome

    async def verified(_self, updates, *, requested_by):
        del requested_by
        return [
            ListingUpdateResult(
                listing_id=update.listing_id,
                outcome=WriteOutcome.VERIFIED_APPLIED,
                response={"verification": {"observed": {
                    "provider": "woocommerce",
                    "external_id": str(update.external_primary_id),
                    "parent_external_id": update.parent_external_id,
                    "product_type": update.product_type,
                    "price": update.current_price,
                    "stock": update.current_stock,
                    "status": update.current_status,
                    "currency": update.currency,
                    "unit": update.unit,
                }}},
            )
            for update in updates
        ]

    monkeypatch.setattr(
        "app.flowhub.unified_workspace.connectors.WooCommerceWorkspaceConnector.verify_updates",
        verified,
    )


def _seed(db, *, product_type: str = "simple", currency: str = "EUR", unit: str = "EUR") -> None:
    from app.flowhub.data_layer.models import DlProductCache
    from app.flowhub.setup.service import AppConfigService

    AppConfigService(db).set("server.currency", currency)
    AppConfigService(db).set("server.currency_unit", unit)
    db.add(
        DlProductCache(
            connector_id="woocommerce:primary",
            product_id="101",
            external_id=101,
            sku="SKU-101",
            name="Canonical Test Product",
            product_type=product_type,
            price="100",
            regular_price="100",
            stock_qty=5,
            status="publish",
            stock_status="instock",
            manage_stock=True,
            freshness="fresh",
            last_fetched_at=datetime.now(timezone.utc).replace(tzinfo=None),
            last_successful_read=datetime.now(timezone.utc).replace(tzinfo=None),
            exists=True,
            record_hash="woo-cache-1",
        )
    )
    db.commit()
    _seed_pricing_policy(db)


def _seed_pricing_policy(db) -> None:
    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.pricing_authority.contracts import PricingAuthority
    from app.flowhub.pricing_authority.service import ChannelPricingAuthorityService
    from app.flowhub.pricing_matrix.models import ChannelPricingPolicyHead
    from app.flowhub.pricing_matrix.service import PricingMatrixService
    from app.flowhub.unified_workspace.services import UnifiedWorkspaceService

    user = db.query(FlowHubUser).first()
    assert user is not None
    UnifiedWorkspaceService(db)._seed_channels()
    pricing = PricingMatrixService(db)
    existing_head = db.get(ChannelPricingPolicyHead, "woocommerce:primary")
    if existing_head is not None and existing_head.effective_activation_id:
        return
    pricing.declare_unit(
        scope="channel",
        scope_reference="woocommerce:primary",
        currency="EUR",
        unit="EUR",
        user=user,
    )
    policy = pricing.create_policy_revision(
        payload={
            "name": "Unified Workspace Test Policy",
            "computation_currency": "EUR",
            "round_order": "surcharge_then_round",
            "max_quote_age_days": 30,
            "min_quote_count": 1,
            "evaluation_timezone": "UTC",
            "rules": [
                {
                    "rate_mode": "percent_bp",
                    "rate_value": 0,
                    "round_mode": "floor",
                    "round_step_minor": 100,
                    "surcharge_minor": 0,
                }
            ],
        },
        user=user,
    )
    pricing.activate(
        channel_id="woocommerce:primary",
        policy_revision_id=policy["id"],
        expected_head_version=0,
        reason="Unified Workspace integration test setup",
        user=user,
    )
    authority = ChannelPricingAuthorityService(db)
    legacy = authority.snapshot("woocommerce:primary")
    locked = authority.transition(
        channel_id="woocommerce:primary",
        new_authority=PricingAuthority.MIGRATION_LOCKED,
        expected_head_version=legacy.head_version,
        reason="Unified Workspace Matrix test setup",
        user=user,
    )
    authority.transition(
        channel_id="woocommerce:primary",
        new_authority=PricingAuthority.PRICING_MATRIX,
        expected_head_version=locked.head_version,
        reason="Unified Workspace Matrix test setup",
        user=user,
    )


def _activate_replacement_policy(db) -> None:
    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.pricing_matrix.models import ChannelPricingPolicyHead
    from app.flowhub.pricing_matrix.service import PricingMatrixService

    user = db.query(FlowHubUser).first()
    head = db.get(ChannelPricingPolicyHead, "woocommerce:primary")
    assert user is not None and head is not None
    pricing = PricingMatrixService(db)
    policy = pricing.create_policy_revision(
        payload={
            "name": "Replacement Unified Workspace Test Policy",
            "computation_currency": "EUR",
            "round_order": "surcharge_then_round",
            "max_quote_age_days": 30,
            "min_quote_count": 1,
            "evaluation_timezone": "UTC",
            "rules": [
                {
                    "rate_mode": "percent_bp",
                    "rate_value": 0,
                    "round_mode": "floor",
                    "round_step_minor": 100,
                    "surcharge_minor": 0,
                }
            ],
        },
        user=user,
    )
    pricing.activate(
        channel_id="woocommerce:primary",
        policy_revision_id=policy["id"],
        expected_head_version=head.head_version,
        reason="Unified Workspace pricing drift test",
        user=user,
    )


def _create(client, auth_headers):
    response = client.post(
        "/api/v2/unified-workspaces/manual",
        headers=auth_headers,
        json={
            "name": "Manual Test",
            "selections": [{"connector_id": "woocommerce:primary", "product_id": "101"}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_manual_workspace_snapshot_grid_draft_and_review_lifecycle(client, auth_headers, db):
    _seed(db)
    workspace = _create(client, auth_headers)

    grid_response = client.get(
        f"/api/v2/unified-workspaces/{workspace['id']}/grid", headers=auth_headers
    )
    assert grid_response.status_code == 200
    grid = grid_response.json()
    assert grid["total"] == 1
    row = grid["items"][0]
    assert row["fields"]["price"]["current"] == "100"
    assert row["fields"]["price"]["target"] == "100"
    assert row["fields"]["price"]["readOnly"] is False
    # WooCommerceWorkspaceConnector declares write_stock=True (governed stock
    # writes, see connectors.py); stock is writable, not read-only.
    assert row["fields"]["stock"]["readOnly"] is False

    saved_response = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/draft/revisions",
        headers=auth_headers,
        json={
            "expected_version": 0,
            "metadata": {"test": "lifecycle"},
            "changes": [
                {
                    "canonical_product_id": row["canonicalProductId"],
                    "listing_id": row["listingId"],
                    "channel_id": row["channelId"],
                    "field": "price",
                    "target_value": "125",
                    "currency": "EUR",
                    "unit": "EUR",
                }
            ],
        },
    )
    assert saved_response.status_code == 201, saved_response.text
    revision = saved_response.json()
    assert revision["revisionNumber"] == 1
    assert revision["noOp"] is False

    review_response = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews",
        headers=auth_headers,
        json={"draft_revision_id": revision["id"]},
    )
    assert review_response.status_code == 201, review_response.text
    review = review_response.json()
    assert review["status"] == "ready"
    assert review["items"][0]["current"] == "100"
    assert review["items"][0]["target"] == "125"
    assert review["items"][0]["eligible"] is True
    assert review["pricingBindings"][0]["channelId"] == "woocommerce:primary"
    assert review["pricingBindings"][0]["workspacePricingEvaluatedAt"]


def test_manual_workspace_supports_grouped_inline_pricing_grid(client, auth_headers, db):
    _seed(db)
    workspace = _create(client, auth_headers)
    response = client.get(
        f"/api/v2/unified-workspaces/{workspace['id']}/grouped-grid?page=1&pageSize=100&view=all",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    grouped = response.json()
    assert grouped["total"] == 1
    assert grouped["items"][0]["children"][0]["listingId"]
    assert grouped["items"][0]["children"][0]["fields"]["price"]["current"] == "100"


def test_grouped_grid_exposes_provider_neutral_product_media(client, auth_headers, db):
    from sqlalchemy import event

    from app.flowhub.data_layer.models import DlProductCache

    _seed(db)
    cache = db.query(DlProductCache).filter_by(
        connector_id="woocommerce:primary", product_id="101"
    ).one()
    cache.images = [
        {"src": "https://cdn.example.test/primary.jpg?consumer_secret=hidden"},
        {"src": "https://cdn.example.test/second.jpg"},
    ]
    db.commit()
    workspace = _create(client, auth_headers)
    media_queries: list[str] = []

    def capture_media_query(_connection, _cursor, statement, _parameters, _context, _many):
        normalized_statement = " ".join(statement.lower().split())
        if "(dl_product_cache.connector_id, dl_product_cache.product_id) in" in normalized_statement:
            media_queries.append(statement)

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", capture_media_query)
    try:
        response = client.get(
            f"/api/v2/unified-workspaces/{workspace['id']}/grouped-grid?page=1&pageSize=100&view=all",
            headers=auth_headers,
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture_media_query)

    assert response.status_code == 200, response.text
    product = response.json()["items"][0]
    assert product["primaryImageUrl"] == "https://cdn.example.test/primary.jpg"
    assert product["media"] == [
        {
            "type": "image",
            "url": "https://cdn.example.test/primary.jpg",
            "position": 0,
            "source": "woocommerce",
        },
        {
            "type": "image",
            "url": "https://cdn.example.test/second.jpg",
            "position": 1,
            "source": "woocommerce",
        },
    ]
    assert "images" not in product
    assert "src" not in product
    assert "consumer_secret" not in repr(product)
    assert len(media_queries) == 1


def test_draft_optimistic_concurrency_and_no_external_write(client, auth_headers, db, monkeypatch):
    _seed(db)
    workspace = _create(client, auth_headers)
    row = client.get(
        f"/api/v2/unified-workspaces/{workspace['id']}/grid", headers=auth_headers
    ).json()["items"][0]
    external = pytest.fail
    monkeypatch.setattr(
        "app.connectors.destinations.woocommerce.write_adapter.WooCommercePriceWriteAdapter.execute_item",
        external,
    )
    body = {
        "expected_version": 0,
        "metadata": {},
        "changes": [
            {
                "canonical_product_id": row["canonicalProductId"],
                "listing_id": row["listingId"],
                "channel_id": row["channelId"],
                "field": "price",
                "target_value": "120",
                "currency": "EUR",
                "unit": "EUR",
            }
        ],
    }
    assert (
        client.post(
            f"/api/v2/unified-workspaces/{workspace['id']}/draft/revisions",
            headers=auth_headers,
            json=body,
        ).status_code
        == 201
    )
    conflict = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/draft/revisions",
        headers=auth_headers,
        json=body,
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "DRAFT_VERSION_CONFLICT"


def test_draft_save_race_that_slips_past_the_version_check_still_reports_a_clean_conflict(
    client, auth_headers, db
):
    """Two sessions can both read draft.version before either commits under
    ordinary READ COMMITTED concurrency, so both pass the application-level
    `draft.version != expected_version` check above and both attempt to
    insert revision_number = expected_version + 1. uq_uw_draft_revision_number
    is the real backstop for that race -- this reproduces the loser's state
    deterministically (a competing revision already occupies that slot while
    draft.version itself has not advanced yet, exactly what a genuine
    concurrent winner leaves behind) and asserts the loser still gets the
    same DRAFT_VERSION_CONFLICT response, not a raw unhandled IntegrityError."""
    from app.flowhub.unified_workspace.models import Draft, DraftRevision
    from app.flowhub.unified_workspace.services import _id

    _seed(db)
    workspace = _create(client, auth_headers)
    row = client.get(
        f"/api/v2/unified-workspaces/{workspace['id']}/grid", headers=auth_headers
    ).json()["items"][0]
    draft = db.query(Draft).filter_by(workspace_id=workspace["id"]).one()
    db.add(DraftRevision(
        id=_id(),
        draft_id=draft.id,
        workspace_id=workspace["id"],
        snapshot_id=draft.snapshot_id,
        revision_number=draft.version + 1,
        parent_revision_id=None,
        restored_from_revision_id=None,
        creator_user_id=draft.owner_user_id,
        checksum="phantom-concurrent-winner",
        metadata_json={},
    ))
    db.commit()

    response = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/draft/revisions",
        headers=auth_headers,
        json={
            "expected_version": 0,
            "metadata": {},
            "changes": [{
                "canonical_product_id": row["canonicalProductId"],
                "listing_id": row["listingId"],
                "channel_id": row["channelId"],
                "field": "price",
                "target_value": "120",
                "currency": "EUR",
                "unit": "EUR",
            }],
        },
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "DRAFT_VERSION_CONFLICT"


def test_variable_parent_is_read_only(client, auth_headers, db):
    _seed(db, product_type="variable")
    workspace = _create(client, auth_headers)
    row = client.get(
        f"/api/v2/unified-workspaces/{workspace['id']}/grid", headers=auth_headers
    ).json()["items"][0]
    assert row["fields"]["price"]["readOnly"] is True
    response = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/draft/revisions",
        headers=auth_headers,
        json={
            "expected_version": 0,
            "metadata": {},
            "changes": [
                {
                    "canonical_product_id": row["canonicalProductId"],
                    "listing_id": row["listingId"],
                    "channel_id": row["channelId"],
                    "field": "price",
                    "target_value": "120",
                    "currency": "EUR",
                    "unit": "EUR",
                }
            ],
        },
    )
    assert response.status_code == 422


def test_iranian_currency_requires_explicit_unit(client, auth_headers, db):
    from app.flowhub.data_layer.models import DlProductCache
    from app.flowhub.setup.service import AppConfigService

    AppConfigService(db).set("server.currency", "IRR")
    db.add(
        DlProductCache(
            connector_id="woocommerce:primary",
            product_id="101",
            name="IRR Product",
            product_type="simple",
            price="100",
            regular_price="100",
            freshness="fresh",
            exists=True,
        )
    )
    db.commit()
    response = client.post(
        "/api/v2/unified-workspaces/manual",
        headers=auth_headers,
        json={
            "name": "IRR",
            "selections": [{"connector_id": "woocommerce:primary", "product_id": "101"}],
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "CURRENCY_UNIT_REQUIRED"


def test_snapshot_and_revision_rows_are_immutable(db, admin):
    from app.flowhub.data_layer.models import DlProductCache
    from app.flowhub.setup.service import AppConfigService
    from app.flowhub.unified_workspace.domain import ImmutableRecordError
    from app.flowhub.unified_workspace.models import WorkspaceSnapshot
    from app.flowhub.unified_workspace.services import UnifiedWorkspaceService

    AppConfigService(db).set("server.currency", "EUR")
    AppConfigService(db).set("server.currency_unit", "EUR")
    db.add(
        DlProductCache(
            connector_id="woocommerce:primary",
            product_id="101",
            name="Product",
            product_type="simple",
            price="100",
            regular_price="100",
            freshness="fresh",
            exists=True,
        )
    )
    db.commit()
    workspace = UnifiedWorkspaceService(db).create_manual_workspace(
        name="Immutable",
        selections=[{"connector_id": "woocommerce:primary", "product_id": "101"}],
        user=admin,
        correlation_id="immutable-test",
    )
    snapshot = db.get(WorkspaceSnapshot, workspace["snapshot"]["id"])
    snapshot.schema_version = "mutated"
    with pytest.raises(ImmutableRecordError):
        db.commit()
    db.rollback()


def test_apply_manifest_is_immutable(client, auth_headers, db):
    from app.flowhub.unified_workspace.domain import ImmutableRecordError
    from app.flowhub.unified_workspace.models import ApplyManifest, ApplyManifestOperation

    workspace, review = _saved_review(client, auth_headers, db)
    item = review["items"][0]
    selection = _select_and_dry_run(client, auth_headers, workspace, review, [item["id"]])
    manifest = db.get(ApplyManifest, selection.json()["manifestId"])
    manifest.operation_count = 999
    with pytest.raises(ImmutableRecordError):
        db.commit()
    db.rollback()

    operation = (
        db.query(ApplyManifestOperation).filter_by(manifest_id=manifest.id).first()
    )
    operation.target_value = "0"
    with pytest.raises(ImmutableRecordError):
        db.commit()
    db.rollback()


def test_viewer_cannot_create_workspace(client, db):
    from app.flowhub.auth.jwt_service import create_access_token
    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.auth.password import hash_password

    viewer = FlowHubUser(
        username=f"viewer_{uuid.uuid4().hex}",
        hashed_password=hash_password("password123"),
        role="viewer",
    )
    db.add(viewer)
    db.commit()
    headers = {
        "Authorization": f"Bearer {create_access_token(viewer.id, viewer.username, viewer.role)}"
    }
    response = client.post(
        "/api/v2/unified-workspaces/manual",
        headers=headers,
        json={
            "name": "Denied",
            "selections": [{"connector_id": "woocommerce:primary", "product_id": "101"}],
        },
    )
    assert response.status_code == 403


def _saved_review(
    client,
    auth_headers,
    db,
    *,
    second_product: bool = False,
    deactivate_before_review: bool = False,
):
    _seed(db)
    if second_product:
        from app.flowhub.data_layer.models import DlProductCache

        db.add(
            DlProductCache(
                connector_id="woocommerce:primary",
                product_id="102",
                external_id=102,
                sku="SKU-102",
                name="Second Product",
                product_type="simple",
                price="200",
                regular_price="200",
                stock_qty=3,
                status="publish",
                manage_stock=True,
                freshness="fresh",
                exists=True,
                record_hash="woo-cache-2",
            )
        )
        db.commit()
    selections = [{"connector_id": "woocommerce:primary", "product_id": "101"}]
    if second_product:
        selections.append({"connector_id": "woocommerce:primary", "product_id": "102"})
    workspace_response = client.post(
        "/api/v2/unified-workspaces/manual",
        headers=auth_headers,
        json={"name": "Apply Test", "selections": selections},
    )
    assert workspace_response.status_code == 201
    workspace = workspace_response.json()
    rows = client.get(
        f"/api/v2/unified-workspaces/{workspace['id']}/grid", headers=auth_headers
    ).json()["items"]
    changes = [
        {
            "canonical_product_id": row["canonicalProductId"],
            "listing_id": row["listingId"],
            "channel_id": row["channelId"],
            "field": "price",
            "target_value": str(150 + index * 100),
            "currency": "EUR",
            "unit": "EUR",
        }
        for index, row in enumerate(rows)
    ]
    revision_response = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/draft/revisions",
        headers=auth_headers,
        json={"expected_version": 0, "metadata": {}, "changes": changes},
    )
    assert revision_response.status_code == 201
    if deactivate_before_review:
        from app.flowhub.auth.models import FlowHubUser
        from app.flowhub.pricing_matrix.models import ChannelPricingPolicyHead
        from app.flowhub.pricing_matrix.service import PricingMatrixService

        user = db.query(FlowHubUser).first()
        head = db.get(ChannelPricingPolicyHead, "woocommerce:primary")
        assert user is not None and head is not None
        PricingMatrixService(db).deactivate(
            channel_id="woocommerce:primary",
            expected_head_version=head.head_version,
            reason="Unified Workspace missing activation test",
            user=user,
        )
    review_response = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews",
        headers=auth_headers,
        json={"draft_revision_id": revision_response.json()["id"]},
    )
    assert review_response.status_code == 201
    return workspace, review_response.json()


def _run_dry_run(client, auth_headers, workspace, review, selection):
    """Advance an explicitly saved selection through the canonical boundary."""
    assert "manifestId" not in selection
    response = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews/{review['id']}/dry-run",
        headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    dry_run = response.json()
    assert dry_run["status"] == "passed", dry_run
    assert dry_run["reviewedCount"] >= dry_run["writeCount"]
    return SimpleNamespace(status_code=200, text="", json=lambda: {**selection, **dry_run})


def _select_and_dry_run(client, auth_headers, workspace, review, item_ids):
    selection = client.put(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews/{review['id']}/selection",
        headers=auth_headers,
        json={"review_item_ids": item_ids},
    )
    assert selection.status_code == 200, selection.text
    return _run_dry_run(client, auth_headers, workspace, review, selection.json())


def test_replace_draft_mode_drops_changes_omitted_from_the_new_revision(
    client, auth_headers, db
):
    workspace, initial_review = _saved_review(
        client, auth_headers, db, second_product=True
    )
    first = initial_review["items"][0]
    omitted_listing_id = initial_review["items"][1]["listingId"]

    replacement = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/draft/revisions",
        headers=auth_headers,
        json={
            "expected_version": 1,
            "mode": "replace",
            "metadata": {"test": "replace"},
            "changes": [
                {
                    "canonical_product_id": first["canonicalProductId"],
                    "listing_id": first["listingId"],
                    "channel_id": first["channelId"],
                    "field": "price",
                    "target_value": "175",
                    "currency": "EUR",
                    "unit": "EUR",
                }
            ],
        },
    )
    assert replacement.status_code == 201, replacement.text
    assert replacement.json()["draftVersion"] == 2

    reviewed = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews",
        headers=auth_headers,
        json={"draft_revision_id": replacement.json()["id"]},
    )
    assert reviewed.status_code == 201, reviewed.text
    result = reviewed.json()
    assert result["summary"]["total"] == 1
    assert [item["listingId"] for item in result["items"]] == [first["listingId"]]
    assert omitted_listing_id not in {item["listingId"] for item in result["items"]}


def test_stale_channel_cache_is_a_warning_and_remains_auto_selectable(
    client, auth_headers, db
):
    """A merely-stale (but successfully fetched) Channel Cache is a caveat, not
    a blocker: the Apply pipeline re-verifies the live cache version/checksum
    before writing, so a stale read is still safe to auto-select. Blocking it
    here broke automatic selection for the common case of a Channel Cache that
    has not been re-read in the last cycle."""
    from app.flowhub.unified_workspace.models import ChannelCache

    workspace, review = _saved_review(client, auth_headers, db)
    assert review["items"][0]["eligible"] is True
    assert review["items"][0]["warnings"] == []

    cache = db.query(ChannelCache).filter_by(listing_id=review["items"][0]["listingId"]).one()
    cache.freshness = "stale"
    db.commit()

    restale = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews",
        headers=auth_headers,
        json={"draft_revision_id": review["draftRevisionId"]},
    )
    assert restale.status_code == 201, restale.text
    item = restale.json()["items"][0]
    assert item["eligible"] is True
    assert item["errors"] == []
    assert item["warnings"] == ["channel_cache_not_fresh"]
    assert item["validationState"] == "warning"

    selection = client.put(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews/{restale.json()['id']}/selection",
        headers=auth_headers,
        json={"review_item_ids": [item["id"]]},
    )
    assert selection.status_code == 200, selection.text


def test_failed_channel_cache_fetch_still_blocks_review(client, auth_headers, db):
    """Unlike mere staleness, a failed fetch leaves no trustworthy Channel
    baseline to compare against -- this must remain a hard block."""
    from app.flowhub.unified_workspace.models import ChannelCache

    workspace, review = _saved_review(client, auth_headers, db)
    cache = db.query(ChannelCache).filter_by(listing_id=review["items"][0]["listingId"]).one()
    cache.fetch_status = "failed"
    db.commit()

    refreshed = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews",
        headers=auth_headers,
        json={"draft_revision_id": review["draftRevisionId"]},
    )
    assert refreshed.status_code == 201, refreshed.text
    item = refreshed.json()["items"][0]
    assert item["eligible"] is False
    assert "channel_cache_unavailable" in item["errors"]
    assert item["validationState"] == "error"


def test_generate_review_auto_selects_both_price_increases_and_decreases(
    client, auth_headers, db
):
    workspace, review = _saved_review(client, auth_headers, db, second_product=True)
    increase, decrease = review["items"]
    assert float(increase["target"]) > float(increase["current"])
    # _saved_review only writes increases; flip the second product's target
    # below its current price to cover a genuine decrease too.
    lowered = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/draft/revisions",
        headers=auth_headers,
        json={
            "expected_version": 1,
            "mode": "merge",
            "metadata": {},
            "changes": [
                {
                    "canonical_product_id": decrease["canonicalProductId"],
                    "listing_id": decrease["listingId"],
                    "channel_id": decrease["channelId"],
                    "field": "price",
                    "target_value": "80",
                    "currency": "EUR",
                    "unit": "EUR",
                }
            ],
        },
    )
    assert lowered.status_code == 201, lowered.text
    reviewed = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews",
        headers=auth_headers,
        json={"draft_revision_id": lowered.json()["id"]},
    )
    assert reviewed.status_code == 201, reviewed.text
    by_listing = {item["listingId"]: item for item in reviewed.json()["items"]}
    assert by_listing[increase["listingId"]]["eligible"] is True
    assert float(by_listing[increase["listingId"]]["target"]) > float(by_listing[increase["listingId"]]["current"])
    assert by_listing[decrease["listingId"]]["eligible"] is True
    assert float(by_listing[decrease["listingId"]]["target"]) < float(by_listing[decrease["listingId"]]["current"])


def test_formatting_only_price_difference_is_not_a_change(client, auth_headers, db):
    """Canonical pricing semantics: "100", "100.0", and "100.00" are the same
    value. A formatting-only difference must never be treated as a change."""
    _seed(db)
    workspace = _create(client, auth_headers)
    row = client.get(
        f"/api/v2/unified-workspaces/{workspace['id']}/grid", headers=auth_headers
    ).json()["items"][0]
    assert row["fields"]["price"]["current"] == "100"

    revision = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/draft/revisions",
        headers=auth_headers,
        json={
            "expected_version": 0,
            "metadata": {},
            "changes": [
                {
                    "canonical_product_id": row["canonicalProductId"],
                    "listing_id": row["listingId"],
                    "channel_id": row["channelId"],
                    "field": "price",
                    "target_value": "100.00",
                    "currency": "EUR",
                    "unit": "EUR",
                }
            ],
        },
    )
    assert revision.status_code == 201, revision.text

    regrid = client.get(
        f"/api/v2/unified-workspaces/{workspace['id']}/grid", headers=auth_headers
    ).json()["items"][0]
    assert regrid["fields"]["price"]["current"] == "100"
    assert regrid["fields"]["price"]["target"] == "100"

    review = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews",
        headers=auth_headers,
        json={"draft_revision_id": revision.json()["id"]},
    )
    assert review.status_code == 422, review.text
    assert review.json()["detail"]["code"] == "REVIEW_EMPTY"


def test_preview_and_review_generation_perform_zero_channel_writes(
    client, auth_headers, db, monkeypatch
):
    """Preview (grid/grouped-grid), Draft save, and Review generation must
    never reach an outbound Channel write adapter -- only an explicit,
    confirmed Apply may write."""
    _seed(db)
    workspace = _create(client, auth_headers)

    def fail(*_args, **_kwargs):
        pytest.fail("Preview/Review must never call an outbound Channel write adapter")

    monkeypatch.setattr(
        "app.connectors.destinations.woocommerce.write_adapter.WooCommercePriceWriteAdapter.execute_item",
        fail,
    )
    monkeypatch.setattr(
        "app.flowhub.unified_workspace.connectors.WooCommerceWorkspaceConnector.apply_updates",
        fail,
    )

    row = client.get(
        f"/api/v2/unified-workspaces/{workspace['id']}/grid", headers=auth_headers
    ).json()["items"][0]
    client.get(
        f"/api/v2/unified-workspaces/{workspace['id']}/grouped-grid?page=1&pageSize=100&view=all",
        headers=auth_headers,
    )
    revision = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/draft/revisions",
        headers=auth_headers,
        json={
            "expected_version": 0,
            "metadata": {},
            "changes": [
                {
                    "canonical_product_id": row["canonicalProductId"],
                    "listing_id": row["listingId"],
                    "channel_id": row["channelId"],
                    "field": "price",
                    "target_value": "125",
                    "currency": "EUR",
                    "unit": "EUR",
                }
            ],
        },
    )
    assert revision.status_code == 201
    review = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews",
        headers=auth_headers,
        json={"draft_revision_id": revision.json()["id"]},
    )
    assert review.status_code == 201
    assert review.json()["items"][0]["eligible"] is True
    selection = client.put(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews/{review.json()['id']}/selection",
        headers=auth_headers,
        json={"review_item_ids": [review.json()["items"][0]["id"]]},
    )
    assert selection.status_code == 200


def test_apply_is_selected_only_idempotent_and_patches_verified_cache(
    client, auth_headers, db, monkeypatch
):
    from app.flowhub.unified_workspace.connectors import ListingUpdateResult
    from app.flowhub.unified_workspace.models import ChannelCache
    from app.flowhub.write_pipeline.workspace_contracts import WriteOutcome

    workspace, review = _saved_review(client, auth_headers, db, second_product=True)
    selected = review["items"][0]
    selection = _select_and_dry_run(client, auth_headers, workspace, review, [selected["id"]])

    async def fake_apply(_self, updates, *, requested_by):
        assert requested_by
        assert len(updates) == 1
        update = updates[0]
        return [
            ListingUpdateResult(
                listing_id=update.listing_id,
                outcome=WriteOutcome.VERIFIED_APPLIED,
                response={"id": "provider-1"},
                external_response_id="provider-1",
                accepted_price=update.target_price,
            )
        ]

    monkeypatch.setattr(
        "app.flowhub.unified_workspace.connectors.WooCommerceWorkspaceConnector.apply_updates",
        fake_apply,
    )
    headers = {
        **auth_headers,
        "Idempotency-Key": "selected-only-1",
        "X-Correlation-ID": "apply-selected-only",
    }
    applied = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/apply",
        headers=headers,
        json={
            "review_id": review["id"],
            "expected_selection_checksum": selection.json()["selectionChecksum"],
            "manifest_id": selection.json()["manifestId"],
            "expected_manifest_checksum": selection.json()["manifestChecksum"],
            "confirmed": True,
        },
    )
    assert applied.status_code == 202, applied.text
    result = applied.json()
    assert result["status"] == "applied"
    assert len(result["items"]) == 1
    assert result["items"][0]["listingId"] == selected["listingId"]
    cache = db.query(ChannelCache).filter_by(listing_id=selected["listingId"]).one()
    assert cache.price_raw == selected["target"]
    repeated = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/apply",
        headers=headers,
        json={
            "review_id": review["id"],
            "expected_selection_checksum": selection.json()["selectionChecksum"],
            "manifest_id": selection.json()["manifestId"],
            "expected_manifest_checksum": selection.json()["manifestChecksum"],
            "confirmed": True,
        },
    )
    assert repeated.status_code == 202
    assert repeated.json()["id"] == result["id"]


def test_apply_manifest_payload_matches_live_listing_and_cache_state_used_by_write_intent(
    client, auth_headers, db, monkeypatch
):
    from app.flowhub.unified_workspace.connectors import ListingUpdateResult
    from app.flowhub.unified_workspace.domain import checksum
    from app.flowhub.unified_workspace.models import ApplyManifestOperation, ChannelCache, Listing
    from app.flowhub.write_pipeline.workspace_contracts import WriteOutcome

    workspace, review = _saved_review(client, auth_headers, db)
    selected = review["items"][0]
    selection = _select_and_dry_run(client, auth_headers, workspace, review, [selected["id"]])
    listing = db.get(Listing, selected["listingId"])
    cache_version_at_manifest_time = (
        db.query(ChannelCache).filter_by(listing_id=selected["listingId"]).one().cache_version
    )

    async def fake_apply(_self, updates, *, requested_by):
        update = updates[0]
        return [
            ListingUpdateResult(
                listing_id=update.listing_id,
                outcome=WriteOutcome.VERIFIED_APPLIED,
                response={"id": "provider-1"},
                external_response_id="provider-1",
                accepted_price=update.target_price,
            )
        ]

    monkeypatch.setattr(
        "app.flowhub.unified_workspace.connectors.WooCommerceWorkspaceConnector.apply_updates",
        fake_apply,
    )
    applied = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/apply",
        headers={**auth_headers, "Idempotency-Key": "payload-hash-parity"},
        json={
            "review_id": review["id"],
            "expected_selection_checksum": selection.json()["selectionChecksum"],
            "manifest_id": selection.json()["manifestId"],
            "expected_manifest_checksum": selection.json()["manifestChecksum"],
            "confirmed": True,
        },
    )
    assert applied.status_code == 202, applied.text
    manifest_op = (
        db.query(ApplyManifestOperation)
        .filter_by(manifest_id=selection.json()["manifestId"], review_item_id=selected["id"])
        .one()
    )
    # The manifest's payload was built by the same _operation_payload helper
    # _write_intent uses; it must describe the listing/cache identity that
    # was actually in effect when the manifest was generated (before Apply's
    # own successful write bumped the cache version), proving there is
    # exactly one source of truth for what feeds the checksum rather than
    # two independently maintained copies.
    payload = manifest_op.listing_payload_json
    assert payload["listing"] == listing.id
    assert payload["mapping_version"] == listing.mapping_version
    assert payload["cache_version"] == cache_version_at_manifest_time
    assert payload["targets"]["price"] == selected["target"]
    assert manifest_op.listing_payload_hash == checksum(payload)


def test_select_review_items_generates_apply_manifest_with_payload_bound_checksum(
    client, auth_headers, db
):
    workspace, review = _saved_review(client, auth_headers, db)
    item = review["items"][0]
    first = _select_and_dry_run(client, auth_headers, workspace, review, [item["id"]])
    body = first.json()
    assert body["manifestId"]
    assert body["manifestChecksum"]
    assert len(body["operations"]) == 1
    assert body["operations"][0]["listingId"] == item["listingId"]
    assert body["operations"][0]["channelId"] == item["channelId"]
    assert body["operations"][0]["target"] == item["target"]
    assert body["affectedChannelIds"] == [item["channelId"]]

    # Reselecting the identical (listing, channel, field) scope after the
    # *target value* changes via a new Draft Revision + Review produces a
    # different manifestChecksum -- proving the manifest is bound to the
    # payload, not just to which fields are selected (unlike the pre-existing
    # selectionChecksum, which is scope-only).
    revision = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/draft/revisions",
        headers=auth_headers,
        json={
            "expected_version": 1,
            "metadata": {},
            "changes": [
                {
                    "canonical_product_id": item["canonicalProductId"],
                    "listing_id": item["listingId"],
                    "channel_id": item["channelId"],
                    "field": "price",
                    "target_value": "999",
                    "currency": "EUR",
                    "unit": "EUR",
                }
            ],
        },
    )
    assert revision.status_code == 201, revision.text
    reviewed = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews",
        headers=auth_headers,
        json={"draft_revision_id": revision.json()["id"]},
    )
    assert reviewed.status_code == 201, reviewed.text
    new_review = reviewed.json()
    new_item = new_review["items"][0]
    second = _select_and_dry_run(client, auth_headers, workspace, new_review, [new_item["id"]])
    assert second.json()["manifestChecksum"] != body["manifestChecksum"]


def test_apply_rejects_when_selection_changed_after_manifest_generated(
    client, auth_headers, db
):
    from app.flowhub.unified_workspace.models import ApplyJob

    workspace, review = _saved_review(client, auth_headers, db, second_product=True)
    first, second = review["items"]
    original = _select_and_dry_run(client, auth_headers, workspace, review, [first["id"]])
    manifest_id = original.json()["manifestId"]
    manifest_checksum = original.json()["manifestChecksum"]
    selection_checksum = original.json()["selectionChecksum"]

    changed = client.put(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews/{review['id']}/selection",
        headers=auth_headers,
        json={"review_item_ids": [second["id"]]},
    )
    assert changed.status_code == 200

    response = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/apply",
        headers={**auth_headers, "Idempotency-Key": "stale-manifest-selection"},
        json={
            "review_id": review["id"],
            "expected_selection_checksum": selection_checksum,
            "manifest_id": manifest_id,
            "expected_manifest_checksum": manifest_checksum,
            "confirmed": True,
        },
    )
    assert response.status_code == 409
    # The selection-checksum guard (pre-existing) is reached first since the
    # selection itself also changed; either code proves no stale write occurs.
    assert response.json()["detail"]["code"] in {
        "APPLY_SELECTION_CHECKSUM_MISMATCH",
        "STALE_APPLY_MANIFEST",
    }
    assert db.query(ApplyJob).filter_by(review_id=review["id"]).count() == 0


def test_apply_rejects_when_manifest_checksum_submitted_does_not_match_manifest_row(
    client, auth_headers, db
):
    from app.flowhub.unified_workspace.models import ApplyJob

    workspace, review = _saved_review(client, auth_headers, db)
    item = review["items"][0]
    selection = _select_and_dry_run(client, auth_headers, workspace, review, [item["id"]])
    response = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/apply",
        headers={**auth_headers, "Idempotency-Key": "tampered-manifest-checksum"},
        json={
            "review_id": review["id"],
            "expected_selection_checksum": selection.json()["selectionChecksum"],
            "manifest_id": selection.json()["manifestId"],
            "expected_manifest_checksum": "a" * 64,
            "confirmed": True,
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "APPLY_MANIFEST_CHECKSUM_MISMATCH"
    assert db.query(ApplyJob).filter_by(review_id=review["id"]).count() == 0


def test_apply_after_stale_manifest_rejection_can_retry_with_fresh_manifest(
    client, auth_headers, db, monkeypatch
):
    from app.flowhub.unified_workspace.connectors import ListingUpdateResult
    from app.flowhub.write_pipeline.workspace_contracts import WriteOutcome

    workspace, review = _saved_review(client, auth_headers, db, second_product=True)
    first, second = review["items"]
    stale = _select_and_dry_run(client, auth_headers, workspace, review, [first["id"]])
    stale_manifest_id = stale.json()["manifestId"]
    stale_manifest_checksum = stale.json()["manifestChecksum"]
    stale_selection_checksum = stale.json()["selectionChecksum"]

    fresh = _select_and_dry_run(client, auth_headers, workspace, review, [second["id"]])

    rejected = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/apply",
        headers={**auth_headers, "Idempotency-Key": "retry-1"},
        json={
            "review_id": review["id"],
            "expected_selection_checksum": stale_selection_checksum,
            "manifest_id": stale_manifest_id,
            "expected_manifest_checksum": stale_manifest_checksum,
            "confirmed": True,
        },
    )
    assert rejected.status_code == 409

    async def fake_apply(_self, updates, *, requested_by):
        update = updates[0]
        return [
            ListingUpdateResult(
                listing_id=update.listing_id,
                outcome=WriteOutcome.VERIFIED_APPLIED,
                response={"id": "provider-1"},
                external_response_id="provider-1",
                accepted_price=update.target_price,
            )
        ]

    monkeypatch.setattr(
        "app.flowhub.unified_workspace.connectors.WooCommerceWorkspaceConnector.apply_updates",
        fake_apply,
    )
    retried = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/apply",
        headers={**auth_headers, "Idempotency-Key": "retry-2"},
        json={
            "review_id": review["id"],
            "expected_selection_checksum": fresh.json()["selectionChecksum"],
            "manifest_id": fresh.json()["manifestId"],
            "expected_manifest_checksum": fresh.json()["manifestChecksum"],
            "confirmed": True,
        },
    )
    assert retried.status_code == 202, retried.text
    assert retried.json()["status"] == "applied"


def test_cache_change_marks_review_stale_and_blocks_apply(client, auth_headers, db):
    from app.flowhub.unified_workspace.models import ChannelCache

    workspace, review = _saved_review(client, auth_headers, db)
    item = review["items"][0]
    selection = _select_and_dry_run(client, auth_headers, workspace, review, [item["id"]])
    cache = db.query(ChannelCache).filter_by(listing_id=item["listingId"]).one()
    cache.cache_version += 1
    cache.checksum = "changed-after-review"
    db.commit()
    response = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/apply",
        headers={**auth_headers, "Idempotency-Key": "stale-1"},
        json={
            "review_id": review["id"],
            "expected_selection_checksum": selection.json()["selectionChecksum"],
            "manifest_id": selection.json()["manifestId"],
            "expected_manifest_checksum": selection.json()["manifestChecksum"],
            "confirmed": True,
        },
    )
    assert response.status_code == 409
    # The manifest freshness check (bound to cache_version/checksum via the
    # operation payload) now catches this class of drift before
    # _assert_review_fresh's own cache-identity check is reached.
    assert response.json()["detail"]["code"] == "STALE_APPLY_MANIFEST"


def test_pricing_policy_must_be_activated_before_review(client, auth_headers, db):
    _workspace, review = _saved_review(
        client, auth_headers, db, deactivate_before_review=True
    )

    assert review["status"] == "blocked"
    assert "policy_not_activated" in review["items"][0]["errors"]


def test_pricing_activation_change_marks_review_stale_before_apply(
    client, auth_headers, db, monkeypatch
):
    workspace, review = _saved_review(client, auth_headers, db)
    item = review["items"][0]
    confirmed = _select_and_dry_run(client, auth_headers, workspace, review, [item["id"]])
    _activate_replacement_policy(db)

    async def forbidden(*_args, **_kwargs):
        pytest.fail("stale pricing activation reached the Write Pipeline")

    monkeypatch.setattr(
        "app.flowhub.write_pipeline.service.WritePipelineService.execute_workspace",
        forbidden,
    )
    response = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/apply",
        headers={**auth_headers, "Idempotency-Key": "pricing-activation-stale"},
        json={
            "review_id": review["id"],
            "expected_selection_checksum": confirmed.json()["selectionChecksum"],
            "manifest_id": confirmed.json()["manifestId"],
            "expected_manifest_checksum": confirmed.json()["manifestChecksum"],
            "confirmed": True,
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "STALE_REVIEW"


def test_pricing_channel_config_change_marks_review_stale_before_apply(
    client, auth_headers, db, monkeypatch
):
    workspace, review = _saved_review(client, auth_headers, db)
    item = review["items"][0]
    confirmed = _select_and_dry_run(client, auth_headers, workspace, review, [item["id"]])

    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.pricing_matrix.service import PricingMatrixService

    user = db.query(FlowHubUser).first()
    assert user is not None
    PricingMatrixService(db).declare_unit(
        scope="channel",
        scope_reference="woocommerce:primary",
        currency="EUR",
        unit="EUR",
        connector_config_version="changed-after-review",
        user=user,
    )

    async def forbidden(*_args, **_kwargs):
        pytest.fail("stale pricing channel config reached the Write Pipeline")

    monkeypatch.setattr(
        "app.flowhub.write_pipeline.service.WritePipelineService.execute_workspace",
        forbidden,
    )
    response = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/apply",
        headers={**auth_headers, "Idempotency-Key": "pricing-config-stale"},
        json={
            "review_id": review["id"],
            "expected_selection_checksum": confirmed.json()["selectionChecksum"],
            "manifest_id": confirmed.json()["manifestId"],
            "expected_manifest_checksum": confirmed.json()["manifestChecksum"],
            "confirmed": True,
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "STALE_REVIEW"


def test_pricing_binding_failure_isolated_per_channel(db, admin):
    from app.flowhub.pricing_matrix.service import PricingMatrixService
    from app.flowhub.unified_workspace.services import UnifiedWorkspaceService

    _seed(db)
    workspace = UnifiedWorkspaceService(db).create_manual_workspace(
        name="Pricing Binding Isolation",
        selections=[{"connector_id": "woocommerce:primary", "product_id": "101"}],
        user=admin,
        correlation_id="pricing-binding-isolation",
    )
    result = PricingMatrixService(db).bind_workspace_channels(
        workspace_id=workspace["id"],
        channel_ids=["snappshop:main", "woocommerce:primary"],
        evaluated_at=datetime.now(timezone.utc).replace(tzinfo=None),
        execution_policy_snapshot={"operationVersion": "test"},
    )

    assert [item["channelId"] for item in result["bindings"]] == ["woocommerce:primary"]
    assert result["issues"] == {"snappshop:main": "policy_not_activated"}


def test_pricing_binding_race_blocks_before_write_pipeline(
    client, auth_headers, db, monkeypatch
):
    workspace, review = _saved_review(client, auth_headers, db)
    item = review["items"][0]
    confirmed = _select_and_dry_run(client, auth_headers, workspace, review, [item["id"]])

    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.pricing_matrix.models import ChannelPricingPolicyHead
    from app.flowhub.pricing_matrix.service import PricingMatrixService

    original_verify = PricingMatrixService.verify_workspace_channels
    calls = 0

    def verify_with_race(self, *, workspace_id, channel_ids):
        nonlocal calls
        calls += 1
        if calls == 3:
            user = self.db.query(FlowHubUser).first()
            head = self.db.get(ChannelPricingPolicyHead, "woocommerce:primary")
            assert user is not None and head is not None
            self.deactivate(
                channel_id="woocommerce:primary",
                expected_head_version=head.head_version,
                reason="Unified Workspace pricing race test",
                user=user,
            )
        return original_verify(self, workspace_id=workspace_id, channel_ids=channel_ids)

    monkeypatch.setattr(PricingMatrixService, "verify_workspace_channels", verify_with_race)

    async def forbidden(*_args, **_kwargs):
        pytest.fail("pricing binding race reached the Write Pipeline")

    monkeypatch.setattr(
        "app.flowhub.write_pipeline.service.WritePipelineService.execute_workspace",
        forbidden,
    )
    response = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/apply",
        headers={**auth_headers, "Idempotency-Key": "pricing-binding-race"},
        json={
            "review_id": review["id"],
            "expected_selection_checksum": confirmed.json()["selectionChecksum"],
            "manifest_id": confirmed.json()["manifestId"],
            "expected_manifest_checksum": confirmed.json()["manifestChecksum"],
            "confirmed": True,
        },
    )
    assert response.status_code == 202
    assert response.json()["status"] == "stale"
    assert calls >= 3


@pytest.mark.parametrize(
    ("disabled_resource", "draft_error", "review_error"),
    [
        ("listing", "LISTING_DISABLED", "listing_disabled"),
        ("channel", "CHANNEL_UNAVAILABLE", "channel_unavailable"),
        ("channel_unimplemented", "CHANNEL_UNAVAILABLE", "channel_unavailable"),
    ],
)
def test_disabled_listing_or_channel_is_read_only_and_review_ineligible(
    client,
    auth_headers,
    db,
    disabled_resource,
    draft_error,
    review_error,
):
    from app.flowhub.unified_workspace.models import Listing, WorkspaceChannel

    workspace, initial_review = _saved_review(client, auth_headers, db)
    item = initial_review["items"][0]
    listing = db.get(Listing, item["listingId"])
    channel = db.get(WorkspaceChannel, item["channelId"])
    assert listing is not None
    assert channel is not None
    if disabled_resource == "listing":
        listing.enabled = False
    elif disabled_resource == "channel_unimplemented":
        channel.implementation_state = "coming_soon"
    else:
        channel.enabled = False
    db.commit()

    grid = client.get(
        f"/api/v2/unified-workspaces/{workspace['id']}/grid",
        headers=auth_headers,
    )
    assert grid.status_code == 200, grid.text
    assert grid.json()["items"][0]["fields"]["price"]["readOnly"] is True
    grouped = client.get(
        f"/api/v2/unified-workspaces/{workspace['id']}/grouped-grid?page=1&pageSize=100&view=all",
        headers=auth_headers,
    )
    assert grouped.status_code == 200, grouped.text
    assert grouped.json()["items"][0]["children"][0]["fields"]["price"]["readOnly"] is True

    save = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/draft/revisions",
        headers=auth_headers,
        json={
            "expected_version": 1,
            "changes": [
                {
                    "canonical_product_id": item["canonicalProductId"],
                    "listing_id": item["listingId"],
                    "channel_id": item["channelId"],
                    "field": "price",
                    "target_value": "175",
                    "currency": "EUR",
                    "unit": "EUR",
                }
            ],
        },
    )
    assert save.status_code == 422, save.text
    assert save.json()["detail"]["code"] == draft_error

    reviewed = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews",
        headers=auth_headers,
        json={"draft_revision_id": initial_review["draftRevisionId"]},
    )
    assert reviewed.status_code == 201, reviewed.text
    result = reviewed.json()
    assert result["status"] == "blocked"
    assert result["summary"]["eligible"] == 0
    assert review_error in result["items"][0]["errors"]

    selection = client.put(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews/{result['id']}/selection",
        headers=auth_headers,
        json={"review_item_ids": [result["items"][0]["id"]]},
    )
    assert selection.status_code == 409
    assert selection.json()["detail"]["code"] == "REVIEW_NOT_READY"


@pytest.mark.parametrize(
    "disabled_resource", ["listing", "channel", "channel_unimplemented"]
)
def test_disabled_listing_or_channel_after_review_blocks_apply_before_provider(
    client, auth_headers, db, monkeypatch, disabled_resource
):
    from app.flowhub.unified_workspace.models import Listing, WorkspaceChannel

    workspace, review = _saved_review(client, auth_headers, db)
    item = review["items"][0]
    confirmed = _select_and_dry_run(client, auth_headers, workspace, review, [item["id"]])

    from app.flowhub.unified_workspace.services import UnifiedWorkspaceService

    original_acquire = UnifiedWorkspaceService._acquire_listing_locks

    def disable_after_lock(self, workspace_id, job_id, lock_scope):
        result = original_acquire(self, workspace_id, job_id, lock_scope)
        if disabled_resource == "listing":
            resource = self.db.get(Listing, item["listingId"])
            assert resource is not None
            resource.enabled = False
        else:
            resource = self.db.get(WorkspaceChannel, item["channelId"])
            assert resource is not None
            if disabled_resource == "channel_unimplemented":
                resource.implementation_state = "coming_soon"
            else:
                resource.enabled = False
        self.db.commit()
        return result

    monkeypatch.setattr(
        UnifiedWorkspaceService, "_acquire_listing_locks", disable_after_lock
    )

    async def forbidden(*_args, **_kwargs):
        pytest.fail("disabled Listing or Channel reached the Write Pipeline")

    monkeypatch.setattr(
        "app.flowhub.write_pipeline.service.WritePipelineService.execute_workspace",
        forbidden,
    )
    response = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/apply",
        headers={
            **auth_headers,
            "Idempotency-Key": f"disabled-after-review-{disabled_resource}",
        },
        json={
            "review_id": review["id"],
            "expected_selection_checksum": confirmed.json()["selectionChecksum"],
            "manifest_id": confirmed.json()["manifestId"],
            "expected_manifest_checksum": confirmed.json()["manifestChecksum"],
            "confirmed": True,
        },
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "STALE_REVIEW"


def test_restore_creates_new_revision_without_mutating_history(client, auth_headers, db):
    workspace, review = _saved_review(client, auth_headers, db)
    source_revision_id = review["draftRevisionId"]
    response = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/draft/revisions/{source_revision_id}/restore",
        headers=auth_headers,
        json={"expected_version": 1},
    )
    assert response.status_code == 201
    restored = response.json()
    assert restored["id"] != source_revision_id
    assert restored["restoredFromRevisionId"] == source_revision_id
    assert restored["revisionNumber"] == 2
    history = client.get(
        f"/api/v2/unified-workspaces/{workspace['id']}/draft/revisions", headers=auth_headers
    ).json()
    assert history["total"] == 2


def test_listing_schema_supports_multiple_marketplace_listings_without_collapse(db, admin):
    from app.flowhub.unified_workspace.models import Listing
    from app.flowhub.unified_workspace.services import UnifiedWorkspaceService

    _seed(db)
    workspace = UnifiedWorkspaceService(db).create_manual_workspace(
        name="Cardinality",
        selections=[{"connector_id": "woocommerce:primary", "product_id": "101"}],
        user=admin,
        correlation_id="cardinality",
    )
    existing = db.query(Listing).filter_by(channel_id="woocommerce:primary").one()
    service = UnifiedWorkspaceService(db)
    service._seed_channels()
    first = Listing(
        id=str(uuid.uuid4()),
        canonical_product_id=existing.canonical_product_id,
        channel_id="snappshop:main",
        external_primary_id="SNP-1",
        external_id_type="product_number",
        secondary_identifiers_json={},
        sku="S-1",
        label="Snapp Listing One",
        mapping_state="resolved",
        mapping_version=1,
        capability_state_json={},
        enabled=True,
    )
    second = Listing(
        id=str(uuid.uuid4()),
        canonical_product_id=existing.canonical_product_id,
        channel_id="snappshop:main",
        external_primary_id="SNP-2",
        external_id_type="product_number",
        secondary_identifiers_json={},
        sku="S-2",
        label="Snapp Listing Two",
        mapping_state="resolved",
        mapping_version=1,
        capability_state_json={},
        enabled=True,
    )
    db.add_all([first, second])
    db.commit()
    assert (
        db.query(Listing)
        .filter_by(canonical_product_id=existing.canonical_product_id, channel_id="snappshop:main")
        .count()
        == 2
    )
    assert workspace["entryPoint"] == "manual"


def test_source_workspace_requires_persisted_source_and_never_reads_provider(
    client, auth_headers, db, monkeypatch
):
    _seed(db)
    calls = 0

    async def fake_preview(_self, _user):
        nonlocal calls
        calls += 1
        return SimpleNamespace(
            id="legacy-preview-1",
            sourceId="nextcloud:primary",
            sourceName="Price source.xlsx",
            startedAt=datetime(2026, 1, 2, 3, 4, 5),
            rows=[
                {
                    "source": {"row": 7, "sku": "SKU-101"},
                    "matchedProduct": {"productId": "101"},
                    "proposedPrice": "130",
                    "sourceStock": 8,
                    "errors": [],
                    "warnings": ["source-warning"],
                },
                {
                    "source": {"row": 8, "sku": "UNMATCHED"},
                    "matchedProduct": None,
                    "proposedPrice": "140",
                    "sourceStock": 2,
                    "errors": ["unmatched"],
                    "warnings": [],
                },
            ],
        )

    monkeypatch.setattr(
        "app.flowhub.workspace.price_workflow.WorkspacePriceWorkflowService.preview_from_nextcloud",
        fake_preview,
    )
    response = client.post(
        "/api/v2/unified-workspaces/source",
        headers={**auth_headers, "X-Correlation-ID": "source-read-once"},
        json={"name": "Source Test"},
    )
    assert response.status_code == 422, response.text
    assert any(
        detail["loc"][-1] == "source_id" and detail["type"] == "missing"
        for detail in response.json()["detail"]
    )
    assert calls == 0


def test_preferences_grid_filters_audit_and_mapping_decisions(client, auth_headers, db):
    from app.flowhub.unified_workspace.models import CanonicalProduct

    _seed(db)
    workspace = _create(client, auth_headers)
    default_preferences = client.get(
        "/api/v2/unified-workspaces/preferences/me", headers=auth_headers
    )
    assert default_preferences.status_code == 200
    assert default_preferences.json()["version"] == 0
    saved = client.put(
        "/api/v2/unified-workspaces/preferences/me",
        headers=auth_headers,
        json={
            "expected_version": 0,
            "visibleChannelIds": ["woocommerce:primary"],
            "channelOrder": ["snappshop:main", "woocommerce:primary"],
            "visibleFields": {"price": True, "stock": False, "status": True, "sku": True},
            "displayNameSource": "woocommerce:primary",
        },
    )
    assert saved.status_code == 200
    assert saved.json()["version"] == 1
    conflict = client.put(
        "/api/v2/unified-workspaces/preferences/me",
        headers=auth_headers,
        json={
            "expected_version": 0,
            "visibleChannelIds": [],
            "channelOrder": [],
            "visibleFields": {},
            "displayNameSource": "canonical",
        },
    )
    assert conflict.status_code == 409
    invalid = client.put(
        "/api/v2/unified-workspaces/preferences/me",
        headers=auth_headers,
        json={
            "expected_version": 1,
            "visibleChannelIds": ["digikala:main"],
            "channelOrder": [],
            "visibleFields": {},
            "displayNameSource": "canonical",
        },
    )
    assert invalid.status_code == 422

    grid = client.get(
        f"/api/v2/unified-workspaces/{workspace['id']}/grid",
        headers=auth_headers,
        params={
            "search": "Canonical",
            "productType": "simple",
            "mappingState": "resolved",
            "channelId": "woocommerce:primary",
            "sku": "SKU-101",
            # ChannelCache.status is canonical availability (instock/
            # outofstock), never provider publication state -- it is the
            # governed "status" write dimension (see the accepted_status
            # write-back in _record_listing_success), matching the seeded
            # stock_status="instock", not status="publish".
            "channelStatus": "instock",
            "minPrice": 90,
            "maxPrice": 110,
            "stockQuantity": 5,
            "sort": "price:desc,stock:asc",
        },
    )
    assert grid.status_code == 200
    row = grid.json()["items"][0]

    proposed = CanonicalProduct(
        id=str(uuid.uuid4()),
        name="Approved Canonical Product",
        sku="APPROVED-1",
        product_type="simple",
        status="active",
    )
    db.add(proposed)
    db.commit()
    mapping = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/mappings/{row['listingId']}/decisions",
        headers=auth_headers,
        json={
            "proposed_canonical_product_id": proposed.id,
            "decision": "approved",
            "reason": "Owner verified exact external identity",
            "evidence": {"external_id": "101"},
        },
    )
    assert mapping.status_code == 201, mapping.text
    assert mapping.json()["canonicalProductId"] == proposed.id
    assert mapping.json()["mappingVersion"] == 2
    audit = client.get(
        f"/api/v2/unified-workspaces/{workspace['id']}/audit",
        headers=auth_headers,
        params={"page": 1, "pageSize": 200},
    )
    assert audit.status_code == 200
    assert any(item["eventType"] == "mapping_approved" for item in audit.json()["items"])


@pytest.mark.asyncio
async def test_cache_refresh_is_explicit_sanitized_and_blocks_coming_soon(db, admin, monkeypatch):
    from app.flowhub.unified_workspace.services import UnifiedWorkspaceService

    _seed(db)
    service = UnifiedWorkspaceService(db)
    service.create_manual_workspace(
        name="Refresh",
        selections=[{"connector_id": "woocommerce:primary", "product_id": "101"}],
        user=admin,
        correlation_id="refresh-create",
    )

    async def fake_refresh(_self, channel_id, username):
        assert channel_id == "woocommerce:primary"
        assert username == admin.username
        return {"status": "ok", "raw": {"secret": "never-audited"}}

    monkeypatch.setattr(
        "app.flowhub.commerce.service.CommerceHubService.refresh_channel_cache", fake_refresh
    )
    result = await service.refresh_channel_cache("woocommerce:primary", admin, "refresh-explicit")
    assert result["synchronizedListings"] == 1
    with pytest.raises(Exception) as exc:
        await service.refresh_channel_cache("digikala:main", admin, "refresh-coming-soon")
    assert getattr(exc.value, "status_code", None) == 422


def test_apply_partial_failure_is_auditable_and_retry_safe(client, auth_headers, db, monkeypatch):
    from app.flowhub.unified_workspace.connectors import ListingUpdateResult

    workspace, review = _saved_review(client, auth_headers, db, second_product=True)
    item_ids = [item["id"] for item in review["items"]]
    selected = _select_and_dry_run(client, auth_headers, workspace, review, item_ids)

    async def partial(_self, updates, *, requested_by):
        from app.flowhub.write_pipeline.workspace_contracts import WriteOutcome

        assert requested_by
        return [
            ListingUpdateResult(
                listing_id=updates[0].listing_id,
                outcome=WriteOutcome.VERIFIED_APPLIED,
                response={"id": "success-1"},
                accepted_price=updates[0].target_price,
            ),
            ListingUpdateResult(
                listing_id=updates[1].listing_id,
                outcome=WriteOutcome.FAILED,
                response={"request_id": "failed-2"},
                error_category="rate_limit",
                error_message="try again",
                retry_eligible=True,
            ),
        ]

    monkeypatch.setattr(
        "app.flowhub.unified_workspace.connectors.WooCommerceWorkspaceConnector.apply_updates",
        partial,
    )
    response = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/apply",
        headers={**auth_headers, "Idempotency-Key": "partial-apply-1"},
        json={
            "review_id": review["id"],
            "expected_selection_checksum": selected.json()["selectionChecksum"],
            "manifest_id": selected.json()["manifestId"],
            "expected_manifest_checksum": selected.json()["manifestChecksum"],
            "confirmed": True,
        },
    )
    assert response.status_code == 202, response.text
    job = response.json()
    assert job["status"] == "partially_applied"
    assert {item["status"] for item in job["items"]} == {"applied", "failed"}
    failed = next(item for item in job["items"] if item["status"] == "failed")
    assert failed["errorMessage"] == "try again"
    fetched = client.get(
        f"/api/v2/unified-workspaces/{workspace['id']}/apply/{job['id']}",
        headers=auth_headers,
    )
    assert fetched.status_code == 200


def test_shared_write_pipeline_authority_and_selection_checksum_conflict(
    client, auth_headers, db, monkeypatch
):
    from app.flowhub.write_pipeline.workspace_contracts import WorkspaceWriteResult, WriteOutcome

    workspace, review = _saved_review(client, auth_headers, db, second_product=True)
    first, second = review["items"]
    confirmed = _select_and_dry_run(client, auth_headers, workspace, review, [first["id"]])
    checksum_a = confirmed.json()["selectionChecksum"]
    manifest_id_a = confirmed.json()["manifestId"]
    manifest_checksum_a = confirmed.json()["manifestChecksum"]
    replaced = _select_and_dry_run(client, auth_headers, workspace, review, [second["id"]])
    calls = []

    async def pipeline(_self, command, _user, *, reconcile_only=False):
        calls.append((command, reconcile_only))
        return [
            WorkspaceWriteResult(
                listing_id=intent.listing_id,
                outcome=WriteOutcome.VERIFIED_APPLIED,
                accepted_price=intent.target_price,
            )
            for intent in command.intents
        ]

    monkeypatch.setattr(
        "app.flowhub.write_pipeline.service.WritePipelineService.execute_workspace", pipeline
    )
    stale = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/apply",
        headers={**auth_headers, "Idempotency-Key": "selection-tab-a"},
        json={
            "review_id": review["id"],
            "expected_selection_checksum": checksum_a,
            "manifest_id": manifest_id_a,
            "expected_manifest_checksum": manifest_checksum_a,
            "confirmed": True,
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "APPLY_SELECTION_CHECKSUM_MISMATCH"
    assert calls == []

    current_checksum = replaced.json()["selectionChecksum"]
    current_manifest_id = replaced.json()["manifestId"]
    current_manifest_checksum = replaced.json()["manifestChecksum"]
    applied = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/apply",
        headers={**auth_headers, "Idempotency-Key": "selection-tab-b"},
        json={
            "review_id": review["id"],
            "expected_selection_checksum": current_checksum,
            "manifest_id": current_manifest_id,
            "expected_manifest_checksum": current_manifest_checksum,
            "confirmed": True,
        },
    )
    assert applied.status_code == 202, applied.text
    assert len(calls) == 1
    command, reconcile_only = calls[0]
    assert reconcile_only is False
    assert command.selection_checksum == current_checksum
    assert [intent.listing_id for intent in command.intents] == [second["listingId"]]


@pytest.mark.parametrize("stale_dependency", ["ruleset", "cache_age"])
def test_ruleset_and_cache_max_age_block_apply_before_dispatch(
    client, auth_headers, db, monkeypatch, stale_dependency
):
    from datetime import timedelta

    from app.flowhub.unified_workspace.models import ChannelCache, Review
    from app.flowhub.unified_workspace.services import utcnow

    workspace, review = _saved_review(client, auth_headers, db)
    item = review["items"][0]
    confirmed = _select_and_dry_run(client, auth_headers, workspace, review, [item["id"]])
    if stale_dependency == "ruleset":
        db.get(Review, review["id"]).ruleset_version = "retired-ruleset"
    else:
        cache = db.query(ChannelCache).filter_by(listing_id=item["listingId"]).one()
        cache.fetched_at = utcnow() - timedelta(days=14)
    db.commit()

    async def forbidden(*_args, **_kwargs):
        pytest.fail("stale Review reached the Write Pipeline")

    monkeypatch.setattr(
        "app.flowhub.write_pipeline.service.WritePipelineService.execute_workspace", forbidden
    )
    response = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/apply",
        headers={**auth_headers, "Idempotency-Key": f"stale-{stale_dependency}"},
        json={
            "review_id": review["id"],
            "expected_selection_checksum": confirmed.json()["selectionChecksum"],
            "manifest_id": confirmed.json()["manifestId"],
            "expected_manifest_checksum": confirmed.json()["manifestChecksum"],
            "confirmed": True,
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "STALE_REVIEW"


def test_reconciliation_required_is_durable_and_never_marks_success(
    client, auth_headers, db, monkeypatch
):
    from app.flowhub.unified_workspace.connectors import ListingUpdateResult
    from app.flowhub.unified_workspace.models import ChannelCache, UnifiedAuditEntry, WorkspaceLock
    from app.flowhub.write_pipeline.models import (
        ProviderWriteAttempt,
        ProviderWriteAttemptEvent,
    )
    from app.flowhub.write_pipeline.workspace_contracts import WriteOutcome

    workspace, review = _saved_review(client, auth_headers, db)
    item = review["items"][0]
    confirmed = _select_and_dry_run(client, auth_headers, workspace, review, [item["id"]])
    before = db.query(ChannelCache).filter_by(listing_id=item["listingId"]).one().price_raw

    async def uncertain(_self, updates, *, requested_by):
        return [
            ListingUpdateResult(
                listing_id=updates[0].listing_id,
                outcome=WriteOutcome.RECONCILIATION_REQUIRED,
                error_category="readback_timeout",
                error_message="provider may have committed",
            )
        ]

    monkeypatch.setattr(
        "app.flowhub.unified_workspace.connectors.WooCommerceWorkspaceConnector.apply_updates",
        uncertain,
    )
    response = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/apply",
        headers={**auth_headers, "Idempotency-Key": "uncertain-durable-1"},
        json={
            "review_id": review["id"],
            "expected_selection_checksum": confirmed.json()["selectionChecksum"],
            "manifest_id": confirmed.json()["manifestId"],
            "expected_manifest_checksum": confirmed.json()["manifestChecksum"],
            "confirmed": True,
        },
    )
    assert response.status_code == 202, response.text
    job = response.json()
    assert job["status"] == "reconciliation_required"
    assert job["items"][0]["status"] == "reconciliation_required"
    assert db.query(ProviderWriteAttempt).filter_by(apply_job_id=job["id"]).count() == 1
    outcomes = {
        row.outcome
        for row in db.query(ProviderWriteAttemptEvent)
        .join(
            ProviderWriteAttempt,
            ProviderWriteAttempt.id == ProviderWriteAttemptEvent.attempt_id,
        )
        .filter(ProviderWriteAttempt.apply_job_id == job["id"])
    }
    assert {"dispatch_intent_recorded", "dispatched", "reconciliation_required"} <= outcomes
    assert db.query(WorkspaceLock).filter_by(apply_job_id=job["id"]).count() == 1
    assert db.query(ChannelCache).filter_by(listing_id=item["listingId"]).one().price_raw == before
    audit_types = {
        row.event_type
        for row in db.query(UnifiedAuditEntry).filter_by(apply_job_id=job["id"]).all()
    }
    assert "apply_item_succeeded" not in audit_types


def test_apply_global_listing_lock_mapping_conflict_and_expired_reclaim(
    client, auth_headers, db, monkeypatch
):
    from datetime import timedelta

    from app.flowhub.unified_workspace.connectors import ListingUpdateResult
    from app.flowhub.unified_workspace.models import ApplyJob, CanonicalProduct, WorkspaceLock
    from app.flowhub.unified_workspace.services import utcnow
    from app.flowhub.write_pipeline.workspace_contracts import WriteOutcome

    first_workspace, first_review = _saved_review(client, auth_headers, db)
    first_item = first_review["items"][0]
    first_selection = _select_and_dry_run(client, auth_headers, first_workspace, first_review, [first_item["id"]]).json()

    async def uncertain(_self, updates, *, requested_by):
        return [
            ListingUpdateResult(
                listing_id=updates[0].listing_id,
                outcome=WriteOutcome.RECONCILIATION_REQUIRED,
                error_message="unknown external outcome",
            )
        ]

    monkeypatch.setattr(
        "app.flowhub.unified_workspace.connectors.WooCommerceWorkspaceConnector.apply_updates",
        uncertain,
    )
    first_apply = client.post(
        f"/api/v2/unified-workspaces/{first_workspace['id']}/apply",
        headers={**auth_headers, "Idempotency-Key": "global-lock-first"},
        json={
            "review_id": first_review["id"],
            "expected_selection_checksum": first_selection["selectionChecksum"],
            "manifest_id": first_selection["manifestId"],
            "expected_manifest_checksum": first_selection["manifestChecksum"],
            "confirmed": True,
        },
    )
    assert first_apply.status_code == 202
    assert first_apply.json()["status"] == "reconciliation_required"

    proposed = CanonicalProduct(
        id=str(uuid.uuid4()),
        name="Lock conflict target",
        product_type="simple",
        status="active",
    )
    db.add(proposed)
    db.commit()
    mapping = client.post(
        f"/api/v2/unified-workspaces/{first_workspace['id']}/mappings/{first_item['listingId']}/decisions",
        headers=auth_headers,
        json={
            "proposed_canonical_product_id": proposed.id,
            "decision": "approved",
            "reason": "must be blocked while Apply owns Listing",
            "evidence": {},
        },
    )
    assert mapping.status_code == 409
    assert mapping.json()["detail"]["code"] == "LISTING_MUTATION_LOCKED"

    second_workspace = _create(client, auth_headers)
    second_row = client.get(
        f"/api/v2/unified-workspaces/{second_workspace['id']}/grid", headers=auth_headers
    ).json()["items"][0]
    revision = client.post(
        f"/api/v2/unified-workspaces/{second_workspace['id']}/draft/revisions",
        headers=auth_headers,
        json={
            "expected_version": 0,
            "metadata": {},
            "changes": [
                {
                    "canonical_product_id": second_row["canonicalProductId"],
                    "listing_id": second_row["listingId"],
                    "channel_id": second_row["channelId"],
                    "field": "price",
                    "target_value": "175",
                    "currency": "EUR",
                    "unit": "EUR",
                }
            ],
        },
    ).json()
    second_review = client.post(
        f"/api/v2/unified-workspaces/{second_workspace['id']}/reviews",
        headers=auth_headers,
        json={"draft_revision_id": revision["id"]},
    ).json()
    second_selection = _select_and_dry_run(client, auth_headers, second_workspace, second_review, [second_review["items"][0]["id"]]).json()
    blocked = client.post(
        f"/api/v2/unified-workspaces/{second_workspace['id']}/apply",
        headers={**auth_headers, "Idempotency-Key": "global-lock-second"},
        json={
            "review_id": second_review["id"],
            "expected_selection_checksum": second_selection["selectionChecksum"],
            "manifest_id": second_selection["manifestId"],
            "expected_manifest_checksum": second_selection["manifestChecksum"],
            "confirmed": True,
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "APPLY_SCOPE_LOCKED"

    lock = db.query(WorkspaceLock).filter_by(listing_id=second_row["listingId"]).one()
    lock.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    expired_uncertain_selection = _select_and_dry_run(client, auth_headers, second_workspace, second_review, [second_review["items"][0]["id"]]).json()
    expired_uncertain = client.post(
        f"/api/v2/unified-workspaces/{second_workspace['id']}/apply",
        headers={**auth_headers, "Idempotency-Key": "global-lock-expired-uncertain"},
        json={
            "review_id": second_review["id"],
            "expected_selection_checksum": expired_uncertain_selection["selectionChecksum"],
            "manifest_id": expired_uncertain_selection["manifestId"],
            "expected_manifest_checksum": expired_uncertain_selection["manifestChecksum"],
            "confirmed": True,
        },
    )
    assert expired_uncertain.status_code == 409
    assert (
        expired_uncertain.json()["detail"]["code"]
        == "APPLY_SCOPE_RECONCILIATION_REQUIRED"
    )
    terminal_job = db.query(ApplyJob).filter_by(
        idempotency_key="global-lock-expired-uncertain"
    ).one()
    assert terminal_job.status == "failed"
    lock = db.query(WorkspaceLock).filter_by(listing_id=second_row["listingId"]).one()
    lock.apply_job_id = terminal_job.id
    lock.workspace_id = second_workspace["id"]
    db.commit()
    reconfirmed = _select_and_dry_run(client, auth_headers, second_workspace, second_review, [second_review["items"][0]["id"]]).json()

    async def verified(_self, updates, *, requested_by):
        return [
            ListingUpdateResult(
                listing_id=updates[0].listing_id,
                outcome=WriteOutcome.VERIFIED_APPLIED,
                accepted_price=updates[0].target_price,
            )
        ]

    monkeypatch.setattr(
        "app.flowhub.unified_workspace.connectors.WooCommerceWorkspaceConnector.apply_updates",
        verified,
    )
    reclaimed = client.post(
        f"/api/v2/unified-workspaces/{second_workspace['id']}/apply",
        headers={**auth_headers, "Idempotency-Key": "global-lock-reclaimed"},
        json={
            "review_id": second_review["id"],
            "expected_selection_checksum": reconfirmed["selectionChecksum"],
            "manifest_id": reconfirmed["manifestId"],
            "expected_manifest_checksum": reconfirmed["manifestChecksum"],
            "confirmed": True,
        },
    )
    assert reclaimed.status_code == 202, reclaimed.text
    assert reclaimed.json()["status"] == "applied"
    assert db.query(WorkspaceLock).filter_by(listing_id=second_row["listingId"]).count() == 0


def test_manual_workspace_request_requires_exactly_one_selection_source(
    client, auth_headers, db
):
    _seed(db)

    neither = client.post(
        "/api/v2/unified-workspaces/manual",
        headers=auth_headers,
        json={"name": "Missing scope"},
    )
    both = client.post(
        "/api/v2/unified-workspaces/manual",
        headers=auth_headers,
        json={
            "name": "Ambiguous scope",
            "selections": [
                {"connector_id": "woocommerce:primary", "product_id": "101"}
            ],
            "catalog_scope": {},
        },
    )

    assert neither.status_code == 422
    assert both.status_code == 422


def test_catalog_scope_creates_one_immutable_cached_snapshot(client, auth_headers, db):
    from app.flowhub.unified_workspace.models import (
        ChannelCache,
        Listing,
        MappingRevision,
        SnapshotRow,
        WorkspaceSnapshot,
    )

    _seed(db)
    cached = db.query(_data_models.DlProductCache).filter_by(product_id="101").one()
    cached.categories = [{"id": 7, "name": "Accessories"}]
    db.commit()

    response = client.post(
        "/api/v2/unified-workspaces/manual",
        headers=auth_headers,
        json={
            "name": "Cached catalog",
            "catalog_scope": {
                "search": "Canonical Test",
                "category_id": 7,
                "product_type": "simple",
                "channel_id": "woocommerce:primary",
                "stock_state": "in_stock",
            },
        },
    )

    assert response.status_code == 201, response.text
    workspace = response.json()
    snapshot = db.get(WorkspaceSnapshot, workspace["snapshot"]["id"])
    assert snapshot is not None
    assert snapshot.acquisition_metadata_json == {
        "selection_count": 1,
        "read_external_source": False,
    }
    assert db.query(SnapshotRow).filter_by(snapshot_id=snapshot.id).count() == 1
    listing = db.query(Listing).filter_by(
        channel_id="woocommerce:primary", external_primary_id="101"
    ).one()
    assert listing.enabled is True
    assert db.query(MappingRevision).filter_by(listing_id=listing.id).count() == 1
    assert db.query(ChannelCache).filter_by(listing_id=listing.id).count() == 1


def test_catalog_bootstrap_never_refreshes_existing_authoritative_identity(
    client, auth_headers, db
):
    from app.flowhub.unified_workspace.models import ChannelCache, MappingRevision

    _seed(db)
    _create(client, auth_headers)
    channel_cache = db.query(ChannelCache).one()
    original = (
        channel_cache.cache_version,
        channel_cache.checksum,
        channel_cache.fetched_at,
        channel_cache.price_raw,
    )
    mapping_count = db.query(MappingRevision).count()
    cached = db.query(_data_models.DlProductCache).filter_by(product_id="101").one()
    cached.regular_price = "999"
    cached.price = "999"
    cached.record_hash = "newer-secondary-cache-evidence"
    db.commit()

    response = client.post(
        "/api/v2/unified-workspaces/manual",
        headers=auth_headers,
        json={"name": "Read-only catalog snapshot", "catalog_scope": {}},
    )

    assert response.status_code == 201, response.text
    db.expire_all()
    unchanged = db.query(ChannelCache).one()
    assert (
        unchanged.cache_version,
        unchanged.checksum,
        unchanged.fetched_at,
        unchanged.price_raw,
    ) == original
    assert db.query(MappingRevision).count() == mapping_count


def test_catalog_scope_excludes_disabled_listings_and_channels(client, auth_headers, db):
    from app.flowhub.unified_workspace.models import Listing, WorkspaceChannel

    _seed(db)
    _create(client, auth_headers)
    listing = db.query(Listing).filter_by(
        channel_id="woocommerce:primary", external_primary_id="101"
    ).one()
    listing.enabled = False
    db.commit()

    disabled_listing = client.post(
        "/api/v2/unified-workspaces/manual",
        headers=auth_headers,
        json={"name": "Disabled listing", "catalog_scope": {}},
    )
    assert disabled_listing.status_code == 422
    assert disabled_listing.json()["detail"]["code"] == "CATALOG_SCOPE_EMPTY"

    listing.enabled = True
    channel = db.get(WorkspaceChannel, "woocommerce:primary")
    assert channel is not None
    channel.enabled = False
    db.commit()
    disabled_channel = client.post(
        "/api/v2/unified-workspaces/manual",
        headers=auth_headers,
        json={"name": "Disabled channel", "catalog_scope": {}},
    )
    assert disabled_channel.status_code == 422
    assert disabled_channel.json()["detail"]["code"] == "CATALOG_SCOPE_EMPTY"

    channel.enabled = True
    channel.implementation_state = "coming_soon"
    db.commit()
    unimplemented_channel = client.post(
        "/api/v2/unified-workspaces/manual",
        headers=auth_headers,
        json={"name": "Unimplemented channel", "catalog_scope": {}},
    )
    assert unimplemented_channel.status_code == 422
    assert unimplemented_channel.json()["detail"]["code"] == "CATALOG_SCOPE_EMPTY"


def test_catalog_scope_rejects_empty_and_over_limit(client, auth_headers, db, monkeypatch):
    from app.flowhub.data_layer.models import DlProductCache
    from app.flowhub.unified_workspace import services as workspace_services

    _seed(db)
    empty = client.post(
        "/api/v2/unified-workspaces/manual",
        headers=auth_headers,
        json={"name": "Empty", "catalog_scope": {"channel_id": "snappshop:main"}},
    )
    assert empty.status_code == 422
    assert empty.json()["detail"]["code"] == "CATALOG_SCOPE_EMPTY"

    db.add(
        DlProductCache(
            connector_id="woocommerce:primary",
            product_id="102",
            name="Second product",
            sku="SKU-102",
            product_type="simple",
            regular_price="200",
            stock_qty=2,
            stock_status="instock",
            freshness="fresh",
            last_fetched_at=datetime.now(timezone.utc).replace(tzinfo=None),
            last_successful_read=datetime.now(timezone.utc).replace(tzinfo=None),
            exists=True,
        )
    )
    db.commit()
    materialized = client.post(
        "/api/v2/unified-workspaces/manual",
        headers=auth_headers,
        json={
            "name": "Materialize test identities",
            "selections": [
                {"connector_id": "woocommerce:primary", "product_id": "101"},
                {"connector_id": "woocommerce:primary", "product_id": "102"},
            ],
        },
    )
    assert materialized.status_code == 201, materialized.text
    monkeypatch.setattr(workspace_services, "MAX_SELECTION", 1)
    too_large = client.post(
        "/api/v2/unified-workspaces/manual",
        headers=auth_headers,
        json={"name": "Too large", "catalog_scope": {"channel_id": "woocommerce:primary"}},
    )
    assert too_large.status_code == 422
    assert too_large.json()["detail"]["code"] == "CATALOG_SCOPE_TOO_LARGE"


def test_grouped_grid_filters_products_but_preserves_all_channel_children(
    client, auth_headers, db, admin
):
    from app.flowhub.data_layer.models import DlProductCache
    from app.flowhub.unified_workspace.models import Listing, WorkspaceChannel
    from app.flowhub.unified_workspace.services import UnifiedWorkspaceService

    _seed(db)
    woo_cache = db.query(DlProductCache).filter_by(product_id="101").one()
    woo_cache.categories = [{"id": 7, "name": "Accessories"}]
    db.commit()
    UnifiedWorkspaceService(db).create_manual_workspace(
        name="Materialize identity",
        selections=[{"connector_id": "woocommerce:primary", "product_id": "101"}],
        user=admin,
        correlation_id="materialize-catalog-filter",
    )
    woo_listing = db.query(Listing).filter_by(
        channel_id="woocommerce:primary", external_primary_id="101"
    ).one()
    snapp_channel = db.get(WorkspaceChannel, "snappshop:main")
    assert snapp_channel is not None
    db.add(
        DlProductCache(
            connector_id="snappshop:main",
            product_id="S-101",
            name="Canonical Test Product",
            sku="SNAPP-SKU-101",
            product_type="simple",
            regular_price="120",
            stock_qty=0,
            stock_status="outofstock",
            freshness="fresh",
            last_fetched_at=datetime.now(timezone.utc).replace(tzinfo=None),
            last_successful_read=datetime.now(timezone.utc).replace(tzinfo=None),
            exists=True,
            record_hash="snapp-cache-101",
        )
    )
    db.add(
        Listing(
            id=str(uuid.uuid4()),
            canonical_product_id=woo_listing.canonical_product_id,
            channel_id="snappshop:main",
            external_primary_id="S-101",
            external_id_type="product_number",
            secondary_identifiers_json={},
            sku="SNAPP-SKU-101",
            label="Canonical Test Product",
            mapping_state="resolved",
            mapping_version=1,
            capability_state_json=snapp_channel.capabilities_json,
            enabled=True,
        )
    )
    db.commit()
    UnifiedWorkspaceService(db).create_manual_workspace(
        name="Materialize grouped identities",
        selections=[
            {"connector_id": "woocommerce:primary", "product_id": "101"},
            {"connector_id": "snappshop:main", "product_id": "S-101"},
        ],
        user=admin,
        correlation_id="materialize-grouped-identities",
    )

    created = client.post(
        "/api/v2/unified-workspaces/manual",
        headers=auth_headers,
        json={"name": "Grouped filters", "catalog_scope": {}},
    )
    assert created.status_code == 201, created.text
    workspace_id = created.json()["id"]

    for query in (
        "search=Canonical%20Test",
        "search=SKU-101",
        "search=SNAPP-SKU-101",
        "search=S-101",
        "categoryId=Accessories",
        "productType=simple",
        "channelId=snappshop%3Amain",
        "stockState=out_of_stock",
    ):
        response = client.get(
            f"/api/v2/unified-workspaces/{workspace_id}/grouped-grid?page=1&pageSize=100&view=all&{query}",
            headers=auth_headers,
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["total"] == 1
        assert {child["channelId"] for child in result["items"][0]["children"]} == {
            "woocommerce:primary",
            "snappshop:main",
        }
        assert result["items"][0]["sourceKey"] is None


def test_large_manual_selection_uses_bounded_sqlite_batches(db, admin):
    from app.flowhub.data_layer.models import DlProductCache
    from app.flowhub.unified_workspace.models import SnapshotRow
    from app.flowhub.unified_workspace.services import UnifiedWorkspaceService

    _seed(db)
    rows = [
        DlProductCache(
            connector_id="woocommerce:primary",
            product_id=str(product_id),
            name=f"Product {product_id}",
            sku=f"SKU-{product_id}",
            product_type="simple",
            regular_price="100",
            stock_qty=1,
            stock_status="instock",
            freshness="fresh",
            exists=True,
        )
        for product_id in range(102, 602)
    ]
    db.add_all(rows)
    db.commit()
    selections = [
        {"connector_id": "woocommerce:primary", "product_id": str(product_id)}
        for product_id in range(101, 602)
    ]

    workspace = UnifiedWorkspaceService(db).create_manual_workspace(
        name="SQLite batch",
        selections=selections,
        user=admin,
        correlation_id="sqlite-batch",
    )

    assert (
        db.query(SnapshotRow).filter_by(snapshot_id=workspace["snapshot"]["id"]).count()
        == 501
    )


def test_grouped_grid_changed_view_is_not_empty_before_any_draft_revision_exists(
    client, auth_headers, db
):
    """Regression for Userback #8215161: "Workspace appears empty after
    successful fetch". A freshly created workspace has no Draft Revision yet
    (nothing has been edited), so the "changed" view must not resolve to an
    empty include-set — that previously hid every row even though the fetch
    genuinely populated the Workspace Snapshot.
    """
    _seed(db)
    workspace = _create(client, auth_headers)

    response = client.get(
        f"/api/v2/unified-workspaces/{workspace['id']}/grouped-grid?page=1&pageSize=100&view=changed",
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "Canonical Test Product"


def test_dry_run_uses_targeted_read_creates_manifest_only_after_live_evidence(
    client, auth_headers, db, monkeypatch
):
    """Phase-B contract: selection writes no provider data; Dry Run reads once,
    records its full scope, and only verified writes enter the manifest."""
    from app.flowhub.unified_workspace.connectors import ListingUpdateResult
    from app.flowhub.write_pipeline.workspace_contracts import WriteOutcome

    workspace, review = _saved_review(client, auth_headers, db)
    selected = review["items"][0]
    selection = client.put(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews/{review['id']}/selection",
        headers=auth_headers,
        json={"review_item_ids": [selected["id"]]},
    )
    assert selection.status_code == 200
    assert "manifestId" not in selection.json()

    reads: list[str] = []

    async def observed(_self, updates, *, requested_by):
        reads.extend(update.listing_id for update in updates)
        return [
            ListingUpdateResult(
                listing_id=update.listing_id,
                outcome=WriteOutcome.VERIFIED_APPLIED,
                response={"verification": {"observed": {
                    "external_id": update.external_primary_id,
                    "parent_external_id": update.parent_external_id,
                    "product_type": update.product_type,
                    "price": "100.00",
                    "currency": update.currency,
                    "unit": update.unit,
                }}},
            )
            for update in updates
        ]

    monkeypatch.setattr(
        "app.flowhub.unified_workspace.connectors.WooCommerceWorkspaceConnector.verify_updates",
        observed,
    )
    dry_run = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews/{review['id']}/dry-run",
        headers=auth_headers,
    )
    assert dry_run.status_code == 200, dry_run.text
    body = dry_run.json()
    assert body["status"] == "passed"
    assert body["reviewedCount"] == 1
    assert body["writeCount"] == 1
    assert body["blockerCount"] == 0
    assert body["manifestId"]
    assert reads == [selected["listingId"]]


@pytest.mark.parametrize(
    ("observed", "expected_status", "expected_writes", "expected_reason"),
    [
        ({"external_id": "101", "parent_external_id": None, "price": 150.0}, "passed", 0, "ALREADY_CURRENT"),
        ({"external_id": "101", "parent_external_id": None, "price": 99.0}, "blocked", 0, "CHANNEL_DRIFT"),
        (None, "blocked", 0, "CHANNEL_STATE_UNVERIFIABLE"),
    ],
)
def test_dry_run_preserves_noops_and_distinguishes_drift_from_unverifiable(
    client, auth_headers, db, monkeypatch, observed, expected_status, expected_writes, expected_reason
):
    from app.flowhub.unified_workspace.connectors import ListingUpdateResult
    from app.flowhub.write_pipeline.workspace_contracts import WriteOutcome

    workspace, review = _saved_review(client, auth_headers, db)
    selected = review["items"][0]
    assert client.put(f"/api/v2/unified-workspaces/{workspace['id']}/reviews/{review['id']}/selection", headers=auth_headers, json={"review_item_ids": [selected["id"]]}).status_code == 200

    async def current(_self, updates, *, requested_by):
        return [
            ListingUpdateResult(
                listing_id=update.listing_id,
                outcome=WriteOutcome.RECONCILIATION_REQUIRED,
                response={"verification": {"observed": (
                    None if observed is None else {
                        "external_id": update.external_primary_id,
                        "parent_external_id": update.parent_external_id,
                        "product_type": update.product_type,
                        "price": update.current_price,
                        "currency": update.currency,
                        "unit": update.unit,
                        **observed,
                    }
                )}},
            )
            for update in updates
        ]

    monkeypatch.setattr("app.flowhub.unified_workspace.connectors.WooCommerceWorkspaceConnector.verify_updates", current)
    response = client.post(f"/api/v2/unified-workspaces/{workspace['id']}/reviews/{review['id']}/dry-run", headers=auth_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == expected_status
    assert body["reviewedCount"] == 1
    assert body["writeCount"] == expected_writes
    assert body["scopes"][0]["reason"] == expected_reason
    assert "manifestId" not in body


def _bind_workspace_to_sheet_source(db, workspace_id: str, user_id: int = 1):
    """Attach a manual test Workspace to exact, mutable sheet authority."""
    from app.flowhub.source_workspace.models import (
        FlowHubSheet,
        SheetRevision,
        SourceMappingRevision,
        SourceProfile,
    )
    from app.flowhub.unified_workspace.models import (
        UnifiedWorkspace,
        WorkspaceSnapshot,
        WorkspaceSourceBinding,
    )

    source = SourceProfile(
        id=str(uuid.uuid4()), name="Phase B Source", source_kind="flowhub_sheet",
        worksheet_mode="selected", worksheet_name="Prices", data_start_row=2,
        status="active", version=1, owner_user_id=user_id,
    )
    sheet = FlowHubSheet(
        id=str(uuid.uuid4()), source_id=source.id, name="Prices", current_version=1,
        owner_user_id=user_id,
    )
    revision = SheetRevision(
        id=str(uuid.uuid4()), sheet_id=sheet.id, version=1, checksum="s" * 64,
        formula_engine_version="test", row_count=1, column_count=2,
        created_by_user_id=user_id,
    )
    mapping = SourceMappingRevision(
        id=str(uuid.uuid4()), source_id=source.id, version=1, checksum="m" * 64,
        worksheet_mode="selected", worksheet_name="Prices", data_start_row=2,
        value_policy_json={}, identity_authority_json={}, identity_policy_version=1,
        created_by_user_id=user_id,
    )
    db.add_all([
        source, sheet, revision, mapping,
        WorkspaceSourceBinding(
            workspace_id=workspace_id, source_id=source.id, source_version=1,
            bound_by_user_id=user_id,
        ),
    ])
    db.flush()
    db.execute(
        update(UnifiedWorkspace)
        .where(UnifiedWorkspace.id == workspace_id)
        .values(entry_point="source", source_type="flowhub_sheet")
    )
    db.execute(
        update(WorkspaceSnapshot)
        .where(WorkspaceSnapshot.workspace_id == workspace_id)
        .values(source_metadata_json={
            "source_id": source.id,
            "source_version": 1,
            "mapping_revision_id": mapping.id,
            "mapping_checksum": mapping.checksum,
            "sheet_revision_id": revision.id,
            "sheet_revision_checksum": revision.checksum,
        })
    )
    db.commit()
    return sheet


def test_dry_run_blocks_changed_source_sheet_without_provider_dispatch(
    client, auth_headers, db, monkeypatch
):
    workspace, review = _saved_review(client, auth_headers, db)
    sheet = _bind_workspace_to_sheet_source(db, workspace["id"])
    sheet.current_version = 2
    db.commit()
    writes: list[str] = []

    async def forbidden_write(_self, updates, *, requested_by):
        writes.extend(update.listing_id for update in updates)
        return []

    monkeypatch.setattr(
        "app.flowhub.unified_workspace.connectors.WooCommerceWorkspaceConnector.apply_updates",
        forbidden_write,
    )
    item = review["items"][0]
    assert client.put(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews/{review['id']}/selection",
        headers=auth_headers, json={"review_item_ids": [item["id"]]},
    ).status_code == 200
    blocked = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews/{review['id']}/dry-run",
        headers=auth_headers,
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "SOURCE_CHANGED"
    assert writes == []


def test_apply_blocks_changed_source_sheet_after_dry_run_without_dispatch(
    client, auth_headers, db, monkeypatch
):
    workspace, review = _saved_review(client, auth_headers, db)
    sheet = _bind_workspace_to_sheet_source(db, workspace["id"])
    item = review["items"][0]
    confirmed = _select_and_dry_run(client, auth_headers, workspace, review, [item["id"]]).json()
    sheet.current_version = 2
    db.commit()
    writes: list[str] = []

    async def forbidden_write(_self, updates, *, requested_by):
        writes.extend(update.listing_id for update in updates)
        return []

    monkeypatch.setattr(
        "app.flowhub.unified_workspace.connectors.WooCommerceWorkspaceConnector.apply_updates",
        forbidden_write,
    )
    blocked = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/apply",
        headers={**auth_headers, "Idempotency-Key": "source-changed-before-apply"},
        json={
            "review_id": review["id"],
            "expected_selection_checksum": confirmed["selectionChecksum"],
            "manifest_id": confirmed["manifestId"],
            "expected_manifest_checksum": confirmed["manifestChecksum"],
            "confirmed": True,
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "SOURCE_CHANGED"
    assert writes == []


@pytest.mark.parametrize(
    ("override", "missing", "reason"),
    [
        ({"product_type": "variation"}, None, "CHANNEL_DRIFT"),
        ({"parent_external_id": "parent-1"}, None, "CHANNEL_DRIFT"),
        ({"currency": "USD"}, None, "CHANNEL_DRIFT"),
        ({"unit": "RIAL"}, None, "CHANNEL_DRIFT"),
        ({}, "product_type", "CHANNEL_STATE_UNVERIFIABLE"),
        ({}, "price", "CHANNEL_STATE_UNVERIFIABLE"),
    ],
)
def test_dry_run_blocks_incomplete_or_changed_live_pricing_evidence(
    client, auth_headers, db, monkeypatch, override, missing, reason
):
    from app.flowhub.unified_workspace.connectors import ListingUpdateResult
    from app.flowhub.write_pipeline.workspace_contracts import WriteOutcome

    workspace, review = _saved_review(client, auth_headers, db)
    item = review["items"][0]
    assert client.put(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews/{review['id']}/selection",
        headers=auth_headers, json={"review_item_ids": [item["id"]]},
    ).status_code == 200
    writes: list[str] = []

    async def observed(_self, updates, *, requested_by):
        result = []
        for candidate in updates:
            evidence = {
                "external_id": candidate.external_primary_id,
                "parent_external_id": candidate.parent_external_id,
                "product_type": candidate.product_type,
                "price": "100.0000000000000001",
                "currency": candidate.currency,
                "unit": candidate.unit,
                **override,
            }
            if missing:
                evidence.pop(missing)
            result.append(ListingUpdateResult(
                listing_id=candidate.listing_id,
                outcome=WriteOutcome.RECONCILIATION_REQUIRED,
                response={"verification": {"observed": evidence}},
            ))
        return result

    async def forbidden_write(_self, updates, *, requested_by):
        writes.extend(update.listing_id for update in updates)
        return []

    monkeypatch.setattr(
        "app.flowhub.unified_workspace.connectors.WooCommerceWorkspaceConnector.verify_updates", observed
    )
    monkeypatch.setattr(
        "app.flowhub.unified_workspace.connectors.WooCommerceWorkspaceConnector.apply_updates", forbidden_write
    )
    response = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews/{review['id']}/dry-run",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "blocked"
    assert response.json()["scopes"][0]["reason"] == reason
    assert "manifestId" not in response.json()
    from app.flowhub.unified_workspace.models import DryRunScope

    persisted = db.query(DryRunScope).filter_by(dry_run_id=response.json()["id"]).one()
    assert persisted is not None
    if missing:
        assert missing not in persisted.observed_live_json
    else:
        assert persisted.observed_live_json["price"] == "100.0000000000000001"
    assert writes == []


def test_apply_post_lock_timeout_is_unverifiable_and_never_dispatches(
    client, auth_headers, db, monkeypatch
):
    from app.flowhub.unified_workspace.connectors import ListingUpdateResult
    from app.flowhub.write_pipeline.workspace_contracts import WriteOutcome

    workspace, review = _saved_review(client, auth_headers, db)
    item = review["items"][0]
    confirmed = _select_and_dry_run(client, auth_headers, workspace, review, [item["id"]]).json()
    reads = 0
    writes: list[str] = []

    async def timeout_after_dry_run(_self, updates, *, requested_by):
        nonlocal reads
        reads += 1
        return [ListingUpdateResult(
            listing_id=update.listing_id,
            outcome=WriteOutcome.RECONCILIATION_REQUIRED,
            response={"verification": {"observed": None, "error": {"category": "timeout"}}},
        ) for update in updates]

    async def forbidden_write(_self, updates, *, requested_by):
        writes.extend(update.listing_id for update in updates)
        return []

    monkeypatch.setattr("app.flowhub.unified_workspace.connectors.WooCommerceWorkspaceConnector.verify_updates", timeout_after_dry_run)
    monkeypatch.setattr("app.flowhub.unified_workspace.connectors.WooCommerceWorkspaceConnector.apply_updates", forbidden_write)
    blocked = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/apply",
        headers={**auth_headers, "Idempotency-Key": "post-lock-timeout"},
        json={
            "review_id": review["id"], "expected_selection_checksum": confirmed["selectionChecksum"],
            "manifest_id": confirmed["manifestId"], "expected_manifest_checksum": confirmed["manifestChecksum"],
            "confirmed": True,
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "CHANNEL_STATE_UNVERIFIABLE"
    assert reads == 1
    assert writes == []
