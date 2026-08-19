"""Postgres concurrency coverage for the per-entity Channel Read work queue.

SQLite's StaticPool test setup serializes all sessions onto one connection,
so it cannot exercise FOR UPDATE SKIP LOCKED or the partial unique index
race the way a real Postgres backend can. See ADR_CHANNEL_READ_ARCHITECTURE.md
for the lease/coalescing model this exercises.

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

from app.flowhub.data_layer.job_lifecycle import RefreshJobAlreadyRunning, RefreshJobLifecycle
from app.flowhub.data_layer.models import (
    DlChannelEntityWork,
    DlChannelEntityWorkReceipt,
    DlRefreshJob,
)
from app.flowhub.database import FlowHubBase
from app.flowhub.integration_platform.models import IntegrationConnectorInstance
from app.flowhub.read_engine.entity_work import (
    claim_entity_work,
    complete_entity_work,
    enqueue_entity_work,
    recover_expired_entity_work,
)
from app.flowhub.webhooks.models import WebhookReceipt

pytestmark = pytest.mark.postgres


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.fixture(scope="module")
def postgres_engine() -> Engine:
    url = os.environ.get("FLOWHUB_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("FLOWHUB_TEST_POSTGRES_URL is not configured")

    admin_engine = sa.create_engine(url, pool_pre_ping=True)
    schema = f"channel_entity_work_test_{uuid.uuid4().hex}"
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


def _seed_channel(db: Session, channel_id: str) -> None:
    db.add(
        IntegrationConnectorInstance(
            id=channel_id,
            connector_type="woocommerce",
            name=channel_id,
            version="1.0.0",
            enabled=True,
            read_only=False,
            status="configured",
            created_at=utcnow(),
            updated_at=utcnow(),
        )
    )
    db.commit()


def _receipt(db: Session, channel_id: str, provider_event_id: str, wc_product_id: str = "57926") -> int:
    receipt = WebhookReceipt(
        channel_id=channel_id,
        provider="woocommerce",
        provider_event_id=provider_event_id,
        payload_hash=uuid.uuid4().hex,
        payload_summary_json={"topic": "product.updated"},
        normalized_event_json={"topic": "product.updated", "wc_product_id": wc_product_id},
        received_at=utcnow(),
        acknowledged_at=utcnow(),
        processing_state="queued",
        attempt_count=0,
    )
    db.add(receipt)
    db.commit()
    return receipt.id


def _work(
    db: Session,
    *,
    connector_id: str = "woocommerce:contended",
    entity_id: str = "57926",
    status: str = "pending",
    max_attempts: int = 5,
    attempt_count: int = 0,
) -> int:
    work = DlChannelEntityWork(
        connector_id=connector_id,
        entity_type="products",
        entity_id=entity_id,
        status=status,
        strategy="LIGHT",
        reason="WEBHOOK_PRODUCT_UPDATED",
        latest_reason="WEBHOOK_PRODUCT_UPDATED",
        latest_event_at=utcnow(),
        attempt_count=attempt_count,
        max_attempts=max_attempts,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(work)
    db.commit()
    return work.id


# ---------------------------------------------------------------------------
# 1. Multiple workers, different products: safe concurrency, no double claim
# ---------------------------------------------------------------------------


def test_concurrent_claim_has_no_double_processing(pg_sessions):
    with pg_sessions() as db:
        work_ids = [_work(db, entity_id=str(100 + i)) for i in range(6)]

    barrier = threading.Barrier(3)

    def claim(worker_index: int) -> list[int]:
        with pg_sessions() as db:
            barrier.wait(timeout=10)
            # limit=2 with 6 rows across 3 single-call workers is deliberate:
            # since the assertions below require all 6 claimed and no worker
            # can exceed 2, pigeonhole forces every worker to claim exactly
            # 2 -- a deterministic spread, not a scheduling-order coin flip
            # (limit=10 let one fast worker legitimately claim all 6 under
            # SKIP LOCKED, which is correct but exercises no real contention).
            claimed = claim_entity_work(db, worker_id=f"worker-{worker_index}", limit=2, lease_seconds=120)
            return [work.id for work in claimed]

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(claim, range(3)))

    all_claimed = [work_id for batch in results for work_id in batch]
    assert sorted(all_claimed) == sorted(work_ids), "every row must be claimed exactly once, none lost"
    assert len(all_claimed) == len(set(all_claimed)), "no row may be claimed by two workers"

    with pg_sessions() as db:
        rows = db.query(DlChannelEntityWork).filter(DlChannelEntityWork.id.in_(work_ids)).all()
        assert all(row.status == "running" for row in rows)
        worker_ids = {row.worker_id for row in rows}
        assert len(worker_ids) >= 2, "claims should have spread across more than one worker"


# ---------------------------------------------------------------------------
# 2. Multiple webhook updates for the same product coalesce safely
# ---------------------------------------------------------------------------


def test_concurrent_enqueue_coalesces_to_one_pending_row(pg_sessions):
    barrier = threading.Barrier(5)

    def enqueue(i: int):
        with pg_sessions() as db:
            barrier.wait(timeout=10)
            work = enqueue_entity_work(
                db,
                connector_id="woocommerce:contended",
                entity_type="products",
                entity_id="57926",
                reason="WEBHOOK_PRODUCT_UPDATED",
                event_at=utcnow() + timedelta(seconds=i),
            )
            return work.id

    with ThreadPoolExecutor(max_workers=5) as pool:
        work_ids = list(pool.map(enqueue, range(5)))

    assert len(set(work_ids)) == 1, "concurrent enqueues for one entity must coalesce onto one row"
    with pg_sessions() as db:
        assert (
            db.query(DlChannelEntityWork)
            .filter_by(connector_id="woocommerce:contended", entity_type="products", entity_id="57926")
            .count()
            == 1
        )


# ---------------------------------------------------------------------------
# 3. New evidence while running requeues instead of completing
# ---------------------------------------------------------------------------


def test_supersede_during_running_requeues_instead_of_completing(pg_sessions):
    with pg_sessions() as db:
        work_id = _work(db, status="running")
        db.query(DlChannelEntityWork).filter_by(id=work_id).update(
            {"worker_id": "worker-a", "started_at": utcnow(), "lease_expires_at": utcnow() + timedelta(seconds=120)}
        )
        db.commit()

    with pg_sessions() as db:
        # New evidence arrives mid-flight (a second webhook for the same
        # entity while the first is still being processed).
        enqueue_entity_work(
            db,
            connector_id="woocommerce:contended",
            entity_type="products",
            entity_id="57926",
            reason="WEBHOOK_PRODUCT_UPDATED",
            event_at=utcnow() + timedelta(seconds=5),
        )

    with pg_sessions() as db:
        work = db.get(DlChannelEntityWork, work_id)
        assert work.superseded_at is not None
        completed = complete_entity_work(db, work, outcome="completed")

    assert completed.status == "pending", "superseded completion must requeue, not finish"
    assert completed.completed_at is None


# ---------------------------------------------------------------------------
# 4. Terminal completion flips exactly the linked receipts
# ---------------------------------------------------------------------------


def test_terminal_completion_flips_exactly_linked_receipts(pg_sessions):
    with pg_sessions() as db:
        _seed_channel(db, "woocommerce:contended")
        work_id = _work(db, status="running")
        covered_ids = [_receipt(db, "woocommerce:contended", f"wh:dl-{i}") for i in range(3)]
        for receipt_id in covered_ids:
            db.add(DlChannelEntityWorkReceipt(work_id=work_id, receipt_id=receipt_id, linked_at=utcnow()))
        db.commit()
        other_work_id = _work(db, entity_id="99999", status="running")
        unrelated_id = _receipt(db, "woocommerce:contended", "wh:dl-unrelated", wc_product_id="99999")
        db.add(DlChannelEntityWorkReceipt(work_id=other_work_id, receipt_id=unrelated_id, linked_at=utcnow()))
        db.commit()

    with pg_sessions() as db:
        work = db.get(DlChannelEntityWork, work_id)
        complete_entity_work(db, work, outcome="completed")

    with pg_sessions() as db:
        covered = db.query(WebhookReceipt).filter(WebhookReceipt.id.in_(covered_ids)).all()
        assert all(receipt.processing_state == "processed" for receipt in covered)
        unrelated = db.get(WebhookReceipt, unrelated_id)
        assert unrelated.processing_state == "queued"


# ---------------------------------------------------------------------------
# 5 & 6. Retry/backoff and dead-letter at attempt exhaustion
# ---------------------------------------------------------------------------


def test_failure_below_max_attempts_requeues_with_backoff(pg_sessions):
    with pg_sessions() as db:
        work_id = _work(db, status="running", max_attempts=5, attempt_count=1)
        _seed_channel(db, "woocommerce:contended")
        receipt_id = _receipt(db, "woocommerce:contended", "wh:dl-retry")
        db.add(DlChannelEntityWorkReceipt(work_id=work_id, receipt_id=receipt_id, linked_at=utcnow()))
        db.commit()

    with pg_sessions() as db:
        work = db.get(DlChannelEntityWork, work_id)
        complete_entity_work(db, work, outcome="failed", error_category="timeout", error_message="slow store")

    with pg_sessions() as db:
        work = db.get(DlChannelEntityWork, work_id)
        assert work.status == "pending"
        assert work.next_attempt_at is not None and work.next_attempt_at > utcnow()
        receipt = db.get(WebhookReceipt, receipt_id)
        assert receipt.processing_state == "queued", "receipts stay untouched while the work item still has budget"


def test_failure_at_max_attempts_dead_letters_linked_receipts(pg_sessions):
    with pg_sessions() as db:
        work_id = _work(db, status="running", max_attempts=1, attempt_count=1)
        _seed_channel(db, "woocommerce:contended")
        receipt_id = _receipt(db, "woocommerce:contended", "wh:dl-exhausted")
        db.add(DlChannelEntityWorkReceipt(work_id=work_id, receipt_id=receipt_id, linked_at=utcnow()))
        db.commit()

    with pg_sessions() as db:
        work = db.get(DlChannelEntityWork, work_id)
        complete_entity_work(db, work, outcome="failed", error_category="timeout", error_message="slow store")

    with pg_sessions() as db:
        work = db.get(DlChannelEntityWork, work_id)
        assert work.status == "failed"
        receipt = db.get(WebhookReceipt, receipt_id)
        assert receipt.processing_state in {"retry_scheduled", "dead_letter"}
        # The receipt's own MAX_PROCESSING_ATTEMPTS budget governs its final
        # state independently -- a fresh receipt still has budget left, so
        # it is scheduled for its own retry rather than immediately dead-
        # lettered; either way it must never stay stuck "queued" forever.
        assert receipt.attempt_count == 1


# ---------------------------------------------------------------------------
# 7. Lease expiry does not permanently block the connector
# ---------------------------------------------------------------------------


def test_lease_expiry_recovery_respects_max_attempts(pg_sessions):
    with pg_sessions() as db:
        recoverable_id = _work(db, entity_id="1", status="running", max_attempts=5, attempt_count=1)
        exhausted_id = _work(db, entity_id="2", status="running", max_attempts=1, attempt_count=1)
        stale = utcnow() - timedelta(seconds=1)
        db.query(DlChannelEntityWork).filter(
            DlChannelEntityWork.id.in_([recoverable_id, exhausted_id])
        ).update({"lease_expires_at": stale, "started_at": stale}, synchronize_session=False)
        db.commit()

    with pg_sessions() as db:
        recovered = recover_expired_entity_work(db)

    assert {work.id for work in recovered} == {recoverable_id, exhausted_id}
    with pg_sessions() as db:
        recoverable = db.get(DlChannelEntityWork, recoverable_id)
        assert recoverable.status == "pending", "a connector must not be permanently blocked by one dead worker"
        exhausted = db.get(DlChannelEntityWork, exhausted_id)
        assert exhausted.status == "failed"
        assert exhausted.error_category == "execution_lease_expired"


# ---------------------------------------------------------------------------
# 8. Crash-then-retry / duplicate completion is idempotent
# ---------------------------------------------------------------------------


def test_idempotent_replay_of_claim_and_complete_is_a_no_op(pg_sessions):
    """Two concurrent completions of the same work item (e.g. a false-
    positive lease-recovery race with a still-alive worker's own
    completion) must not double-mutate state or crash. flip_linked_receipts
    calls the existing WebhookIngestionService.mark_woocommerce_receipt_processed
    for both racers, but that method's own SELECT ... FOR UPDATE on the
    receipt row (webhooks/service.py's _process_receipt) already serializes
    them: exactly one racer observes the not-yet-processed row and records
    the one real attempt: the other unblocks afterward, observes
    processing_state == "processed", and returns without incrementing
    attempt_count a second time."""
    with pg_sessions() as db:
        _seed_channel(db, "woocommerce:contended")
        work_id = _work(db, status="running")
        receipt_ids = [_receipt(db, "woocommerce:contended", f"wh:dl-replay-{i}") for i in range(2)]
        for receipt_id in receipt_ids:
            db.add(DlChannelEntityWorkReceipt(work_id=work_id, receipt_id=receipt_id, linked_at=utcnow()))
        db.commit()

    barrier = threading.Barrier(2)

    def complete(_: int) -> str:
        with pg_sessions() as db:
            work = db.get(DlChannelEntityWork, work_id)
            barrier.wait(timeout=10)
            result = complete_entity_work(db, work, outcome="completed")
            return result.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(complete, range(2)))

    assert all(status == "completed" for status in outcomes)
    with pg_sessions() as db:
        work = db.get(DlChannelEntityWork, work_id)
        assert work.status == "completed"
        receipts = db.query(WebhookReceipt).filter(WebhookReceipt.id.in_(receipt_ids)).all()
        assert all(receipt.processing_state == "processed" for receipt in receipts)
        assert all(receipt.attempt_count == 1 for receipt in receipts), (
            "exactly one real attempt despite two racing completions -- not 0 (a"
            " successful transition still counts as an attempt) and not 2 (the"
            " second racer's flip must be serialized into a no-op, not a double-count)"
        )
        # Exactly one join row per (work, receipt) -- no duplicate linking.
        assert db.query(DlChannelEntityWorkReceipt).filter_by(work_id=work_id).count() == 2


# ---------------------------------------------------------------------------
# Bonus: FULL channel-wide lease and targeted entity-work lease are
# independent -- the structural fix for the 2026-08-18 incident.
# ---------------------------------------------------------------------------


def test_concurrent_full_job_and_entity_work_lease_are_independent(pg_sessions):
    with pg_sessions() as db:
        full_job = DlRefreshJob(
            job_type="scheduled",
            entity_type="products",
            connector_id="woocommerce:contended",
            status="pending",
            triggered_by="test",
            created_at=utcnow(),
            meta={"strategy": "initial_full_read"},
        )
        db.add(full_job)
        db.commit()
        full_job_id = full_job.id
        # A different product than whatever the FULL job would touch.
        work_id = _work(db, entity_id="different-product")

    barrier = threading.Barrier(2)

    def run_full():
        with pg_sessions() as db:
            job = db.get(DlRefreshJob, full_job_id)
            barrier.wait(timeout=10)
            try:
                RefreshJobLifecycle(db).start(job)
                return "started"
            except RefreshJobAlreadyRunning:
                return "blocked"

    def run_targeted():
        with pg_sessions() as db:
            barrier.wait(timeout=10)
            claimed = claim_entity_work(db, worker_id="targeted-worker", limit=10, lease_seconds=120)
            return "claimed" if any(work.id == work_id for work in claimed) else "blocked"

    with ThreadPoolExecutor(max_workers=2) as pool:
        full_future = pool.submit(run_full)
        targeted_future = pool.submit(run_targeted)
        full_result = full_future.result(timeout=10)
        targeted_result = targeted_future.result(timeout=10)

    assert full_result == "started", "the FULL job must acquire its own lease uncontended"
    assert targeted_result == "claimed", "a targeted claim for a different product must never be blocked by FULL"
