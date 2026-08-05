"""Add durable Source Acquisition Run lifecycle persistence.

Revision ID: FLOWHUB_025
Revises: FLOWHUB_024
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op


revision = "FLOWHUB_025"
down_revision = "FLOWHUB_024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saq_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("resource_scope", sa.String(240), nullable=False, server_default="source"),
        sa.Column("trigger_kind", sa.String(30), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(240), nullable=True),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("correlation_id", sa.String(120), nullable=False),
        sa.Column("parent_run_id", sa.String(36), nullable=True),
        sa.Column("root_run_id", sa.String(36), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("result", sa.String(40), nullable=False, server_default="none"),
        sa.Column("queued_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("terminal_at", sa.DateTime(), nullable=True),
        sa.Column("cancellation_requested_at", sa.DateTime(), nullable=True),
        sa.Column("cancellation_requested_by_user_id", sa.Integer(), nullable=True),
        sa.Column("worker_id", sa.String(120), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("failure_code", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled','abandoned')",
            name="ck_saq_run_status",
        ),
        sa.CheckConstraint(
            "result IN ('observed','not_modified','content_unchanged_reparse','none')",
            name="ck_saq_run_result",
        ),
        sa.CheckConstraint(
            "(status IN ('queued','running') AND result = 'none') "
            "OR (status = 'succeeded' AND result IN "
            "('observed','not_modified','content_unchanged_reparse')) "
            "OR (status IN ('failed','cancelled','abandoned') AND result = 'none')",
            name="ck_saq_run_status_result",
        ),
        sa.CheckConstraint("attempt_number > 0", name="ck_saq_run_attempt_number"),
        sa.CheckConstraint(
            "(status IN ('queued','running') AND terminal_at IS NULL) "
            "OR (status IN ('succeeded','failed','cancelled','abandoned') "
            "AND terminal_at IS NOT NULL)",
            name="ck_saq_run_terminal_timestamp",
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sc_sources.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["flowhub_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_run_id"], ["saq_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["root_run_id"], ["saq_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["cancellation_requested_by_user_id"], ["flowhub_users.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index("ix_saq_runs_source_id", "saq_runs", ["source_id"])
    op.create_index("ix_saq_runs_actor_user_id", "saq_runs", ["actor_user_id"])
    op.create_index("ix_saq_runs_parent_run_id", "saq_runs", ["parent_run_id"])
    op.create_index("ix_saq_runs_root_run_id", "saq_runs", ["root_run_id"])
    op.create_index("ix_saq_runs_status", "saq_runs", ["status"])
    op.create_index("ix_saq_runs_source_scope_status", "saq_runs", ["source_id", "resource_scope", "status"])
    op.create_index("ix_saq_runs_correlation_id", "saq_runs", ["correlation_id"])
    op.create_index("ix_saq_runs_lease_expiry", "saq_runs", ["lease_expires_at"])
    op.create_index(
        "uq_saq_runs_idempotency_scope",
        "saq_runs",
        ["source_id", "resource_scope", "idempotency_key"],
        unique=True,
        sqlite_where=sa.text("idempotency_key IS NOT NULL"),
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_index(
        "uq_saq_runs_active_scope",
        "saq_runs",
        ["source_id", "resource_scope"],
        unique=True,
        sqlite_where=sa.text("status IN ('queued','running')"),
        postgresql_where=sa.text("status IN ('queued','running')"),
    )
    op.create_index(
        "uq_saq_runs_root_attempt",
        "saq_runs",
        ["root_run_id", "attempt_number"],
        unique=True,
    )


def downgrade() -> None:
    raise NotImplementedError(
        "FLOWHUB_025 is forward-only: downgrading would destroy Source Acquisition Run audit "
        "and retry lineage. Restore a verified backup instead."
    )
