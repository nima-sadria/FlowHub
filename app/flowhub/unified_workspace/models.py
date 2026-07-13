"""Normalized persistence model for the FlowHub v1.2 workspace."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, Mapper, mapped_column, relationship

from app.flowhub.database import FlowHubBase
from app.flowhub.unified_workspace.domain import ImmutableRecordError, utcnow


class UnifiedWorkspace(FlowHubBase):
    __tablename__ = "uw_workspaces"
    __table_args__ = (
        CheckConstraint("entry_point IN ('source','manual')", name="ck_uw_workspace_entry_point"),
        CheckConstraint("status IN ('active','archived')", name="ck_uw_workspace_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    entry_point: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    source_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    snapshot: Mapped[WorkspaceSnapshot] = relationship(
        "WorkspaceSnapshot", back_populates="workspace", uselist=False
    )


class CurrencyProfile(FlowHubBase):
    __tablename__ = "uw_currency_profiles"
    __table_args__ = (
        CheckConstraint("scope IN ('global','source','channel')", name="ck_uw_currency_scope"),
        UniqueConstraint(
            "scope", "scope_reference", "version", name="uq_uw_currency_profile_version"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    scope_reference: Mapped[str] = mapped_column(String(120), nullable=False, default="default")
    currency: Mapped[str] = mapped_column(String(12), nullable=False)
    unit: Mapped[str] = mapped_column(String(24), nullable=False)
    normalization_currency: Mapped[str] = mapped_column(String(12), nullable=False)
    normalization_unit: Mapped[str] = mapped_column(String(24), nullable=False)
    conversion_factor: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    conversion_rule: Mapped[str] = mapped_column(String(120), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class WorkspaceSnapshot(FlowHubBase):
    __tablename__ = "uw_workspace_snapshots"
    __table_args__ = (
        UniqueConstraint("workspace_id", name="uq_uw_snapshot_workspace"),
        CheckConstraint("entry_point IN ('source','manual')", name="ck_uw_snapshot_entry_point"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("uw_workspaces.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    entry_point: Mapped[str] = mapped_column(String(20), nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    creator_user_id: Mapped[int] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=False
    )
    schema_version: Mapped[str] = mapped_column(String(40), nullable=False)
    content_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    normalization_version: Mapped[str] = mapped_column(String(40), nullable=False)
    validation_ruleset_version: Mapped[str] = mapped_column(String(40), nullable=False)
    mapping_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    currency_profile_id: Mapped[str] = mapped_column(
        ForeignKey("uw_currency_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    source_metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    acquisition_metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    workspace: Mapped[UnifiedWorkspace] = relationship(
        "UnifiedWorkspace", back_populates="snapshot"
    )
    rows: Mapped[list[SnapshotRow]] = relationship(
        "SnapshotRow", back_populates="snapshot", order_by="SnapshotRow.row_number"
    )


class CanonicalProduct(FlowHubBase):
    __tablename__ = "uw_canonical_products"
    __table_args__ = (
        CheckConstraint(
            "product_type IN ('simple','variable','variation')", name="ck_uw_product_type"
        ),
        CheckConstraint("status IN ('active','inactive','draft')", name="ck_uw_product_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(1000), nullable=False, index=True)
    sku: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    product_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("uw_canonical_products.id", ondelete="RESTRICT"), nullable=True
    )
    brand: Mapped[str | None] = mapped_column(String(240), nullable=True, index=True)
    category: Mapped[str | None] = mapped_column(String(240), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class WorkspaceChannel(FlowHubBase):
    __tablename__ = "uw_channels"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    connector_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    implementation_state: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    capabilities_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    capability_version: Mapped[str] = mapped_column(String(40), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class Listing(FlowHubBase):
    __tablename__ = "uw_listings"
    __table_args__ = (
        UniqueConstraint(
            "channel_id", "external_primary_id", name="uq_uw_listing_external_identity"
        ),
        CheckConstraint(
            "mapping_state IN ('resolved','unresolved','conflict')",
            name="ck_uw_listing_mapping_state",
        ),
        Index("ix_uw_listing_product_channel", "canonical_product_id", "channel_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    canonical_product_id: Mapped[str] = mapped_column(
        ForeignKey("uw_canonical_products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    channel_id: Mapped[str] = mapped_column(
        ForeignKey("uw_channels.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    external_primary_id: Mapped[str] = mapped_column(String(255), nullable=False)
    external_id_type: Mapped[str] = mapped_column(String(80), nullable=False)
    secondary_identifiers_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    sku: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    label: Mapped[str] = mapped_column(String(500), nullable=False)
    mapping_state: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    mapping_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    capability_state_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class MappingRevision(FlowHubBase):
    __tablename__ = "uw_mapping_revisions"
    __table_args__ = (
        UniqueConstraint("listing_id", "revision_number", name="uq_uw_mapping_revision_number"),
        CheckConstraint(
            "decision IN ('approved','rejected','automatic')", name="ck_uw_mapping_decision"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    listing_id: Mapped[str] = mapped_column(
        ForeignKey("uw_listings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_canonical_product_id: Mapped[str | None] = mapped_column(
        ForeignKey("uw_canonical_products.id", ondelete="RESTRICT"), nullable=True
    )
    proposed_canonical_product_id: Mapped[str] = mapped_column(
        ForeignKey("uw_canonical_products.id", ondelete="RESTRICT"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    approved_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=True
    )
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class ChannelCache(FlowHubBase):
    __tablename__ = "uw_channel_cache"
    __table_args__ = (UniqueConstraint("listing_id", name="uq_uw_cache_listing"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    listing_id: Mapped[str] = mapped_column(
        ForeignKey("uw_listings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    channel_id: Mapped[str] = mapped_column(
        ForeignKey("uw_channels.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    price_raw: Mapped[str | None] = mapped_column(String(100), nullable=True)
    price_currency: Mapped[str | None] = mapped_column(String(12), nullable=True)
    price_unit: Mapped[str | None] = mapped_column(String(24), nullable=True)
    stock_quantity: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    manage_stock: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    cache_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    connector_version: Mapped[str] = mapped_column(String(40), nullable=False)
    freshness: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    fetch_status: Mapped[str] = mapped_column(String(30), nullable=False)
    external_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    error_category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)


class SnapshotRow(FlowHubBase):
    __tablename__ = "uw_snapshot_rows"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "row_number", name="uq_uw_snapshot_row_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("uw_workspace_snapshots.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    canonical_product_id: Mapped[str | None] = mapped_column(
        ForeignKey("uw_canonical_products.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    listing_id: Mapped[str | None] = mapped_column(
        ForeignKey("uw_listings.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    mapping_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_data_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    normalized_data_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    row_checksum: Mapped[str] = mapped_column(String(64), nullable=False)

    snapshot: Mapped[WorkspaceSnapshot] = relationship("WorkspaceSnapshot", back_populates="rows")


class Draft(FlowHubBase):
    __tablename__ = "uw_drafts"
    __table_args__ = (
        CheckConstraint("status IN ('draft','reviewed','applied')", name="ck_uw_draft_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("uw_workspaces.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("uw_workspace_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    current_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("uw_draft_revisions.id", ondelete="RESTRICT", use_alter=True), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class DraftRevision(FlowHubBase):
    __tablename__ = "uw_draft_revisions"
    __table_args__ = (
        UniqueConstraint("draft_id", "revision_number", name="uq_uw_draft_revision_number"),
        UniqueConstraint("draft_id", "checksum", name="uq_uw_draft_revision_checksum"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    draft_id: Mapped[str] = mapped_column(
        ForeignKey("uw_drafts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("uw_workspaces.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("uw_workspace_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("uw_draft_revisions.id", ondelete="RESTRICT"), nullable=True
    )
    restored_from_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("uw_draft_revisions.id", ondelete="RESTRICT"), nullable=True
    )
    creator_user_id: Mapped[int] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=False
    )
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class DraftRevisionChange(FlowHubBase):
    __tablename__ = "uw_draft_revision_changes"
    __table_args__ = (
        UniqueConstraint("revision_id", "listing_id", "field", name="uq_uw_revision_listing_field"),
        CheckConstraint("field IN ('price','stock','status')", name="ck_uw_change_field"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    revision_id: Mapped[str] = mapped_column(
        ForeignKey("uw_draft_revisions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    canonical_product_id: Mapped[str] = mapped_column(
        ForeignKey("uw_canonical_products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    listing_id: Mapped[str] = mapped_column(
        ForeignKey("uw_listings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    channel_id: Mapped[str] = mapped_column(
        ForeignKey("uw_channels.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    field: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    target_value: Mapped[str] = mapped_column(Text, nullable=False)
    currency: Mapped[str | None] = mapped_column(String(12), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(24), nullable=True)
    change_checksum: Mapped[str] = mapped_column(String(64), nullable=False)


class Review(FlowHubBase):
    __tablename__ = "uw_reviews"
    __table_args__ = (
        CheckConstraint("status IN ('ready','blocked','stale')", name="ck_uw_review_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("uw_workspaces.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("uw_workspace_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    draft_revision_id: Mapped[str] = mapped_column(
        ForeignKey("uw_draft_revisions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    ruleset_version: Mapped[str] = mapped_column(String(40), nullable=False)
    capability_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    currency_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    currency_profile_id: Mapped[str] = mapped_column(
        ForeignKey("uw_currency_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    currency_profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    currency_profile_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    currency_source_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    currency_channel_references_json: Mapped[list[Any]] = mapped_column(
        JSON, nullable=False, default=list
    )
    currency_ruleset_version: Mapped[str] = mapped_column(String(40), nullable=False)
    mapping_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    stale_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    selection_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    selection_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    selected_channel_ids_json: Mapped[list[Any]] = mapped_column(
        JSON, nullable=False, default=list
    )


class ReviewItem(FlowHubBase):
    __tablename__ = "uw_review_items"
    __table_args__ = (
        UniqueConstraint("review_id", "draft_change_id", name="uq_uw_review_change"),
        Index("ix_uw_review_item_selection", "review_id", "selected", "eligible"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    review_id: Mapped[str] = mapped_column(
        ForeignKey("uw_reviews.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    draft_change_id: Mapped[str] = mapped_column(
        ForeignKey("uw_draft_revision_changes.id", ondelete="RESTRICT"), nullable=False
    )
    canonical_product_id: Mapped[str] = mapped_column(
        ForeignKey("uw_canonical_products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    listing_id: Mapped[str] = mapped_column(
        ForeignKey("uw_listings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    channel_id: Mapped[str] = mapped_column(
        ForeignKey("uw_channels.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    field: Mapped[str] = mapped_column(String(20), nullable=False)
    current_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_value: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_value_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    payload_summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    validation_state: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    warnings_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    errors_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ReviewCacheVersion(FlowHubBase):
    __tablename__ = "uw_review_cache_versions"
    __table_args__ = (
        UniqueConstraint("review_id", "listing_id", name="uq_uw_review_cache_listing"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    review_id: Mapped[str] = mapped_column(
        ForeignKey("uw_reviews.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    listing_id: Mapped[str] = mapped_column(
        ForeignKey("uw_listings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    channel_id: Mapped[str] = mapped_column(
        ForeignKey("uw_channels.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    cache_version: Mapped[int] = mapped_column(Integer, nullable=False)
    cache_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    mapping_version: Mapped[int] = mapped_column(Integer, nullable=False)
    capability_version: Mapped[str] = mapped_column(String(40), nullable=False)


class ReviewSelection(FlowHubBase):
    __tablename__ = "uw_review_selections"
    __table_args__ = (
        UniqueConstraint("review_id", "review_item_id", name="uq_uw_review_selection_item"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    review_id: Mapped[str] = mapped_column(
        ForeignKey("uw_reviews.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    review_item_id: Mapped[str] = mapped_column(
        ForeignKey("uw_review_items.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    selected_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=False
    )
    selected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class ApplyJob(FlowHubBase):
    __tablename__ = "uw_apply_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','partially_applied','applied','failed','cancelled','blocked','stale','reconciliation_required')",
            name="ck_uw_apply_status",
        ),
        UniqueConstraint("idempotency_key", name="uq_uw_apply_idempotency"),
        UniqueConstraint("logical_operation_key", name="uq_uw_apply_logical_operation"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("uw_workspaces.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("uw_workspace_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    draft_revision_id: Mapped[str] = mapped_column(
        ForeignKey("uw_draft_revisions.id", ondelete="RESTRICT"), nullable=False
    )
    review_id: Mapped[str] = mapped_column(
        ForeignKey("uw_reviews.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    requested_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    logical_operation_key: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    selection_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    worker_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Monotonic ownership fencing prevents a stale worker from finalizing a
    # recovered operation.  The token is persisted with the job and must be
    # presented by every state transition after provider I/O.
    fencing_token: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_token: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    recovery_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    operation_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ApplyJobItem(FlowHubBase):
    __tablename__ = "uw_apply_job_items"
    __table_args__ = (
        UniqueConstraint("apply_job_id", "review_item_id", name="uq_uw_apply_review_item"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    apply_job_id: Mapped[str] = mapped_column(
        ForeignKey("uw_apply_jobs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    review_item_id: Mapped[str] = mapped_column(
        ForeignKey("uw_review_items.id", ondelete="RESTRICT"), nullable=False
    )
    canonical_product_id: Mapped[str] = mapped_column(
        ForeignKey("uw_canonical_products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    listing_id: Mapped[str] = mapped_column(
        ForeignKey("uw_listings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    channel_id: Mapped[str] = mapped_column(
        ForeignKey("uw_channels.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    field: Mapped[str] = mapped_column(String(20), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    connector_response_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    external_response_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    cache_sync_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ValidationIssue(FlowHubBase):
    __tablename__ = "uw_validation_issues"
    __table_args__ = (
        CheckConstraint("severity IN ('warning','error')", name="ck_uw_issue_severity"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("uw_workspaces.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("uw_workspace_snapshots.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    review_id: Mapped[str | None] = mapped_column(
        ForeignKey("uw_reviews.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    canonical_product_id: Mapped[str | None] = mapped_column(
        ForeignKey("uw_canonical_products.id", ondelete="RESTRICT"), nullable=True
    )
    listing_id: Mapped[str | None] = mapped_column(
        ForeignKey("uw_listings.id", ondelete="RESTRICT"), nullable=True
    )
    channel_id: Mapped[str | None] = mapped_column(
        ForeignKey("uw_channels.id", ondelete="RESTRICT"), nullable=True
    )
    code: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class UnifiedAuditEntry(FlowHubBase):
    __tablename__ = "uw_audit_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    correlation_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, index=True
    )
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    draft_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    draft_revision_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    review_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    apply_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    canonical_product_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    listing_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    channel_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    changed_field: Mapped[str | None] = mapped_column(String(20), nullable=True)
    previous_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_result: Mapped[str | None] = mapped_column(String(30), nullable=True)
    review_result: Mapped[str | None] = mapped_column(String(30), nullable=True)
    apply_result: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    metadata_checksum: Mapped[str] = mapped_column(String(64), nullable=False)


class WorkspaceLock(FlowHubBase):
    __tablename__ = "uw_workspace_locks"
    __table_args__ = (UniqueConstraint("channel_id", "listing_id", name="uq_uw_lock_scope"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("uw_workspaces.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    channel_id: Mapped[str] = mapped_column(
        ForeignKey("uw_channels.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    listing_id: Mapped[str] = mapped_column(
        ForeignKey("uw_listings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    apply_job_id: Mapped[str] = mapped_column(
        ForeignKey("uw_apply_jobs.id", ondelete="CASCADE"), nullable=False
    )
    acquired_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class ApplyAttempt(FlowHubBase):
    """Immutable external dispatch intent committed before provider I/O."""

    __tablename__ = "uw_apply_attempts"
    __table_args__ = (
        UniqueConstraint("apply_job_item_id", "attempt_number", name="uq_uw_attempt_number"),
        UniqueConstraint("provider_idempotency_key", name="uq_uw_attempt_provider_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    apply_job_id: Mapped[str] = mapped_column(
        ForeignKey("uw_apply_jobs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    apply_job_item_id: Mapped[str] = mapped_column(
        ForeignKey("uw_apply_job_items.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    listing_id: Mapped[str] = mapped_column(
        ForeignKey("uw_listings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    channel_id: Mapped[str] = mapped_column(
        ForeignKey("uw_channels.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    normalized_payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class ApplyAttemptEvent(FlowHubBase):
    """Append-only outcome evidence for an immutable dispatch intent."""

    __tablename__ = "uw_apply_attempt_events"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('pending','dispatched','provider_accepted','verified_applied','failed','reconciliation_required','recovering')",
            name="ck_uw_attempt_event_outcome",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    attempt_id: Mapped[str] = mapped_column(
        ForeignKey("uw_apply_attempts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    outcome: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    provider_response_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error_category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class UserWorkspacePreference(FlowHubBase):
    __tablename__ = "uw_user_preferences"
    __table_args__ = (UniqueConstraint("user_id", name="uq_uw_preference_user"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    visible_channel_ids_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    channel_order_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    visible_fields_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    display_name_source: Mapped[str] = mapped_column(
        String(120), nullable=False, default="canonical"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


_IMMUTABLE_MODELS = (
    CurrencyProfile,
    WorkspaceSnapshot,
    SnapshotRow,
    MappingRevision,
    DraftRevision,
    DraftRevisionChange,
    ReviewItem,
    ReviewCacheVersion,
    UnifiedAuditEntry,
    ApplyAttempt,
    ApplyAttemptEvent,
)


def _reject_immutable_change(
    _mapper: Mapper[Any], _connection: Connection, target: Any
) -> None:
    raise ImmutableRecordError(f"{target.__class__.__name__} records are immutable.")


for _model in _IMMUTABLE_MODELS:
    event.listen(_model, "before_update", _reject_immutable_change)
    event.listen(_model, "before_delete", _reject_immutable_change)
