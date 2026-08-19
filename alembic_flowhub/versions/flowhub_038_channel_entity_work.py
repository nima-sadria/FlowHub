"""Add the per-entity Channel Read work queue.

Independent lease scope from dl_refresh_jobs: dl_refresh_jobs stays
(connector_id, entity_type)-scoped for FULL/DEEP channel-wide work;
dl_channel_entity_work is (connector_id, entity_type, entity_id)-scoped for
LIGHT/PRODUCT targeted work, claimed by workers via SELECT ... FOR UPDATE
SKIP LOCKED. See docs/architecture/ADR_CHANNEL_READ_ARCHITECTURE.md.

Revision ID: FLOWHUB_038
Revises: FLOWHUB_037
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "FLOWHUB_038"
down_revision = "FLOWHUB_037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dl_channel_entity_work",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("connector_id", sa.String(255), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False, server_default="products"),
        sa.Column("entity_id", sa.String(255), nullable=False),
        sa.Column("parent_entity_id", sa.String(255), nullable=True),
        # pending -> running -> completed | failed | cancelled. See
        # entity_work.py for the transition rules (coalescing, supersede,
        # bounded retry with backoff).
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("strategy", sa.String(20), nullable=False, server_default="LIGHT"),
        sa.Column("reason", sa.String(50), nullable=False),
        sa.Column("latest_reason", sa.String(50), nullable=False),
        sa.Column("worker_id", sa.String(160), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(), nullable=True),
        sa.Column("latest_event_at", sa.DateTime(), nullable=False),
        sa.Column("latest_provider_event_id", sa.String(160), nullable=True),
        # Set when new evidence arrives while this row is "running"; complete_entity_work()
        # requeues to pending instead of finishing when this is newer than started_at.
        sa.Column("superseded_at", sa.DateTime(), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("failed_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_category", sa.String(80), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','running','completed','failed','cancelled')",
            name="ck_dl_channel_entity_work_status",
        ),
        sa.CheckConstraint("strategy IN ('LIGHT','FULL','DEEP')", name="ck_dl_channel_entity_work_strategy"),
    )
    op.create_index(
        "ix_dl_channel_entity_work_claim",
        "dl_channel_entity_work",
        ["status", "next_attempt_at", "latest_event_at"],
    )
    op.create_index(
        "ix_dl_channel_entity_work_connector_entity",
        "dl_channel_entity_work",
        ["connector_id", "entity_type", "entity_id"],
    )
    # Exactly one active (pending|running) row per entity -- the coalescing
    # target. Historical completed/failed rows are unlimited: they are
    # evidence for Observation Confidence, not leases.
    op.create_index(
        "uq_dl_channel_entity_work_active",
        "dl_channel_entity_work",
        ["connector_id", "entity_type", "entity_id"],
        unique=True,
        sqlite_where=sa.text("status IN ('pending', 'running')"),
        postgresql_where=sa.text("status IN ('pending', 'running')"),
    )

    op.create_table(
        "dl_channel_entity_work_receipts",
        sa.Column("work_id", sa.Integer(), nullable=False),
        sa.Column("receipt_id", sa.Integer(), nullable=False),
        sa.Column("linked_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("work_id", "receipt_id"),
        sa.ForeignKeyConstraint(["work_id"], ["dl_channel_entity_work.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["receipt_id"], ["webhook_receipts.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_dl_channel_entity_work_receipts_receipt",
        "dl_channel_entity_work_receipts",
        ["receipt_id"],
    )


def downgrade() -> None:
    raise NotImplementedError(
        "FLOWHUB_038 is forward-only; entity-work rows are audit/retry evidence."
    )
