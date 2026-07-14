"""Add source-centric mappings and versioned FlowHub Sheets.

Revision ID: FLOWHUB_018
Revises: FLOWHUB_017

The migration is additive, explicit, and forward-only.  It does not rewrite or
reinterpret any v1.2 Workspace, Snapshot, Draft, Review, Apply, or Audit row.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "FLOWHUB_018"
down_revision = "FLOWHUB_017"
branch_labels = None
depends_on = None


def _immutable(table: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.exec_driver_sql(
            "CREATE OR REPLACE FUNCTION sc_reject_immutable_mutation() "
            "RETURNS trigger AS $$ BEGIN RAISE EXCEPTION "
            "'immutable source revision record'; END; $$ LANGUAGE plpgsql"
        )
        bind.exec_driver_sql(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION sc_reject_immutable_mutation()"
        )
    else:
        for operation in ("UPDATE", "DELETE"):
            bind.exec_driver_sql(
                f"CREATE TRIGGER {table}_immutable_{operation.lower()} "
                f"BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, "
                "'immutable source revision record'); END"
            )


def upgrade() -> None:
    op.create_table(
        "sc_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("source_kind", sa.String(30), nullable=False),
        sa.Column("external_source_id", sa.String(120), nullable=True),
        sa.Column("worksheet_mode", sa.String(20), nullable=False),
        sa.Column("worksheet_name", sa.String(240), nullable=True),
        sa.Column("data_start_row", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "source_kind IN ('flowhub_sheet','imported_sheet','external')",
            name="ck_sc_source_kind",
        ),
        sa.CheckConstraint("status IN ('active','disabled')", name="ck_sc_source_status"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["flowhub_users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("external_source_id", name="uq_sc_source_external"),
    )
    op.create_index("ix_sc_sources_kind", "sc_sources", ["source_kind"])
    op.create_index("ix_sc_sources_owner", "sc_sources", ["owner_user_id"])
    op.create_index("ix_sc_sources_status", "sc_sources", ["status"])

    op.create_table(
        "sc_source_mapping_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("worksheet_mode", sa.String(20), nullable=False),
        sa.Column("worksheet_name", sa.String(240), nullable=True),
        sa.Column("data_start_row", sa.Integer(), nullable=False),
        sa.Column("value_policy_json", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sc_sources.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["flowhub_users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("source_id", "version", name="uq_sc_mapping_revision_version"),
        sa.UniqueConstraint("source_id", "checksum", name="uq_sc_mapping_revision_checksum"),
    )
    op.create_index("ix_sc_mapping_source", "sc_source_mapping_revisions", ["source_id"])

    op.create_table(
        "sc_source_field_mappings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mapping_revision_id", sa.String(36), nullable=False),
        sa.Column("field", sa.String(30), nullable=False),
        sa.Column("reference_type", sa.String(30), nullable=False),
        sa.Column("reference_value", sa.String(240), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "field IN ('name','source_key','category','brand','cost')", name="ck_sc_source_field"
        ),
        sa.CheckConstraint(
            "reference_type IN ('column_letter','header_name','column_id','disabled')",
            name="ck_sc_source_reference_type",
        ),
        sa.ForeignKeyConstraint(
            ["mapping_revision_id"], ["sc_source_mapping_revisions.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("mapping_revision_id", "field", name="uq_sc_source_field_mapping"),
    )
    op.create_index("ix_sc_source_field_revision", "sc_source_field_mappings", ["mapping_revision_id"])

    op.create_table(
        "sc_source_channel_mappings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mapping_revision_id", sa.String(36), nullable=False),
        sa.Column("channel_id", sa.String(120), nullable=False),
        sa.Column("worksheet_name", sa.String(240), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["mapping_revision_id"], ["sc_source_mapping_revisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["channel_id"], ["uw_channels.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("mapping_revision_id", "channel_id", name="uq_sc_channel_mapping"),
    )
    op.create_index("ix_sc_channel_mapping_revision", "sc_source_channel_mappings", ["mapping_revision_id"])
    op.create_index("ix_sc_channel_mapping_channel", "sc_source_channel_mappings", ["channel_id"])

    op.create_table(
        "sc_source_channel_field_mappings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_mapping_id", sa.String(36), nullable=False),
        sa.Column("field", sa.String(30), nullable=False),
        sa.Column("reference_type", sa.String(30), nullable=False),
        sa.Column("reference_value", sa.String(240), nullable=True),
        sa.CheckConstraint(
            "field IN ('external_id','price','stock','status')", name="ck_sc_channel_field"
        ),
        sa.CheckConstraint(
            "reference_type IN ('column_letter','header_name','column_id','disabled')",
            name="ck_sc_channel_reference_type",
        ),
        sa.ForeignKeyConstraint(
            ["channel_mapping_id"], ["sc_source_channel_mappings.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("channel_mapping_id", "field", name="uq_sc_channel_field_mapping"),
    )
    op.create_index("ix_sc_channel_field_mapping", "sc_source_channel_field_mappings", ["channel_mapping_id"])

    op.create_table(
        "sc_sheets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sc_sources.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["flowhub_users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("source_id", name="uq_sc_sheet_source"),
    )
    op.create_index("ix_sc_sheet_owner", "sc_sheets", ["owner_user_id"])

    op.create_table(
        "sc_sheet_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("sheet_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("formula_engine_version", sa.String(40), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("column_count", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["sheet_id"], ["sc_sheets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["flowhub_users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("sheet_id", "version", name="uq_sc_sheet_revision_version"),
        sa.UniqueConstraint("sheet_id", "checksum", name="uq_sc_sheet_revision_checksum"),
    )
    op.create_index("ix_sc_revision_sheet", "sc_sheet_revisions", ["sheet_id"])

    op.create_table(
        "sc_sheet_columns",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision_id", sa.String(36), nullable=False),
        sa.Column("column_key", sa.String(36), nullable=False),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("data_type", sa.String(30), nullable=False),
        sa.ForeignKeyConstraint(["revision_id"], ["sc_sheet_revisions.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("revision_id", "position", name="uq_sc_sheet_column_position"),
        sa.UniqueConstraint("revision_id", "column_key", name="uq_sc_sheet_column_key"),
    )
    op.create_index("ix_sc_column_revision", "sc_sheet_columns", ["revision_id"])

    op.create_table(
        "sc_sheet_rows",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision_id", sa.String(36), nullable=False),
        sa.Column("row_key", sa.String(36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["revision_id"], ["sc_sheet_revisions.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("revision_id", "row_key", name="uq_sc_sheet_row_key"),
        sa.UniqueConstraint("revision_id", "position", name="uq_sc_sheet_row_position"),
    )
    op.create_index("ix_sc_sheet_row_revision_position", "sc_sheet_rows", ["revision_id", "position"])

    op.create_table(
        "sc_sheet_cells",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("revision_id", sa.String(36), nullable=False),
        sa.Column("row_id", sa.String(36), nullable=False),
        sa.Column("column_key", sa.String(36), nullable=False),
        sa.Column("raw_value", sa.Text(), nullable=True),
        sa.Column("calculated_value", sa.Text(), nullable=True),
        sa.Column("formula_expression", sa.Text(), nullable=True),
        sa.Column("formula_dependencies_json", sa.JSON(), nullable=False),
        sa.Column("calculation_error", sa.String(120), nullable=True),
        sa.ForeignKeyConstraint(["revision_id"], ["sc_sheet_revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["row_id"], ["sc_sheet_rows.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("row_id", "column_key", name="uq_sc_sheet_cell_coordinate"),
    )
    op.create_index("ix_sc_sheet_cell_revision", "sc_sheet_cells", ["revision_id"])
    op.create_index("ix_sc_sheet_cell_row", "sc_sheet_cells", ["row_id"])
    op.create_index("ix_sc_sheet_cell_revision_column", "sc_sheet_cells", ["revision_id", "column_key"])

    op.create_table(
        "sc_sheet_import_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("sheet_id", sa.String(36), nullable=False),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("source_filename", sa.String(500), nullable=False),
        sa.Column("worksheet_name", sa.String(240), nullable=False),
        sa.Column("imported_row_count", sa.Integer(), nullable=False),
        sa.Column("mapping_version", sa.Integer(), nullable=False),
        sa.Column("source_checksum", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('validated','completed','failed')", name="ck_sc_import_status"),
        sa.ForeignKeyConstraint(["sheet_id"], ["sc_sheets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["flowhub_users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_sc_import_sheet", "sc_sheet_import_jobs", ["sheet_id"])

    op.create_table(
        "sc_data_quality_issues",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("snapshot_id", sa.String(36), nullable=True),
        sa.Column("worksheet_name", sa.String(240), nullable=True),
        sa.Column("source_row_key", sa.String(36), nullable=True),
        sa.Column("source_product_name", sa.String(240), nullable=True),
        sa.Column("mapping_state", sa.String(40), nullable=True),
        sa.Column("channel_id", sa.String(120), nullable=True),
        sa.Column("canonical_product_id", sa.String(36), nullable=True),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("code", sa.String(120), nullable=False),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("recommended_action", sa.String(1000), nullable=False),
        sa.Column("technical_details_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("severity IN ('warning','error','blocked')", name="ck_sc_issue_severity"),
        sa.ForeignKeyConstraint(["source_id"], ["sc_sources.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["uw_workspace_snapshots.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["channel_id"], ["uw_channels.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["canonical_product_id"], ["uw_canonical_products.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_sc_issue_filters", "sc_data_quality_issues", ["source_id", "channel_id", "category", "severity"])
    op.create_index("ix_sc_issue_snapshot", "sc_data_quality_issues", ["snapshot_id"])
    op.create_index("ix_sc_issue_product", "sc_data_quality_issues", ["source_product_name"])
    op.create_index("ix_sc_issue_mapping_state", "sc_data_quality_issues", ["mapping_state"])

    for table in (
        "sc_source_mapping_revisions",
        "sc_source_field_mappings",
        "sc_source_channel_mappings",
        "sc_source_channel_field_mappings",
        "sc_sheet_revisions",
        "sc_sheet_columns",
        "sc_sheet_rows",
        "sc_sheet_cells",
        "sc_sheet_import_jobs",
    ):
        _immutable(table)


def downgrade() -> None:
    raise RuntimeError("FLOWHUB_018 is forward-only to preserve Source and Sheet history")
