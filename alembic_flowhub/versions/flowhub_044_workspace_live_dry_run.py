"""Persist canonical Workspace live-verification Dry Runs.

Revision ID: FLOWHUB_044
Revises: FLOWHUB_043
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

IMMUTABLE_TABLES = ("uw_dry_run_scopes",)


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _tables() -> set[str]:
    return set(_inspector().get_table_names())


def _columns(table: str) -> set[str]:
    return {str(column["name"]) for column in _inspector().get_columns(table)}


def _install_immutability(dialect: str) -> None:
    bind = op.get_bind()
    if dialect == "postgresql":
        bind.exec_driver_sql(
            "CREATE OR REPLACE FUNCTION uw_reject_immutable_mutation() "
            "RETURNS trigger AS $$ BEGIN RAISE EXCEPTION "
            "'immutable Unified Workspace record'; END; $$ LANGUAGE plpgsql"
        )
        for table in IMMUTABLE_TABLES:
            bind.exec_driver_sql(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
            bind.exec_driver_sql(
                f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
                "FOR EACH ROW EXECUTE FUNCTION uw_reject_immutable_mutation()"
            )
    else:
        for table in IMMUTABLE_TABLES:
            for operation in ("UPDATE", "DELETE"):
                bind.exec_driver_sql(
                    f"CREATE TRIGGER IF NOT EXISTS {table}_immutable_{operation.lower()} "
                    f"BEFORE {operation} ON {table} "
                    "BEGIN SELECT RAISE(ABORT, 'immutable Unified Workspace record'); END"
                )

revision = "FLOWHUB_044"
down_revision = "FLOWHUB_043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect not in {"postgresql", "sqlite"}:
        raise RuntimeError(f"FLOWHUB_044 does not support {dialect}.")
    if "uw_dry_runs" not in _tables():
        op.create_table(
            "uw_dry_runs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("workspace_id", sa.String(36), sa.ForeignKey("uw_workspaces.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("snapshot_id", sa.String(36), sa.ForeignKey("uw_workspace_snapshots.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("review_id", sa.String(36), sa.ForeignKey("uw_reviews.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("selection_version", sa.Integer(), nullable=False),
            sa.Column("selection_checksum", sa.String(64), nullable=False),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("evidence_checksum", sa.String(64), nullable=False),
            sa.Column("reviewed_count", sa.Integer(), nullable=False),
            sa.Column("write_count", sa.Integer(), nullable=False),
            sa.Column("blocker_count", sa.Integer(), nullable=False),
            sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.CheckConstraint("status IN ('running','passed','blocked','error','invalidated')", name="ck_uw_dry_run_status"),
        )
    if "uw_dry_run_scopes" not in _tables():
        op.create_table(
            "uw_dry_run_scopes",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("dry_run_id", sa.String(36), sa.ForeignKey("uw_dry_runs.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("review_item_id", sa.String(36), sa.ForeignKey("uw_review_items.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("listing_id", sa.String(36), sa.ForeignKey("uw_listings.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("channel_id", sa.String(120), sa.ForeignKey("uw_channels.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("disposition", sa.String(32), nullable=False),
            sa.Column("reason_code", sa.String(120), nullable=True),
            sa.Column("expected_before_json", sa.JSON(), nullable=False),
            sa.Column("observed_live_json", sa.JSON(), nullable=False),
            sa.Column("live_fingerprint", sa.String(64), nullable=True),
            sa.UniqueConstraint("dry_run_id", "review_item_id", name="uq_uw_dry_run_scope_item"),
        )
    _install_immutability(dialect)
    if "dry_run_id" not in _columns("uw_apply_manifests"):
        op.add_column("uw_apply_manifests", sa.Column("dry_run_id", sa.String(36), nullable=True))
    # SQLite cannot add this FK without rebuilding historical immutable tables.
    # PostgreSQL gets the durable constraint; service validation fails closed on
    # both dialects and keeps legacy cache-only manifests historical only.
    if dialect == "postgresql":
        fk_names = {item["name"] for item in _inspector().get_foreign_keys("uw_apply_manifests")}
        if "fk_uw_apply_manifests_dry_run" not in fk_names:
            op.create_foreign_key(
                "fk_uw_apply_manifests_dry_run",
                "uw_apply_manifests",
                "uw_dry_runs",
                ["dry_run_id"],
                ["id"],
                ondelete="RESTRICT",
            )
    for statement in (
        "CREATE INDEX IF NOT EXISTS ix_uw_dry_runs_review_id ON uw_dry_runs(review_id)",
        "CREATE INDEX IF NOT EXISTS ix_uw_dry_runs_selection_checksum ON uw_dry_runs(selection_checksum)",
        "CREATE INDEX IF NOT EXISTS ix_uw_dry_run_scopes_dry_run_id ON uw_dry_run_scopes(dry_run_id)",
        "CREATE INDEX IF NOT EXISTS ix_uw_apply_manifests_dry_run_id ON uw_apply_manifests(dry_run_id)",
    ):
        bind.exec_driver_sql(statement)


def downgrade() -> None:
    raise RuntimeError("FLOWHUB_044 records safety evidence and is forward-only.")
