"""Channel Read architecture, Phase A/B: strategy resolution and the
targeted (LIGHT/PRODUCT) read path. See ADR_CHANNEL_READ_ARCHITECTURE.md.
"""

from __future__ import annotations

import os

os.environ.setdefault("FLOWHUB_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FLOWHUB_JWT_SECRET", "test-channel-read-jwt-secret-32-bytes!")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.flowhub.auth import models as _auth_models  # noqa: F401
from app.flowhub.data_layer.models import DlProductCache, DlRefreshJob
from app.flowhub.database import FlowHubBase
from app.flowhub.integration_platform import models as _integration_platform_models  # noqa: F401
from app.flowhub.read_engine.contracts import (
    ChannelReadRequest,
    ConnectorReadCapabilities,
    ReadPage,
    ReadReason,
    ReadScope,
    ReadStrategy,
)
from app.flowhub.read_engine.exceptions import IncrementalReadUnsupported
from app.flowhub.read_engine.strategy_resolver import (
    MECHANISM_ENTITY_READ,
    MECHANISM_INITIAL_FULL_READ,
    MECHANISM_METADATA_FILTER,
    MECHANISM_MODIFIED_SINCE,
    resolve,
)
from app.flowhub.setup import models as _setup_models  # noqa: F401


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    FlowHubBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# ChannelReadRequest
# ---------------------------------------------------------------------------


def test_product_scope_requires_identifiers():
    with pytest.raises(ValueError):
        ChannelReadRequest(
            connector_id="woocommerce:primary",
            strategy=ReadStrategy.LIGHT,
            scope=ReadScope.PRODUCT,
            reason=ReadReason.WEBHOOK_PRODUCT_UPDATED,
        )


def test_channel_scope_rejects_identifiers():
    with pytest.raises(ValueError):
        ChannelReadRequest(
            connector_id="woocommerce:primary",
            strategy=ReadStrategy.FULL,
            scope=ReadScope.CHANNEL,
            reason=ReadReason.OWNER_REQUESTED,
            identifiers=("57926",),
        )


# ---------------------------------------------------------------------------
# strategy_resolver.resolve()
# ---------------------------------------------------------------------------


def _request(**overrides):
    defaults = dict(
        connector_id="woocommerce:primary",
        strategy=ReadStrategy.LIGHT,
        scope=ReadScope.CHANNEL,
        reason=ReadReason.PERIODIC_RECONCILIATION,
    )
    defaults.update(overrides)
    return ChannelReadRequest(**defaults)


def test_product_scope_resolves_to_entity_read_when_supported():
    request = _request(scope=ReadScope.PRODUCT, identifiers=("57926",), reason=ReadReason.WEBHOOK_PRODUCT_UPDATED)
    capabilities = ConnectorReadCapabilities(supports_entity_read=True)

    plan = resolve(request, capabilities, has_cache=True)

    assert plan.strategy is ReadStrategy.LIGHT
    assert plan.scope is ReadScope.PRODUCT
    assert plan.mechanism == MECHANISM_ENTITY_READ
    assert plan.identifiers == ("57926",)


def test_product_scope_falls_back_to_metadata_filter_without_entity_read():
    request = _request(scope=ReadScope.PRODUCT, identifiers=("57926",), reason=ReadReason.OWNER_REQUESTED)
    capabilities = ConnectorReadCapabilities(supports_entity_read=False, supports_batch_read=True)

    plan = resolve(request, capabilities, has_cache=True)

    assert plan.mechanism == MECHANISM_METADATA_FILTER
    assert plan.strategy is ReadStrategy.LIGHT


def test_product_scope_fails_closed_without_any_targeted_mechanism():
    request = _request(scope=ReadScope.PRODUCT, identifiers=("57926",), reason=ReadReason.OWNER_REQUESTED)
    capabilities = ConnectorReadCapabilities()

    with pytest.raises(IncrementalReadUnsupported):
        resolve(request, capabilities, has_cache=True)


def test_channel_scope_forces_full_when_no_cache_exists():
    request = _request(strategy=ReadStrategy.LIGHT)
    capabilities = ConnectorReadCapabilities(supports_full_snapshot=True, supports_modified_since=True)

    plan = resolve(request, capabilities, has_cache=False)

    assert plan.strategy is ReadStrategy.FULL
    assert plan.mechanism == MECHANISM_INITIAL_FULL_READ


def test_channel_scope_prefers_modified_since_when_cache_exists():
    request = _request(strategy=ReadStrategy.LIGHT)
    capabilities = ConnectorReadCapabilities(supports_full_snapshot=True, supports_modified_since=True)

    plan = resolve(request, capabilities, has_cache=True)

    assert plan.mechanism == MECHANISM_MODIFIED_SINCE


def test_channel_scope_falls_back_to_metadata_filter():
    request = _request(strategy=ReadStrategy.LIGHT)
    capabilities = ConnectorReadCapabilities(supports_full_snapshot=True, supports_batch_read=True)

    plan = resolve(request, capabilities, has_cache=True)

    assert plan.mechanism == MECHANISM_METADATA_FILTER


def test_full_request_fails_closed_when_connector_cannot_snapshot():
    request = _request(strategy=ReadStrategy.FULL)
    capabilities = ConnectorReadCapabilities()

    with pytest.raises(IncrementalReadUnsupported):
        resolve(request, capabilities, has_cache=False)


def test_deep_requires_deep_recovery_capability():
    request = _request(strategy=ReadStrategy.DEEP, reason=ReadReason.RECOVERY)

    with pytest.raises(IncrementalReadUnsupported):
        resolve(request, ConnectorReadCapabilities(supports_full_snapshot=True), has_cache=True)

    plan = resolve(
        request,
        ConnectorReadCapabilities(supports_full_snapshot=True, supports_deep_recovery=True),
        has_cache=True,
    )
    assert plan.strategy is ReadStrategy.DEEP
    assert plan.scope is ReadScope.CHANNEL


def test_deep_is_never_selected_merely_because_cache_is_empty():
    """DEEP must only be chosen for an explicit DEEP request, never as an
    automatic escalation from a plain LIGHT/FULL request with no cache."""
    request = _request(strategy=ReadStrategy.LIGHT)
    capabilities = ConnectorReadCapabilities(supports_full_snapshot=True, supports_deep_recovery=True)

    plan = resolve(request, capabilities, has_cache=False)

    assert plan.strategy is ReadStrategy.FULL


# ---------------------------------------------------------------------------
# IncrementalReadEngine.run_entity()
# ---------------------------------------------------------------------------


class _EntityAdapter:
    connector_id = "woocommerce:primary"
    connector_type = "woocommerce"

    def __init__(self, capabilities=None, page=None):
        self.capabilities = capabilities or ConnectorReadCapabilities(supports_entity_read=True)
        self._page = page
        self.calls: list[dict] = []

    async def fetch_entity(self, *, entity_id, parent_id=None):
        self.calls.append({"entity_id": entity_id, "parent_id": parent_id})
        return self._page


@pytest.mark.asyncio
async def test_run_entity_fails_closed_without_capability(db):
    from app.flowhub.read_engine.service import IncrementalReadEngine

    adapter = _EntityAdapter(capabilities=ConnectorReadCapabilities(supports_entity_read=False))

    with pytest.raises(IncrementalReadUnsupported):
        await IncrementalReadEngine(db).run_entity(adapter, entity_id="57926")
    assert adapter.calls == []


@pytest.mark.asyncio
async def test_run_entity_upserts_a_single_product_and_creates_no_refresh_job(db):
    from app.flowhub.read_engine.service import IncrementalReadEngine

    page = ReadPage(items=[{"id": "57926", "sku": "SKU-1", "name": "Widget", "price": "10.00"}], next_cursor=None)
    adapter = _EntityAdapter(page=page)

    progress = await IncrementalReadEngine(db).run_entity(adapter, entity_id="57926")

    assert progress.status == "completed"
    assert progress.job_id is None
    assert progress.strategy == "entity_read"
    assert progress.products_stored == 1
    row = db.query(DlProductCache).filter_by(connector_id="woocommerce:primary", product_id="57926").one()
    assert row.name == "Widget"
    assert row.freshness == "fresh"
    # The channel-wide lease table must stay untouched by a targeted read.
    assert db.query(DlRefreshJob).count() == 0


@pytest.mark.asyncio
async def test_run_entity_not_found_marks_stale_without_clobbering_known_fields(db):
    from app.flowhub.read_engine.service import IncrementalReadEngine

    db.add(
        DlProductCache(
            connector_id="woocommerce:primary",
            product_id="57926",
            name="Widget",
            sku="SKU-1",
            last_price="10.00",
            exists=True,
            freshness="fresh",
        )
    )
    db.commit()
    page = ReadPage(items=[{"product_id": "57926", "exists": False}], next_cursor=None)
    adapter = _EntityAdapter(page=page)

    progress = await IncrementalReadEngine(db).run_entity(adapter, entity_id="57926")

    assert progress.products_stored == 1
    row = db.query(DlProductCache).filter_by(connector_id="woocommerce:primary", product_id="57926").one()
    assert row.exists is False
    assert row.freshness == "stale"
    assert row.name == "Widget"  # preserved, not clobbered with null fields
    assert row.last_price == "10.00"


@pytest.mark.asyncio
async def test_run_entity_passes_parent_id_through_to_the_adapter(db):
    from app.flowhub.read_engine.service import IncrementalReadEngine

    adapter = _EntityAdapter(page=ReadPage(items=[], next_cursor=None))

    await IncrementalReadEngine(db).run_entity(adapter, entity_id="99", parent_id="57926")

    assert adapter.calls == [{"entity_id": "99", "parent_id": "57926"}]


# ---------------------------------------------------------------------------
# ProductReadModelService.mark_not_found()
# ---------------------------------------------------------------------------


def test_mark_not_found_preserves_previously_observed_fields(db):
    from app.flowhub.data_layer.product_service import ProductReadModelService

    db.add(
        DlProductCache(
            connector_id="woocommerce:primary",
            product_id="57926",
            name="Widget",
            sku="SKU-1",
            last_price="10.00",
            exists=True,
            freshness="fresh",
        )
    )
    db.commit()

    ProductReadModelService(db).mark_not_found("woocommerce:primary", "57926")

    row = db.query(DlProductCache).filter_by(connector_id="woocommerce:primary", product_id="57926").one()
    assert row.exists is False
    assert row.freshness == "stale"
    assert row.name == "Widget"
    assert row.last_price == "10.00"


def test_mark_not_found_is_a_no_op_for_an_uncached_product(db):
    from app.flowhub.data_layer.product_service import ProductReadModelService

    ProductReadModelService(db).mark_not_found("woocommerce:primary", "nonexistent")

    assert db.query(DlProductCache).count() == 0


# ---------------------------------------------------------------------------
# WooCommerceProductReadAdapter.fetch_entity()
# ---------------------------------------------------------------------------


def test_woocommerce_capabilities_advertise_entity_read_and_full_snapshot():
    from app.connectors.read.woocommerce import WooCommerceProductReadAdapter

    adapter = WooCommerceProductReadAdapter(url="https://store.example.test", key="ck_test", secret="cs_test")

    assert adapter.capabilities.supports_entity_read is True
    assert adapter.capabilities.supports_full_snapshot is True
    assert adapter.capabilities.max_page_size == 100
    assert adapter.capabilities.recommended_concurrency >= 1


@pytest.mark.asyncio
async def test_woocommerce_fetch_entity_reads_one_product_and_its_variations(monkeypatch):
    from app.connectors.read.woocommerce import WooCommerceProductReadAdapter

    async def fake_get_product(creds, product_id):
        assert product_id == 57926
        return {"id": 57926, "type": "variable", "sku": "PARENT", "name": "Parent", "images": []}

    async def fake_list_variations(creds, product_id, page=1, per_page=100):
        assert product_id == 57926
        if page == 1:
            return [{"id": 1, "regular_price": "10.00"}]
        return []

    monkeypatch.setattr("app.connectors.read.woocommerce.get_product", fake_get_product)
    monkeypatch.setattr("app.connectors.read.woocommerce.list_variations", fake_list_variations)

    adapter = WooCommerceProductReadAdapter(url="https://store.example.test", key="ck_test", secret="cs_test")
    page = await adapter.fetch_entity(entity_id="57926")

    assert [item["product_id"] for item in page.items] == ["57926", "1"]
    assert adapter.products_read == 1
    assert adapter.variable_products_read == 1


@pytest.mark.asyncio
async def test_woocommerce_fetch_entity_not_found_returns_exists_false(monkeypatch):
    from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
    from app.connectors.read.woocommerce import WooCommerceProductReadAdapter

    async def fake_get_product(creds, product_id):
        raise ConnectorError(code=ConnectorErrorCode.NOT_FOUND, message="gone", provider="woocommerce")

    monkeypatch.setattr("app.connectors.read.woocommerce.get_product", fake_get_product)

    adapter = WooCommerceProductReadAdapter(url="https://store.example.test", key="ck_test", secret="cs_test")
    page = await adapter.fetch_entity(entity_id="57926")

    assert page.items == [{"product_id": "57926", "exists": False}]


@pytest.mark.asyncio
async def test_woocommerce_fetch_entity_propagates_non_not_found_errors(monkeypatch):
    from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
    from app.connectors.read.woocommerce import WooCommerceProductReadAdapter

    async def fake_get_product(creds, product_id):
        raise ConnectorError(code=ConnectorErrorCode.RATE_LIMITED, message="slow down", provider="woocommerce")

    monkeypatch.setattr("app.connectors.read.woocommerce.get_product", fake_get_product)

    adapter = WooCommerceProductReadAdapter(url="https://store.example.test", key="ck_test", secret="cs_test")
    with pytest.raises(ConnectorError):
        await adapter.fetch_entity(entity_id="57926")


@pytest.mark.asyncio
async def test_woocommerce_fetch_entity_uses_known_variation_fast_path(monkeypatch):
    from app.connectors.read.woocommerce import WooCommerceProductReadAdapter

    calls: list[tuple[int, int]] = []

    async def fake_get_variation(creds, product_id, variation_id):
        calls.append((product_id, variation_id))
        return {"id": variation_id, "regular_price": "12.00"}

    monkeypatch.setattr("app.connectors.read.woocommerce.get_variation", fake_get_variation)

    adapter = WooCommerceProductReadAdapter(url="https://store.example.test", key="ck_test", secret="cs_test")
    page = await adapter.fetch_entity(entity_id="99", parent_id="57926")

    assert calls == [(57926, 99)]
    assert page.items[0]["product_id"] == "99"
    assert page.items[0]["parent_id"] == "57926"


# ---------------------------------------------------------------------------
# ManualReadService.run_entity()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_manual_read_service_run_entity_passes_cached_parent_id(db, monkeypatch):
    from app.flowhub.read_engine.manual import ManualReadService
    from app.flowhub.read_engine.service import ReadProgress
    from app.flowhub.setup.service import AppConfigService

    AppConfigService(db).set_many(
        {"woocommerce.url": "https://store.example.test", "woocommerce.key": "ck_test", "woocommerce.secret": "cs_test"},
        updated_by="test",
    )
    db.add(DlProductCache(connector_id="woocommerce:primary", product_id="99", parent_id="57926"))
    db.commit()

    captured = {}

    async def fake_run_entity(self, adapter, *, entity_id, parent_id=None):
        captured["entity_id"] = entity_id
        captured["parent_id"] = parent_id
        return ReadProgress(
            job_id=None,
            connector_id=adapter.connector_id,
            strategy="entity_read",
            status="completed",
            requests_completed=1,
            requests_delayed=0,
            products_stored=1,
            remaining_queue=0,
            estimated_completion_seconds=None,
        )

    monkeypatch.setattr("app.flowhub.read_engine.service.IncrementalReadEngine.run_entity", fake_run_entity)

    result = await ManualReadService(db).run_entity("woocommerce:primary", "99", triggered_by="owner")

    assert captured == {"entity_id": "99", "parent_id": "57926"}
    assert result["manual_triggered"] is True
    assert result["entity_id"] == "99"


@pytest.mark.asyncio
async def test_manual_read_service_run_entity_unsupported_connector_returns_409(db):
    from fastapi import HTTPException

    from app.flowhub.read_engine.manual import ManualReadService
    from app.flowhub.setup.service import AppConfigService

    AppConfigService(db).set_many(
        {
            "nextcloud.url": "https://cloud.example.test",
            "nextcloud.username": "user",
            "nextcloud.password": "password",
            "nextcloud.spreadsheet_path": "/prices.xlsx",
        },
        updated_by="test",
    )

    with pytest.raises(HTTPException) as exc_info:
        await ManualReadService(db).run_entity("nextcloud:primary", "99", triggered_by="owner")
    assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# API route ordering
# ---------------------------------------------------------------------------
#
# APIRouter's "{connector_id:path}" converter matches "/" too. If the plain
# manual route were registered before the entity sub-route, it would swallow
# "/entity/{entity_id}" as part of connector_id and the entity route would
# never be reached.


def test_entity_route_is_registered_before_the_greedy_manual_route():
    from app.flowhub.api.v2.read_engine import router

    names = [route.endpoint.__name__ for route in router.routes]
    assert names.index("run_manual_entity_read") < names.index("run_manual_read")


def test_entity_route_reachable_end_to_end_through_a_minimal_app():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.flowhub.api.v2 import read_engine as read_engine_api
    from app.flowhub.auth.dependencies import get_current_user
    from app.flowhub.auth.models import FlowHubUser

    calls: list[tuple[str, str, str]] = []

    class _FakeService:
        async def run_entity(self, connector_id: str, entity_id: str, *, triggered_by: str) -> dict:
            calls.append((connector_id, entity_id, triggered_by))
            return {"entity_id": entity_id, "manual_triggered": True}

        async def run_manual(self, connector_id: str, *, triggered_by: str) -> dict:
            calls.append(("full", connector_id, triggered_by))
            return {"manual_triggered": True}

    app = FastAPI()
    app.include_router(read_engine_api.router, prefix="/api/v2")
    app.dependency_overrides[get_current_user] = lambda: FlowHubUser(id=1, username="owner", role="owner")
    app.dependency_overrides[read_engine_api._service] = lambda: _FakeService()

    with TestClient(app) as client:
        response = client.post("/api/v2/read/manual/woocommerce:primary/entity/57926")

    assert response.status_code == 200
    assert response.json() == {"entity_id": "57926", "manual_triggered": True}
    assert calls == [("woocommerce:primary", "57926", "owner")]


def test_plain_manual_route_still_reachable_end_to_end():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.flowhub.api.v2 import read_engine as read_engine_api
    from app.flowhub.auth.dependencies import get_current_user
    from app.flowhub.auth.models import FlowHubUser

    calls: list[tuple[str, str]] = []

    class _FakeService:
        async def run_manual(self, connector_id: str, *, triggered_by: str) -> dict:
            calls.append((connector_id, triggered_by))
            return {"manual_triggered": True}

    app = FastAPI()
    app.include_router(read_engine_api.router, prefix="/api/v2")
    app.dependency_overrides[get_current_user] = lambda: FlowHubUser(id=1, username="owner", role="owner")
    app.dependency_overrides[read_engine_api._service] = lambda: _FakeService()

    with TestClient(app) as client:
        response = client.post("/api/v2/read/manual/woocommerce:primary")

    assert response.status_code == 200
    assert response.json() == {"manual_triggered": True}
    assert calls == [("woocommerce:primary", "owner")]
