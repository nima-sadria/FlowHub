"""Separate bounded worksheet metadata discovery from Source acquisition.

This migration is additive and forward-only.

Revision ID: FLOWHUB_033
Revises: FLOWHUB_032
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "FLOWHUB_033"
down_revision = "FLOWHUB_032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dl_source_discovery_locks",
        sa.Column("source_id", sa.String(255), primary_key=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "dl_source_discovery_reservations",
        sa.Column("id", sa.String(120), primary_key=True),
        sa.Column("source_id", sa.String(255), nullable=False),
        sa.Column("user_id", sa.String(160), nullable=False),
        sa.Column("reserved_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("error_code", sa.String(120), nullable=True),
    )
    op.create_index("ix_dl_source_discovery_reservations_source_id", "dl_source_discovery_reservations", ["source_id"])
    op.create_index("ix_dl_source_discovery_reservations_user_id", "dl_source_discovery_reservations", ["user_id"])
    op.create_index("ix_dl_source_discovery_reservations_reserved_at", "dl_source_discovery_reservations", ["reserved_at"])
    op.create_index("ix_dl_source_discovery_reservations_status", "dl_source_discovery_reservations", ["status"])
    op.create_table(
        "dl_worksheet_discovery_cache",
        sa.Column("source_id", sa.String(255), primary_key=True),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("provider_change_token", sa.String(255), nullable=True),
        sa.Column("worksheets", sa.JSON(), nullable=False),
        sa.Column("metadata_checksum", sa.String(64), nullable=False),
        sa.Column("discovered_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "dl_source_identity_validations",
        sa.Column("source_id", sa.String(255), primary_key=True),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("candidate_checksum", sa.String(64), nullable=False),
        sa.Column("source_revision_id", sa.String(255), nullable=True),
        sa.Column("valid", sa.Boolean(), nullable=False),
        sa.Column("conflicts", sa.JSON(), nullable=False),
        sa.Column("validated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    raise RuntimeError(
        "FLOWHUB_033 stores discovery accounting and metadata provenance. "
        "Restore a verified backup instead of downgrading."
    )
