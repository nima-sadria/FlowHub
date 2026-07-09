"""Add rate limiter diagnostics and product read metadata.

Revision ID: FLOWHUB_009
Revises: FLOWHUB_008
Create Date: 2026-07-09
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "FLOWHUB_009"
down_revision = "FLOWHUB_008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    _add_column_if_missing("dl_connector_telemetry", sa.Column("queue_length", sa.Integer(), nullable=True, server_default="0"))
    _add_column_if_missing("dl_connector_telemetry", sa.Column("last_throttle_at", sa.DateTime(), nullable=True))
    _add_column_if_missing("dl_connector_telemetry", sa.Column("last_connector_delay_ms", sa.Float(), nullable=True))
    _add_column_if_missing("dl_connector_telemetry", sa.Column("last_request_duration_ms", sa.Float(), nullable=True))

    _add_column_if_missing("dl_product_cache", sa.Column("last_price", sa.Text(), nullable=True))
    _add_column_if_missing("dl_product_cache", sa.Column("last_successful_read", sa.DateTime(), nullable=True))
    _add_column_if_missing("dl_product_cache", sa.Column("last_modified", sa.String(length=100), nullable=True))
    _add_column_if_missing("dl_product_cache", sa.Column("exists", sa.Boolean(), nullable=False, server_default=sa.true()))
    _add_column_if_missing("dl_product_cache", sa.Column("record_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    _drop_column_if_present("dl_product_cache", "record_hash")
    _drop_column_if_present("dl_product_cache", "exists")
    _drop_column_if_present("dl_product_cache", "last_modified")
    _drop_column_if_present("dl_product_cache", "last_successful_read")
    _drop_column_if_present("dl_product_cache", "last_price")

    _drop_column_if_present("dl_connector_telemetry", "last_request_duration_ms")
    _drop_column_if_present("dl_connector_telemetry", "last_connector_delay_ms")
    _drop_column_if_present("dl_connector_telemetry", "last_throttle_at")
    _drop_column_if_present("dl_connector_telemetry", "queue_length")


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if column.name not in _columns(table_name):
        op.add_column(table_name, column)


def _drop_column_if_present(table_name: str, column_name: str) -> None:
    if column_name in _columns(table_name):
        op.drop_column(table_name, column_name)
