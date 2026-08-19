"""Add explicit Workspace Source bindings and deleted Source tombstones.

Revision ID: FLOWHUB_041
Revises: FLOWHUB_040
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "FLOWHUB_041"
down_revision = "FLOWHUB_040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    columns = {item["name"] for item in sa.inspect(bind).get_columns("sc_sources")}
    if "deleted_at" not in columns:
        op.add_column("sc_sources", sa.Column("deleted_at", sa.DateTime(), nullable=True))

    if dialect_name == "sqlite":
        with op.batch_alter_table("sc_sources", recreate="always") as batch:
            batch.drop_constraint("ck_sc_source_status", type_="check")
            batch.create_check_constraint(
                "ck_sc_source_status",
                "status IN ('active','disabled','archived','deleted')",
            )
    else:
        op.drop_constraint("ck_sc_source_status", "sc_sources", type_="check")
        op.create_check_constraint(
            "ck_sc_source_status",
            "sc_sources",
            "status IN ('active','disabled','archived','deleted')",
        )

    if "uw_workspace_source_bindings" not in sa.inspect(bind).get_table_names():
        op.create_table(
            "uw_workspace_source_bindings",
            sa.Column("workspace_id", sa.String(36), nullable=False),
            sa.Column("source_id", sa.String(36), nullable=False),
            sa.Column("source_version", sa.Integer(), nullable=False),
            sa.Column("bound_by_user_id", sa.Integer(), nullable=False),
            sa.Column("bound_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ["workspace_id"], ["uw_workspaces.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(
                ["source_id"], ["sc_sources.id"], ondelete="RESTRICT"
            ),
            sa.ForeignKeyConstraint(
                ["bound_by_user_id"], ["flowhub_users.id"], ondelete="RESTRICT"
            ),
            sa.PrimaryKeyConstraint("workspace_id"),
        )
        op.create_index(
            "ix_uw_workspace_source_bindings_source_id",
            "uw_workspace_source_bindings",
            ["source_id"],
        )


def downgrade() -> None:
    raise RuntimeError(
        "FLOWHUB_041 establishes destructive Source and Workspace binding semantics. "
        "Restore a verified backup instead of downgrading."
    )
