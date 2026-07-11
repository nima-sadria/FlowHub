"""Add normalized channel order synchronization tables.

Revision ID: FLOWHUB_014
Revises: FLOWHUB_013
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "FLOWHUB_014"
down_revision = "FLOWHUB_013"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _create_index_if_missing(name: str, table: str, columns: list[str]) -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {idx["name"] for idx in inspector.get_indexes(table)}
    if name not in existing:
        op.create_index(name, table, columns)


def upgrade() -> None:
    tables = _tables()
    if "channel_orders" not in tables:
        op.create_table(
            "channel_orders",
            sa.Column("internal_id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("channel_id", sa.String(120), nullable=False),
            sa.Column("connector_type", sa.String(80), nullable=False),
            sa.Column("provider_order_id", sa.String(180), nullable=False),
            sa.Column("order_number", sa.String(180), nullable=True),
            sa.Column("provider_status", sa.String(120), nullable=False, server_default="UNKNOWN"),
            sa.Column("normalized_status", sa.String(80), nullable=False, server_default="unknown"),
            sa.Column("created_at_provider", sa.DateTime(), nullable=True),
            sa.Column("updated_at_provider", sa.DateTime(), nullable=True),
            sa.Column("delivery_type", sa.String(120), nullable=True),
            sa.Column("currency", sa.String(16), nullable=True),
            sa.Column("original_amount", sa.Float(), nullable=True),
            sa.Column("final_amount", sa.Float(), nullable=True),
            sa.Column("service_fee", sa.Float(), nullable=True),
            sa.Column("discount_amount", sa.Float(), nullable=True),
            sa.Column("customer_reference", sa.String(96), nullable=True),
            sa.Column("raw_hash", sa.String(64), nullable=False),
            sa.Column("raw_summary_json", sa.JSON(), nullable=False),
            sa.Column("first_seen_at", sa.DateTime(), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(), nullable=False),
            sa.Column("last_provider_event_at", sa.DateTime(), nullable=True),
            sa.Column("synchronization_state", sa.String(60), nullable=False, server_default="synced"),
            sa.Column("event_source", sa.String(80), nullable=False, server_default="api"),
            sa.Column("error_state", sa.String(120), nullable=True),
            sa.UniqueConstraint("channel_id", "provider_order_id", name="uq_channel_order_provider_id"),
        )
    for name, columns in {
        "ix_channel_orders_channel_id": ["channel_id"],
        "ix_channel_orders_connector_type": ["connector_type"],
        "ix_channel_orders_provider_order_id": ["provider_order_id"],
        "ix_channel_orders_order_number": ["order_number"],
        "ix_channel_orders_normalized_status": ["normalized_status"],
        "ix_channel_orders_synchronization_state": ["synchronization_state"],
    }.items():
        _create_index_if_missing(name, "channel_orders", columns)

    if "channel_order_items" not in tables:
        op.create_table(
            "channel_order_items",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("order_id", sa.Integer(), nullable=False),
            sa.Column("provider_item_id", sa.String(180), nullable=False),
            sa.Column("external_product_id", sa.String(180), nullable=True),
            sa.Column("sku", sa.String(180), nullable=True),
            sa.Column("product_number", sa.String(180), nullable=True),
            sa.Column("parent_product_number", sa.String(180), nullable=True),
            sa.Column("name", sa.String(300), nullable=False, server_default=""),
            sa.Column("quantity", sa.Float(), nullable=False, server_default="0"),
            sa.Column("canceled_quantity", sa.Float(), nullable=False, server_default="0"),
            sa.Column("deliverable_quantity", sa.Float(), nullable=True),
            sa.Column("original_price", sa.Float(), nullable=True),
            sa.Column("final_price", sa.Float(), nullable=True),
            sa.Column("item_status", sa.String(120), nullable=True),
            sa.Column("cancellation_reason", sa.Text(), nullable=True),
            sa.Column("raw_summary_json", sa.JSON(), nullable=False),
            sa.UniqueConstraint("order_id", "provider_item_id", name="uq_channel_order_item_provider_id"),
        )
    for name, columns in {
        "ix_channel_order_items_order_id": ["order_id"],
        "ix_channel_order_items_external_product_id": ["external_product_id"],
        "ix_channel_order_items_sku": ["sku"],
    }.items():
        _create_index_if_missing(name, "channel_order_items", columns)

    if "channel_shipments" not in tables:
        op.create_table(
            "channel_shipments",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("order_id", sa.Integer(), nullable=False),
            sa.Column("shipment_number", sa.String(180), nullable=False),
            sa.Column("status_code", sa.String(120), nullable=True),
            sa.Column("status_title", sa.String(180), nullable=True),
            sa.Column("delivery_method", sa.String(120), nullable=True),
            sa.Column("pickup_or_send_window", sa.String(240), nullable=True),
            sa.Column("raw_summary_json", sa.JSON(), nullable=False),
            sa.UniqueConstraint("order_id", "shipment_number", name="uq_channel_order_shipment_number"),
        )
    _create_index_if_missing("ix_channel_shipments_order_id", "channel_shipments", ["order_id"])

    if "channel_invoices" not in tables:
        op.create_table(
            "channel_invoices",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("order_id", sa.Integer(), nullable=False),
            sa.Column("invoice_number", sa.String(180), nullable=False),
            sa.Column("amount", sa.Float(), nullable=True),
            sa.Column("currency", sa.String(16), nullable=True),
            sa.Column("raw_summary_json", sa.JSON(), nullable=False),
            sa.UniqueConstraint("order_id", "invoice_number", name="uq_channel_order_invoice_number"),
        )
    _create_index_if_missing("ix_channel_invoices_order_id", "channel_invoices", ["order_id"])

    if "channel_order_events" not in tables:
        op.create_table(
            "channel_order_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("channel_id", sa.String(120), nullable=False),
            sa.Column("connector_type", sa.String(80), nullable=False),
            sa.Column("provider_event_id", sa.String(180), nullable=False),
            sa.Column("provider_order_id", sa.String(180), nullable=True),
            sa.Column("order_number", sa.String(180), nullable=True),
            sa.Column("event_type", sa.String(80), nullable=False),
            sa.Column("normalized_event_type", sa.String(80), nullable=False),
            sa.Column("occurred_at", sa.DateTime(), nullable=True),
            sa.Column("source", sa.String(80), nullable=False),
            sa.Column("raw_hash", sa.String(64), nullable=False),
            sa.Column("raw_summary_json", sa.JSON(), nullable=False),
            sa.Column("state", sa.String(60), nullable=False, server_default="accepted"),
            sa.Column("duplicate", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("channel_id", "provider_event_id", name="uq_channel_order_event_provider_id"),
        )
    for name, columns in {
        "ix_channel_order_events_channel_id": ["channel_id"],
        "ix_channel_order_events_connector_type": ["connector_type"],
        "ix_channel_order_events_provider_event_id": ["provider_event_id"],
        "ix_channel_order_events_provider_order_id": ["provider_order_id"],
        "ix_channel_order_events_state": ["state"],
    }.items():
        _create_index_if_missing(name, "channel_order_events", columns)

    if "channel_inventory_effects" not in tables:
        op.create_table(
            "channel_inventory_effects",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("channel_id", sa.String(120), nullable=False),
            sa.Column("order_id", sa.Integer(), nullable=True),
            sa.Column("source_event_id", sa.String(180), nullable=False),
            sa.Column("provider_item_id", sa.String(180), nullable=False),
            sa.Column("sku", sa.String(180), nullable=True),
            sa.Column("external_product_id", sa.String(180), nullable=True),
            sa.Column("effect_type", sa.String(80), nullable=False),
            sa.Column("quantity_delta", sa.Float(), nullable=False),
            sa.Column("applied_to_canonical_inventory", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("state", sa.String(60), nullable=False, server_default="proposed"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("channel_id", "source_event_id", "provider_item_id", "effect_type", name="uq_channel_inventory_effect"),
        )
    for name, columns in {
        "ix_channel_inventory_effects_channel_id": ["channel_id"],
        "ix_channel_inventory_effects_order_id": ["order_id"],
        "ix_channel_inventory_effects_source_event_id": ["source_event_id"],
        "ix_channel_inventory_effects_sku": ["sku"],
        "ix_channel_inventory_effects_state": ["state"],
    }.items():
        _create_index_if_missing(name, "channel_inventory_effects", columns)

    if "channel_order_sync_checkpoints" not in tables:
        op.create_table(
            "channel_order_sync_checkpoints",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("channel_id", sa.String(120), nullable=False),
            sa.Column("connector_type", sa.String(80), nullable=False),
            sa.Column("source", sa.String(80), nullable=False),
            sa.Column("cursor", sa.String(300), nullable=True),
            sa.Column("interval_seconds", sa.Integer(), nullable=False, server_default="900"),
            sa.Column("last_run_at", sa.DateTime(), nullable=True),
            sa.Column("next_run_at", sa.DateTime(), nullable=True),
            sa.Column("locked_at", sa.DateTime(), nullable=True),
            sa.Column("lock_owner", sa.String(120), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("channel_id", "source", name="uq_channel_order_sync_checkpoint"),
        )
    _create_index_if_missing("ix_channel_order_sync_checkpoints_channel_id", "channel_order_sync_checkpoints", ["channel_id"])

    if "channel_order_sync_audit" not in tables:
        op.create_table(
            "channel_order_sync_audit",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("channel_id", sa.String(120), nullable=False),
            sa.Column("connector_type", sa.String(80), nullable=False),
            sa.Column("order_id", sa.Integer(), nullable=True),
            sa.Column("event_name", sa.String(120), nullable=False),
            sa.Column("message", sa.Text(), nullable=False, server_default=""),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    for name, columns in {
        "ix_channel_order_sync_audit_channel_id": ["channel_id"],
        "ix_channel_order_sync_audit_order_id": ["order_id"],
        "ix_channel_order_sync_audit_event_name": ["event_name"],
    }.items():
        _create_index_if_missing(name, "channel_order_sync_audit", columns)


def downgrade() -> None:
    tables = _tables()
    for table in (
        "channel_order_sync_audit",
        "channel_order_sync_checkpoints",
        "channel_inventory_effects",
        "channel_order_events",
        "channel_invoices",
        "channel_shipments",
        "channel_order_items",
        "channel_orders",
    ):
        if table in tables:
            op.drop_table(table)
