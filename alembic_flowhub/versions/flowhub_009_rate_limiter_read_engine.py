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
    op.add_column("dl_connector_telemetry", sa.Column("queue_length", sa.Integer(), nullable=True, server_default="0"))
    op.add_column("dl_connector_telemetry", sa.Column("last_throttle_at", sa.DateTime(), nullable=True))
    op.add_column("dl_connector_telemetry", sa.Column("last_connector_delay_ms", sa.Float(), nullable=True))
    op.add_column("dl_connector_telemetry", sa.Column("last_request_duration_ms", sa.Float(), nullable=True))

    op.add_column("dl_product_cache", sa.Column("last_price", sa.Text(), nullable=True))
    op.add_column("dl_product_cache", sa.Column("last_successful_read", sa.DateTime(), nullable=True))
    op.add_column("dl_product_cache", sa.Column("last_modified", sa.String(length=100), nullable=True))
    op.add_column("dl_product_cache", sa.Column("exists", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("dl_product_cache", sa.Column("record_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("dl_product_cache", "record_hash")
    op.drop_column("dl_product_cache", "exists")
    op.drop_column("dl_product_cache", "last_modified")
    op.drop_column("dl_product_cache", "last_successful_read")
    op.drop_column("dl_product_cache", "last_price")

    op.drop_column("dl_connector_telemetry", "last_request_duration_ms")
    op.drop_column("dl_connector_telemetry", "last_connector_delay_ms")
    op.drop_column("dl_connector_telemetry", "last_throttle_at")
    op.drop_column("dl_connector_telemetry", "queue_length")
