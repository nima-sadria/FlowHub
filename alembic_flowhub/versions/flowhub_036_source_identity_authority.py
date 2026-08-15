"""Persist provider-neutral Source identity authority and local validation evidence.

This migration is additive and forward-only. Existing Mapping revisions receive
an empty authority object. Revisions with an explicit required Source Product
Key are marked as identity policy v2; all others retain v1. No provider
authority is inferred from historical key values or Channel mappings.

Revision ID: FLOWHUB_036
Revises: FLOWHUB_035
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "FLOWHUB_036"
down_revision = "FLOWHUB_035"
branch_labels = None
depends_on = None


def _suspend_mapping_revision_immutability() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.exec_driver_sql(
            "DROP TRIGGER IF EXISTS sc_source_mapping_revisions_immutable "
            "ON sc_source_mapping_revisions"
        )
        return
    bind.exec_driver_sql(
        "DROP TRIGGER IF EXISTS sc_source_mapping_revisions_immutable_update"
    )


def _restore_mapping_revision_immutability() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.exec_driver_sql(
            "CREATE TRIGGER sc_source_mapping_revisions_immutable "
            "BEFORE UPDATE OR DELETE ON sc_source_mapping_revisions "
            "FOR EACH ROW EXECUTE FUNCTION sc_reject_immutable_mutation()"
        )
        return
    bind.exec_driver_sql(
        "CREATE TRIGGER sc_source_mapping_revisions_immutable_update "
        "BEFORE UPDATE ON sc_source_mapping_revisions BEGIN "
        "SELECT RAISE(ABORT, 'immutable source revision record'); END"
    )


def _immutable(table: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.exec_driver_sql(
            "CREATE OR REPLACE FUNCTION flowhub_reject_append_only_mutation() "
            "RETURNS trigger AS $$ BEGIN RAISE EXCEPTION "
            "'append-only identity evidence'; END; $$ LANGUAGE plpgsql"
        )
        bind.exec_driver_sql(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION flowhub_reject_append_only_mutation()"
        )
        return
    for operation in ("UPDATE", "DELETE"):
        bind.exec_driver_sql(
            f"CREATE TRIGGER {table}_immutable_{operation.lower()} "
            f"BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, "
            "'append-only identity evidence'); END"
        )


def upgrade() -> None:
    op.add_column(
        "sc_source_mapping_revisions",
        sa.Column(
            "identity_authority_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column(
        "sc_source_mapping_revisions",
        sa.Column(
            "identity_policy_version",
            sa.Integer(),
            sa.CheckConstraint(
                "identity_policy_version IN (1, 2)",
                name="ck_sc_mapping_identity_policy_version",
            ),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    # identity_policy_version existed only in the request contract before
    # FLOWHUB_036. Its durable, provider-neutral signal is the required
    # Source Product Key field on the immutable Mapping aggregate. Preserve
    # that v2 guarantee without inferring an Identity Authority.
    _suspend_mapping_revision_immutability()
    op.execute(
        sa.text(
            "UPDATE sc_source_mapping_revisions AS mapping "
            "SET identity_policy_version = 2 "
            "WHERE (EXISTS ("
            "SELECT 1 FROM sc_source_field_mappings AS field "
            "WHERE field.mapping_revision_id = mapping.id "
            "AND field.field = 'source_key' AND field.required = true "
            "AND field.reference_type <> 'disabled'"
            ") AND NOT EXISTS ("
            "SELECT 1 FROM sc_source_worksheet_rule_sets AS per_sheet "
            "WHERE per_sheet.mapping_revision_id = mapping.id "
            "AND per_sheet.mode = 'per_worksheet'"
            ") OR EXISTS ("
            "SELECT 1 FROM sc_source_worksheet_rule_sets AS rule_set "
            "WHERE rule_set.mapping_revision_id = mapping.id "
            "AND rule_set.mode = 'per_worksheet' "
            "AND EXISTS ("
            "SELECT 1 FROM sc_source_worksheet_rules AS enabled_rule "
            "WHERE enabled_rule.rule_set_id = rule_set.id "
            "AND enabled_rule.enabled = true"
            ") AND NOT EXISTS ("
            "SELECT 1 FROM sc_source_worksheet_rules AS missing_rule "
            "WHERE missing_rule.rule_set_id = rule_set.id "
            "AND missing_rule.enabled = true AND NOT EXISTS ("
            "SELECT 1 FROM sc_source_worksheet_fields AS field "
            "WHERE field.worksheet_rule_id = missing_rule.id "
            "AND field.field = 'source_key' AND field.required = true "
            "AND field.reference_type <> 'disabled'"
            ")"
            ")"
            ")"
            ")"
        )
    )
    _restore_mapping_revision_immutability()

    op.create_table(
        "saq_observation_datasets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("observation_id", sa.String(36), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("resource_scope", sa.String(240), nullable=False),
        sa.Column("binding_fingerprint", sa.String(64), nullable=False),
        sa.Column("parser_version", sa.String(40), nullable=False),
        sa.Column("formula_evaluation_version", sa.String(40), nullable=False),
        sa.Column("source_snapshot_id", sa.Integer(), nullable=False),
        sa.Column("source_snapshot_version", sa.Integer(), nullable=False),
        sa.Column("workbook_checksum", sa.String(64), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("worksheet_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "source_snapshot_version > 0", name="ck_saq_dataset_snapshot_version"
        ),
        sa.CheckConstraint("row_count >= 0", name="ck_saq_dataset_row_count"),
        sa.CheckConstraint(
            "worksheet_count >= 0", name="ck_saq_dataset_worksheet_count"
        ),
        sa.ForeignKeyConstraint(
            ["observation_id"], ["saq_observations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sc_sources.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"], ["dl_source_snapshots.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "observation_id", name="uq_saq_observation_dataset_observation"
        ),
    )
    op.create_index(
        "ix_saq_observation_datasets_observation_id",
        "saq_observation_datasets",
        ["observation_id"],
    )
    op.create_index(
        "ix_saq_observation_datasets_source_id",
        "saq_observation_datasets",
        ["source_id"],
    )
    op.create_index(
        "ix_saq_observation_datasets_source_snapshot_id",
        "saq_observation_datasets",
        ["source_snapshot_id"],
    )
    op.create_index(
        "ix_saq_observation_dataset_source_scope_created",
        "saq_observation_datasets",
        ["source_id", "resource_scope", "created_at"],
    )

    op.create_table(
        "saq_observation_worksheet_datasets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("dataset_id", sa.String(36), nullable=False),
        sa.Column("worksheet_name", sa.String(240), nullable=False),
        sa.Column("worksheet_order", sa.Integer(), nullable=False),
        sa.Column("rows_json", sa.JSON(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "worksheet_order > 0", name="ck_saq_dataset_worksheet_order"
        ),
        sa.CheckConstraint(
            "row_count >= 0", name="ck_saq_dataset_worksheet_row_count"
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["saq_observation_datasets.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "dataset_id",
            "worksheet_name",
            name="uq_saq_observation_dataset_worksheet_name",
        ),
        sa.UniqueConstraint(
            "dataset_id",
            "worksheet_order",
            name="uq_saq_observation_dataset_worksheet_order",
        ),
    )
    op.create_index(
        "ix_saq_observation_worksheet_datasets_dataset_id",
        "saq_observation_worksheet_datasets",
        ["dataset_id"],
    )
    op.create_index(
        "ix_saq_observation_worksheet_dataset_order",
        "saq_observation_worksheet_datasets",
        ["dataset_id", "worksheet_order"],
    )

    op.create_table(
        "sc_mapping_identity_assessments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("mapping_revision_id", sa.String(36), nullable=False),
        sa.Column("dataset_id", sa.String(36), nullable=True),
        sa.Column("sheet_revision_id", sa.String(36), nullable=True),
        sa.Column("source_revision_kind", sa.String(40), nullable=False),
        sa.Column("source_revision_id", sa.String(120), nullable=False),
        sa.Column("identity_fingerprint", sa.String(64), nullable=False),
        sa.Column("binding_context_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("participating_row_count", sa.Integer(), nullable=False),
        sa.Column("valid_key_count", sa.Integer(), nullable=False),
        sa.Column("missing_key_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_key_count", sa.Integer(), nullable=False),
        sa.Column("duplicate_row_count", sa.Integer(), nullable=False),
        sa.Column("binding_conflict_count", sa.Integer(), nullable=False),
        sa.Column("missing_rows_json", sa.JSON(), nullable=False),
        sa.Column("duplicate_groups_json", sa.JSON(), nullable=False),
        sa.Column("binding_conflicts_json", sa.JSON(), nullable=False),
        sa.Column("mapping_references_json", sa.JSON(), nullable=False),
        sa.Column("algorithm_version", sa.String(40), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("validated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "source_revision_kind IN ('source_observation','flowhub_sheet_revision')",
            name="ck_sc_identity_assessment_revision_kind",
        ),
        sa.CheckConstraint(
            "status IN ('pass','blocked')", name="ck_sc_identity_assessment_status"
        ),
        sa.CheckConstraint(
            "participating_row_count >= 0 AND valid_key_count >= 0 "
            "AND missing_key_count >= 0 AND duplicate_key_count >= 0 "
            "AND duplicate_row_count >= 0 AND binding_conflict_count >= 0",
            name="ck_sc_identity_assessment_counts",
        ),
        sa.CheckConstraint(
            "((source_revision_kind = 'source_observation' AND dataset_id IS NOT NULL "
            "AND sheet_revision_id IS NULL) OR "
            "(source_revision_kind = 'flowhub_sheet_revision' AND dataset_id IS NULL "
            "AND sheet_revision_id IS NOT NULL))",
            name="ck_sc_identity_assessment_evidence",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sc_sources.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["mapping_revision_id"],
            ["sc_source_mapping_revisions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["saq_observation_datasets.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["sheet_revision_id"], ["sc_sheet_revisions.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "mapping_revision_id",
            "source_revision_kind",
            "source_revision_id",
            "identity_fingerprint",
            "binding_context_fingerprint",
            "algorithm_version",
            name="uq_sc_identity_assessment_revision",
        ),
        sa.UniqueConstraint("checksum", name="uq_sc_identity_assessment_checksum"),
    )
    op.create_index(
        "ix_sc_mapping_identity_assessments_source_id",
        "sc_mapping_identity_assessments",
        ["source_id"],
    )
    op.create_index(
        "ix_sc_mapping_identity_assessments_mapping_revision_id",
        "sc_mapping_identity_assessments",
        ["mapping_revision_id"],
    )
    op.create_index(
        "ix_sc_identity_assessment_source_validated",
        "sc_mapping_identity_assessments",
        ["source_id", "validated_at"],
    )

    op.create_table(
        "sc_source_product_identities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("source_key_hash", sa.String(64), nullable=False),
        sa.Column("normalized_source_key", sa.Text(), nullable=False),
        sa.Column("normalization_version", sa.String(40), nullable=False),
        sa.Column("canonical_product_id", sa.String(36), nullable=False),
        sa.Column("first_mapping_revision_id", sa.String(36), nullable=False),
        sa.Column("first_source_revision_kind", sa.String(40), nullable=False),
        sa.Column("first_source_revision_id", sa.String(120), nullable=False),
        sa.Column("first_dataset_id", sa.String(36), nullable=True),
        sa.Column("first_sheet_revision_id", sa.String(36), nullable=True),
        sa.Column(
            "identity_authority_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sc_sources.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["canonical_product_id"], ["uw_canonical_products.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["first_mapping_revision_id"],
            ["sc_source_mapping_revisions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["first_dataset_id"],
            ["saq_observation_datasets.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["first_sheet_revision_id"],
            ["sc_sheet_revisions.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "first_source_revision_kind IN "
            "('source_observation','flowhub_sheet_revision')",
            name="ck_sc_source_product_identity_revision_kind",
        ),
        sa.CheckConstraint(
            "((first_source_revision_kind = 'source_observation' "
            "AND first_dataset_id IS NOT NULL AND first_sheet_revision_id IS NULL) OR "
            "(first_source_revision_kind = 'flowhub_sheet_revision' "
            "AND first_dataset_id IS NULL AND first_sheet_revision_id IS NOT NULL))",
            name="ck_sc_source_product_identity_evidence",
        ),
        sa.UniqueConstraint(
            "source_id",
            "normalization_version",
            "source_key_hash",
            name="uq_sc_source_product_identity_key",
        ),
    )
    op.create_index(
        "ix_sc_source_product_identities_source_id",
        "sc_source_product_identities",
        ["source_id"],
    )
    op.create_index(
        "ix_sc_source_product_identities_canonical_product_id",
        "sc_source_product_identities",
        ["canonical_product_id"],
    )
    op.create_index(
        "ix_sc_source_product_identity_canonical",
        "sc_source_product_identities",
        ["canonical_product_id", "source_id"],
    )
    for table in (
        "saq_observation_datasets",
        "saq_observation_worksheet_datasets",
        "sc_mapping_identity_assessments",
        "sc_source_product_identities",
    ):
        _immutable(table)


def downgrade() -> None:
    raise RuntimeError(
        "FLOWHUB_036 stores immutable Source identity and local validation evidence. "
        "Restore a verified backup instead of downgrading."
    )
