"""Generalize Product Pricing operation items beyond Price-only.

Revision ID: FLOWHUB_045
Revises: FLOWHUB_044
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "FLOWHUB_045"
down_revision = "FLOWHUB_044"
branch_labels = None
depends_on = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _columns(table: str) -> set[str]:
    return {str(column["name"]) for column in _inspector().get_columns(table)}


TABLE = "flowhub_product_price_operation_items"


def upgrade() -> None:
    existing = _columns(TABLE)
    dialect = op.get_bind().dialect.name

    if "field" not in existing:
        op.add_column(TABLE, sa.Column("field", sa.String(length=20), nullable=False, server_default="price"))
    if "current_status_value" not in existing:
        op.add_column(TABLE, sa.Column("current_status_value", sa.String(length=40), nullable=True))
    if "proposed_status_value" not in existing:
        op.add_column(TABLE, sa.Column("proposed_status_value", sa.String(length=40), nullable=True))

    # Price/Stock QTY operation items keep using the existing numeric columns;
    # Stock Status items use the new text columns instead and leave the
    # numeric columns null, so those columns must become nullable.
    if dialect == "sqlite":
        with op.batch_alter_table(TABLE, recreate="always") as batch:
            batch.alter_column("current_value", existing_type=sa.Float(), nullable=True)
            batch.alter_column("proposed_value", existing_type=sa.Float(), nullable=True)
            batch.alter_column("outbound_value", existing_type=sa.Float(), nullable=True)
    else:
        op.alter_column(TABLE, "current_value", existing_type=sa.Float(), nullable=True)
        op.alter_column(TABLE, "proposed_value", existing_type=sa.Float(), nullable=True)
        op.alter_column(TABLE, "outbound_value", existing_type=sa.Float(), nullable=True)

    _create_index_if_missing("ix_flowhub_product_price_operation_items_field", TABLE, ["field"])


def downgrade() -> None:
    existing = _columns(TABLE)
    dialect = op.get_bind().dialect.name
    indexes = {index["name"] for index in _inspector().get_indexes(TABLE)}
    if "ix_flowhub_product_price_operation_items_field" in indexes:
        op.drop_index("ix_flowhub_product_price_operation_items_field", table_name=TABLE)

    if dialect == "sqlite":
        with op.batch_alter_table(TABLE, recreate="always") as batch:
            batch.alter_column("current_value", existing_type=sa.Float(), nullable=False)
            batch.alter_column("proposed_value", existing_type=sa.Float(), nullable=False)
            batch.alter_column("outbound_value", existing_type=sa.Float(), nullable=False)
            if "proposed_status_value" in existing:
                batch.drop_column("proposed_status_value")
            if "current_status_value" in existing:
                batch.drop_column("current_status_value")
            if "field" in existing:
                batch.drop_column("field")
    else:
        op.alter_column(TABLE, "current_value", existing_type=sa.Float(), nullable=False)
        op.alter_column(TABLE, "proposed_value", existing_type=sa.Float(), nullable=False)
        op.alter_column(TABLE, "outbound_value", existing_type=sa.Float(), nullable=False)
        if "proposed_status_value" in existing:
            op.drop_column(TABLE, "proposed_status_value")
        if "current_status_value" in existing:
            op.drop_column(TABLE, "current_status_value")
        if "field" in existing:
            op.drop_column(TABLE, "field")


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    inspector = _inspector()
    if index_name not in {index["name"] for index in inspector.get_indexes(table_name)}:
        op.create_index(index_name, table_name, columns)
