"""Persistence repositories; business policy remains in application services."""

from __future__ import annotations

from datetime import datetime
from typing import cast as typing_cast

from sqlalchemy import Numeric, asc, cast, desc, or_
from sqlalchemy.orm import Session

from app.flowhub.unified_workspace.models import (
    ApplyJob,
    ApplyJobItem,
    CanonicalProduct,
    ChannelCache,
    Draft,
    DraftRevision,
    DraftRevisionChange,
    Listing,
    Review,
    ReviewCacheVersion,
    ReviewItem,
    ReviewSelection,
    SnapshotRow,
    UnifiedAuditEntry,
    UnifiedWorkspace,
    UserWorkspacePreference,
    WorkspaceChannel,
    WorkspaceLock,
    WorkspaceSnapshot,
)


class WorkspaceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, workspace_id: str) -> UnifiedWorkspace | None:
        return self.db.get(UnifiedWorkspace, workspace_id)

    def add(self, workspace: UnifiedWorkspace) -> None:
        self.db.add(workspace)

    def snapshot(self, workspace_id: str) -> WorkspaceSnapshot | None:
        return self.db.query(WorkspaceSnapshot).filter_by(workspace_id=workspace_id).first()

    def grid_rows(
        self,
        snapshot_id: str,
        *,
        page: int,
        page_size: int,
        search: str | None = None,
        product_type: str | None = None,
        mapping_state: str | None = None,
        category: str | None = None,
        brand: str | None = None,
        channel_id: str | None = None,
        sku: str | None = None,
        listing_id: str | None = None,
        channel_status: str | None = None,
        min_price: float | None = None,
        max_price: float | None = None,
        stock_quantity: float | None = None,
        sorts: list[tuple[str, str]] | None = None,
    ) -> tuple[
        list[tuple[SnapshotRow, CanonicalProduct | None, Listing | None, ChannelCache | None]], int
    ]:
        query = (
            self.db.query(SnapshotRow, CanonicalProduct, Listing, ChannelCache)
            .outerjoin(CanonicalProduct, CanonicalProduct.id == SnapshotRow.canonical_product_id)
            .outerjoin(Listing, Listing.id == SnapshotRow.listing_id)
            .outerjoin(ChannelCache, ChannelCache.listing_id == Listing.id)
            .filter(SnapshotRow.snapshot_id == snapshot_id)
        )
        if search:
            query = query.filter(CanonicalProduct.name.ilike(f"%{search.strip()}%"))
        if product_type:
            query = query.filter(CanonicalProduct.product_type == product_type)
        if mapping_state:
            query = query.filter(Listing.mapping_state == mapping_state)
        if category:
            query = query.filter(CanonicalProduct.category == category)
        if brand:
            query = query.filter(CanonicalProduct.brand == brand)
        if channel_id:
            query = query.filter(Listing.channel_id == channel_id)
        if sku:
            query = query.filter(Listing.sku.ilike(f"%{sku.strip()}%"))
        if listing_id:
            query = query.filter(Listing.id == listing_id)
        if channel_status:
            query = query.filter(ChannelCache.status == channel_status)
        if min_price is not None:
            query = query.filter(cast(ChannelCache.price_raw, Numeric) >= min_price)
        if max_price is not None:
            query = query.filter(cast(ChannelCache.price_raw, Numeric) <= max_price)
        if stock_quantity is not None:
            query = query.filter(ChannelCache.stock_quantity == stock_quantity)
        total = query.count()
        columns = {
            "name": CanonicalProduct.name,
            "brand": CanonicalProduct.brand,
            "category": CanonicalProduct.category,
            "product_type": CanonicalProduct.product_type,
            "mapping_state": Listing.mapping_state,
            "channel": Listing.channel_id,
            "listing_id": Listing.id,
            "price": cast(ChannelCache.price_raw, Numeric),
            "stock": ChannelCache.stock_quantity,
            "status": ChannelCache.status,
            "sku": Listing.sku,
        }
        orderings = []
        for field, direction in (sorts or [("name", "asc")])[:5]:
            column = columns.get(field)
            if column is not None:
                orderings.append(desc(column) if direction == "desc" else asc(column))
        rows = (
            query.order_by(*orderings, SnapshotRow.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        typed_rows = typing_cast(
            list[tuple[SnapshotRow, CanonicalProduct | None, Listing | None, ChannelCache | None]],
            rows,
        )
        return typed_rows, total

    def grouped_rows(
        self,
        snapshot_id: str,
        *,
        page: int,
        page_size: int,
        search: str | None = None,
        include_product_ids: set[str] | None = None,
        exclude_product_ids: set[str] | None = None,
        category: str | None = None,
        product_type: str | None = None,
        channel_id: str | None = None,
        stock_state: str | None = None,
    ) -> tuple[
        list[tuple[SnapshotRow, CanonicalProduct, Listing, ChannelCache | None]], int
    ]:
        products = (
            self.db.query(CanonicalProduct.id, CanonicalProduct.name)
            .join(SnapshotRow, SnapshotRow.canonical_product_id == CanonicalProduct.id)
            .filter(
                SnapshotRow.snapshot_id == snapshot_id,
                SnapshotRow.listing_id.is_not(None),
            )
        )
        needs_listing_join = bool(search or channel_id or stock_state)
        if needs_listing_join:
            products = products.join(Listing, Listing.id == SnapshotRow.listing_id)
        if search:
            pattern = f"%{search.strip()}%"
            products = products.filter(
                or_(
                    CanonicalProduct.name.ilike(pattern),
                    CanonicalProduct.sku.ilike(pattern),
                    Listing.sku.ilike(pattern),
                    Listing.external_primary_id.ilike(pattern),
                )
            )
        if category:
            products = products.filter(CanonicalProduct.category == category.strip())
        if product_type:
            products = products.filter(CanonicalProduct.product_type == product_type)
        if channel_id:
            products = products.filter(Listing.channel_id == channel_id)
        if stock_state:
            products = products.outerjoin(ChannelCache, ChannelCache.listing_id == Listing.id)
            if stock_state == "in_stock":
                products = products.filter(ChannelCache.stock_quantity > 0)
            elif stock_state == "out_of_stock":
                products = products.filter(ChannelCache.stock_quantity <= 0)
            elif stock_state == "unknown":
                products = products.filter(ChannelCache.stock_quantity.is_(None))
        if include_product_ids is not None:
            if not include_product_ids:
                return [], 0
            products = products.filter(CanonicalProduct.id.in_(include_product_ids))
        if exclude_product_ids:
            products = products.filter(CanonicalProduct.id.not_in(exclude_product_ids))
        products = products.distinct()
        total = products.count()
        product_ids = [
            item[0]
            for item in products.order_by(CanonicalProduct.name, CanonicalProduct.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        ]
        if not product_ids:
            return [], total
        rows = (
            self.db.query(SnapshotRow, CanonicalProduct, Listing, ChannelCache)
            .join(CanonicalProduct, CanonicalProduct.id == SnapshotRow.canonical_product_id)
            .join(Listing, Listing.id == SnapshotRow.listing_id)
            .outerjoin(ChannelCache, ChannelCache.listing_id == Listing.id)
            .filter(
                SnapshotRow.snapshot_id == snapshot_id,
                CanonicalProduct.id.in_(product_ids),
            )
            .order_by(CanonicalProduct.name, CanonicalProduct.id, Listing.channel_id, Listing.label)
            .all()
        )
        return typing_cast(
            list[tuple[SnapshotRow, CanonicalProduct, Listing, ChannelCache | None]], rows
        ), total

    def grouped_product_count(self, snapshot_id: str) -> int:
        return (
            self.db.query(CanonicalProduct.id)
            .join(SnapshotRow, SnapshotRow.canonical_product_id == CanonicalProduct.id)
            .filter(
                SnapshotRow.snapshot_id == snapshot_id,
                SnapshotRow.listing_id.is_not(None),
            )
            .distinct()
            .count()
        )


class DraftRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def for_workspace(self, workspace_id: str) -> Draft | None:
        return self.db.query(Draft).filter_by(workspace_id=workspace_id).first()

    def revision(self, revision_id: str) -> DraftRevision | None:
        return self.db.get(DraftRevision, revision_id)

    def revisions(
        self, draft_id: str, *, page: int, page_size: int
    ) -> tuple[list[DraftRevision], int]:
        query = self.db.query(DraftRevision).filter_by(draft_id=draft_id)
        return (
            query.order_by(DraftRevision.revision_number.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all(),
            query.count(),
        )

    def changes(self, revision_id: str) -> list[DraftRevisionChange]:
        return (
            self.db.query(DraftRevisionChange)
            .filter_by(revision_id=revision_id)
            .order_by(
                DraftRevisionChange.canonical_product_id,
                DraftRevisionChange.listing_id,
                DraftRevisionChange.field,
            )
            .all()
        )


class ReviewRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, review_id: str) -> Review | None:
        return self.db.get(Review, review_id)

    def items(self, review_id: str, *, selected_only: bool = False) -> list[ReviewItem]:
        query = self.db.query(ReviewItem).filter_by(review_id=review_id)
        if selected_only:
            query = query.filter(ReviewItem.selected.is_(True))
        return query.order_by(ReviewItem.channel_id, ReviewItem.listing_id, ReviewItem.field).all()

    def cache_versions(self, review_id: str) -> list[ReviewCacheVersion]:
        return self.db.query(ReviewCacheVersion).filter_by(review_id=review_id).all()

    def selections(self, review_id: str) -> list[ReviewSelection]:
        return self.db.query(ReviewSelection).filter_by(review_id=review_id).all()


class ApplyRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, job_id: str) -> ApplyJob | None:
        return self.db.get(ApplyJob, job_id)

    def by_idempotency(self, key: str) -> ApplyJob | None:
        return self.db.query(ApplyJob).filter_by(idempotency_key=key).first()

    def by_logical_operation(self, key: str) -> ApplyJob | None:
        return self.db.query(ApplyJob).filter_by(logical_operation_key=key).first()

    def items(self, job_id: str) -> list[ApplyJobItem]:
        return (
            self.db.query(ApplyJobItem)
            .filter_by(apply_job_id=job_id)
            .order_by(ApplyJobItem.channel_id, ApplyJobItem.listing_id)
            .all()
        )

    def overlapping_locks(
        self, listing_ids: list[str], now: datetime
    ) -> list[WorkspaceLock]:
        return (
            self.db.query(WorkspaceLock)
            .filter(
                WorkspaceLock.listing_id.in_(listing_ids),
                WorkspaceLock.expires_at > now,
            )
            .all()
        )


class AuditRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(
        self, workspace_id: str, *, page: int, page_size: int
    ) -> tuple[list[UnifiedAuditEntry], int]:
        query = self.db.query(UnifiedAuditEntry).filter_by(workspace_id=workspace_id)
        return (
            query.order_by(UnifiedAuditEntry.occurred_at.desc(), UnifiedAuditEntry.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all(),
            query.count(),
        )


class PreferenceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def for_user(self, user_id: int) -> UserWorkspacePreference | None:
        return self.db.query(UserWorkspacePreference).filter_by(user_id=user_id).first()


class ChannelRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, channel_id: str) -> WorkspaceChannel | None:
        return self.db.get(WorkspaceChannel, channel_id)

    def implemented(self) -> list[WorkspaceChannel]:
        return (
            self.db.query(WorkspaceChannel)
            .filter_by(implementation_state="implemented", enabled=True)
            .order_by(WorkspaceChannel.name)
            .all()
        )
