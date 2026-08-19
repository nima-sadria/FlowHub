"""Phase D: FULL refresh performance -- bounded concurrency, batch
persistence, and the unseen-sweep concurrency fix.

Genuine PostgreSQL fencing (ON CONFLICT ... WHERE) is covered separately in
test_full_light_fencing_postgres.py, which requires a real PostgreSQL
backend. This file exercises the SQLite-fallback path's own correctness
(same fencing truth table, different mechanism) and the WooCommerce
adapter's bounded concurrency.
"""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("FLOWHUB_DATABASE_URL", "sqlite:///:memory:")

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.flowhub.data_layer.models import DlProductCache, DlRefreshJob
from app.flowhub.database import FlowHubBase
from app.flowhub.integration_platform import models as _integration_platform_models  # noqa: F401
from app.flowhub.unified_workspace import models as _unified_workspace_models  # noqa: F401
from app.flowhub.webhooks import models as _webhook_models  # noqa: F401


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


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
# WooCommerceProductReadAdapter.fetch_products: bounded concurrency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_products_bounds_concurrent_variation_fetches(monkeypatch):
    from app.connectors.read.woocommerce import WooCommerceProductReadAdapter

    in_flight = 0
    max_in_flight = 0

    async def fake_list_products_paged(creds, page=1, per_page=100, **kwargs):
        items = [{"id": i, "type": "variable", "sku": f"SKU-{i}", "images": []} for i in range(100, 106)]
        return items, len(items), 1

    async def fake_list_variations(creds, product_id, page=1, per_page=100):
        nonlocal in_flight, max_in_flight
        if page > 1:
            return []
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return [{"id": product_id * 10 + 1, "regular_price": "5.00"}]

    monkeypatch.setattr("app.connectors.read.woocommerce.list_products_paged", fake_list_products_paged)
    monkeypatch.setattr("app.connectors.read.woocommerce.list_variations", fake_list_variations)

    adapter = WooCommerceProductReadAdapter(url="https://store.example.test", key="ck_test", secret="cs_test")
    assert adapter.capabilities.recommended_concurrency == 4

    await adapter.fetch_products()

    assert max_in_flight <= 4, "variation fan-out must respect recommended_concurrency"
    assert max_in_flight > 1, "fan-out should actually run concurrently, not fall back to sequential"
    assert adapter.variable_products_read == 6
    assert adapter.variations_read == 6


@pytest.mark.asyncio
async def test_fetch_products_still_returns_all_items_with_concurrency(monkeypatch):
    from app.connectors.read.woocommerce import WooCommerceProductReadAdapter

    async def fake_list_products_paged(creds, page=1, per_page=100, **kwargs):
        items = [
            {"id": 1, "type": "simple", "sku": "S-1", "images": []},
            {"id": 2, "type": "variable", "sku": "S-2", "images": []},
            {"id": 3, "type": "variable", "sku": "S-3", "images": []},
        ]
        return items, len(items), 1

    async def fake_list_variations(creds, product_id, page=1, per_page=100):
        if page > 1:
            return []
        return [{"id": product_id * 100 + 1, "regular_price": "5.00"}, {"id": product_id * 100 + 2, "regular_price": "6.00"}]

    monkeypatch.setattr("app.connectors.read.woocommerce.list_products_paged", fake_list_products_paged)
    monkeypatch.setattr("app.connectors.read.woocommerce.list_variations", fake_list_variations)

    adapter = WooCommerceProductReadAdapter(url="https://store.example.test", key="ck_test", secret="cs_test")
    page = await adapter.fetch_products()

    ids = {item["product_id"] for item in page.items}
    assert ids == {"1", "2", "3", "201", "202", "301", "302"}


# ---------------------------------------------------------------------------
# ProductReadModelService.bulk_upsert (SQLite fallback path)
# ---------------------------------------------------------------------------


def test_bulk_upsert_inserts_new_rows(db):
    from app.flowhub.data_layer.product_service import ProductReadModelService

    service = ProductReadModelService(db)
    items = [(str(i), {"sku": f"SKU-{i}", "name": f"Product {i}"}) for i in range(5)]

    stored = service.bulk_upsert("woocommerce:primary", items)

    assert stored == 5
    assert db.query(DlProductCache).count() == 5
    row = db.query(DlProductCache).filter_by(product_id="0").one()
    assert row.sku == "SKU-0"
    assert row.freshness == "fresh"
    assert row.last_fetched_at is not None


def test_bulk_upsert_updates_existing_rows(db):
    from app.flowhub.data_layer.product_service import ProductReadModelService

    db.add(DlProductCache(connector_id="woocommerce:primary", product_id="1", name="Old Name"))
    db.commit()
    service = ProductReadModelService(db)

    stored = service.bulk_upsert("woocommerce:primary", [("1", {"name": "New Name"})])

    assert stored == 1
    assert db.query(DlProductCache).count() == 1
    assert db.query(DlProductCache).filter_by(product_id="1").one().name == "New Name"


def test_bulk_upsert_empty_batch_is_a_no_op(db):
    from app.flowhub.data_layer.product_service import ProductReadModelService

    assert ProductReadModelService(db).bulk_upsert("woocommerce:primary", []) == 0
    assert db.query(DlProductCache).count() == 0


def test_bulk_upsert_fencing_skips_an_older_observation(db):
    """The core FULL-vs-LIGHT correctness invariant, exercised on the
    SQLite fallback path: an incoming write older than the row's current
    provider_observed_at must never overwrite it."""
    from app.flowhub.data_layer.product_service import ProductReadModelService

    newer = utcnow()
    older = newer - timedelta(hours=1)
    db.add(
        DlProductCache(
            connector_id="woocommerce:primary", product_id="1", name="Newer (from LIGHT)", provider_observed_at=newer
        )
    )
    db.commit()
    service = ProductReadModelService(db)

    stored = service.bulk_upsert("woocommerce:primary", [("1", {"name": "Stale (from FULL)", "provider_observed_at": older})])

    row = db.query(DlProductCache).filter_by(product_id="1").one()
    assert row.name == "Newer (from LIGHT)", "an older observation must never overwrite a newer one"
    # bulk_upsert still reports the row as processed -- the fencing skip is
    # a silent no-op at the DB layer, not a reported failure.
    assert stored == 1


def test_bulk_upsert_fencing_allows_a_newer_observation(db):
    from app.flowhub.data_layer.product_service import ProductReadModelService

    older = utcnow() - timedelta(hours=1)
    newer = utcnow()
    db.add(DlProductCache(connector_id="woocommerce:primary", product_id="1", name="Old", provider_observed_at=older))
    db.commit()
    service = ProductReadModelService(db)

    service.bulk_upsert("woocommerce:primary", [("1", {"name": "New", "provider_observed_at": newer})])

    assert db.query(DlProductCache).filter_by(product_id="1").one().name == "New"


def test_bulk_upsert_allows_write_when_existing_observed_at_is_null(db):
    from app.flowhub.data_layer.product_service import ProductReadModelService

    db.add(DlProductCache(connector_id="woocommerce:primary", product_id="1", name="Old", provider_observed_at=None))
    db.commit()
    service = ProductReadModelService(db)

    service.bulk_upsert("woocommerce:primary", [("1", {"name": "New", "provider_observed_at": utcnow()})])

    assert db.query(DlProductCache).filter_by(product_id="1").one().name == "New"


def test_bulk_upsert_skips_rows_whose_listing_is_apply_locked(db, monkeypatch):
    """bulk_upsert must skip -- not abort the whole batch for -- a row whose
    Listing is currently owned by an in-flight Apply job. The Listing-guard
    mechanism itself (real FK chain: Workspace/Channel/CanonicalProduct/
    Listing/ApplyJob/WorkspaceLock) is exercised elsewhere; here we only
    need to prove bulk_upsert's own catch-and-continue behavior when that
    mechanism raises."""
    import app.flowhub.data_layer.product_service as product_service_module
    from app.flowhub.data_layer.product_service import ProductReadModelService
    from app.flowhub.unified_workspace.listing_guard import ListingGuardConflict

    def fake_guard(db_arg, connector_id, product_id):
        if product_id == "1":
            raise ListingGuardConflict(connector_id, "listing-1", "apply-job-1")
        return None

    monkeypatch.setattr(
        "app.flowhub.unified_workspace.listing_guard.acquire_external_listing_guard", fake_guard
    )
    # bulk_upsert imports the guard function inside its own method body (to
    # avoid a module-level circular import), so the patch target above is
    # what actually gets called -- confirmed by asserting the skip below.
    _ = product_service_module

    service = ProductReadModelService(db)
    stored = service.bulk_upsert(
        "woocommerce:primary",
        [("1", {"name": "Contended"}), ("2", {"name": "Uncontended"})],
    )

    assert stored == 1, "the contended row is skipped, not the whole batch"
    assert db.query(DlProductCache).filter_by(product_id="2").count() == 1
    assert db.query(DlProductCache).filter_by(product_id="1").count() == 0


# ---------------------------------------------------------------------------
# run_manual: batched persistence + no unbounded checkpoint growth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_manual_checkpoint_does_not_grow_with_catalog_size(db):
    """The old seen_product_ids-in-meta approach re-serialized every seen id
    on every page. This asserts job.meta stays small regardless of how many
    products have been processed."""
    from app.flowhub.read_engine.contracts import ConnectorReadCapabilities, ReadPage
    from app.flowhub.read_engine.service import IncrementalReadEngine

    class _PagedAdapter:
        connector_id = "woocommerce:primary"
        connector_type = "woocommerce"
        capabilities = ConnectorReadCapabilities(supports_pagination=True)

        def __init__(self, pages):
            self._pages = pages

        async def fetch_products(self, *, modified_since=None, cursor=None, product_ids=None):
            index = int(cursor or "0")
            items = self._pages[index]
            next_cursor = str(index + 1) if index + 1 < len(self._pages) else None
            return ReadPage(items=items, next_cursor=next_cursor)

    pages = [[{"id": str(i), "sku": f"SKU-{i}", "price": "10.00"} for i in range(page * 50, page * 50 + 50)] for page in range(5)]
    adapter = _PagedAdapter(pages)

    progress = await IncrementalReadEngine(db).run_manual(adapter)

    assert progress.status == "completed"
    assert progress.products_stored == 250
    assert db.query(DlProductCache).count() == 250
    # A CHANNEL/FULL-scope read is not zero-staleness (unlike a targeted
    # LIGHT read) but a row just successfully written is trivially within
    # its own TTL -- LIKELY_FRESH, never STALE at write time.
    sample_row = db.query(DlProductCache).filter_by(product_id="0").one()
    assert sample_row.observation_confidence == "LIKELY_FRESH"
    assert sample_row.observation_confidence_reason == "within_channel_ttl"
    job = db.query(DlRefreshJob).one()
    assert "seen_product_ids" not in (job.meta or {})


@pytest.mark.asyncio
async def test_run_manual_unseen_sweep_preserves_a_concurrently_touched_product(db):
    """A product touched by a concurrent targeted read mid-FULL-scan (its
    last_fetched_at bumped to "now") must survive the unseen sweep even
    though it never appeared on any of this run's own pages -- the
    correctness gap the seen_product_ids-based sweep would have had once
    LIGHT can run concurrently with FULL."""
    from app.flowhub.data_layer.product_service import ProductReadModelService
    from app.flowhub.read_engine.contracts import ConnectorReadCapabilities, ReadPage
    from app.flowhub.read_engine.service import IncrementalReadEngine

    class _OnePageAdapter:
        connector_id = "woocommerce:primary"
        connector_type = "woocommerce"
        capabilities = ConnectorReadCapabilities(supports_pagination=True)

        async def fetch_products(self, *, modified_since=None, cursor=None, product_ids=None):
            if cursor:
                return ReadPage(items=[], next_cursor=None)
            # Simulate: while FULL's one page is "in flight", a concurrent
            # targeted LIGHT read for product "concurrent" lands first.
            ProductReadModelService(db).bulk_upsert(
                "woocommerce:primary", [("concurrent", {"name": "Touched mid-scan"})]
            )
            return ReadPage(items=[{"id": "999", "sku": "SKU-999", "price": "1.00"}], next_cursor=None)

    progress = await IncrementalReadEngine(db).run_manual(_OnePageAdapter(), force_full=True)

    assert progress.status == "completed"
    concurrent_row = db.query(DlProductCache).filter_by(product_id="concurrent").one()
    assert concurrent_row.exists is True, "must not be swept just because FULL's own pages never saw it"
    seen_row = db.query(DlProductCache).filter_by(product_id="999").one()
    assert seen_row.exists is True


@pytest.mark.asyncio
async def test_run_manual_unseen_sweep_still_retires_genuinely_stale_products(db):
    from app.flowhub.read_engine.contracts import ConnectorReadCapabilities, ReadPage
    from app.flowhub.read_engine.service import IncrementalReadEngine

    db.add(
        DlProductCache(
            connector_id="woocommerce:primary",
            product_id="gone",
            name="No longer in the catalog",
            exists=True,
            freshness="fresh",
            last_fetched_at=utcnow() - timedelta(days=30),
        )
    )
    db.commit()

    class _EmptyPageAdapter:
        connector_id = "woocommerce:primary"
        connector_type = "woocommerce"
        capabilities = ConnectorReadCapabilities(supports_pagination=True)

        async def fetch_products(self, *, modified_since=None, cursor=None, product_ids=None):
            return ReadPage(items=[], next_cursor=None)

    await IncrementalReadEngine(db).run_manual(_EmptyPageAdapter(), force_full=True)

    row = db.query(DlProductCache).filter_by(product_id="gone").one()
    assert row.exists is False
    assert row.freshness == "stale"


# ---------------------------------------------------------------------------
# Durable telemetry (Phase D benchmarking requirement)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_manual_records_durable_telemetry_for_http_boundary_limited_connectors(db):
    """WooCommerce-style connectors (uses_http_boundary_limiter=True) bypass
    RateLimitService.acquire() entirely, so run_manual's own telemetry call
    is the *only* source of request-count evidence for them."""
    from app.flowhub.data_layer.models import DlConnectorTelemetry
    from app.flowhub.read_engine.contracts import ConnectorReadCapabilities, ReadPage
    from app.flowhub.read_engine.service import IncrementalReadEngine

    class _BoundaryLimitedAdapter:
        connector_id = "woocommerce:primary"
        connector_type = "woocommerce"
        uses_http_boundary_limiter = True
        capabilities = ConnectorReadCapabilities(supports_pagination=True)

        async def fetch_products(self, *, modified_since=None, cursor=None, product_ids=None):
            return ReadPage(items=[{"id": "1", "sku": "A"}, {"id": "2", "sku": "B"}], next_cursor=None)

    await IncrementalReadEngine(db).run_manual(_BoundaryLimitedAdapter())

    row = db.query(DlConnectorTelemetry).filter_by(connector_id="woocommerce:primary").one()
    assert row.request_count == 1
    assert row.products_fetched == 2
    assert row.last_refresh_duration_ms is not None


@pytest.mark.asyncio
async def test_run_manual_does_not_double_count_requests_for_standard_limited_connectors(db):
    """A connector going through the standard RateLimitService.acquire()
    path already gets request_count incremented there
    (record_acquire) -- run_manual's own telemetry call must not add a
    second increment on top of it."""
    from app.flowhub.data_layer.models import DlConnectorTelemetry
    from app.flowhub.read_engine.contracts import ConnectorReadCapabilities, ReadPage
    from app.flowhub.read_engine.service import IncrementalReadEngine

    class _StandardLimitedAdapter:
        connector_id = "nextcloud:primary"
        connector_type = "nextcloud"
        capabilities = ConnectorReadCapabilities(supports_pagination=True)

        async def fetch_products(self, *, modified_since=None, cursor=None, product_ids=None):
            return ReadPage(items=[{"id": "1", "sku": "A"}], next_cursor=None)

    await IncrementalReadEngine(db).run_manual(_StandardLimitedAdapter())

    row = db.query(DlConnectorTelemetry).filter_by(connector_id="nextcloud:primary").one()
    assert row.request_count == 1, "RateLimitService.record_acquire already counted it once"
    assert row.products_fetched == 1
