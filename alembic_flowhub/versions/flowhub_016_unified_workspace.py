"""Add the FlowHub v1.2 unified multi-channel workspace schema.

Revision ID: FLOWHUB_016
Revises: FLOWHUB_015

The migration is additive and intentionally has no destructive downgrade.
"""

from __future__ import annotations

from sqlalchemy import text

from alembic import op
from alembic_flowhub.flowhub_016_frozen_schema import (
    POSTGRESQL_DDL,
    SQLITE_DDL,
)

revision = "FLOWHUB_016"
down_revision = "FLOWHUB_015"
branch_labels = None
depends_on = None

IMMUTABLE_TABLES = (
    "uw_currency_profiles",
    "uw_workspace_snapshots",
    "uw_snapshot_rows",
    "uw_mapping_revisions",
    "uw_draft_revisions",
    "uw_draft_revision_changes",
    "uw_review_items",
    "uw_review_cache_versions",
    "uw_audit_entries",
    "uw_apply_attempts",
    "uw_apply_attempt_events",
)


def upgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    if dialect_name == "postgresql":
        statements = POSTGRESQL_DDL
    elif dialect_name == "sqlite":
        statements = SQLITE_DDL
    else:
        raise RuntimeError(
            f"FLOWHUB_016 supports PostgreSQL and SQLite, not {dialect_name}."
        )
    for statement in statements:
        bind.exec_driver_sql(statement)
    if dialect_name == "postgresql":
        bind.execute(
            text(
                """
                CREATE OR REPLACE FUNCTION uw_reject_immutable_mutation()
                RETURNS trigger AS $$
                BEGIN
                    RAISE EXCEPTION 'immutable Unified Workspace record';
                END;
                $$ LANGUAGE plpgsql
                """
            )
        )
        for table_name in IMMUTABLE_TABLES:
            bind.execute(text(f"DROP TRIGGER IF EXISTS {table_name}_immutable ON {table_name}"))
            bind.execute(
                text(
                    f"CREATE TRIGGER {table_name}_immutable BEFORE UPDATE OR DELETE ON {table_name} "
                    "FOR EACH ROW EXECUTE FUNCTION uw_reject_immutable_mutation()"
                )
            )
    elif dialect_name == "sqlite":
        for table_name in IMMUTABLE_TABLES:
            for operation in ("UPDATE", "DELETE"):
                trigger_name = f"{table_name}_immutable_{operation.lower()}"
                bind.execute(
                    text(
                        f"CREATE TRIGGER IF NOT EXISTS {trigger_name} BEFORE {operation} ON {table_name} "
                        "BEGIN SELECT RAISE(ABORT, 'immutable Unified Workspace record'); END"
                    )
                )


def downgrade() -> None:
    """Business history is retained; destructive downgrade is forbidden."""
