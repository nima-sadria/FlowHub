"""Append-only per-Channel pricing-engine authority persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, event
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from app.flowhub.database import FlowHubBase
from app.flowhub.unified_workspace.domain import ImmutableRecordError, utcnow


class ChannelPricingAuthorityEvent(FlowHubBase):
    __tablename__ = "pm_channel_pricing_authority_events"
    __table_args__ = (
        CheckConstraint(
            "previous_authority IS NULL OR previous_authority IN "
            "('legacy_formula_engine','migration_locked','pricing_matrix')",
            name="ck_pm_authority_event_previous",
        ),
        CheckConstraint(
            "new_authority IN ('legacy_formula_engine','migration_locked','pricing_matrix')",
            name="ck_pm_authority_event_new",
        ),
        CheckConstraint("expected_head_version >= 0", name="ck_pm_authority_event_head_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    channel_id: Mapped[str] = mapped_column(
        ForeignKey("uw_channels.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    previous_authority: Mapped[str | None] = mapped_column(String(40), nullable=True)
    new_authority: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    expected_head_version: Mapped[int] = mapped_column(Integer, nullable=False)
    predecessor_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("pm_channel_pricing_authority_events.id", ondelete="RESTRICT"), nullable=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=True
    )
    actor_reference: Mapped[str] = mapped_column(String(160), nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    request_metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class ChannelPricingAuthorityHead(FlowHubBase):
    __tablename__ = "pm_channel_pricing_authority_heads"
    __table_args__ = (
        CheckConstraint(
            "current_authority IN ('legacy_formula_engine','migration_locked','pricing_matrix')",
            name="ck_pm_authority_head_current",
        ),
        CheckConstraint("head_version >= 0", name="ck_pm_authority_head_version"),
    )

    channel_id: Mapped[str] = mapped_column(
        ForeignKey("uw_channels.id", ondelete="RESTRICT"), primary_key=True
    )
    current_authority: Mapped[str] = mapped_column(String(40), nullable=False)
    effective_event_id: Mapped[str] = mapped_column(
        ForeignKey("pm_channel_pricing_authority_events.id", ondelete="RESTRICT"), nullable=False
    )
    head_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class PricingAuthorityWriteRejection(FlowHubBase):
    """Append-only audit evidence for a write rejected before provider dispatch."""

    __tablename__ = "pm_pricing_authority_write_rejections"
    __table_args__ = (
        CheckConstraint(
            "pricing_origin IS NULL OR pricing_origin IN ('legacy_formula_engine','pricing_matrix')",
            name="ck_pm_authority_rejection_origin",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    channel_id: Mapped[str] = mapped_column(
        ForeignKey("uw_channels.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    listing_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    operation_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    pricing_origin: Mapped[str | None] = mapped_column(String(40), nullable=True)
    current_authority: Mapped[str | None] = mapped_column(String(40), nullable=True)
    current_event_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    current_head_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_event_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    expected_head_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason_code: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    correlation_id: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


def _reject_immutable_change(
    _mapper: Mapper[Any], _connection: Connection, target: Any
) -> None:
    raise ImmutableRecordError(f"{target.__class__.__name__} records are immutable.")


for _model in (ChannelPricingAuthorityEvent, PricingAuthorityWriteRejection):
    event.listen(_model, "before_update", _reject_immutable_change)
    event.listen(_model, "before_delete", _reject_immutable_change)
