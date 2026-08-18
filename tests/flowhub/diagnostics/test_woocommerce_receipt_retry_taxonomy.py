"""Webhook-receipt outcomes must follow the real failure category.

Production regression (2026-08-18): 13 `product.updated` receipts for
`woocommerce:primary` dead-lettered with `attempt_count: 5` and
`error_category: "temporary"`, in batches exactly 30s apart -- the order-sync
runner's `loop_interval_seconds` default. The store was healthy (its `/orders`
endpoint answered 200 OK throughout).

Two defects combined to produce that:

  1. `ScheduledDiagnosticsEvaluator._sync_products` hardcoded
     `error_category="temporary"` for *every* refresh failure, so retryability
     never reflected the actual cause.
  2. A refresh that was never executed -- because FlowHub's own single-flight
     lease was still held by another (possibly already-dead) job -- was
     reported as a failed refresh, burning one of each receipt's five attempts
     on every 30s tick. Five ticks = ~2.5 minutes to dead-letter a batch of
     perfectly good deliveries.

These tests pin both fixes.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("FLOWHUB_DATABASE_URL", "sqlite:///:memory:")

from app.flowhub.auth import models as _auth_models  # noqa: F401
from app.flowhub.business_observability import models as _bo_models  # noqa: F401
from app.flowhub.commerce.service import CommerceHubService
from app.flowhub.data_layer import models as _data_layer_models  # noqa: F401
from app.flowhub.database import FlowHubBase
from app.flowhub.diagnostics.scheduling import ScheduledDiagnosticsEvaluator
from app.flowhub.integration_platform import models as _integration_models  # noqa: F401
from app.flowhub.integration_platform.models import (
    IntegrationConnectorInstance,
    IntegrationConnectorSetting,
)
from app.flowhub.orders import models as _order_models  # noqa: F401
from app.flowhub.security.upstream_errors import (
    CATEGORY_AUTH_FAILED,
    CATEGORY_INTERNAL_ERROR,
    CATEGORY_REFRESH_IN_PROGRESS,
    CATEGORY_UPSTREAM_UNAVAILABLE,
)
from app.flowhub.source_acquisition import models as _acquisition_models  # noqa: F401
from app.flowhub.source_workspace import models as _source_models  # noqa: F401
from app.flowhub.unified_workspace import models as _unified_models  # noqa: F401
from app.flowhub.webhooks import models as _webhook_models  # noqa: F401
from app.flowhub.webhooks.models import WebhookDeadLetter, WebhookReceipt

CHANNEL = "woocommerce:primary"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    FlowHubBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    try:
        yield factory
    finally:
        FlowHubBase.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture(autouse=True)
def clean_product_policy(monkeypatch):
    monkeypatch.delenv("FLOWHUB_WOOCOMMERCE_PRODUCT_SYNC_ENABLED", raising=False)
    monkeypatch.delenv("FLOWHUB_WOOCOMMERCE_PRODUCT_SYNC_INTERVAL_SECONDS", raising=False)


def _seed_channel_with_queued_receipts(session_factory, count: int) -> list[int]:
    now = _now()
    receipt_ids: list[int] = []
    with session_factory() as db:
        db.add(
            IntegrationConnectorInstance(
                id=CHANNEL,
                connector_type="woocommerce",
                name="WooCommerce",
                version="1.0.0",
                enabled=True,
                read_only=True,
                status="configured",
                created_at=now,
                updated_at=now,
            )
        )
        for key in ("url", "key", "secret"):
            db.add(
                IntegrationConnectorSetting(
                    connector_id=CHANNEL,
                    key=key,
                    value_json="configured" if key == "url" else None,
                    secret=key in {"key", "secret"},
                    configured=True,
                    updated_at=now,
                )
            )
        for index in range(count):
            receipt = WebhookReceipt(
                channel_id=CHANNEL,
                provider="woocommerce",
                provider_event_id=f"wh-1:dl-{index}",
                payload_hash=f"hash-{index}",
                payload_summary_json={"topic": "product.updated"},
                normalized_event_json={"topic": "product.updated", "wc_product_id": str(55700 + index)},
                received_at=now,
                acknowledged_at=now,
                processing_state="queued",
                attempt_count=0,
                retention_until=now + timedelta(days=90),
            )
            db.add(receipt)
            db.flush()
            receipt_ids.append(receipt.id)
        db.commit()
    return receipt_ids


def _refresh_result(status: str, *, error: dict | None = None, deferred: bool = False) -> dict:
    result: dict = {"ok": status.startswith("completed"), "status": status}
    if error is not None:
        result["error"] = error
    if deferred:
        result["deferred"] = True
    return result


def _patch_refresh(monkeypatch, result: dict) -> list[str]:
    calls: list[str] = []

    async def fake_refresh(self, channel_id, actor, **kwargs):
        calls.append(channel_id)
        return result

    monkeypatch.setattr(CommerceHubService, "refresh_channel_cache", fake_refresh)
    return calls


def _receipt_states(session_factory, receipt_ids):
    with session_factory() as db:
        return [
            (row.processing_state, row.attempt_count, row.last_error_category)
            for row in (db.get(WebhookReceipt, rid) for rid in receipt_ids)
        ]


@pytest.mark.asyncio
async def test_deferred_refresh_leaves_receipts_queued_without_burning_attempts(
    session_factory, monkeypatch
):
    """The exact production death spiral, pinned.

    A lease conflict means the refresh never ran. The receipts must be left
    untouched for the next tick -- not charged an attempt.
    """

    receipt_ids = _seed_channel_with_queued_receipts(session_factory, 4)
    _patch_refresh(
        monkeypatch,
        _refresh_result(
            "deferred",
            deferred=True,
            error={
                "code": "CHANNEL_REFRESH_IN_PROGRESS",
                "message": "A product cache refresh is already running for this channel.",
                "category": CATEGORY_REFRESH_IN_PROGRESS,
                "upstream_attributable": False,
                "http_status": None,
                "source": "flowhub",
            },
        ),
    )

    # Five consecutive ticks -- the number that dead-lettered every receipt in
    # production (MAX_PROCESSING_ATTEMPTS).
    for _ in range(5):
        await ScheduledDiagnosticsEvaluator(session_factory).run_once()

    assert _receipt_states(session_factory, receipt_ids) == [("queued", 0, None)] * 4
    with session_factory() as db:
        assert db.query(WebhookDeadLetter).count() == 0


@pytest.mark.asyncio
async def test_genuine_upstream_failure_is_retryable_and_categorized_honestly(
    session_factory, monkeypatch
):
    receipt_ids = _seed_channel_with_queued_receipts(session_factory, 1)
    _patch_refresh(
        monkeypatch,
        _refresh_result(
            "failed",
            error={
                "code": "CHANNEL_UPSTREAM_ERROR",
                "message": "The external service returned an invalid or unavailable response.",
                "category": CATEGORY_UPSTREAM_UNAVAILABLE,
                "upstream_attributable": True,
                "http_status": 522,
                "source": "woocommerce",
            },
        ),
    )

    await ScheduledDiagnosticsEvaluator(session_factory).run_once()

    state, attempts, category = _receipt_states(session_factory, receipt_ids)[0]
    assert state == "retry_scheduled"
    assert attempts == 1
    # No longer the blanket "temporary".
    assert category == CATEGORY_UPSTREAM_UNAVAILABLE


@pytest.mark.asyncio
async def test_auth_failure_dead_letters_immediately_instead_of_retrying_five_times(
    session_factory, monkeypatch
):
    """An expired credential is not a transient blip.

    Under the old hardcoded "temporary" it burned all five attempts and then
    dead-lettered with a message that blamed the network.
    """

    receipt_ids = _seed_channel_with_queued_receipts(session_factory, 1)
    _patch_refresh(
        monkeypatch,
        _refresh_result(
            "failed",
            error={
                "code": "CHANNEL_AUTH_FAILED",
                "message": "Authentication failed.",
                "category": CATEGORY_AUTH_FAILED,
                "upstream_attributable": True,
                "http_status": 401,
                "source": "woocommerce",
            },
        ),
    )

    await ScheduledDiagnosticsEvaluator(session_factory).run_once()

    state, attempts, category = _receipt_states(session_factory, receipt_ids)[0]
    assert state == "dead_letter"
    assert attempts == 1
    assert category == CATEGORY_AUTH_FAILED
    with session_factory() as db:
        dead = db.query(WebhookDeadLetter).one()
        assert dead.error_category == CATEGORY_AUTH_FAILED


@pytest.mark.asyncio
async def test_internal_failure_is_not_retried_as_if_upstream_were_broken(
    session_factory, monkeypatch
):
    receipt_ids = _seed_channel_with_queued_receipts(session_factory, 1)
    _patch_refresh(
        monkeypatch,
        _refresh_result(
            "failed",
            error={
                "code": "CHANNEL_INTERNAL_ERROR",
                "message": "An internal error prevented this operation from completing.",
                "category": CATEGORY_INTERNAL_ERROR,
                "upstream_attributable": False,
                "http_status": None,
                "source": "flowhub",
            },
        ),
    )

    await ScheduledDiagnosticsEvaluator(session_factory).run_once()

    state, attempts, category = _receipt_states(session_factory, receipt_ids)[0]
    assert state == "dead_letter"
    assert attempts == 1
    assert category == CATEGORY_INTERNAL_ERROR


@pytest.mark.asyncio
async def test_successful_refresh_processes_every_queued_receipt(
    session_factory, monkeypatch
):
    receipt_ids = _seed_channel_with_queued_receipts(session_factory, 3)
    _patch_refresh(monkeypatch, _refresh_result("completed"))

    await ScheduledDiagnosticsEvaluator(session_factory).run_once()

    assert all(
        state == "processed" for state, _attempts, _category in _receipt_states(session_factory, receipt_ids)
    )
    with session_factory() as db:
        assert db.query(WebhookDeadLetter).count() == 0
