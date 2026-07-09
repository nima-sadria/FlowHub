"""FLOWHUB_008 - generic write pipeline foundation

Revision ID: FLOWHUB_008
Revises: FLOWHUB_007
Create Date: 2026-07-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "FLOWHUB_008"
down_revision = "FLOWHUB_007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not _table_exists("flowhub_write_batches"):
        op.create_table(
            "flowhub_write_batches",
            sa.Column("id", sa.String(length=120), nullable=False),
            sa.Column("channel_id", sa.String(length=120), nullable=False),
            sa.Column("channel_type", sa.String(length=80), nullable=False),
            sa.Column("operation_type", sa.String(length=80), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("source_preview_id", sa.String(length=120), nullable=True),
            sa.Column("batch_hash", sa.String(length=64), nullable=False),
            sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("currency", sa.String(length=12), nullable=False, server_default=""),
            sa.Column("created_by", sa.String(length=160), nullable=False, server_default=""),
            sa.Column("approved_by", sa.String(length=160), nullable=True),
            sa.Column("approval_reason", sa.Text(), nullable=True),
            sa.Column("safety_summary_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("executed_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("ix_flowhub_write_batches_channel_id", "flowhub_write_batches", ["channel_id"])
    _create_index_if_missing("ix_flowhub_write_batches_channel_type", "flowhub_write_batches", ["channel_type"])
    _create_index_if_missing("ix_flowhub_write_batches_operation_type", "flowhub_write_batches", ["operation_type"])
    _create_index_if_missing("ix_flowhub_write_batches_status", "flowhub_write_batches", ["status"])

    if not _table_exists("flowhub_write_items"):
        op.create_table(
            "flowhub_write_items",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("batch_id", sa.String(length=120), nullable=False),
            sa.Column("channel_product_id", sa.String(length=120), nullable=False),
            sa.Column("sku", sa.String(length=160), nullable=False, server_default=""),
            sa.Column("product_name", sa.String(length=240), nullable=False, server_default=""),
            sa.Column("current_price", sa.Float(), nullable=False),
            sa.Column("proposed_price", sa.Float(), nullable=False),
            sa.Column("delta_amount", sa.Float(), nullable=False),
            sa.Column("delta_percent", sa.Float(), nullable=False),
            sa.Column("currency", sa.String(length=12), nullable=False, server_default=""),
            sa.Column("pre_write_snapshot_json", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("provider_result_json", sa.JSON(), nullable=False),
            sa.Column("error_code", sa.String(length=120), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["batch_id"], ["flowhub_write_batches.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("ix_flowhub_write_items_batch_id", "flowhub_write_items", ["batch_id"])
    _create_index_if_missing("ix_flowhub_write_items_channel_product_id", "flowhub_write_items", ["channel_product_id"])
    _create_index_if_missing("ix_flowhub_write_items_status", "flowhub_write_items", ["status"])

    if not _table_exists("flowhub_write_events"):
        op.create_table(
            "flowhub_write_events",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("batch_id", sa.String(length=120), nullable=False),
            sa.Column("item_id", sa.Integer(), nullable=True),
            sa.Column("event_type", sa.String(length=120), nullable=False),
            sa.Column("severity", sa.String(length=30), nullable=False, server_default="info"),
            sa.Column("message", sa.Text(), nullable=False, server_default=""),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("correlation_id", sa.String(length=120), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["batch_id"], ["flowhub_write_batches.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["item_id"], ["flowhub_write_items.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("ix_flowhub_write_events_batch_id", "flowhub_write_events", ["batch_id"])
    _create_index_if_missing("ix_flowhub_write_events_item_id", "flowhub_write_events", ["item_id"])
    _create_index_if_missing("ix_flowhub_write_events_event_type", "flowhub_write_events", ["event_type"])


def downgrade() -> None:
    if _table_exists("flowhub_write_events"):
        op.drop_table("flowhub_write_events")
    if _table_exists("flowhub_write_items"):
        op.drop_table("flowhub_write_items")
    if _table_exists("flowhub_write_batches"):
        op.drop_table("flowhub_write_batches")


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _table_exists(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    indexes = {index["name"] for index in _inspector().get_indexes(table_name)}
    if index_name not in indexes:
        op.create_index(index_name, table_name, columns)
