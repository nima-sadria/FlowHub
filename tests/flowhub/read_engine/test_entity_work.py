"""Sequential-logic coverage for the per-entity Channel Read work queue.

Genuine concurrency (FOR UPDATE SKIP LOCKED, the partial-unique-index race)
is covered separately in test_channel_entity_work_postgres.py, which
requires a real PostgreSQL backend. This file exercises the same functions'
single-threaded correctness against SQLite: coalescing rules, the
supersede/requeue mechanism, retry/backoff, lease recovery, and receipt
linking -- everything that doesn't require true concurrent access to verify.
"""

from __future__ import annotations

import os

os.environ.setdefault("FLOWHUB_DATABASE_URL", "sqlite:///:memory:")

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.flowhub.data_layer.models import DlChannelEntityWork, DlChannelEntityWorkReceipt
from app.flowhub.database import FlowHubBase
from app.flowhub.read_engine.entity_work import (
    claim_entity_work,
    complete_entity_work,
    enqueue_entity_work,
    flip_linked_receipts,
    recover_expired_entity_work,
    sync_pending_woocommerce_receipts,
)
from app.flowhub.webhooks.models import WebhookReceipt


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


def _receipt(db, provider_event_id: str, wc_product_id: str | None = "57926", channel_id: str = "woocommerce:primary") -> int:
    receipt = WebhookReceipt(
        channel_id=channel_id,
        provider="woocommerce",
        provider_event_id=provider_event_id,
        payload_hash=provider_event_id,
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


# ---------------------------------------------------------------------------
# enqueue_entity_work
# ---------------------------------------------------------------------------


def test_enqueue_creates_a_new_pending_row(db):
    work = enqueue_entity_work(
        db,
        connector_id="woocommerce:primary",
        entity_type="products",
        entity_id="57926",
        reason="WEBHOOK_PRODUCT_UPDATED",
        event_at=utcnow(),
    )

    assert work.status == "pending"
    assert work.attempt_count == 0
    assert db.query(DlChannelEntityWork).count() == 1


def test_enqueue_coalesces_newer_evidence_into_existing_pending_row(db):
    first_time = utcnow()
    first = enqueue_entity_work(
        db,
        connector_id="woocommerce:primary",
        entity_type="products",
        entity_id="57926",
        reason="WEBHOOK_PRODUCT_UPDATED",
        event_at=first_time,
        provider_event_id="wh:dl-1",
    )

    later_time = first_time + timedelta(seconds=30)
    second = enqueue_entity_work(
        db,
        connector_id="woocommerce:primary",
        entity_type="products",
        entity_id="57926",
        reason="OWNER_REQUESTED",
        event_at=later_time,
        provider_event_id="wh:dl-2",
    )

    assert second.id == first.id
    assert db.query(DlChannelEntityWork).count() == 1
    assert second.latest_event_at == later_time
    assert second.latest_reason == "OWNER_REQUESTED"
    assert second.latest_provider_event_id == "wh:dl-2"
    assert second.reason == "WEBHOOK_PRODUCT_UPDATED", "original reason (first cause) is preserved"


def test_enqueue_ignores_older_evidence_for_latest_event_fields(db):
    now = utcnow()
    enqueue_entity_work(
        db, connector_id="woocommerce:primary", entity_type="products", entity_id="57926",
        reason="WEBHOOK_PRODUCT_UPDATED", event_at=now,
    )
    stale = enqueue_entity_work(
        db, connector_id="woocommerce:primary", entity_type="products", entity_id="57926",
        reason="PERIODIC_RECONCILIATION", event_at=now - timedelta(seconds=30),
    )

    assert stale.latest_event_at == now
    assert stale.latest_reason == "WEBHOOK_PRODUCT_UPDATED"


def test_enqueue_marks_superseded_when_existing_row_is_running(db):
    work = enqueue_entity_work(
        db, connector_id="woocommerce:primary", entity_type="products", entity_id="57926",
        reason="WEBHOOK_PRODUCT_UPDATED", event_at=utcnow(),
    )
    claim_entity_work(db, worker_id="w1", limit=10, lease_seconds=120)
    db.refresh(work)
    assert work.status == "running"

    enqueue_entity_work(
        db, connector_id="woocommerce:primary", entity_type="products", entity_id="57926",
        reason="WEBHOOK_PRODUCT_UPDATED", event_at=utcnow() + timedelta(seconds=5),
    )

    db.refresh(work)
    assert work.superseded_at is not None


def test_enqueue_different_entities_create_independent_rows(db):
    enqueue_entity_work(
        db, connector_id="woocommerce:primary", entity_type="products", entity_id="1",
        reason="WEBHOOK_PRODUCT_UPDATED", event_at=utcnow(),
    )
    enqueue_entity_work(
        db, connector_id="woocommerce:primary", entity_type="products", entity_id="2",
        reason="WEBHOOK_PRODUCT_UPDATED", event_at=utcnow(),
    )

    assert db.query(DlChannelEntityWork).count() == 2


def test_enqueue_with_receipt_id_links_it_in_the_same_call(db):
    receipt_id = _receipt(db, "wh:dl-linked")

    work = enqueue_entity_work(
        db, connector_id="woocommerce:primary", entity_type="products", entity_id="57926",
        reason="WEBHOOK_PRODUCT_UPDATED", event_at=utcnow(), receipt_id=receipt_id,
    )

    link = db.query(DlChannelEntityWorkReceipt).filter_by(work_id=work.id, receipt_id=receipt_id).one()
    assert link is not None


# ---------------------------------------------------------------------------
# claim_entity_work
# ---------------------------------------------------------------------------


def test_claim_selects_only_pending_rows_and_sets_lease_fields(db):
    enqueue_entity_work(
        db, connector_id="woocommerce:primary", entity_type="products", entity_id="1",
        reason="WEBHOOK_PRODUCT_UPDATED", event_at=utcnow(),
    )

    claimed = claim_entity_work(db, worker_id="worker-1", limit=10, lease_seconds=60)

    assert len(claimed) == 1
    work = claimed[0]
    assert work.status == "running"
    assert work.worker_id == "worker-1"
    assert work.attempt_count == 1
    assert work.lease_expires_at is not None
    assert work.lease_expires_at > utcnow()


def test_claim_respects_limit(db):
    for i in range(5):
        enqueue_entity_work(
            db, connector_id="woocommerce:primary", entity_type="products", entity_id=str(i),
            reason="WEBHOOK_PRODUCT_UPDATED", event_at=utcnow(),
        )

    claimed = claim_entity_work(db, worker_id="worker-1", limit=2, lease_seconds=60)

    assert len(claimed) == 2
    assert db.query(DlChannelEntityWork).filter_by(status="pending").count() == 3


def test_claim_skips_rows_with_future_next_attempt_at(db):
    work = enqueue_entity_work(
        db, connector_id="woocommerce:primary", entity_type="products", entity_id="1",
        reason="WEBHOOK_PRODUCT_UPDATED", event_at=utcnow(),
    )
    work.next_attempt_at = utcnow() + timedelta(minutes=5)
    db.commit()

    claimed = claim_entity_work(db, worker_id="worker-1", limit=10, lease_seconds=60)

    assert claimed == []


def test_claim_does_not_reclaim_a_running_row(db):
    enqueue_entity_work(
        db, connector_id="woocommerce:primary", entity_type="products", entity_id="1",
        reason="WEBHOOK_PRODUCT_UPDATED", event_at=utcnow(),
    )
    first = claim_entity_work(db, worker_id="worker-1", limit=10, lease_seconds=60)
    assert len(first) == 1

    second = claim_entity_work(db, worker_id="worker-2", limit=10, lease_seconds=60)
    assert second == []


# ---------------------------------------------------------------------------
# complete_entity_work
# ---------------------------------------------------------------------------


def test_complete_success_marks_terminal_and_flips_receipts(db):
    receipt_id = _receipt(db, "wh:dl-1")
    work = enqueue_entity_work(
        db, connector_id="woocommerce:primary", entity_type="products", entity_id="57926",
        reason="WEBHOOK_PRODUCT_UPDATED", event_at=utcnow(), receipt_id=receipt_id,
    )
    claim_entity_work(db, worker_id="worker-1", limit=10, lease_seconds=60)
    db.refresh(work)

    result = complete_entity_work(db, work, outcome="completed")

    assert result.status == "completed"
    assert result.completed_at is not None
    receipt = db.get(WebhookReceipt, receipt_id)
    assert receipt.processing_state == "processed"


def test_complete_failure_below_max_attempts_requeues_with_backoff(db):
    work = enqueue_entity_work(
        db, connector_id="woocommerce:primary", entity_type="products", entity_id="57926",
        reason="WEBHOOK_PRODUCT_UPDATED", event_at=utcnow(),
    )
    claim_entity_work(db, worker_id="worker-1", limit=10, lease_seconds=60)
    db.refresh(work)
    assert work.attempt_count == 1

    result = complete_entity_work(db, work, outcome="failed", error_category="timeout", error_message="slow")

    assert result.status == "pending"
    assert result.next_attempt_at is not None
    assert result.next_attempt_at > utcnow()
    assert result.error_category == "timeout"


def test_complete_failure_permanent_category_dead_letters_immediately(db):
    """A permanent category (not in TRANSIENT_ERRORS) must not retry even
    on the very first attempt."""
    work = enqueue_entity_work(
        db, connector_id="woocommerce:primary", entity_type="products", entity_id="57926",
        reason="WEBHOOK_PRODUCT_UPDATED", event_at=utcnow(),
    )
    claim_entity_work(db, worker_id="worker-1", limit=10, lease_seconds=60)
    db.refresh(work)

    result = complete_entity_work(db, work, outcome="failed", error_category="auth_failed", error_message="bad key")

    assert result.status == "failed"
    assert result.failed_at is not None


def test_complete_failure_at_max_attempts_dead_letters_even_if_transient(db):
    work = enqueue_entity_work(
        db, connector_id="woocommerce:primary", entity_type="products", entity_id="57926",
        reason="WEBHOOK_PRODUCT_UPDATED", event_at=utcnow(),
    )
    work.max_attempts = 1
    db.commit()
    claim_entity_work(db, worker_id="worker-1", limit=10, lease_seconds=60)
    db.refresh(work)
    assert work.attempt_count == 1

    result = complete_entity_work(db, work, outcome="failed", error_category="timeout", error_message="slow")

    assert result.status == "failed", "transient category must still dead-letter once attempts are exhausted"


def test_complete_superseded_success_requeues_instead_of_finishing(db):
    work = enqueue_entity_work(
        db, connector_id="woocommerce:primary", entity_type="products", entity_id="57926",
        reason="WEBHOOK_PRODUCT_UPDATED", event_at=utcnow(),
    )
    claim_entity_work(db, worker_id="worker-1", limit=10, lease_seconds=60)
    db.refresh(work)
    enqueue_entity_work(
        db, connector_id="woocommerce:primary", entity_type="products", entity_id="57926",
        reason="WEBHOOK_PRODUCT_UPDATED", event_at=utcnow() + timedelta(seconds=5),
    )
    db.refresh(work)
    assert work.superseded_at is not None

    result = complete_entity_work(db, work, outcome="completed")

    assert result.status == "pending"
    assert result.completed_at is None


def test_complete_repeated_call_on_already_completed_row_is_a_safe_no_op(db):
    """A crash-then-retry replay must not corrupt or double-mutate state."""
    receipt_id = _receipt(db, "wh:dl-replay")
    work = enqueue_entity_work(
        db, connector_id="woocommerce:primary", entity_type="products", entity_id="57926",
        reason="WEBHOOK_PRODUCT_UPDATED", event_at=utcnow(), receipt_id=receipt_id,
    )
    claim_entity_work(db, worker_id="worker-1", limit=10, lease_seconds=60)
    db.refresh(work)

    complete_entity_work(db, work, outcome="completed")
    db.refresh(work)
    result = complete_entity_work(db, work, outcome="completed")

    assert result.status == "completed"
    receipt = db.get(WebhookReceipt, receipt_id)
    assert receipt.processing_state == "processed"
    assert db.query(DlChannelEntityWorkReceipt).filter_by(work_id=work.id).count() == 1


# ---------------------------------------------------------------------------
# recover_expired_entity_work
# ---------------------------------------------------------------------------


def test_recover_resets_a_stale_claim_with_attempts_remaining(db):
    work = enqueue_entity_work(
        db, connector_id="woocommerce:primary", entity_type="products", entity_id="57926",
        reason="WEBHOOK_PRODUCT_UPDATED", event_at=utcnow(),
    )
    claim_entity_work(db, worker_id="dead-worker", limit=10, lease_seconds=60)
    db.refresh(work)
    work.lease_expires_at = utcnow() - timedelta(seconds=1)
    db.commit()

    recovered = recover_expired_entity_work(db)

    assert [item.id for item in recovered] == [work.id]
    db.refresh(work)
    assert work.status == "pending"
    assert work.worker_id is None


def test_recover_dead_letters_and_flips_receipts_once_attempts_exhausted(db):
    receipt_id = _receipt(db, "wh:dl-exhausted")
    work = enqueue_entity_work(
        db, connector_id="woocommerce:primary", entity_type="products", entity_id="57926",
        reason="WEBHOOK_PRODUCT_UPDATED", event_at=utcnow(), receipt_id=receipt_id,
    )
    work.max_attempts = 1
    db.commit()
    claim_entity_work(db, worker_id="dead-worker", limit=10, lease_seconds=60)
    db.refresh(work)
    work.lease_expires_at = utcnow() - timedelta(seconds=1)
    db.commit()

    recover_expired_entity_work(db)

    db.refresh(work)
    assert work.status == "failed"
    assert work.error_category == "execution_lease_expired"
    receipt = db.get(WebhookReceipt, receipt_id)
    assert receipt.processing_state in {"retry_scheduled", "dead_letter"}


def test_recover_leaves_a_healthy_lease_untouched(db):
    work = enqueue_entity_work(
        db, connector_id="woocommerce:primary", entity_type="products", entity_id="57926",
        reason="WEBHOOK_PRODUCT_UPDATED", event_at=utcnow(),
    )
    claim_entity_work(db, worker_id="alive-worker", limit=10, lease_seconds=600)

    recovered = recover_expired_entity_work(db)

    assert recovered == []
    db.refresh(work)
    assert work.status == "running"


# ---------------------------------------------------------------------------
# flip_linked_receipts
# ---------------------------------------------------------------------------


def test_flip_linked_receipts_only_touches_this_work_items_receipts(db):
    receipt_a = _receipt(db, "wh:dl-a")
    receipt_b = _receipt(db, "wh:dl-b")
    work_a = enqueue_entity_work(
        db, connector_id="woocommerce:primary", entity_type="products", entity_id="1",
        reason="WEBHOOK_PRODUCT_UPDATED", event_at=utcnow(), receipt_id=receipt_a,
    )
    enqueue_entity_work(
        db, connector_id="woocommerce:primary", entity_type="products", entity_id="2",
        reason="WEBHOOK_PRODUCT_UPDATED", event_at=utcnow(), receipt_id=receipt_b,
    )

    count = flip_linked_receipts(db, work_a, outcome="completed", error_category=None, error_message=None)

    assert count == 1
    assert db.get(WebhookReceipt, receipt_a).processing_state == "processed"
    assert db.get(WebhookReceipt, receipt_b).processing_state == "queued"


def test_flip_linked_receipts_returns_zero_for_a_work_item_with_no_receipts(db):
    work = enqueue_entity_work(
        db, connector_id="woocommerce:primary", entity_type="products", entity_id="1",
        reason="OWNER_REQUESTED", event_at=utcnow(),
    )

    assert flip_linked_receipts(db, work, outcome="completed", error_category=None, error_message=None) == 0


# ---------------------------------------------------------------------------
# sync_pending_woocommerce_receipts
# ---------------------------------------------------------------------------


def test_sync_links_a_pending_receipt_to_a_new_work_item(db):
    _receipt(db, "wh:dl-1", wc_product_id="57926")

    linked = sync_pending_woocommerce_receipts(db, "woocommerce:primary")

    assert linked == 1
    work = db.query(DlChannelEntityWork).filter_by(entity_id="57926").one()
    assert work.status == "pending"
    assert work.reason == "WEBHOOK_PRODUCT_UPDATED"


def test_sync_ignores_receipts_for_other_channels(db):
    _receipt(db, "wh:dl-1", wc_product_id="57926", channel_id="woocommerce:other")

    linked = sync_pending_woocommerce_receipts(db, "woocommerce:primary")

    assert linked == 0
    assert db.query(DlChannelEntityWork).count() == 0


def test_sync_dead_letters_a_receipt_with_no_resolvable_product_id(db):
    receipt_id = _receipt(db, "wh:dl-bad", wc_product_id=None)

    linked = sync_pending_woocommerce_receipts(db, "woocommerce:primary")

    assert linked == 0
    receipt = db.get(WebhookReceipt, receipt_id)
    assert receipt.processing_state == "dead_letter", "must not be silently orphaned forever"
    assert db.query(DlChannelEntityWork).count() == 0


def test_sync_does_not_relink_a_receipt_already_covered_by_active_work(db):
    _receipt(db, "wh:dl-1", wc_product_id="57926")
    first_pass = sync_pending_woocommerce_receipts(db, "woocommerce:primary")
    assert first_pass == 1

    second_pass = sync_pending_woocommerce_receipts(db, "woocommerce:primary")

    assert second_pass == 0
    assert db.query(DlChannelEntityWork).count() == 1


def test_sync_relinks_a_receipt_whose_prior_work_item_is_terminal(db):
    """A receipt that still has its own retry budget must not be stranded
    behind an already-terminal (failed/completed) work item forever."""
    _receipt(db, "wh:dl-1", wc_product_id="57926")
    sync_pending_woocommerce_receipts(db, "woocommerce:primary")
    work = db.query(DlChannelEntityWork).filter_by(entity_id="57926").one()
    claim_entity_work(db, worker_id="worker-1", limit=10, lease_seconds=60)
    db.refresh(work)
    complete_entity_work(
        db, work, outcome="failed", error_category="internal_error", error_message="boom"
    )  # permanent category -> terminal on first attempt
    db.refresh(work)
    assert work.status == "failed"

    receipt = db.query(WebhookReceipt).filter_by(provider_event_id="wh:dl-1").one()
    receipt.processing_state = "retry_scheduled"
    receipt.next_attempt_at = None
    db.commit()

    linked = sync_pending_woocommerce_receipts(db, "woocommerce:primary")

    assert linked == 1
    assert db.query(DlChannelEntityWork).filter_by(entity_id="57926").count() == 2
