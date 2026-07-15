"""Add immutable per-worksheet Source rule revisions.

Revision ID: FLOWHUB_019
Revises: FLOWHUB_018

The migration is additive, explicit, and forward-only. Existing FLOWHUB_018
mapping revisions remain valid and are interpreted as shared worksheet rules.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "FLOWHUB_019"
down_revision = "FLOWHUB_018"
branch_labels = None
depends_on = None


def _dialect_name() -> str:
    dialect_name = op.get_context().dialect.name
    if dialect_name not in {"postgresql", "sqlite"}:
        raise RuntimeError(f"FLOWHUB_019 does not support dialect {dialect_name!r}")
    return dialect_name


def _execute(sql: str) -> None:
    """Emit trigger DDL in online and Alembic ``--sql`` modes."""
    op.execute(sa.text(sql))


def _immutable(table: str) -> None:
    if _dialect_name() == "postgresql":
        _execute(
            "CREATE OR REPLACE FUNCTION sc_reject_immutable_mutation() "
            "RETURNS trigger AS $$ BEGIN RAISE EXCEPTION "
            "'immutable source revision record'; END; $$ LANGUAGE plpgsql"
        )
        _execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION sc_reject_immutable_mutation()"
        )
        return
    for operation in ("UPDATE", "DELETE"):
        _execute(
            f"CREATE TRIGGER {table}_immutable_{operation.lower()} "
            f"BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, "
            "'immutable source revision record'); END"
        )


def _worksheet_rule_set_guard() -> None:
    table = "sc_source_worksheet_rule_sets"
    if _dialect_name() == "postgresql":
        _execute(
            "CREATE OR REPLACE FUNCTION sc_guard_worksheet_rule_set_mutation() "
            "RETURNS trigger AS $$ BEGIN "
            "IF TG_OP = 'INSERT' THEN "
            "IF NEW.sealed THEN RAISE EXCEPTION 'worksheet rule set must start open'; END IF; "
            "RETURN NEW; "
            "ELSIF TG_OP = 'DELETE' THEN "
            "RAISE EXCEPTION 'immutable worksheet rule set'; "
            "END IF; "
            "IF OLD.sealed OR NOT NEW.sealed "
            "OR NEW.id IS DISTINCT FROM OLD.id "
            "OR NEW.mapping_revision_id IS DISTINCT FROM OLD.mapping_revision_id "
            "OR NEW.mode IS DISTINCT FROM OLD.mode "
            "OR NEW.duplicate_product_policy IS DISTINCT FROM OLD.duplicate_product_policy "
            "OR NEW.created_at IS DISTINCT FROM OLD.created_at "
            "THEN RAISE EXCEPTION 'immutable worksheet rule set'; END IF; "
            "RETURN NEW; END; $$ LANGUAGE plpgsql"
        )
        _execute(
            f"CREATE TRIGGER {table}_state_guard BEFORE INSERT OR UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION sc_guard_worksheet_rule_set_mutation()"
        )
        return
    _execute(
        f"CREATE TRIGGER {table}_open_insert BEFORE INSERT ON {table} "
        "WHEN NEW.sealed != 0 BEGIN SELECT RAISE(ABORT, "
        "'worksheet rule set must start open'); END"
    )
    _execute(
        f"CREATE TRIGGER {table}_seal_update BEFORE UPDATE ON {table} "
        "WHEN NOT (OLD.sealed = 0 AND NEW.sealed = 1 "
        "AND NEW.id IS OLD.id "
        "AND NEW.mapping_revision_id IS OLD.mapping_revision_id "
        "AND NEW.mode IS OLD.mode "
        "AND NEW.duplicate_product_policy IS OLD.duplicate_product_policy "
        "AND NEW.created_at IS OLD.created_at) "
        "BEGIN SELECT RAISE(ABORT, 'immutable worksheet rule set'); END"
    )
    _execute(
        f"CREATE TRIGGER {table}_immutable_delete BEFORE DELETE ON {table} "
        "BEGIN SELECT RAISE(ABORT, 'immutable worksheet rule set'); END"
    )


def _worksheet_child_insert_guard(
    table: str,
    *,
    postgres_from: str,
    sqlite_from: str,
) -> None:
    function_name = f"{table}_guard_insert"
    if _dialect_name() == "postgresql":
        _execute(
            f"CREATE OR REPLACE FUNCTION {function_name}() RETURNS trigger AS $$ BEGIN "
            f"PERFORM 1 {postgres_from}; "
            "IF NOT FOUND THEN RAISE EXCEPTION "
            "'worksheet rule set is sealed'; END IF; "
            "RETURN NEW; END; $$ LANGUAGE plpgsql"
        )
        _execute(
            f"CREATE TRIGGER {table}_construction_insert BEFORE INSERT ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION {function_name}()"
        )
        return
    _execute(
        f"CREATE TRIGGER {table}_construction_insert BEFORE INSERT ON {table} "
        f"WHEN NOT EXISTS (SELECT 1 {sqlite_from}) "
        "BEGIN SELECT RAISE(ABORT, 'worksheet rule set is sealed'); END"
    )


def _data_quality_scan_guard() -> None:
    table = "sc_data_quality_scans"
    if _dialect_name() == "postgresql":
        _execute(
            "CREATE OR REPLACE FUNCTION sc_guard_data_quality_scan_mutation() "
            "RETURNS trigger AS $$ BEGIN "
            "IF TG_OP = 'INSERT' THEN "
            "IF NEW.status <> 'checking' OR NEW.checked_at IS NOT NULL THEN "
            "RAISE EXCEPTION 'data quality scan must start checking'; END IF; "
            "RETURN NEW; "
            "ELSIF TG_OP = 'DELETE' THEN "
            "RAISE EXCEPTION 'immutable data quality scan'; "
            "END IF; "
            "IF OLD.status <> 'checking' "
            "OR NEW.id IS DISTINCT FROM OLD.id "
            "OR NEW.owner_user_id IS DISTINCT FROM OLD.owner_user_id "
            "OR NEW.source_id IS DISTINCT FROM OLD.source_id "
            "OR NEW.source_ids_json::text IS DISTINCT FROM OLD.source_ids_json::text "
            "OR NEW.created_at IS DISTINCT FROM OLD.created_at "
            "OR (NEW.status IN ('completed','failed') AND NEW.checked_at IS NULL) "
            "THEN RAISE EXCEPTION 'immutable data quality scan'; END IF; "
            "RETURN NEW; END; $$ LANGUAGE plpgsql"
        )
        _execute(
            f"CREATE TRIGGER {table}_state_guard BEFORE INSERT OR UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION sc_guard_data_quality_scan_mutation()"
        )
        return
    _execute(
        f"CREATE TRIGGER {table}_checking_insert BEFORE INSERT ON {table} "
        "WHEN NEW.status != 'checking' OR NEW.checked_at IS NOT NULL "
        "BEGIN SELECT RAISE(ABORT, 'data quality scan must start checking'); END"
    )
    _execute(
        f"CREATE TRIGGER {table}_state_update BEFORE UPDATE ON {table} "
        "WHEN OLD.status != 'checking' "
        "OR NEW.id IS NOT OLD.id "
        "OR NEW.owner_user_id IS NOT OLD.owner_user_id "
        "OR NEW.source_id IS NOT OLD.source_id "
        "OR NEW.source_ids_json IS NOT OLD.source_ids_json "
        "OR NEW.created_at IS NOT OLD.created_at "
        "OR (NEW.status IN ('completed','failed') AND NEW.checked_at IS NULL) "
        "BEGIN SELECT RAISE(ABORT, 'immutable data quality scan'); END"
    )
    _execute(
        f"CREATE TRIGGER {table}_immutable_delete BEFORE DELETE ON {table} "
        "BEGIN SELECT RAISE(ABORT, 'immutable data quality scan'); END"
    )


def _data_quality_issue_insert_guard() -> None:
    table = "sc_data_quality_issues"
    if _dialect_name() == "postgresql":
        _execute(
            "CREATE OR REPLACE FUNCTION sc_guard_data_quality_issue_insert() "
            "RETURNS trigger AS $$ BEGIN "
            "IF NEW.scan_id IS NULL THEN RETURN NEW; END IF; "
            "PERFORM 1 FROM sc_data_quality_scans "
            "WHERE id = NEW.scan_id AND status = 'checking' FOR UPDATE; "
            "IF NOT FOUND THEN RAISE EXCEPTION "
            "'data quality scan is not checking'; END IF; "
            "RETURN NEW; END; $$ LANGUAGE plpgsql"
        )
        _execute(
            f"CREATE TRIGGER {table}_scan_insert_guard BEFORE INSERT ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION sc_guard_data_quality_issue_insert()"
        )
        return
    _execute(
        f"CREATE TRIGGER {table}_scan_insert_guard BEFORE INSERT ON {table} "
        "WHEN NEW.scan_id IS NOT NULL AND NOT EXISTS ("
        "SELECT 1 FROM sc_data_quality_scans "
        "WHERE id = NEW.scan_id AND status = 'checking') "
        "BEGIN SELECT RAISE(ABORT, 'data quality scan is not checking'); END"
    )


def _data_quality_scan_source_insert_guard() -> None:
    table = "sc_data_quality_scan_sources"
    if _dialect_name() == "postgresql":
        _execute(
            "CREATE OR REPLACE FUNCTION sc_guard_data_quality_scan_source_insert() "
            "RETURNS trigger AS $$ BEGIN "
            "PERFORM 1 FROM sc_data_quality_scans "
            "WHERE id = NEW.scan_id AND status = 'checking' FOR UPDATE; "
            "IF NOT FOUND THEN RAISE EXCEPTION "
            "'data quality scan is not checking'; END IF; "
            "RETURN NEW; END; $$ LANGUAGE plpgsql"
        )
        _execute(
            f"CREATE TRIGGER {table}_scan_insert_guard BEFORE INSERT ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION sc_guard_data_quality_scan_source_insert()"
        )
        return
    _execute(
        f"CREATE TRIGGER {table}_scan_insert_guard BEFORE INSERT ON {table} "
        "WHEN NOT EXISTS (SELECT 1 FROM sc_data_quality_scans "
        "WHERE id = NEW.scan_id AND status = 'checking') "
        "BEGIN SELECT RAISE(ABORT, 'data quality scan is not checking'); END"
    )


def _data_quality_issues_v18() -> sa.Table:
    """Frozen FLOWHUB_018 shape used for deterministic SQLite batch SQL."""
    metadata = sa.MetaData()
    sa.Table("sc_sources", metadata, sa.Column("id", sa.String(36)))
    sa.Table("uw_workspace_snapshots", metadata, sa.Column("id", sa.String(36)))
    sa.Table("uw_channels", metadata, sa.Column("id", sa.String(120)))
    sa.Table("uw_canonical_products", metadata, sa.Column("id", sa.String(36)))
    table = sa.Table(
        "sc_data_quality_issues",
        metadata,
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
        sa.CheckConstraint(
            "severity IN ('warning','error','blocked')",
            name="ck_sc_issue_severity",
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sc_sources.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["uw_workspace_snapshots.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["channel_id"], ["uw_channels.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["canonical_product_id"],
            ["uw_canonical_products.id"],
            ondelete="RESTRICT",
        ),
    )
    sa.Index(
        "ix_sc_issue_filters",
        table.c.source_id,
        table.c.channel_id,
        table.c.category,
        table.c.severity,
    )
    sa.Index("ix_sc_issue_snapshot", table.c.snapshot_id)
    sa.Index("ix_sc_issue_product", table.c.source_product_name)
    sa.Index("ix_sc_issue_mapping_state", table.c.mapping_state)
    return table


def upgrade() -> None:
    dialect_name = _dialect_name()
    op.create_table(
        "sc_data_quality_scans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=True),
        sa.Column("source_ids_json", sa.JSON(), nullable=False),
        sa.Column("source_results_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("sources_checked", sa.Integer(), nullable=False),
        sa.Column("products_checked", sa.Integer(), nullable=False),
        sa.Column("issue_count", sa.Integer(), nullable=False),
        sa.Column("blocking_issue_count", sa.Integer(), nullable=False),
        sa.Column("warning_count", sa.Integer(), nullable=False),
        sa.Column("affected_product_count", sa.Integer(), nullable=False),
        sa.Column("affected_channel_count", sa.Integer(), nullable=False),
        sa.Column("affected_source_count", sa.Integer(), nullable=False),
        sa.Column("previous_issue_count", sa.Integer(), nullable=True),
        sa.Column("resolved_since_previous", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("checked_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('checking','completed','failed')",
            name="ck_sc_data_quality_scan_status",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["flowhub_users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sc_sources.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_sc_data_quality_scan_owner_created",
        "sc_data_quality_scans",
        ["owner_user_id", "created_at"],
    )
    op.create_index(
        "ix_sc_data_quality_scan_source_created",
        "sc_data_quality_scans",
        ["source_id", "created_at"],
    )
    op.create_index(
        "ix_sc_data_quality_scans_owner_user_id",
        "sc_data_quality_scans",
        ["owner_user_id"],
    )
    op.create_index(
        "ix_sc_data_quality_scans_source_id",
        "sc_data_quality_scans",
        ["source_id"],
    )
    op.create_index(
        "ix_sc_data_quality_scans_status",
        "sc_data_quality_scans",
        ["status"],
    )
    op.create_table(
        "sc_data_quality_scan_sources",
        sa.Column("scan_id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), primary_key=True),
        sa.ForeignKeyConstraint(
            ["scan_id"], ["sc_data_quality_scans.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sc_sources.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_sc_data_quality_scan_source_scope",
        "sc_data_quality_scan_sources",
        ["source_id", "scan_id"],
    )
    if dialect_name == "sqlite":
        with op.batch_alter_table(
            "sc_data_quality_issues",
            copy_from=_data_quality_issues_v18(),
        ) as batch_op:
            batch_op.alter_column(
                "source_row_key",
                existing_type=sa.String(36),
                type_=sa.String(512),
                existing_nullable=True,
            )
            batch_op.add_column(sa.Column("scan_id", sa.String(36), nullable=True))
            batch_op.create_foreign_key(
                "fk_sc_data_quality_issue_scan",
                "sc_data_quality_scans",
                ["scan_id"],
                ["id"],
                ondelete="RESTRICT",
            )
            batch_op.create_index("ix_sc_data_quality_issues_scan_id", ["scan_id"])
    else:
        op.alter_column(
            "sc_data_quality_issues",
            "source_row_key",
            existing_type=sa.String(36),
            type_=sa.String(512),
            existing_nullable=True,
        )
        op.add_column(
            "sc_data_quality_issues",
            sa.Column("scan_id", sa.String(36), nullable=True),
        )
        op.create_foreign_key(
            "fk_sc_data_quality_issue_scan",
            "sc_data_quality_issues",
            "sc_data_quality_scans",
            ["scan_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        op.create_index(
            "ix_sc_data_quality_issues_scan_id",
            "sc_data_quality_issues",
            ["scan_id"],
        )

    op.create_table(
        "sc_source_worksheet_rule_sets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mapping_revision_id", sa.String(36), nullable=False),
        sa.Column("mode", sa.String(30), nullable=False),
        sa.Column("duplicate_product_policy", sa.String(30), nullable=False),
        sa.Column("sealed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("mode IN ('shared','per_worksheet')", name="ck_sc_worksheet_rule_mode"),
        sa.CheckConstraint(
            "duplicate_product_policy IN ('block','last_sheet_wins')",
            name="ck_sc_worksheet_duplicate_policy",
        ),
        sa.ForeignKeyConstraint(
            ["mapping_revision_id"],
            ["sc_source_mapping_revisions.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("mapping_revision_id", name="uq_sc_worksheet_rule_set_revision"),
    )
    op.create_index(
        "ix_sc_worksheet_rule_set_revision",
        "sc_source_worksheet_rule_sets",
        ["mapping_revision_id"],
    )

    op.create_table(
        "sc_source_worksheet_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("rule_set_id", sa.String(36), nullable=False),
        sa.Column("worksheet_name", sa.String(240), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("data_start_row", sa.Integer(), nullable=False),
        sa.Column("value_policy_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["rule_set_id"], ["sc_source_worksheet_rule_sets.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("rule_set_id", "worksheet_name", name="uq_sc_worksheet_rule_name"),
    )
    op.create_index(
        "ix_sc_worksheet_rule_set",
        "sc_source_worksheet_rules",
        ["rule_set_id"],
    )

    op.create_table(
        "sc_source_worksheet_fields",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("worksheet_rule_id", sa.String(36), nullable=False),
        sa.Column("field", sa.String(30), nullable=False),
        sa.Column("reference_type", sa.String(30), nullable=False),
        sa.Column("reference_value", sa.String(240), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "field IN ('name','source_key','category','brand','cost')",
            name="ck_sc_worksheet_source_field",
        ),
        sa.CheckConstraint(
            "reference_type IN ('column_letter','header_name','column_id','disabled')",
            name="ck_sc_worksheet_source_reference_type",
        ),
        sa.ForeignKeyConstraint(
            ["worksheet_rule_id"], ["sc_source_worksheet_rules.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "worksheet_rule_id", "field", name="uq_sc_worksheet_source_field"
        ),
    )
    op.create_index(
        "ix_sc_worksheet_source_field_rule",
        "sc_source_worksheet_fields",
        ["worksheet_rule_id"],
    )

    op.create_table(
        "sc_source_worksheet_channels",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("worksheet_rule_id", sa.String(36), nullable=False),
        sa.Column("channel_id", sa.String(120), nullable=False),
        sa.Column("worksheet_name", sa.String(240), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["worksheet_rule_id"], ["sc_source_worksheet_rules.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["channel_id"], ["uw_channels.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "worksheet_rule_id", "channel_id", name="uq_sc_worksheet_channel"
        ),
    )
    op.create_index(
        "ix_sc_worksheet_channel_rule",
        "sc_source_worksheet_channels",
        ["worksheet_rule_id"],
    )
    op.create_index(
        "ix_sc_worksheet_channel_identity",
        "sc_source_worksheet_channels",
        ["channel_id"],
    )

    op.create_table(
        "sc_source_worksheet_channel_fields",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("worksheet_channel_mapping_id", sa.String(36), nullable=False),
        sa.Column("field", sa.String(30), nullable=False),
        sa.Column("reference_type", sa.String(30), nullable=False),
        sa.Column("reference_value", sa.String(240), nullable=True),
        sa.CheckConstraint(
            "field IN ('external_id','price','stock','status')",
            name="ck_sc_worksheet_channel_field",
        ),
        sa.CheckConstraint(
            "reference_type IN ('column_letter','header_name','column_id','disabled')",
            name="ck_sc_worksheet_channel_reference_type",
        ),
        sa.ForeignKeyConstraint(
            ["worksheet_channel_mapping_id"],
            ["sc_source_worksheet_channels.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "worksheet_channel_mapping_id",
            "field",
            name="uq_sc_worksheet_channel_field",
        ),
    )
    op.create_index(
        "ix_sc_worksheet_channel_field_mapping",
        "sc_source_worksheet_channel_fields",
        ["worksheet_channel_mapping_id"],
    )

    _data_quality_scan_guard()
    _data_quality_scan_source_insert_guard()
    _immutable("sc_data_quality_scan_sources")
    _data_quality_issue_insert_guard()
    _immutable("sc_data_quality_issues")

    _worksheet_rule_set_guard()
    _worksheet_child_insert_guard(
        "sc_source_worksheet_rules",
        postgres_from=(
            "FROM sc_source_worksheet_rule_sets rs "
            "WHERE rs.id = NEW.rule_set_id AND NOT rs.sealed FOR UPDATE"
        ),
        sqlite_from=(
            "FROM sc_source_worksheet_rule_sets rs "
            "WHERE rs.id = NEW.rule_set_id AND rs.sealed = 0"
        ),
    )
    _worksheet_child_insert_guard(
        "sc_source_worksheet_fields",
        postgres_from=(
            "FROM sc_source_worksheet_rules r "
            "JOIN sc_source_worksheet_rule_sets rs ON rs.id = r.rule_set_id "
            "WHERE r.id = NEW.worksheet_rule_id AND NOT rs.sealed FOR UPDATE OF rs"
        ),
        sqlite_from=(
            "FROM sc_source_worksheet_rules r "
            "JOIN sc_source_worksheet_rule_sets rs ON rs.id = r.rule_set_id "
            "WHERE r.id = NEW.worksheet_rule_id AND rs.sealed = 0"
        ),
    )
    _worksheet_child_insert_guard(
        "sc_source_worksheet_channels",
        postgres_from=(
            "FROM sc_source_worksheet_rules r "
            "JOIN sc_source_worksheet_rule_sets rs ON rs.id = r.rule_set_id "
            "WHERE r.id = NEW.worksheet_rule_id AND NOT rs.sealed FOR UPDATE OF rs"
        ),
        sqlite_from=(
            "FROM sc_source_worksheet_rules r "
            "JOIN sc_source_worksheet_rule_sets rs ON rs.id = r.rule_set_id "
            "WHERE r.id = NEW.worksheet_rule_id AND rs.sealed = 0"
        ),
    )
    _worksheet_child_insert_guard(
        "sc_source_worksheet_channel_fields",
        postgres_from=(
            "FROM sc_source_worksheet_channels c "
            "JOIN sc_source_worksheet_rules r ON r.id = c.worksheet_rule_id "
            "JOIN sc_source_worksheet_rule_sets rs ON rs.id = r.rule_set_id "
            "WHERE c.id = NEW.worksheet_channel_mapping_id "
            "AND NOT rs.sealed FOR UPDATE OF rs"
        ),
        sqlite_from=(
            "FROM sc_source_worksheet_channels c "
            "JOIN sc_source_worksheet_rules r ON r.id = c.worksheet_rule_id "
            "JOIN sc_source_worksheet_rule_sets rs ON rs.id = r.rule_set_id "
            "WHERE c.id = NEW.worksheet_channel_mapping_id AND rs.sealed = 0"
        ),
    )
    for table in (
        "sc_source_worksheet_rules",
        "sc_source_worksheet_fields",
        "sc_source_worksheet_channels",
        "sc_source_worksheet_channel_fields",
    ):
        _immutable(table)


def downgrade() -> None:
    raise RuntimeError("FLOWHUB_019 is forward-only to preserve worksheet rule history")
