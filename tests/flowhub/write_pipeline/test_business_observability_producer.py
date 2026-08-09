"""Write Pipeline -> Business Observability producer wiring (Business Observability v1, Phase 1)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.business_observability.models import BusinessEvent
from app.flowhub.database import FlowHubBase
from app.flowhub.write_pipeline.models import WriteBatch
from app.flowhub.write_pipeline.service import WritePipelineService


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    FlowHubBase.metadata.create_all(engine)
    return Session(engine)


def _batch(status: str) -> WriteBatch:
    return WriteBatch(
        id="batch-1",
        channel_id="woocommerce:primary",
        channel_type="woocommerce",
        operation_type="price_update",
        status=status,
        batch_hash="hash",
        item_count=5,
        currency="EUR",
    )


@pytest.mark.parametrize(
    ("status", "expected_event_type", "expected_severity", "expected_impact", "expected_retryable"),
    [
        ("applied", "write_batch_applied", "info", "none", False),
        (
            "reconciliation_required",
            "write_batch_reconciliation_required",
            "warning",
            "blocking",
            True,
        ),
        ("partially_failed", "write_batch_partially_failed", "error", "partial_failure", True),
        ("failed", "write_batch_failed", "critical", "critical_business_failure", True),
    ],
)
def test_batch_completion_emits_mapped_business_event(
    status, expected_event_type, expected_severity, expected_impact, expected_retryable
) -> None:
    db = _session()
    service = WritePipelineService(db)
    batch = _batch(status)

    service._emit_batch_business_event(
        batch, success_count=3, failure_count=1, reconciliation_count=1, correlation_id="corr-xyz"
    )
    db.commit()

    rows = db.query(BusinessEvent).all()
    assert len(rows) == 1
    event = rows[0]
    assert event.domain == "write_pipeline"
    assert event.event_type == expected_event_type
    assert event.severity == expected_severity
    assert event.business_impact == expected_impact
    assert event.retryable is expected_retryable
    assert event.primary_scope_type == "batch"
    assert event.primary_scope_id == "batch-1"
    assert event.secondary_scopes_json == [
        {"scope_type": "channel", "scope_id": "woocommerce:primary", "scope_label": "woocommerce"}
    ]
    assert event.correlation_id == "corr-xyz"
    assert event.reason_code == status


def test_dry_run_rejection_emits_business_event() -> None:
    db = _session()
    user = FlowHubUser(id=1, username="alice", hashed_password="x", role="operator", is_active=True)
    db.add(user)
    db.commit()

    service = WritePipelineService(db)
    service._record_preview_rejection("preview-1", ["row-1", "row-2"], user, "automatic_apply_disabled")

    rows = db.query(BusinessEvent).filter(BusinessEvent.domain == "write_pipeline").all()
    assert len(rows) == 1
    event = rows[0]
    assert event.event_type == "write_dry_run_rejected"
    assert event.severity == "warning"
    assert event.business_impact == "blocking"
    assert event.reason_code == "automatic_apply_disabled"
    assert event.primary_scope_type == "batch"
    assert event.primary_scope_id == "preview-1"
    assert event.retryable is True
