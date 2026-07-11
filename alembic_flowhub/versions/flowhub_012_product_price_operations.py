"""Add protected product multi-channel price operations.

Revision ID: FLOWHUB_012
Revises: FLOWHUB_011
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "FLOWHUB_012"
down_revision = "FLOWHUB_011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "flowhub_product_price_operations" not in tables:
        op.create_table(
            "flowhub_product_price_operations",
            sa.Column("id", sa.String(length=120), nullable=False),
            sa.Column("product_id", sa.String(length=255), nullable=False),
            sa.Column("sku", sa.String(length=160), nullable=False, server_default=""),
            sa.Column("product_name", sa.String(length=240), nullable=False, server_default=""),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("version_token", sa.String(length=64), nullable=False),
            sa.Column("created_by", sa.String(length=160), nullable=False, server_default=""),
            sa.Column("approved_by", sa.String(length=160), nullable=True),
            sa.Column("approval_reason", sa.Text(), nullable=True),
            sa.Column("summary_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("applied_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("ix_flowhub_product_price_operations_product_id", "flowhub_product_price_operations", ["product_id"])
    _create_index_if_missing("ix_flowhub_product_price_operations_status", "flowhub_product_price_operations", ["status"])

    if "flowhub_product_price_operation_items" not in tables:
        op.create_table(
            "flowhub_product_price_operation_items",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("operation_id", sa.String(length=120), nullable=False),
            sa.Column("channel_id", sa.String(length=120), nullable=False),
            sa.Column("connector_type", sa.String(length=80), nullable=False),
            sa.Column("channel_product_id", sa.String(length=255), nullable=False),
            sa.Column("sku", sa.String(length=160), nullable=False, server_default=""),
            sa.Column("current_value", sa.Float(), nullable=False),
            sa.Column("proposed_value", sa.Float(), nullable=False),
            sa.Column("currency", sa.String(length=12), nullable=False, server_default=""),
            sa.Column("unit", sa.String(length=24), nullable=False, server_default=""),
            sa.Column("outbound_value", sa.Float(), nullable=False),
            sa.Column("outbound_unit", sa.String(length=24), nullable=False, server_default=""),
            sa.Column("stale_token", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False),
            sa.Column("validation_state", sa.String(length=40), nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("result_json", sa.JSON(), nullable=False),
            sa.ForeignKeyConstraint(["operation_id"], ["flowhub_product_price_operations.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("ix_flowhub_product_price_operation_items_operation_id", "flowhub_product_price_operation_items", ["operation_id"])
    _create_index_if_missing("ix_flowhub_product_price_operation_items_channel_id", "flowhub_product_price_operation_items", ["channel_id"])
    _create_index_if_missing("ix_flowhub_product_price_operation_items_status", "flowhub_product_price_operation_items", ["status"])


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "flowhub_product_price_operation_items" in tables:
        op.drop_table("flowhub_product_price_operation_items")
    if "flowhub_product_price_operations" in tables:
        op.drop_table("flowhub_product_price_operations")


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    inspector = sa.inspect(op.get_bind())
    if index_name not in {index["name"] for index in inspector.get_indexes(table_name)}:
        op.create_index(index_name, table_name, columns)
