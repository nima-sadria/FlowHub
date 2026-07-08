"""FlowHub Write Pipeline ORM models.

These tables store operator-approved write batches, item snapshots, and audit
events. They are generic to FlowHub; marketplace-specific execution stays in
channel adapters.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.flowhub.database import FlowHubBase


def _utcnow() -> datetime:
    return datetime.utcnow()


class WriteBatch(FlowHubBase):
    __tablename__ = "flowhub_write_batches"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    channel_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    channel_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    operation_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="dry_run_ready", index=True)
    source_preview_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    batch_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(12), nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    approved_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    approval_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    safety_summary_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    items: Mapped[list["WriteItem"]] = relationship(
        "WriteItem",
        back_populates="batch",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    events: Mapped[list["WriteEvent"]] = relationship(
        "WriteEvent",
        back_populates="batch",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class WriteItem(FlowHubBase):
    __tablename__ = "flowhub_write_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(
        String(120),
        ForeignKey("flowhub_write_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel_product_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    sku: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    product_name: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    current_price: Mapped[float] = mapped_column(Float, nullable=False)
    proposed_price: Mapped[float] = mapped_column(Float, nullable=False)
    delta_amount: Mapped[float] = mapped_column(Float, nullable=False)
    delta_percent: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(12), nullable=False, default="")
    pre_write_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending", index=True)
    provider_result_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    batch: Mapped[WriteBatch] = relationship("WriteBatch", back_populates="items")
    events: Mapped[list["WriteEvent"]] = relationship(
        "WriteEvent",
        back_populates="item",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class WriteEvent(FlowHubBase):
    __tablename__ = "flowhub_write_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(
        String(120),
        ForeignKey("flowhub_write_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("flowhub_write_items.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(30), nullable=False, default="info")
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    correlation_id: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)

    batch: Mapped[WriteBatch] = relationship("WriteBatch", back_populates="events")
    item: Mapped[WriteItem | None] = relationship("WriteItem", back_populates="events")
