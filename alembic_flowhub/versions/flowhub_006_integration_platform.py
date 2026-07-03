"""FLOWHUB_006 - create Integration Platform tables (ip_*)

Revision ID: FLOWHUB_006
Revises: FLOWHUB_005
Create Date: 2026-07-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "FLOWHUB_006"
down_revision = "FLOWHUB_005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ip_connector_instances",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("connector_type", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("read_only", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="disabled"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ip_connector_instances_connector_type", "ip_connector_instances", ["connector_type"])

    op.create_table(
        "ip_connector_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("connector_id", sa.String(length=120), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=True),
        sa.Column("secret", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("configured", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["connector_id"], ["ip_connector_instances.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connector_id", "key", name="uq_ip_connector_setting"),
    )
    op.create_index("ix_ip_connector_settings_connector_id", "ip_connector_settings", ["connector_id"])

    op.create_table(
        "ip_connector_health_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("connector_id", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("checked_at", sa.DateTime(), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ip_connector_health_snapshots_connector_id", "ip_connector_health_snapshots", ["connector_id"])

    op.create_table(
        "ip_connector_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("connector_id", sa.String(length=120), nullable=False),
        sa.Column("event_name", sa.String(length=120), nullable=False),
        sa.Column("severity", sa.String(length=30), nullable=False, server_default="info"),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ip_connector_events_connector_id", "ip_connector_events", ["connector_id"])
    op.create_index("ix_ip_connector_events_event_name", "ip_connector_events", ["event_name"])


def downgrade() -> None:
    op.drop_table("ip_connector_events")
    op.drop_table("ip_connector_health_snapshots")
    op.drop_table("ip_connector_settings")
    op.drop_table("ip_connector_instances")
