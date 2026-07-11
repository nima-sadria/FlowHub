"""Protected multi-channel product price operation models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.flowhub.database import FlowHubBase


def _utcnow() -> datetime:
    return datetime.utcnow()


class ProductPriceOperation(FlowHubBase):
    __tablename__ = "flowhub_product_price_operations"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    product_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    sku: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    product_name: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    version_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    approved_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    approval_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    items: Mapped[list["ProductPriceOperationItem"]] = relationship(
        "ProductPriceOperationItem",
        back_populates="operation",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ProductPriceOperationItem(FlowHubBase):
    __tablename__ = "flowhub_product_price_operation_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    operation_id: Mapped[str] = mapped_column(
        String(120),
        ForeignKey("flowhub_product_price_operations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    connector_type: Mapped[str] = mapped_column(String(80), nullable=False)
    channel_product_id: Mapped[str] = mapped_column(String(255), nullable=False)
    sku: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    current_value: Mapped[float] = mapped_column(Float, nullable=False)
    proposed_value: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(12), nullable=False, default="")
    unit: Mapped[str] = mapped_column(String(24), nullable=False, default="")
    outbound_value: Mapped[float] = mapped_column(Float, nullable=False)
    outbound_unit: Mapped[str] = mapped_column(String(24), nullable=False, default="")
    stale_token: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending", index=True)
    validation_state: Mapped[str] = mapped_column(String(40), nullable=False, default="valid")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    operation: Mapped[ProductPriceOperation] = relationship("ProductPriceOperation", back_populates="items")
