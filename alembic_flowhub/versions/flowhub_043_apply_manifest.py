"""Add the immutable pre-Apply operation manifest (OD-005 / WS-002).

Revision ID: FLOWHUB_043
Revises: FLOWHUB_042

Adds `uw_apply_manifests` and `uw_apply_manifest_operations`: a checksummed,
immutable statement of the exact write operations a Review selection implies,
generated when the selection is saved so it can be shown to the user before
Apply confirmation and re-verified fresh by the server before dispatch. Also
adds nullable `apply_manifest_id`/`manifest_checksum` trace columns to the
existing `uw_apply_jobs` table.

The migration is additive, idempotent, and forward-only: manifests are
evidence of what a user was shown before approving a write, so there is no
safe reverse.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

from alembic import op

revision = "FLOWHUB_043"
down_revision = "FLOWHUB_042"
branch_labels = None
depends_on = None

IMMUTABLE_TABLES = (
    "uw_apply_manifests",
    "uw_apply_manifest_operations",
)


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _tables() -> set[str]:
    return set(_inspector().get_table_names())


def _columns(table: str) -> set[str]:
    return {str(item["name"]) for item in _inspector().get_columns(table)}


def _add(table: str, column: sa.Column[Any]) -> None:
    if column.name not in _columns(table):
        op.add_column(table, column)


def _create_manifest_tables() -> None:
    if "uw_apply_manifests" not in _tables():
        op.create_table(
            "uw_apply_manifests",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("workspace_id", sa.String(36), nullable=False),
            sa.Column("snapshot_id", sa.String(36), nullable=False),
            sa.Column("draft_revision_id", sa.String(36), nullable=False),
            sa.Column("review_id", sa.String(36), nullable=False),
            sa.Column("selection_version", sa.Integer(), nullable=False),
            sa.Column("selection_checksum", sa.String(64), nullable=False),
            sa.Column("manifest_checksum", sa.String(64), nullable=False),
            sa.Column("operation_count", sa.Integer(), nullable=False),
            sa.Column("channel_ids_json", sa.JSON(), nullable=False),
            sa.Column(
                "schema_version",
                sa.String(40),
                nullable=False,
                server_default="uw-manifest-1",
            ),
            sa.Column("created_by_user_id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["workspace_id"], ["uw_workspaces.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(
                ["snapshot_id"], ["uw_workspace_snapshots.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(
                ["draft_revision_id"], ["uw_draft_revisions.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(["review_id"], ["uw_reviews.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(
                ["created_by_user_id"], ["flowhub_users.id"], ondelete="RESTRICT"
            ),
        )
    if "uw_apply_manifest_operations" not in _tables():
        op.create_table(
            "uw_apply_manifest_operations",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("manifest_id", sa.String(36), nullable=False),
            sa.Column("review_item_id", sa.String(36), nullable=False),
            sa.Column("canonical_product_id", sa.String(36), nullable=False),
            sa.Column("listing_id", sa.String(36), nullable=False),
            sa.Column("channel_id", sa.String(120), nullable=False),
            sa.Column("field", sa.String(20), nullable=False),
            sa.Column("current_value", sa.Text(), nullable=True),
            sa.Column("target_value", sa.Text(), nullable=False),
            sa.Column("currency", sa.String(12), nullable=True),
            sa.Column("unit", sa.String(24), nullable=True),
            sa.Column("listing_payload_json", sa.JSON(), nullable=False),
            sa.Column("listing_payload_hash", sa.String(64), nullable=False),
            sa.ForeignKeyConstraint(
                ["manifest_id"], ["uw_apply_manifests.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(
                ["review_item_id"], ["uw_review_items.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(
                ["canonical_product_id"], ["uw_canonical_products.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(["listing_id"], ["uw_listings.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["channel_id"], ["uw_channels.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint(
                "manifest_id", "review_item_id", name="uq_uw_manifest_review_item"
            ),
        )


def _install_immutability(dialect: str) -> None:
    bind = op.get_bind()
    if dialect == "postgresql":
        bind.exec_driver_sql(
            "CREATE OR REPLACE FUNCTION uw_reject_immutable_mutation() "
            "RETURNS trigger AS $$ BEGIN RAISE EXCEPTION "
            "'immutable Unified Workspace record'; END; $$ LANGUAGE plpgsql"
        )
        for table_name in IMMUTABLE_TABLES:
            bind.exec_driver_sql(f"DROP TRIGGER IF EXISTS {table_name}_immutable ON {table_name}")
            bind.exec_driver_sql(
                f"CREATE TRIGGER {table_name}_immutable BEFORE UPDATE OR DELETE ON {table_name} "
                "FOR EACH ROW EXECUTE FUNCTION uw_reject_immutable_mutation()"
            )
    else:
        for table_name in IMMUTABLE_TABLES:
            for operation in ("UPDATE", "DELETE"):
                trigger_name = f"{table_name}_immutable_{operation.lower()}"
                bind.exec_driver_sql(
                    f"CREATE TRIGGER IF NOT EXISTS {trigger_name} BEFORE {operation} ON {table_name} "
                    "BEGIN SELECT RAISE(ABORT, 'immutable Unified Workspace record'); END"
                )


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect not in {"postgresql", "sqlite"}:
        raise RuntimeError(f"FLOWHUB_043 does not support {dialect}.")

    _create_manifest_tables()
    _install_immutability(dialect)

    # Plain nullable column adds do not require a table rebuild on SQLite (that
    # is only needed for constraint changes), and a batch_alter_table rebuild
    # here would trip flowhub_017's soft-FK triggers on uw_apply_jobs.
    _add("uw_apply_jobs", sa.Column("apply_manifest_id", sa.String(36), nullable=True))
    _add("uw_apply_jobs", sa.Column("manifest_checksum", sa.String(64), nullable=True))

    for statement in (
        "CREATE INDEX IF NOT EXISTS ix_uw_apply_manifests_workspace_id "
        "ON uw_apply_manifests(workspace_id)",
        "CREATE INDEX IF NOT EXISTS ix_uw_apply_manifests_review_id "
        "ON uw_apply_manifests(review_id)",
        "CREATE INDEX IF NOT EXISTS ix_uw_apply_manifests_checksum "
        "ON uw_apply_manifests(manifest_checksum)",
        "CREATE INDEX IF NOT EXISTS ix_uw_apply_manifest_ops_manifest_id "
        "ON uw_apply_manifest_operations(manifest_id)",
        "CREATE INDEX IF NOT EXISTS ix_uw_apply_manifest_ops_listing_id "
        "ON uw_apply_manifest_operations(listing_id)",
        "CREATE INDEX IF NOT EXISTS ix_uw_apply_manifest_ops_product_id "
        "ON uw_apply_manifest_operations(canonical_product_id)",
        "CREATE INDEX IF NOT EXISTS ix_uw_apply_jobs_manifest_id "
        "ON uw_apply_jobs(apply_manifest_id)",
    ):
        bind.exec_driver_sql(statement)


def downgrade() -> None:
    raise RuntimeError(
        "FLOWHUB_043 adds evidence of what a user was shown before approving a "
        "write. Restore a verified backup instead of downgrading."
    )
