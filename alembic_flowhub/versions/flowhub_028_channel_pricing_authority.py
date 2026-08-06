"""Add per-Channel pricing-engine authority and final write evidence.

Revision ID: FLOWHUB_028
Revises: FLOWHUB_027
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256

import sqlalchemy as sa

from alembic import op


revision = "FLOWHUB_028"
down_revision = "FLOWHUB_027"
branch_labels = None
depends_on = None


def _seed_event_id(channel_id: str) -> str:
    return f"pae_{sha256(channel_id.encode('utf-8')).hexdigest()[:32]}"


def upgrade() -> None:
    op.create_table(
        "pm_channel_pricing_authority_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_id", sa.String(120), nullable=False),
        sa.Column("previous_authority", sa.String(40), nullable=True),
        sa.Column("new_authority", sa.String(40), nullable=False),
        sa.Column("expected_head_version", sa.Integer(), nullable=False),
        sa.Column("predecessor_event_id", sa.String(36), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_reference", sa.String(160), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("correlation_id", sa.String(120), nullable=False, server_default=""),
        sa.Column("request_metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "previous_authority IS NULL OR previous_authority IN "
            "('legacy_formula_engine','migration_locked','pricing_matrix')",
            name="ck_pm_authority_event_previous",
        ),
        sa.CheckConstraint(
            "new_authority IN ('legacy_formula_engine','migration_locked','pricing_matrix')",
            name="ck_pm_authority_event_new",
        ),
        sa.CheckConstraint("expected_head_version >= 0", name="ck_pm_authority_event_head_version"),
        sa.ForeignKeyConstraint(["channel_id"], ["uw_channels.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["predecessor_event_id"], ["pm_channel_pricing_authority_events.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["flowhub_users.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_pm_channel_pricing_authority_events_channel_id",
        "pm_channel_pricing_authority_events",
        ["channel_id"],
    )
    op.create_index(
        "ix_pm_channel_pricing_authority_events_new_authority",
        "pm_channel_pricing_authority_events",
        ["new_authority"],
    )
    op.create_table(
        "pm_channel_pricing_authority_heads",
        sa.Column("channel_id", sa.String(120), primary_key=True),
        sa.Column("current_authority", sa.String(40), nullable=False),
        sa.Column("effective_event_id", sa.String(36), nullable=False),
        sa.Column("head_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "current_authority IN ('legacy_formula_engine','migration_locked','pricing_matrix')",
            name="ck_pm_authority_head_current",
        ),
        sa.CheckConstraint("head_version >= 0", name="ck_pm_authority_head_version"),
        sa.ForeignKeyConstraint(["channel_id"], ["uw_channels.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["effective_event_id"], ["pm_channel_pricing_authority_events.id"], ondelete="RESTRICT"
        ),
    )
    op.add_column(
        "flowhub_provider_write_attempts",
        sa.Column("pricing_origin", sa.String(40), nullable=True),
    )
    op.add_column(
        "flowhub_provider_write_attempts",
        sa.Column("pricing_authority_event_id", sa.String(36), nullable=True),
    )
    op.add_column(
        "flowhub_provider_write_attempts",
        sa.Column("pricing_authority_head_version", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_flowhub_provider_write_attempts_pricing_origin",
        "flowhub_provider_write_attempts",
        ["pricing_origin"],
    )
    op.add_column(
        "pm_workspace_bindings",
        sa.Column("pricing_authority_event_id", sa.String(36), nullable=True),
    )
    op.add_column(
        "pm_workspace_bindings",
        sa.Column("pricing_authority_head_version", sa.Integer(), nullable=True),
    )
    op.add_column(
        "pm_workspace_bindings",
        sa.Column("expected_pricing_authority", sa.String(40), nullable=True),
    )
    op.create_table(
        "pm_pricing_authority_write_rejections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_id", sa.String(120), nullable=False),
        sa.Column("listing_id", sa.String(120), nullable=False),
        sa.Column("operation_id", sa.String(120), nullable=False),
        sa.Column("pricing_origin", sa.String(40), nullable=True),
        sa.Column("current_authority", sa.String(40), nullable=True),
        sa.Column("current_event_id", sa.String(36), nullable=True),
        sa.Column("current_head_version", sa.Integer(), nullable=True),
        sa.Column("expected_event_id", sa.String(36), nullable=True),
        sa.Column("expected_head_version", sa.Integer(), nullable=True),
        sa.Column("reason_code", sa.String(120), nullable=False),
        sa.Column("correlation_id", sa.String(120), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "pricing_origin IS NULL OR pricing_origin IN ('legacy_formula_engine','pricing_matrix')",
            name="ck_pm_authority_rejection_origin",
        ),
        sa.ForeignKeyConstraint(["channel_id"], ["uw_channels.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_pm_pricing_authority_write_rejections_channel_id",
        "pm_pricing_authority_write_rejections",
        ["channel_id"],
    )
    op.create_index(
        "ix_pm_pricing_authority_write_rejections_listing_id",
        "pm_pricing_authority_write_rejections",
        ["listing_id"],
    )
    op.create_index(
        "ix_pm_pricing_authority_write_rejections_operation_id",
        "pm_pricing_authority_write_rejections",
        ["operation_id"],
    )
    op.create_index(
        "ix_pm_pricing_authority_write_rejections_reason_code",
        "pm_pricing_authority_write_rejections",
        ["reason_code"],
    )

    bind = op.get_bind()
    channel_ids = bind.execute(sa.text("SELECT id FROM uw_channels ORDER BY id")).scalars().all()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    event_rows = []
    head_rows = []
    for channel_id in channel_ids:
        event_id = _seed_event_id(channel_id)
        event_rows.append(
            {
                "id": event_id,
                "channel_id": channel_id,
                "previous_authority": None,
                "new_authority": "legacy_formula_engine",
                "expected_head_version": 0,
                "predecessor_event_id": None,
                "actor_user_id": None,
                "actor_reference": "system:FLOWHUB_028",
                "reason": "Initial Channel pricing authority migration seed.",
                "correlation_id": "migration:FLOWHUB_028",
                "request_metadata_json": {},
                "created_at": now,
            }
        )
        head_rows.append(
            {
                "channel_id": channel_id,
                "current_authority": "legacy_formula_engine",
                "effective_event_id": event_id,
                "head_version": 0,
                "updated_at": now,
            }
        )
    if event_rows:
        op.bulk_insert(
            sa.table(
                "pm_channel_pricing_authority_events",
                sa.column("id", sa.String()),
                sa.column("channel_id", sa.String()),
                sa.column("previous_authority", sa.String()),
                sa.column("new_authority", sa.String()),
                sa.column("expected_head_version", sa.Integer()),
                sa.column("predecessor_event_id", sa.String()),
                sa.column("actor_user_id", sa.Integer()),
                sa.column("actor_reference", sa.String()),
                sa.column("reason", sa.String()),
                sa.column("correlation_id", sa.String()),
                sa.column("request_metadata_json", sa.JSON()),
                sa.column("created_at", sa.DateTime()),
            ),
            event_rows,
        )
        op.bulk_insert(
            sa.table(
                "pm_channel_pricing_authority_heads",
                sa.column("channel_id", sa.String()),
                sa.column("current_authority", sa.String()),
                sa.column("effective_event_id", sa.String()),
                sa.column("head_version", sa.Integer()),
                sa.column("updated_at", sa.DateTime()),
            ),
            head_rows,
        )


def downgrade() -> None:
    raise NotImplementedError(
        "FLOWHUB_028 is forward-only: downgrading would destroy Channel pricing-authority "
        "transition and rejected-write audit evidence. Restore a verified backup instead."
    )
