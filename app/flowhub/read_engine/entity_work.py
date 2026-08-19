"""Per-entity Channel Read work queue: coalesce, claim, complete, recover.

Independent lease scope from DlRefreshJob/RefreshJobLifecycle -- see
ADR_CHANNEL_READ_ARCHITECTURE.md. Webhook receipts are never the claimable
unit; dl_channel_entity_work is. A join table links receipts to whichever
work execution covers them, and every linked receipt transitions atomically
through the *existing* WebhookIngestionService state machine when that
execution reaches a terminal outcome -- no second receipt subsystem.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.flowhub.data_layer.job_lifecycle import utcnow
from app.flowhub.data_layer.models import DlChannelEntityWork, DlChannelEntityWorkReceipt
from app.flowhub.security.redaction import redact_sensitive
from app.flowhub.webhooks.service import TRANSIENT_ERRORS

DEFAULT_MAX_ATTEMPTS = 5  # matches webhooks/service.py MAX_PROCESSING_ATTEMPTS


def enqueue_entity_work(
    db: Session,
    *,
    connector_id: str,
    entity_type: str,
    entity_id: str,
    reason: str,
    event_at: datetime,
    parent_entity_id: str | None = None,
    provider_event_id: str | None = None,
    receipt_id: int | None = None,
    strategy: str = "LIGHT",
    now: datetime | None = None,
) -> DlChannelEntityWork:
    """Idempotent create-or-coalesce, optionally linking one webhook receipt
    to the resulting execution in the same commit.

    Always attempts INSERT first (this codebase's established idiom -- see
    WebhookIngestionService.accept_woocommerce_event), falling back to
    locating and merging into the existing active row on the partial
    unique index conflict (one active row per connector/entity_type/entity_id).
    New evidence for a `pending` row coalesces in place; new evidence for a
    `running` row sets `superseded_at`, which requeues it on completion
    instead of finishing it -- the newest observation always wins.
    """
    now = now or utcnow()
    work = DlChannelEntityWork(
        connector_id=connector_id,
        entity_type=entity_type,
        entity_id=entity_id,
        parent_entity_id=parent_entity_id,
        status="pending",
        strategy=strategy,
        reason=reason,
        latest_reason=reason,
        latest_event_at=event_at,
        latest_provider_event_id=provider_event_id,
        attempt_count=0,
        max_attempts=DEFAULT_MAX_ATTEMPTS,
        created_at=now,
        updated_at=now,
    )
    db.add(work)
    try:
        db.flush()
        if receipt_id is not None:
            _link_receipt(db, work_id=work.id, receipt_id=receipt_id, now=now)
        db.commit()
        db.refresh(work)
        return work
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(DlChannelEntityWork)
            .filter(
                DlChannelEntityWork.connector_id == connector_id,
                DlChannelEntityWork.entity_type == entity_type,
                DlChannelEntityWork.entity_id == entity_id,
                DlChannelEntityWork.status.in_(("pending", "running")),
            )
            .with_for_update()
            .one_or_none()
        )
        if existing is None:
            raise
        if event_at >= existing.latest_event_at:
            existing.latest_event_at = event_at
            existing.latest_reason = reason
            if provider_event_id is not None:
                existing.latest_provider_event_id = provider_event_id
        if existing.status == "running":
            existing.superseded_at = now
        existing.updated_at = now
        if receipt_id is not None:
            _link_receipt(db, work_id=existing.id, receipt_id=receipt_id, now=now)
        db.commit()
        db.refresh(existing)
        return existing


def _link_receipt(db: Session, *, work_id: int, receipt_id: int, now: datetime) -> None:
    exists = db.query(DlChannelEntityWorkReceipt).filter_by(work_id=work_id, receipt_id=receipt_id).first()
    if exists is None:
        db.add(DlChannelEntityWorkReceipt(work_id=work_id, receipt_id=receipt_id, linked_at=now))


def claim_entity_work(
    db: Session,
    *,
    worker_id: str,
    limit: int,
    lease_seconds: int,
    now: datetime | None = None,
) -> list[DlChannelEntityWork]:
    """Claim up to `limit` due, pending work items via FOR UPDATE SKIP
    LOCKED so multiple workers process independent entities concurrently
    without blocking on each other (no-op lock on SQLite; correct on
    PostgreSQL, which is what the concurrency tests exercise)."""
    now = now or utcnow()
    candidates = (
        db.query(DlChannelEntityWork)
        .filter(
            DlChannelEntityWork.status == "pending",
            (DlChannelEntityWork.next_attempt_at.is_(None)) | (DlChannelEntityWork.next_attempt_at <= now),
        )
        .order_by(DlChannelEntityWork.latest_event_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
        .all()
    )
    for work in candidates:
        work.status = "running"
        work.worker_id = worker_id
        work.started_at = work.started_at or now
        work.heartbeat_at = now
        work.lease_expires_at = now + timedelta(seconds=lease_seconds)
        work.attempt_count += 1
        work.superseded_at = None
        work.updated_at = now
    if candidates:
        db.commit()
        for work in candidates:
            db.refresh(work)
    return candidates


def complete_entity_work(
    db: Session,
    work: DlChannelEntityWork,
    *,
    outcome: str,
    error_category: str | None = None,
    error_message: str | None = None,
    now: datetime | None = None,
) -> DlChannelEntityWork:
    """Terminal transition for a claimed work item. `work` must be a plain
    row loaded in the caller's own session (not still under a batch FOR
    UPDATE lock) -- receipts are flipped before the row's own terminal
    commit so a mid-flight crash leaves the row `running` (lease-expiry
    recoverable, and re-flipping an already-processed receipt is a safe
    no-op) rather than stranding a receipt behind an already-terminal row.
    """
    now = now or utcnow()
    if outcome == "completed":
        if work.superseded_at is not None and (work.started_at is None or work.superseded_at > work.started_at):
            # Fresher evidence arrived mid-flight: this observation is
            # already stale. Requeue instead of finishing; receipts stay
            # linked to this same row for the next execution.
            work.status = "pending"
            work.lease_expires_at = None
            work.worker_id = None
            work.next_attempt_at = None
            work.updated_at = now
            db.commit()
            db.refresh(work)
            return work
        flip_linked_receipts(db, work, outcome="completed", error_category=None, error_message=None)
        work.status = "completed"
        work.completed_at = now
        work.lease_expires_at = None
        work.error_message = None
        work.error_category = None
        work.updated_at = now
        db.commit()
        db.refresh(work)
        return work

    retryable = error_category in TRANSIENT_ERRORS and work.attempt_count < work.max_attempts
    if retryable:
        work.status = "pending"
        work.lease_expires_at = None
        work.worker_id = None
        work.next_attempt_at = now + _backoff(work.attempt_count)
        work.error_message = _safe_error(error_message or error_category or "unknown")
        work.error_category = error_category
        work.updated_at = now
        db.commit()
        db.refresh(work)
        return work

    flip_linked_receipts(db, work, outcome="failed", error_category=error_category, error_message=error_message)
    work.status = "failed"
    work.failed_at = now
    work.lease_expires_at = None
    work.error_message = _safe_error(error_message or error_category or "unknown")
    work.error_category = error_category
    work.updated_at = now
    db.commit()
    db.refresh(work)
    return work


def recover_expired_entity_work(db: Session, *, limit: int = 200, now: datetime | None = None) -> list[DlChannelEntityWork]:
    """Mirrors RefreshJobLifecycle.recover_expired() for this table. Unlike
    a channel-wide FULL job, a dead single-entity claim is cheap to just
    retry: bounded scan of running rows past their lease, reset to pending
    if attempts remain, else terminal failed. All row updates in the
    locked batch commit together first (matching RefreshJobLifecycle's
    single-commit pattern, so FOR UPDATE is never released early on a
    still-pending sibling); receipts for newly-terminal rows are flipped
    only after that commit, once the batch lock is already released."""
    now = now or utcnow()
    candidates = (
        db.query(DlChannelEntityWork)
        .filter(DlChannelEntityWork.status == "running")
        .order_by(DlChannelEntityWork.started_at.asc(), DlChannelEntityWork.id.asc())
        .limit(limit)
        .with_for_update()
        .all()
    )
    expired = [work for work in candidates if work.lease_expires_at is not None and work.lease_expires_at < now]
    terminal: list[DlChannelEntityWork] = []
    for work in expired:
        if work.attempt_count < work.max_attempts:
            work.status = "pending"
            work.worker_id = None
            work.lease_expires_at = None
            work.next_attempt_at = None
        else:
            work.status = "failed"
            work.failed_at = now
            work.lease_expires_at = None
            work.error_category = "execution_lease_expired"
            work.error_message = "Completion was not durably recorded before the execution lease expired."
            terminal.append(work)
        work.updated_at = now
    if expired:
        db.commit()
        for work in expired:
            db.refresh(work)
    for work in terminal:
        flip_linked_receipts(
            db, work, outcome="failed", error_category=work.error_category, error_message=work.error_message
        )
    return expired


def flip_linked_receipts(
    db: Session,
    work: DlChannelEntityWork,
    *,
    outcome: str,
    error_category: str | None,
    error_message: str | None,
) -> int:
    """Transition every receipt linked to this work item through the
    *existing* webhook receipt state machine. The only new caller of
    WebhookIngestionService.mark_woocommerce_receipt_processed/_failed --
    webhook_receipts.processing_state semantics are otherwise untouched."""
    from app.flowhub.webhooks.service import WebhookIngestionService

    receipt_ids = [row.receipt_id for row in db.query(DlChannelEntityWorkReceipt).filter_by(work_id=work.id).all()]
    if not receipt_ids:
        return 0
    service = WebhookIngestionService(db)
    for receipt_id in receipt_ids:
        if outcome == "completed":
            service.mark_woocommerce_receipt_processed(receipt_id)
        else:
            service.mark_woocommerce_receipt_failed(
                receipt_id, error_category or "internal_error", error_message or "targeted read failed"
            )
    return len(receipt_ids)


def sync_pending_woocommerce_receipts(db: Session, connector_id: str, *, limit: int = 200) -> int:
    """Link due, not-currently-covered WooCommerce webhook receipts to
    entity work. A receipt whose payload carries no resolvable product id
    is dead-lettered immediately rather than left orphaned forever. A
    receipt is "covered" only while its linked work item is still
    pending/running -- once that work item reaches a terminal outcome, a
    receipt that still has its own retry budget (flip_linked_receipts ->
    mark_woocommerce_receipt_failed may itself schedule a receipt retry)
    is eligible to start a fresh work item rather than being stranded
    behind an already-terminal row."""
    from app.flowhub.webhooks.models import WebhookReceipt
    from app.flowhub.webhooks.service import WebhookIngestionService

    now = utcnow()
    actively_covered = (
        db.query(DlChannelEntityWorkReceipt.receipt_id)
        .join(DlChannelEntityWork, DlChannelEntityWork.id == DlChannelEntityWorkReceipt.work_id)
        .filter(DlChannelEntityWork.status.in_(("pending", "running")))
    )
    rows = (
        db.query(WebhookReceipt)
        .filter(
            WebhookReceipt.channel_id == connector_id,
            WebhookReceipt.provider == "woocommerce",
            WebhookReceipt.processing_state.in_(("queued", "retry_scheduled")),
            WebhookReceipt.id.notin_(actively_covered),
        )
        .filter((WebhookReceipt.next_attempt_at.is_(None)) | (WebhookReceipt.next_attempt_at <= now))
        .order_by(WebhookReceipt.received_at.asc(), WebhookReceipt.id.asc())
        .limit(limit)
        .all()
    )
    linked = 0
    for receipt in rows:
        wc_product_id = (receipt.normalized_event_json or {}).get("wc_product_id")
        if not wc_product_id:
            WebhookIngestionService(db).mark_woocommerce_receipt_failed(
                receipt.id, "malformed_payload", "WooCommerce webhook payload carried no resolvable product id."
            )
            continue
        enqueue_entity_work(
            db,
            connector_id=connector_id,
            entity_type="products",
            entity_id=str(wc_product_id),
            reason="WEBHOOK_PRODUCT_UPDATED",
            event_at=receipt.received_at,
            provider_event_id=receipt.provider_event_id,
            receipt_id=receipt.id,
        )
        linked += 1
    return linked


def _backoff(attempt_no: int) -> timedelta:
    # Deliberately the same shape as webhooks/service.py's _backoff().
    return timedelta(seconds=min(300, 2 ** max(0, attempt_no - 1)))


def _safe_error(value: str) -> str:
    return str(redact_sensitive({"error": value})["error"])[:500]
