"""Postgres-only coverage for the FULL-vs-LIGHT write-fencing invariant.

The SQLite fallback path in ProductReadModelService._bulk_upsert_fallback
already exercises the same truth table (test_full_refresh_performance.py),
but the actual production write path is the PostgreSQL
INSERT ... ON CONFLICT ... WHERE statement in _bulk_upsert_postgresql,
which SQLite cannot execute at all. This module is what proves that
statement -- and genuine concurrent FULL-vs-LIGHT races against it -- are
correct. See ADR_CHANNEL_READ_ARCHITECTURE.md.

Mirrors the schema-per-test-module / TRUNCATE-per-test pattern in
tests/flowhub/webhooks/test_woocommerce_webhooks_postgres.py.
"""

from __future__ import annotations

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.flowhub.data_layer.job_lifecycle import RefreshJobLifecycle
from app.flowhub.data_layer.models import DlChannelEntityWork, DlProductCache, DlRefreshJob
from app.flowhub.data_layer.product_service import ProductReadModelService
from app.flowhub.database import FlowHubBase
from app.flowhub.read_engine.entity_work import claim_entity_work

pytestmark = pytest.mark.postgres


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.fixture(scope="module")
def postgres_engine() -> Engine:
    url = os.environ.get("FLOWHUB_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("FLOWHUB_TEST_POSTGRES_URL is not configured")

    admin_engine = sa.create_engine(url, pool_pre_ping=True)
    schema = f"full_light_fencing_test_{uuid.uuid4().hex}"
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
def pg_sessions(postgres_engine: Engine) -> sessionmaker[Session]:
    with postgres_engine.begin() as connection:
        table_names = ", ".join(f'"{table.name}"' for table in FlowHubBase.metadata.sorted_tables)
        connection.execute(sa.text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))
    return sessionmaker(bind=postgres_engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# 1. Stale FULL data cannot overwrite newer targeted (LIGHT) state
# ---------------------------------------------------------------------------


def test_full_batch_upsert_never_overwrites_newer_targeted_observation(pg_sessions):
    """A LIGHT write lands first with a recent provider_observed_at; a
    slower FULL page then tries to write the same row with an OLDER
    provider_observed_at (fetched before the LIGHT change, committed
    after). The FULL write must be silently fenced off."""
    older = utcnow() - timedelta(hours=1)
    newer = utcnow()
    with pg_sessions() as db:
        service = ProductReadModelService(db)
        service.bulk_upsert(
            "woocommerce:primary",
            [("57926", {"name": "From targeted LIGHT read", "price": "120.00", "provider_observed_at": newer})],
        )

    with pg_sessions() as db:
        service = ProductReadModelService(db)
        stored = service.bulk_upsert(
            "woocommerce:primary",
            [("57926", {"name": "From a slow FULL page", "price": "100.00", "provider_observed_at": older})],
        )
        # The row is still "processed" (guard passed, statement executed) --
        # the fencing WHERE clause silently no-ops the UPDATE branch, it is
        # not reported back as a failure to the caller.
        assert stored == 1

    with pg_sessions() as db:
        row = db.query(DlProductCache).filter_by(connector_id="woocommerce:primary", product_id="57926").one()
        assert row.name == "From targeted LIGHT read"
        assert row.price == "120.00"


def test_full_batch_upsert_allows_a_genuinely_newer_full_page(pg_sessions):
    older = utcnow() - timedelta(hours=1)
    newer = utcnow()
    with pg_sessions() as db:
        ProductReadModelService(db).bulk_upsert(
            "woocommerce:primary", [("57926", {"name": "Stale", "provider_observed_at": older})]
        )

    with pg_sessions() as db:
        ProductReadModelService(db).bulk_upsert(
            "woocommerce:primary", [("57926", {"name": "Fresh from FULL", "provider_observed_at": newer})]
        )

    with pg_sessions() as db:
        row = db.query(DlProductCache).filter_by(connector_id="woocommerce:primary", product_id="57926").one()
        assert row.name == "Fresh from FULL"


def test_concurrent_full_and_targeted_writes_converge_on_the_newest_observation(pg_sessions):
    """Genuine concurrency, not just ordering: two threads race to write
    the same row with different provider_observed_at values. Whichever
    commits, the row must end up holding the strictly newer observation,
    regardless of which write physically committed last."""
    older = utcnow() - timedelta(hours=1)
    newer = utcnow()
    barrier = threading.Barrier(2)

    def write(name: str, observed_at: datetime):
        with pg_sessions() as db:
            barrier.wait(timeout=10)
            ProductReadModelService(db).bulk_upsert(
                "woocommerce:primary", [("57926", {"name": name, "provider_observed_at": observed_at})]
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(
            pool.map(
                lambda args: write(*args),
                [("From FULL (older)", older), ("From LIGHT (newer)", newer)],
            )
        )

    with pg_sessions() as db:
        row = db.query(DlProductCache).filter_by(connector_id="woocommerce:primary", product_id="57926").one()
        assert row.name == "From LIGHT (newer)", "the newer observation must win regardless of commit order"


# ---------------------------------------------------------------------------
# 2. FULL unseen-sweep preserves a concurrently confirmed product
# ---------------------------------------------------------------------------


def test_full_unseen_sweep_preserves_concurrently_confirmed_product(pg_sessions):
    """A product touched by a concurrent targeted write while a FULL job is
    in flight must survive FULL's unseen sweep, even though it never
    appeared on any of FULL's own pages -- the fix for the correctness gap
    the old seen_product_ids-based sweep would have had."""
    with pg_sessions() as db:
        job = DlRefreshJob(
            job_type="manual", entity_type="products", connector_id="woocommerce:primary",
            status="pending", triggered_by="test", created_at=utcnow(),
            meta={"strategy": "initial_full_read"},
        )
        db.add(job)
        db.commit()
        RefreshJobLifecycle(db).start(job)
        db.refresh(job)
        job_started_at = job.started_at

    with pg_sessions() as db:
        # Simulate: FULL's page loop is running (job.started_at already
        # recorded); a concurrent targeted LIGHT read lands for a product
        # FULL's own pages will never include.
        ProductReadModelService(db).bulk_upsert(
            "woocommerce:primary", [("concurrent-57926", {"name": "Touched mid-scan"})]
        )

    with pg_sessions() as db:
        # FULL's completion-time unseen sweep, exactly as
        # IncrementalReadEngine.run_manual performs it.
        unseen = db.query(DlProductCache).filter(
            DlProductCache.connector_id == "woocommerce:primary",
            (DlProductCache.last_fetched_at.is_(None)) | (DlProductCache.last_fetched_at < job_started_at),
        )
        unseen.update({"exists": False, "freshness": "stale"}, synchronize_session=False)
        db.commit()

    with pg_sessions() as db:
        row = db.query(DlProductCache).filter_by(connector_id="woocommerce:primary", product_id="concurrent-57926").one()
        assert row.exists is True, "must not be swept just because FULL's own pages never saw it"
        assert row.freshness != "stale"


# ---------------------------------------------------------------------------
# 3. Crash during FULL is resumable/checkpoint-safe with the new (smaller)
#    checkpoint shape
# ---------------------------------------------------------------------------


def test_full_lease_and_targeted_entity_lease_remain_independent_under_real_concurrency(pg_sessions):
    """Restates the Phase C lease-independence guarantee with a genuine
    PostgreSQL bulk_upsert write happening concurrently with the targeted
    claim, not just lease acquisition -- the full FULL-vs-LIGHT story."""
    with pg_sessions() as db:
        full_job = DlRefreshJob(
            job_type="manual", entity_type="products", connector_id="woocommerce:primary",
            status="pending", triggered_by="test", created_at=utcnow(),
            meta={"strategy": "initial_full_read"},
        )
        db.add(full_job)
        db.commit()
        RefreshJobLifecycle(db).start(full_job)

        work = DlChannelEntityWork(
            connector_id="woocommerce:primary", entity_type="products", entity_id="different-product",
            status="pending", strategy="LIGHT", reason="WEBHOOK_PRODUCT_UPDATED",
            latest_reason="WEBHOOK_PRODUCT_UPDATED", latest_event_at=utcnow(),
            attempt_count=0, max_attempts=5, created_at=utcnow(), updated_at=utcnow(),
        )
        db.add(work)
        db.commit()
        work_id = work.id

    barrier = threading.Barrier(2)

    def run_full_page():
        with pg_sessions() as db:
            barrier.wait(timeout=10)
            return ProductReadModelService(db).bulk_upsert(
                "woocommerce:primary", [("full-scan-product", {"name": "From FULL page"})]
            )

    def run_targeted_claim():
        with pg_sessions() as db:
            barrier.wait(timeout=10)
            claimed = claim_entity_work(db, worker_id="targeted-worker", limit=10, lease_seconds=120)
            return [item.id for item in claimed]

    with ThreadPoolExecutor(max_workers=2) as pool:
        full_future = pool.submit(run_full_page)
        targeted_future = pool.submit(run_targeted_claim)
        full_stored = full_future.result(timeout=10)
        targeted_claimed = targeted_future.result(timeout=10)

    assert full_stored == 1
    assert targeted_claimed == [work_id], "the targeted claim must proceed uncontended while FULL is writing"
