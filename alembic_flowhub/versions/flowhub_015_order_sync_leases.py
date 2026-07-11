"""Add production order sync lease metadata.

Revision ID: FLOWHUB_015
Revises: FLOWHUB_014
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "FLOWHUB_015"
down_revision = "FLOWHUB_014"
branch_labels = None
depends_on = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    columns = _columns("channel_order_sync_checkpoints")
    additions = {
        "lease_expires_at": sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        "lease_heartbeat_at": sa.Column("lease_heartbeat_at", sa.DateTime(), nullable=True),
        "last_success_at": sa.Column("last_success_at", sa.DateTime(), nullable=True),
        "last_failure_at": sa.Column("last_failure_at", sa.DateTime(), nullable=True),
        "last_failure_category": sa.Column("last_failure_category", sa.String(80), nullable=True),
        "last_run_id": sa.Column("last_run_id", sa.String(120), nullable=True),
    }
    for name, column in additions.items():
        if name not in columns:
            op.add_column("channel_order_sync_checkpoints", column)


def downgrade() -> None:
    columns = _columns("channel_order_sync_checkpoints")
    for name in (
        "last_run_id",
        "last_failure_category",
        "last_failure_at",
        "last_success_at",
        "lease_heartbeat_at",
        "lease_expires_at",
    ):
        if name in columns:
            op.drop_column("channel_order_sync_checkpoints", name)
