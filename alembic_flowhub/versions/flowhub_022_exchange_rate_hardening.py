"""Harden exchange-rate scheduling, budgeting, and snapshot identity.

Revision ID: FLOWHUB_022
Revises: FLOWHUB_021
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "FLOWHUB_022"
down_revision = "FLOWHUB_021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    provider_columns = (
        sa.Column("request_completed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider_daily_usage", sa.Integer(), nullable=True),
        sa.Column("provider_hourly_usage", sa.Integer(), nullable=True),
        sa.Column("provider_monthly_usage", sa.Integer(), nullable=True),
        sa.Column("provider_last_use", sa.String(80), nullable=True),
        sa.Column("usage_reconciled_at", sa.DateTime(), nullable=True),
        sa.Column("usage_next_sync_at", sa.DateTime(), nullable=True),
        sa.Column("usage_status", sa.String(30), nullable=False, server_default="unknown"),
        sa.Column("usage_error_code", sa.String(80), nullable=True),
        sa.Column("next_refresh_at", sa.DateTime(), nullable=True),
        sa.Column("last_scheduled_refresh_at", sa.DateTime(), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("authentication_blocked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("schedule_timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("refresh_lock_token", sa.String(64), nullable=True),
        sa.Column("runner_id", sa.String(160), nullable=True),
        sa.Column("runner_state", sa.String(30), nullable=True),
        sa.Column("runner_heartbeat_at", sa.DateTime(), nullable=True),
    )
    for column in provider_columns:
        op.add_column("fh_exchange_rate_providers", column)

    op.add_column(
        "fh_exchange_rate_snapshots",
        sa.Column("classification", sa.String(80), nullable=False, server_default="market"),
    )
    op.add_column(
        "fh_exchange_rate_snapshots",
        sa.Column("side", sa.String(20), nullable=True),
    )
    op.add_column(
        "fh_exchange_rate_snapshots",
        sa.Column("source_key", sa.String(64), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE fh_exchange_rate_snapshots
            SET classification = COALESCE(
                    (SELECT d.classification
                     FROM fh_exchange_rate_definitions d
                     WHERE d.provider_id = fh_exchange_rate_snapshots.provider_id
                       AND d.external_symbol = fh_exchange_rate_snapshots.external_symbol),
                    'market'
                ),
                side = (
                    SELECT d.side
                    FROM fh_exchange_rate_definitions d
                    WHERE d.provider_id = fh_exchange_rate_snapshots.provider_id
                      AND d.external_symbol = fh_exchange_rate_snapshots.external_symbol
                )
            """
        )
    )
    op.create_index(
        "uq_fh_rate_snapshot_source_key",
        "fh_exchange_rate_snapshots",
        ["source_key"],
        unique=True,
    )

    op.add_column(
        "fh_exchange_rate_selections",
        sa.Column("canonical_code", sa.String(120), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE fh_exchange_rate_selections
            SET canonical_code = (
                SELECT d.canonical_code
                FROM fh_exchange_rate_definitions d
                WHERE d.provider_id = fh_exchange_rate_selections.provider_id
                  AND d.external_symbol = fh_exchange_rate_selections.external_symbol
            )
            """
        )
    )


def downgrade() -> None:
    op.drop_column("fh_exchange_rate_selections", "canonical_code")
    op.drop_index(
        "uq_fh_rate_snapshot_source_key",
        table_name="fh_exchange_rate_snapshots",
    )
    op.drop_column("fh_exchange_rate_snapshots", "source_key")
    op.drop_column("fh_exchange_rate_snapshots", "side")
    op.drop_column("fh_exchange_rate_snapshots", "classification")

    for name in (
        "runner_heartbeat_at",
        "runner_state",
        "runner_id",
        "refresh_lock_token",
        "schedule_timezone",
        "authentication_blocked",
        "consecutive_failures",
        "last_scheduled_refresh_at",
        "next_refresh_at",
        "usage_error_code",
        "usage_status",
        "usage_next_sync_at",
        "usage_reconciled_at",
        "provider_last_use",
        "provider_monthly_usage",
        "provider_hourly_usage",
        "provider_daily_usage",
        "request_completed_count",
    ):
        op.drop_column("fh_exchange_rate_providers", name)
