"""Add immutable Workspace previews and atomic source-read reservations.

Revision ID: FLOWHUB_010
Revises: FLOWHUB_009
Create Date: 2026-07-10
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "FLOWHUB_010"
down_revision = "FLOWHUB_009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not _table_exists("dl_workspace_previews"):
        op.create_table(
            "dl_workspace_previews",
            sa.Column("id", sa.String(length=120), nullable=False),
            sa.Column("source_id", sa.String(length=255), nullable=False),
            sa.Column("source_snapshot_id", sa.Integer(), nullable=False),
            sa.Column("source_integrity_hash", sa.String(length=64), nullable=False),
            sa.Column("owner_user_id", sa.Integer(), nullable=False),
            sa.Column("owner_username", sa.String(length=160), nullable=False),
            sa.Column("preview_hash", sa.String(length=64), nullable=False),
            sa.Column("rows_json", sa.JSON(), nullable=False),
            sa.Column("row_hashes_json", sa.JSON(), nullable=False),
            sa.Column("summary_json", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("ix_dl_workspace_previews_source_id", "dl_workspace_previews", ["source_id"])
    _create_index_if_missing("ix_dl_workspace_previews_source_snapshot_id", "dl_workspace_previews", ["source_snapshot_id"])
    _create_index_if_missing("ix_dl_workspace_previews_owner_user_id", "dl_workspace_previews", ["owner_user_id"])
    _create_index_if_missing("ix_dl_workspace_previews_expires_at", "dl_workspace_previews", ["expires_at"])

    if not _table_exists("dl_source_read_locks"):
        op.create_table(
            "dl_source_read_locks",
            sa.Column("source_id", sa.String(length=255), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("source_id"),
        )

    if not _table_exists("dl_source_read_reservations"):
        op.create_table(
            "dl_source_read_reservations",
            sa.Column("id", sa.String(length=120), nullable=False),
            sa.Column("source_id", sa.String(length=255), nullable=False),
            sa.Column("user_id", sa.String(length=160), nullable=False),
            sa.Column("reserved_at", sa.DateTime(), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("error_code", sa.String(length=120), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("ix_dl_source_read_reservations_source_id", "dl_source_read_reservations", ["source_id"])
    _create_index_if_missing("ix_dl_source_read_reservations_user_id", "dl_source_read_reservations", ["user_id"])
    _create_index_if_missing("ix_dl_source_read_reservations_reserved_at", "dl_source_read_reservations", ["reserved_at"])
    _create_index_if_missing("ix_dl_source_read_reservations_status", "dl_source_read_reservations", ["status"])


def downgrade() -> None:
    if _table_exists("dl_source_read_reservations"):
        op.drop_table("dl_source_read_reservations")
    if _table_exists("dl_source_read_locks"):
        op.drop_table("dl_source_read_locks")
    if _table_exists("dl_workspace_previews"):
        op.drop_table("dl_workspace_previews")


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _table_exists(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    indexes = {index["name"] for index in _inspector().get_indexes(table_name)}
    if index_name not in indexes:
        op.create_index(index_name, table_name, columns)
