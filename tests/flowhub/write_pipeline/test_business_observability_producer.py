"""Write Pipeline -> Business Observability producer wiring (Business Observability v1)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.business_observability.models import BusinessEvent
from app.flowhub.database import FlowHubBase
from app.flowhub.pricing_authority.contracts import PricingAuthority, PricingOrigin
from app.flowhub.write_pipeline.models import WriteBatch, WriteItem
from app.flowhub.write_pipeline.service import WritePipelineService
from app.flowhub.write_pipeline.workspace_contracts import WorkspaceWriteIntent, WorkspaceWriteResult, WriteOutcome


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


def _intent(**overrides: object) -> WorkspaceWriteIntent:
    defaults: dict[str, object] = dict(
        apply_job_id="job-1",
        apply_item_ids=("item-1",),
        workspace_id="workspace-1",
        snapshot_id="snapshot-1",
        draft_revision_id="revision-1",
        review_id="review-1",
        selection_checksum="checksum",
        listing_id="listing-1",
        channel_id="woocommerce:primary",
        external_primary_id="123",
        sku="SKU-1",
        product_type="simple",
        parent_external_id=None,
        current_price=100.0,
        current_stock=None,
        current_status=None,
        target_price=120.0,
        target_stock=None,
        target_status=None,
        currency="EUR",
        unit=None,
        mapping_version=1,
        cache_version=1,
        cache_checksum="cache",
        capability_version="v1",
        currency_digest="digest",
        idempotency_key="idem-1",
        payload_hash="hash",
        pricing_origin=PricingOrigin.PRICING_MATRIX,
        expected_pricing_authority=PricingAuthority.PRICING_MATRIX,
    )
    defaults.update(overrides)
    return WorkspaceWriteIntent(**defaults)  # type: ignore[arg-type]


def _write_item(**overrides: object) -> WriteItem:
    defaults: dict[str, object] = dict(
        id=1,
        batch_id="batch-1",
        channel_product_id="123",
        sku="SKU-1",
        product_name="Widget",
        current_price=100.0,
        proposed_price=120.0,
        delta_amount=20.0,
        delta_percent=20.0,
        currency="EUR",
        status="failed",
        error_code="upstream_unavailable",
        error_message="Provider timed out.",
    )
    defaults.update(overrides)
    return WriteItem(**defaults)


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


def test_pricing_authority_rejection_emits_pricing_business_event() -> None:
    db = _session()
    service = WritePipelineService(db)
    intent = _intent()

    service._emit_pricing_authority_business_event(
        intent, reason_code="pricing_origin_not_authorized", correlation_id="corr-pricing-1"
    )
    db.commit()

    rows = db.query(BusinessEvent).filter(BusinessEvent.domain == "pricing").all()
    assert len(rows) == 1
    event = rows[0]
    assert event.event_type == "pricing_apply_blocked"
    assert event.severity == "error"
    assert event.business_impact == "blocking"
    assert event.reason_code == "pricing_origin_not_authorized"
    assert event.primary_scope_type == "channel"
    assert event.primary_scope_id == "woocommerce:primary"
    assert event.secondary_scopes_json == [
        {"scope_type": "product", "scope_id": "listing-1", "scope_label": "SKU-1"},
        {"scope_type": "review", "scope_id": "review-1", "scope_label": None},
        {"scope_type": "workspace", "scope_id": "workspace-1", "scope_label": None},
    ]
    assert event.action_route_key == "workspace.review"
    assert event.action_route_params_json == {"workspace_id": "workspace-1"}
    assert event.correlation_id == "corr-pricing-1"
    assert event.retryable is True


class TestChannelWriteBusinessEvent:
    def test_item_failed_emits_channel_write_failed(self) -> None:
        db = _session()
        service = WritePipelineService(db)
        batch = _batch("partially_failed")
        item = _write_item()
        result = WorkspaceWriteResult(
            listing_id="listing-1",
            outcome=WriteOutcome.FAILED,
            error_category="upstream_unavailable",
            error_message="Provider timed out.",
        )

        service._emit_channel_write_business_event(
            item, "item_failed", result, batch, correlation_id="corr-channel-1"
        )
        db.commit()

        rows = db.query(BusinessEvent).filter(BusinessEvent.domain == "channels").all()
        assert len(rows) == 1
        event = rows[0]
        assert event.event_type == "channel_write_failed"
        assert event.severity == "error"
        assert event.business_impact == "partial_failure"
        assert event.reason_code == "upstream_unavailable"
        assert event.reason_message == "Provider timed out."
        assert event.primary_scope_type == "channel"
        assert event.primary_scope_id == "woocommerce:primary"
        assert event.secondary_scopes_json == [
            {"scope_type": "product", "scope_id": "123", "scope_label": "SKU-1"}
        ]
        assert event.action_route_key == "channel.detail"
        assert event.action_route_params_json == {"channel_id": "woocommerce:primary"}
        assert event.retryable is True

    def test_item_reconciliation_required_emits_non_retryable_event(self) -> None:
        db = _session()
        service = WritePipelineService(db)
        batch = _batch("reconciliation_required")
        item = _write_item(status="reconciliation_required", error_code="read_back_unverified")
        result = WorkspaceWriteResult(
            listing_id="listing-1", outcome=WriteOutcome.RECONCILIATION_REQUIRED
        )

        service._emit_channel_write_business_event(
            item, "item_reconciliation_required", result, batch, correlation_id="corr-channel-2"
        )
        db.commit()

        event = db.query(BusinessEvent).filter(BusinessEvent.domain == "channels").one()
        assert event.event_type == "channel_write_reconciliation_required"
        assert event.severity == "warning"
        assert event.business_impact == "blocking"
        assert event.retryable is False

    def test_item_applied_emits_no_channel_event(self) -> None:
        db = _session()
        service = WritePipelineService(db)
        batch = _batch("applied")
        item = _write_item(status="applied", error_code=None, error_message=None)
        result = WorkspaceWriteResult(listing_id="listing-1", outcome=WriteOutcome.VERIFIED_APPLIED)

        service._emit_channel_write_business_event(
            item, "item_applied", result, batch, correlation_id="corr-channel-3"
        )
        db.commit()

        assert db.query(BusinessEvent).filter(BusinessEvent.domain == "channels").count() == 0

    def test_pricing_authority_rejected_item_is_not_double_reported_as_channels(self) -> None:
        """The same rejection must not appear under both Pricing and Channels."""
        db = _session()
        service = WritePipelineService(db)
        batch = _batch("partially_failed")
        item = _write_item(error_code="pricing_origin_not_authorized")
        result = WorkspaceWriteResult(
            listing_id="listing-1",
            outcome=WriteOutcome.FAILED,
            error_category="pricing_authority",
            error_message="pricing_origin_not_authorized",
        )

        service._emit_channel_write_business_event(
            item, "item_failed", result, batch, correlation_id="corr-channel-4"
        )
        db.commit()

        assert db.query(BusinessEvent).filter(BusinessEvent.domain == "channels").count() == 0
