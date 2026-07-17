"""Read-only aggregation of truthful seller-facing dashboard metrics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, distinct, func, or_
from sqlalchemy.orm import Session

from app.flowhub.orders.models import ChannelOrderRecord
from app.flowhub.unified_workspace.models import (
    ApplyJob,
    ApplyJobItem,
    ChannelCache,
    Draft,
    DraftRevisionChange,
    Listing,
    Review,
    ReviewItem,
    UnifiedWorkspace,
    ValidationIssue,
)


class DashboardService:
    """Aggregate existing records without generating or mutating business data."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def business_summary(self, *, now: datetime | None = None) -> dict[str, Any]:
        current = (now or datetime.now(UTC)).replace(tzinfo=None)
        today = current.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        yesterday = today - timedelta(days=1)

        current_changes = (
            self.db.query(DraftRevisionChange)
            .join(Draft, Draft.current_revision_id == DraftRevisionChange.revision_id)
            .join(UnifiedWorkspace, UnifiedWorkspace.id == Draft.workspace_id)
            .filter(
                UnifiedWorkspace.status == "active",
                Draft.status.in_(("draft", "reviewed")),
            )
        )
        products_with_changes = _count_distinct(
            current_changes, DraftRevisionChange.canonical_product_id
        )
        ready_for_review = _count_distinct(
            current_changes.filter(Draft.status == "draft"),
            DraftRevisionChange.canonical_product_id,
        )

        ready_for_apply = _count_distinct(
            self.db.query(ReviewItem)
            .join(Review, Review.id == ReviewItem.review_id)
            .join(Draft, Draft.current_revision_id == Review.draft_revision_id)
            .join(UnifiedWorkspace, UnifiedWorkspace.id == Draft.workspace_id)
            .filter(
                UnifiedWorkspace.status == "active",
                Draft.status != "applied",
                Review.status == "ready",
                Review.invalidated_at.is_(None),
                ReviewItem.eligible.is_(True),
                ReviewItem.selected.is_(True),
                ~Review.id.in_(
                    self.db.query(ApplyJob.review_id).filter(
                        ApplyJob.status.in_(
                            (
                                "pending",
                                "running",
                                "partially_applied",
                                "applied",
                                "reconciliation_required",
                            )
                        )
                    )
                ),
            ),
            ReviewItem.canonical_product_id,
        )

        current_issues = (
            self.db.query(ValidationIssue)
            .join(UnifiedWorkspace, UnifiedWorkspace.id == ValidationIssue.workspace_id)
            .outerjoin(Review, Review.id == ValidationIssue.review_id)
            .filter(
                UnifiedWorkspace.status == "active",
                or_(
                    ValidationIssue.review_id.is_(None),
                    Review.invalidated_at.is_(None),
                ),
            )
        )
        blocking_issues = current_issues.filter(
            ValidationIssue.severity == "error"
        ).count()
        warnings = current_issues.filter(
            ValidationIssue.severity == "warning"
        ).count()
        affected_products = _count_distinct(
            current_issues.filter(ValidationIssue.canonical_product_id.is_not(None)),
            ValidationIssue.canonical_product_id,
        )

        out_of_stock_products = _count_distinct(
            self.db.query(Listing)
            .join(ChannelCache, ChannelCache.listing_id == Listing.id)
            .filter(
                Listing.enabled.is_(True),
                ChannelCache.stock_quantity.is_not(None),
                ChannelCache.stock_quantity <= 0,
            ),
            Listing.canonical_product_id,
        )
        pending_updates = (
            self.db.query(ApplyJobItem)
            .filter(
                ApplyJobItem.status.in_(
                    (
                        "pending",
                        "dispatched",
                        "provider_accepted",
                        "recovering",
                        "reconciliation_required",
                    )
                )
            )
            .count()
        )
        failed_updates = (
            self.db.query(ApplyJobItem)
            .filter(ApplyJobItem.status == "failed")
            .count()
        )
        order_time = func.coalesce(
            ChannelOrderRecord.created_at_provider,
            ChannelOrderRecord.first_seen_at,
        )
        orders_today = _orders_in_window(self.db, order_time, today, tomorrow)
        orders_yesterday = _orders_in_window(self.db, order_time, yesterday, today)
        revenue_today = _revenue_in_window(self.db, order_time, today, tomorrow)
        updates_today = _updates_in_window(self.db, today, tomorrow)
        updates_yesterday = _updates_in_window(self.db, yesterday, today)

        return {
            "generatedAt": current.isoformat(),
            "metrics": {
                "productsWithChanges": products_with_changes,
                "readyForReview": ready_for_review,
                "readyForApply": ready_for_apply,
                "blockingIssues": blocking_issues,
                "warnings": warnings,
                "affectedProducts": affected_products,
                "outOfStockProducts": out_of_stock_products,
                "pendingUpdates": pending_updates,
                "failedUpdates": failed_updates,
                "ordersToday": orders_today,
                "ordersYesterday": orders_yesterday,
                "updatesAppliedToday": updates_today,
                "updatesAppliedYesterday": updates_yesterday,
                "revenueToday": revenue_today,
            },
        }


def _count_distinct(query: Any, column: Any) -> int:
    value = query.with_entities(func.count(distinct(column))).scalar()
    return int(value or 0)


def _orders_in_window(
    db: Session, order_time: Any, start: datetime, end: datetime
) -> int:
    return int(
        db.query(func.count(ChannelOrderRecord.internal_id))
        .filter(and_(order_time >= start, order_time < end))
        .scalar()
        or 0
    )


def _revenue_in_window(
    db: Session, order_time: Any, start: datetime, end: datetime
) -> list[dict[str, Any]]:
    rows = (
        db.query(
            ChannelOrderRecord.currency,
            func.sum(ChannelOrderRecord.final_amount),
        )
        .filter(
            and_(
                order_time >= start,
                order_time < end,
                ChannelOrderRecord.final_amount.is_not(None),
            )
        )
        .group_by(ChannelOrderRecord.currency)
        .order_by(ChannelOrderRecord.currency.asc())
        .all()
    )
    return [
        {"currency": currency or "UNSPECIFIED", "amount": float(amount or 0)}
        for currency, amount in rows
    ]


def _updates_in_window(db: Session, start: datetime, end: datetime) -> int:
    return int(
        db.query(func.count(ApplyJobItem.id))
        .filter(
            ApplyJobItem.status == "applied",
            ApplyJobItem.completed_at >= start,
            ApplyJobItem.completed_at < end,
        )
        .scalar()
        or 0
    )
