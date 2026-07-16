"""FlowHub v1.2 Unified Workspace lifecycle and invariant tests."""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("FLOWHUB_JWT_SECRET", "unified-workspace-test-secret-32-bytes-long")

from app.flowhub.auth import models as _auth_models  # noqa: F401
from app.flowhub.data_layer import models as _data_models  # noqa: F401
from app.flowhub.integration_platform import models as _integration_models  # noqa: F401
from app.flowhub.product_pricing import models as _pricing_models  # noqa: F401
from app.flowhub.setup import models as _setup_models  # noqa: F401
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
            last_fetched_at=datetime.utcnow(),
            last_successful_read=datetime.utcnow(),
            exists=True,
            record_hash="woo-cache-1",
        )
    )
    db.commit()


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
    assert row["fields"]["stock"]["readOnly"] is True

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


def _saved_review(client, auth_headers, db, *, second_product: bool = False):
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
    review_response = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews",
        headers=auth_headers,
        json={"draft_revision_id": revision_response.json()["id"]},
    )
    assert review_response.status_code == 201
    return workspace, review_response.json()


def test_apply_is_selected_only_idempotent_and_patches_verified_cache(
    client, auth_headers, db, monkeypatch
):
    from app.flowhub.unified_workspace.connectors import ListingUpdateResult
    from app.flowhub.unified_workspace.models import ChannelCache
    from app.flowhub.write_pipeline.workspace_contracts import WriteOutcome

    workspace, review = _saved_review(client, auth_headers, db, second_product=True)
    selected = review["items"][0]
    selection = client.put(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews/{review['id']}/selection",
        headers=auth_headers,
        json={"review_item_ids": [selected["id"]]},
    )
    assert selection.status_code == 200

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
            "confirmed": True,
        },
    )
    assert repeated.status_code == 202
    assert repeated.json()["id"] == result["id"]


def test_cache_change_marks_review_stale_and_blocks_apply(client, auth_headers, db):
    from app.flowhub.unified_workspace.models import ChannelCache

    workspace, review = _saved_review(client, auth_headers, db)
    item = review["items"][0]
    selection = client.put(
            f"/api/v2/unified-workspaces/{workspace['id']}/reviews/{review['id']}/selection",
            headers=auth_headers,
            json={"review_item_ids": [item["id"]]},
    )
    assert selection.status_code == 200
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
            "confirmed": True,
        },
    )
    assert response.status_code == 409
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


def test_source_workspace_reads_source_once_and_materializes_immutable_rows(
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
        json={"name": "Source Test", "currency": "EUR", "unit": "EUR"},
    )
    assert response.status_code == 201, response.text
    workspace = response.json()
    assert workspace["entryPoint"] == "source"
    assert calls == 1

    from app.flowhub.unified_workspace.models import SnapshotRow, WorkspaceSnapshot

    snapshot = db.get(WorkspaceSnapshot, workspace["snapshot"]["id"])
    rows = (
        db.query(SnapshotRow)
        .filter_by(snapshot_id=snapshot.id)
        .order_by(SnapshotRow.row_number)
        .all()
    )
    assert snapshot.acquisition_metadata_json["read_once"] is True
    assert snapshot.source_metadata_json["legacy_preview_id"] == "legacy-preview-1"
    assert len(rows) == 2
    assert rows[0].listing_id is not None
    assert rows[1].listing_id is None

    grid = client.get(f"/api/v2/unified-workspaces/{workspace['id']}/grid", headers=auth_headers)
    assert grid.status_code == 200
    assert calls == 1


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
            "channelStatus": "publish",
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
    selected = client.put(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews/{review['id']}/selection",
        headers=auth_headers,
        json={"review_item_ids": item_ids},
    )
    assert selected.status_code == 200

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
    confirmed = client.put(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews/{review['id']}/selection",
        headers=auth_headers,
        json={"review_item_ids": [first["id"]]},
    )
    assert confirmed.status_code == 200
    checksum_a = confirmed.json()["selectionChecksum"]
    replaced = client.put(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews/{review['id']}/selection",
        headers=auth_headers,
        json={"review_item_ids": [second["id"]]},
    )
    assert replaced.status_code == 200
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
            "confirmed": True,
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "APPLY_SELECTION_CHECKSUM_MISMATCH"
    assert calls == []

    current_checksum = replaced.json()["selectionChecksum"]
    applied = client.post(
        f"/api/v2/unified-workspaces/{workspace['id']}/apply",
        headers={**auth_headers, "Idempotency-Key": "selection-tab-b"},
        json={
            "review_id": review["id"],
            "expected_selection_checksum": current_checksum,
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
    confirmed = client.put(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews/{review['id']}/selection",
        headers=auth_headers,
        json={"review_item_ids": [item["id"]]},
    )
    assert confirmed.status_code == 200
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
    confirmed = client.put(
        f"/api/v2/unified-workspaces/{workspace['id']}/reviews/{review['id']}/selection",
        headers=auth_headers,
        json={"review_item_ids": [item["id"]]},
    )
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
    first_selection = client.put(
        f"/api/v2/unified-workspaces/{first_workspace['id']}/reviews/{first_review['id']}/selection",
        headers=auth_headers,
        json={"review_item_ids": [first_item["id"]]},
    ).json()

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
    second_selection = client.put(
        f"/api/v2/unified-workspaces/{second_workspace['id']}/reviews/{second_review['id']}/selection",
        headers=auth_headers,
        json={"review_item_ids": [second_review["items"][0]["id"]]},
    ).json()
    blocked = client.post(
        f"/api/v2/unified-workspaces/{second_workspace['id']}/apply",
        headers={**auth_headers, "Idempotency-Key": "global-lock-second"},
        json={
            "review_id": second_review["id"],
            "expected_selection_checksum": second_selection["selectionChecksum"],
            "confirmed": True,
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "APPLY_SCOPE_LOCKED"

    lock = db.query(WorkspaceLock).filter_by(listing_id=second_row["listingId"]).one()
    lock.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    expired_uncertain_selection = client.put(
        f"/api/v2/unified-workspaces/{second_workspace['id']}/reviews/{second_review['id']}/selection",
        headers=auth_headers,
        json={"review_item_ids": [second_review["items"][0]["id"]]},
    ).json()
    expired_uncertain = client.post(
        f"/api/v2/unified-workspaces/{second_workspace['id']}/apply",
        headers={**auth_headers, "Idempotency-Key": "global-lock-expired-uncertain"},
        json={
            "review_id": second_review["id"],
            "expected_selection_checksum": expired_uncertain_selection["selectionChecksum"],
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
    reconfirmed = client.put(
        f"/api/v2/unified-workspaces/{second_workspace['id']}/reviews/{second_review['id']}/selection",
        headers=auth_headers,
        json={"review_item_ids": [second_review["items"][0]["id"]]},
    ).json()

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
            "confirmed": True,
        },
    )
    assert reclaimed.status_code == 202, reclaimed.text
    assert reclaimed.json()["status"] == "applied"
    assert db.query(WorkspaceLock).filter_by(listing_id=second_row["listingId"]).count() == 0
