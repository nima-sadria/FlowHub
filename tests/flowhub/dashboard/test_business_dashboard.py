from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.flowhub.auth import models as _auth_models  # noqa: F401
from app.flowhub.dashboard.service import DashboardService
from app.flowhub.database import FlowHubBase
from app.flowhub.orders.models import ChannelOrderRecord
from app.flowhub.unified_workspace.models import (
    ChannelCache,
    Draft,
    DraftRevision,
    DraftRevisionChange,
    Listing,
    Review,
    ReviewItem,
    UnifiedWorkspace,
    ValidationIssue,
)


def _db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    FlowHubBase.metadata.create_all(engine)
    return Session(engine)


def test_empty_dashboard_reports_truthful_zero_state() -> None:
    summary = DashboardService(_db()).business_summary(
        now=datetime(2026, 7, 17, 12)
    )

    metrics = summary["metrics"]
    assert metrics["productsWithChanges"] == 0
    assert metrics["readyForReview"] == 0
    assert metrics["readyForApply"] == 0
    assert metrics["blockingIssues"] == 0
    assert metrics["ordersToday"] == 0
    assert metrics["revenueToday"] == []


def test_order_and_revenue_metrics_use_persisted_records_and_keep_currencies_separate() -> None:
    now = datetime(2026, 7, 17, 12)
    db = _db()
    db.add_all(
        [
            _order(1, now - timedelta(hours=2), 100_000, "IRR"),
            _order(2, now - timedelta(hours=1), 50_000, "IRR"),
            _order(3, now - timedelta(hours=1), 20, "USD"),
            _order(4, now - timedelta(days=1, hours=1), 75_000, "IRR"),
        ]
    )
    db.commit()

    metrics = DashboardService(db).business_summary(now=now)["metrics"]

    assert metrics["ordersToday"] == 3
    assert metrics["ordersYesterday"] == 1
    assert metrics["revenueToday"] == [
        {"currency": "IRR", "amount": 150_000.0},
        {"currency": "USD", "amount": 20.0},
    ]


def test_workflow_metrics_come_from_current_draft_review_issue_and_cache_records() -> None:
    db = _db()
    db.add(
        UnifiedWorkspace(
            id="workspace-1",
            name="Daily pricing",
            entry_point="manual",
            owner_user_id=1,
            status="active",
        )
    )
    db.add(
        Draft(
            id="draft-1",
            workspace_id="workspace-1",
            snapshot_id="snapshot-1",
            owner_user_id=1,
            status="draft",
        )
    )
    db.flush()
    revision = DraftRevision(
        id="revision-1",
        draft_id="draft-1",
        workspace_id="workspace-1",
        snapshot_id="snapshot-1",
        revision_number=1,
        creator_user_id=1,
        checksum="a" * 64,
    )
    db.add(revision)
    db.flush()
    db.get(Draft, "draft-1").current_revision_id = revision.id  # type: ignore[union-attr]
    db.add_all(
        [
            DraftRevisionChange(
                id="change-1",
                revision_id=revision.id,
                canonical_product_id="product-1",
                listing_id="listing-1",
                channel_id="woocommerce:test",
                field="price",
                target_value="120000",
                currency="IRR",
                unit="rial",
                change_checksum="b" * 64,
            ),
            Listing(
                id="listing-1",
                canonical_product_id="product-1",
                channel_id="woocommerce:test",
                external_primary_id="wc-1",
                external_id_type="product_id",
                label="Product one",
                mapping_state="resolved",
                enabled=True,
            ),
        ]
    )
    review = Review(
        id="review-1",
        workspace_id="workspace-1",
        snapshot_id="snapshot-1",
        draft_revision_id=revision.id,
        created_by_user_id=1,
        status="ready",
        ruleset_version="1",
        capability_digest="c" * 64,
        currency_digest="d" * 64,
        currency_profile_id="currency-1",
        currency_profile_version=1,
        currency_profile_checksum="e" * 64,
        currency_source_reference="test",
        currency_ruleset_version="1",
        mapping_digest="f" * 64,
        checksum="1" * 64,
    )
    db.add(review)
    db.flush()
    db.add_all(
        [
            ReviewItem(
                id="review-item-1",
                review_id=review.id,
                draft_change_id="change-1",
                canonical_product_id="product-1",
                listing_id="listing-1",
                channel_id="woocommerce:test",
                field="price",
                current_value="100000",
                target_value="120000",
                validation_state="ready",
                eligible=True,
                selected=True,
            ),
            ValidationIssue(
                id="issue-error",
                workspace_id="workspace-1",
                snapshot_id="snapshot-1",
                review_id=review.id,
                canonical_product_id="product-1",
                listing_id="listing-1",
                channel_id="woocommerce:test",
                code="PRICE_BLOCKED",
                severity="error",
                message="Blocked synthetic price",
            ),
            ValidationIssue(
                id="issue-warning",
                workspace_id="workspace-1",
                snapshot_id="snapshot-1",
                review_id=review.id,
                canonical_product_id="product-1",
                listing_id="listing-1",
                channel_id="woocommerce:test",
                code="PRICE_WARNING",
                severity="warning",
                message="Synthetic price warning",
            ),
            ChannelCache(
                id="cache-1",
                listing_id="listing-1",
                channel_id="woocommerce:test",
                stock_quantity=0,
                cache_version=1,
                checksum="2" * 64,
                connector_version="test",
                freshness="fresh",
                fetch_status="success",
                fetched_at=datetime(2026, 7, 17, 10),
            ),
        ]
    )
    db.commit()

    metrics = DashboardService(db).business_summary(
        now=datetime(2026, 7, 17, 12)
    )["metrics"]

    assert metrics["productsWithChanges"] == 1
    assert metrics["readyForReview"] == 1
    assert metrics["readyForApply"] == 1
    assert metrics["blockingIssues"] == 1
    assert metrics["warnings"] == 1
    assert metrics["affectedProducts"] == 1
    assert metrics["outOfStockProducts"] == 1


def _order(
    index: int, created_at: datetime, amount: float, currency: str
) -> ChannelOrderRecord:
    return ChannelOrderRecord(
        channel_id="woocommerce:test",
        connector_type="woocommerce",
        provider_order_id=f"order-{index}",
        order_number=f"WC-{index}",
        provider_status="processing",
        normalized_status="processing",
        created_at_provider=created_at,
        updated_at_provider=created_at,
        currency=currency,
        final_amount=amount,
        raw_hash=f"{index:064d}",
        raw_summary_json={},
        first_seen_at=created_at,
        last_seen_at=created_at,
        last_provider_event_at=created_at,
        synchronization_state="synced",
        event_source="test_fixture",
    )
