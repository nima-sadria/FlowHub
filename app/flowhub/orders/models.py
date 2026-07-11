"""ORM models for normalized channel orders.

Raw provider events and normalized order state are intentionally separate.
Inventory effects captured here are proposed channel events only; they do not
mutate canonical inventory.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.flowhub.database import FlowHubBase


def _utcnow() -> datetime:
    return datetime.utcnow()


class ChannelOrderRecord(FlowHubBase):
    __tablename__ = "channel_orders"
    __table_args__ = (UniqueConstraint("channel_id", "provider_order_id", name="uq_channel_order_provider_id"),)

    internal_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    connector_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    provider_order_id: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    order_number: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    provider_status: Mapped[str] = mapped_column(String(120), nullable=False, default="UNKNOWN")
    normalized_status: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown", index=True)
    created_at_provider: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at_provider: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivery_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    original_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    service_fee: Mapped[float | None] = mapped_column(Float, nullable=True)
    discount_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    customer_reference: Mapped[str | None] = mapped_column(String(96), nullable=True)
    raw_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_summary_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    last_provider_event_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    synchronization_state: Mapped[str] = mapped_column(String(60), nullable=False, default="synced", index=True)
    event_source: Mapped[str] = mapped_column(String(80), nullable=False, default="api")
    error_state: Mapped[str | None] = mapped_column(String(120), nullable=True)


class ChannelOrderItemRecord(FlowHubBase):
    __tablename__ = "channel_order_items"
    __table_args__ = (UniqueConstraint("order_id", "provider_item_id", name="uq_channel_order_item_provider_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    provider_item_id: Mapped[str] = mapped_column(String(180), nullable=False)
    external_product_id: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    sku: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    product_number: Mapped[str | None] = mapped_column(String(180), nullable=True)
    parent_product_number: Mapped[str | None] = mapped_column(String(180), nullable=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    canceled_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    deliverable_quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    original_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    item_status: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_summary_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class ChannelShipmentRecord(FlowHubBase):
    __tablename__ = "channel_shipments"
    __table_args__ = (UniqueConstraint("order_id", "shipment_number", name="uq_channel_order_shipment_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    shipment_number: Mapped[str] = mapped_column(String(180), nullable=False)
    status_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status_title: Mapped[str | None] = mapped_column(String(180), nullable=True)
    delivery_method: Mapped[str | None] = mapped_column(String(120), nullable=True)
    pickup_or_send_window: Mapped[str | None] = mapped_column(String(240), nullable=True)
    raw_summary_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class ChannelInvoiceRecord(FlowHubBase):
    __tablename__ = "channel_invoices"
    __table_args__ = (UniqueConstraint("order_id", "invoice_number", name="uq_channel_order_invoice_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    invoice_number: Mapped[str] = mapped_column(String(180), nullable=False)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    raw_summary_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class ChannelOrderEventRecord(FlowHubBase):
    __tablename__ = "channel_order_events"
    __table_args__ = (UniqueConstraint("channel_id", "provider_event_id", name="uq_channel_order_event_provider_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    connector_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    provider_event_id: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    provider_order_id: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    order_number: Mapped[str | None] = mapped_column(String(180), nullable=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    normalized_event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    raw_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_summary_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    state: Mapped[str] = mapped_column(String(60), nullable=False, default="accepted", index=True)
    duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)


class ChannelInventoryEffectRecord(FlowHubBase):
    __tablename__ = "channel_inventory_effects"
    __table_args__ = (
        UniqueConstraint("channel_id", "source_event_id", "provider_item_id", "effect_type", name="uq_channel_inventory_effect"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    order_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    source_event_id: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    provider_item_id: Mapped[str] = mapped_column(String(180), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    external_product_id: Mapped[str | None] = mapped_column(String(180), nullable=True)
    effect_type: Mapped[str] = mapped_column(String(80), nullable=False)
    quantity_delta: Mapped[float] = mapped_column(Float, nullable=False)
    applied_to_canonical_inventory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    state: Mapped[str] = mapped_column(String(60), nullable=False, default="proposed", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)


class OrderSyncCheckpoint(FlowHubBase):
    __tablename__ = "channel_order_sync_checkpoints"
    __table_args__ = (UniqueConstraint("channel_id", "source", name="uq_channel_order_sync_checkpoint"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    connector_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    cursor: Mapped[str | None] = mapped_column(String(300), nullable=True)
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=900)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lock_owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)


class OrderSyncAuditRecord(FlowHubBase):
    __tablename__ = "channel_order_sync_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    connector_type: Mapped[str] = mapped_column(String(80), nullable=False)
    order_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    event_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
