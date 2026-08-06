"""Persistence model for immutable Pricing Matrix decisions and activation heads."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from app.flowhub.database import FlowHubBase
from app.flowhub.unified_workspace.domain import ImmutableRecordError, utcnow


class PricingPolicyRevision(FlowHubBase):
    __tablename__ = "pm_policy_revisions"
    __table_args__ = (
        UniqueConstraint("policy_id", "revision_number", name="uq_pm_policy_revision_number"),
        CheckConstraint("basis_strategy = 'min'", name="ck_pm_policy_basis_strategy"),
        CheckConstraint(
            "round_order IN ('round_then_surcharge','surcharge_then_round')",
            name="ck_pm_policy_round_order",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    policy_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    computation_currency: Mapped[str] = mapped_column(String(12), nullable=False)
    basis_strategy: Mapped[str] = mapped_column(String(20), nullable=False, default="min")
    round_order: Mapped[str] = mapped_column(String(40), nullable=False)
    max_quote_age_days: Mapped[int] = mapped_column(Integer, nullable=False)
    min_quote_count: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluation_timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    arithmetic_version: Mapped[str] = mapped_column(String(40), nullable=False)
    unit_registry_version: Mapped[str] = mapped_column(String(40), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class ProductGroupRevision(FlowHubBase):
    __tablename__ = "pm_product_group_revisions"
    __table_args__ = (
        UniqueConstraint("product_group_id", "revision_number", name="uq_pm_group_revision_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    product_group_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class ProductGroupMember(FlowHubBase):
    __tablename__ = "pm_product_group_members"
    __table_args__ = (
        UniqueConstraint(
            "product_group_revision_id",
            "canonical_product_id",
            name="uq_pm_group_revision_member",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    product_group_revision_id: Mapped[str] = mapped_column(
        ForeignKey("pm_product_group_revisions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    canonical_product_id: Mapped[str] = mapped_column(
        ForeignKey("uw_canonical_products.id", ondelete="RESTRICT"), nullable=False, index=True
    )


class PricingRuleEntry(FlowHubBase):
    __tablename__ = "pm_rule_entries"
    __table_args__ = (
        CheckConstraint(
            "rate_mode IN ('percent_bp','multiplier_ppm')", name="ck_pm_rule_rate_mode"
        ),
        CheckConstraint(
            "round_mode IN ('floor','ceil','nearest')", name="ck_pm_rule_round_mode"
        ),
        CheckConstraint("round_step_minor > 0", name="ck_pm_rule_round_step"),
        Index("ix_pm_rule_scope", "policy_revision_id", "channel_id", "product_ref"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    policy_revision_id: Mapped[str] = mapped_column(
        ForeignKey("pm_policy_revisions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    channel_id: Mapped[str | None] = mapped_column(
        ForeignKey("uw_channels.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    product_ref: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    product_group_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("pm_product_group_revisions.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    rate_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    rate_value: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fixed_addend_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    round_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    round_step_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    surcharge_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    guards_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    scope_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class PricingChannelConfigRevision(FlowHubBase):
    __tablename__ = "pm_channel_config_revisions"
    __table_args__ = (
        UniqueConstraint("channel_id", "revision_number", name="uq_pm_channel_config_revision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    channel_id: Mapped[str] = mapped_column(
        ForeignKey("uw_channels.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    currency_profile_id: Mapped[str] = mapped_column(
        ForeignKey("uw_currency_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(12), nullable=False)
    currency_unit: Mapped[str] = mapped_column(String(24), nullable=False)
    unit_registry_version: Mapped[str] = mapped_column(String(40), nullable=False)
    connector_config_version: Mapped[str] = mapped_column(String(80), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class PricingPolicyLifecycleEvent(FlowHubBase):
    __tablename__ = "pm_policy_lifecycle_events"
    __table_args__ = (
        CheckConstraint("event_kind IN ('activate','deactivate')", name="ck_pm_event_kind"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    channel_id: Mapped[str] = mapped_column(
        ForeignKey("uw_channels.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    event_kind: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    predecessor_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("pm_policy_lifecycle_events.id", ondelete="RESTRICT"), nullable=True
    )
    effective_activation_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    policy_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("pm_policy_revisions.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    channel_config_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("pm_channel_config_revisions.id", ondelete="RESTRICT"), nullable=True
    )
    supersedes_activation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_user_id: Mapped[int] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class ChannelPricingPolicyHead(FlowHubBase):
    __tablename__ = "pm_channel_policy_heads"

    channel_id: Mapped[str] = mapped_column(
        ForeignKey("uw_channels.id", ondelete="RESTRICT"), primary_key=True
    )
    current_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("pm_policy_lifecycle_events.id", ondelete="RESTRICT"), nullable=True
    )
    effective_activation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    head_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class WorkspacePricingBinding(FlowHubBase):
    __tablename__ = "pm_workspace_bindings"
    __table_args__ = (
        UniqueConstraint("workspace_id", "channel_id", name="uq_pm_workspace_channel_binding"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("uw_workspaces.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    channel_id: Mapped[str] = mapped_column(
        ForeignKey("uw_channels.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    policy_revision_id: Mapped[str] = mapped_column(
        ForeignKey("pm_policy_revisions.id", ondelete="RESTRICT"), nullable=False
    )
    pricing_policy_activation_id: Mapped[str] = mapped_column(
        ForeignKey("pm_policy_lifecycle_events.id", ondelete="RESTRICT"), nullable=False
    )
    channel_config_revision_id: Mapped[str] = mapped_column(
        ForeignKey("pm_channel_config_revisions.id", ondelete="RESTRICT"), nullable=False
    )
    pricing_authority_event_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    pricing_authority_head_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_pricing_authority: Mapped[str | None] = mapped_column(String(40), nullable=True)
    execution_policy_snapshot_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    workspace_pricing_evaluated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class PricingAttentionSignal(FlowHubBase):
    __tablename__ = "pm_attention_signals"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "channel_id",
            "outcome_code",
            "policy_revision_id",
            name="uq_pm_attention_dedup",
        ),
        CheckConstraint("status IN ('open','resolved','superseded')", name="ck_pm_attention_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    channel_id: Mapped[str] = mapped_column(
        ForeignKey("uw_channels.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    outcome_code: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    policy_revision_id: Mapped[str] = mapped_column(
        ForeignKey("pm_policy_revisions.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open", index=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


_IMMUTABLE_MODELS = (
    PricingPolicyRevision,
    ProductGroupRevision,
    ProductGroupMember,
    PricingRuleEntry,
    PricingChannelConfigRevision,
    PricingPolicyLifecycleEvent,
    WorkspacePricingBinding,
)


def _reject_immutable_change(
    _mapper: Mapper[Any], _connection: Connection, target: Any
) -> None:
    raise ImmutableRecordError(f"{target.__class__.__name__} records are immutable.")


for _model in _IMMUTABLE_MODELS:
    event.listen(_model, "before_update", _reject_immutable_change)
    event.listen(_model, "before_delete", _reject_immutable_change)
