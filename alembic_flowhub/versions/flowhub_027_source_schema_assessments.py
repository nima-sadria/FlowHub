"""Add immutable Source schema expectations, assessments, diffs, and diagnostics.

Revision ID: FLOWHUB_027
Revises: FLOWHUB_026
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op


revision = "FLOWHUB_027"
down_revision = "FLOWHUB_026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saq_mapping_schema_expectations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("mapping_revision_id", sa.String(36), nullable=False),
        sa.Column("canonicalization_version", sa.String(40), nullable=False),
        sa.Column("raw_headers_json", sa.JSON(), nullable=False),
        sa.Column("canonical_headers_json", sa.JSON(), nullable=False),
        sa.Column("raw_fingerprint", sa.String(64), nullable=False),
        sa.Column("canonical_fingerprint", sa.String(64), nullable=False),
        sa.Column("required_canonical_headers_json", sa.JSON(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sc_sources.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["mapping_revision_id"], ["sc_source_mapping_revisions.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("mapping_revision_id", name="uq_saq_mapping_schema_expectation_revision"),
        sa.UniqueConstraint("checksum", name="uq_saq_mapping_schema_expectation_checksum"),
    )
    op.create_index(
        "ix_saq_mapping_schema_expectations_source_id",
        "saq_mapping_schema_expectations",
        ["source_id"],
    )
    op.create_index(
        "ix_saq_mapping_schema_expectations_mapping_revision_id",
        "saq_mapping_schema_expectations",
        ["mapping_revision_id"],
    )
    op.create_index(
        "ix_saq_mapping_schema_expectations_source_created",
        "saq_mapping_schema_expectations",
        ["source_id", "created_at"],
    )
    op.create_table(
        "saq_schema_assessments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("observation_id", sa.String(36), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("resource_scope", sa.String(240), nullable=False),
        sa.Column("mapping_revision_id", sa.String(36), nullable=True),
        sa.Column("mapping_expectation_id", sa.String(36), nullable=True),
        sa.Column("mapping_identity", sa.String(80), nullable=False),
        sa.Column("assessment_algorithm_version", sa.String(40), nullable=False),
        sa.Column("canonicalization_version", sa.String(40), nullable=False),
        sa.Column("execution_status", sa.String(30), nullable=False),
        sa.Column("schema_status", sa.String(30), nullable=True),
        sa.Column("observed_raw_headers_json", sa.JSON(), nullable=False),
        sa.Column("observed_canonical_headers_json", sa.JSON(), nullable=False),
        sa.Column("expected_raw_headers_json", sa.JSON(), nullable=False),
        sa.Column("expected_canonical_headers_json", sa.JSON(), nullable=False),
        sa.Column("observed_raw_fingerprint", sa.String(64), nullable=True),
        sa.Column("observed_canonical_fingerprint", sa.String(64), nullable=True),
        sa.Column("expected_raw_fingerprint", sa.String(64), nullable=True),
        sa.Column("expected_canonical_fingerprint", sa.String(64), nullable=True),
        sa.Column("freshness_basis_json", sa.JSON(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("assessed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "execution_status IN ('not_run','pending','running','passed','failed','skipped','not_applicable')",
            name="ck_saq_assessment_execution_status",
        ),
        sa.CheckConstraint(
            "schema_status IS NULL OR schema_status IN ('match','drift','ambiguous','no_mapping')",
            name="ck_saq_assessment_schema_status",
        ),
        sa.CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="ck_saq_assessment_duration"),
        sa.ForeignKeyConstraint(["observation_id"], ["saq_observations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_id"], ["sc_sources.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["mapping_revision_id"], ["sc_source_mapping_revisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["mapping_expectation_id"], ["saq_mapping_schema_expectations.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "observation_id",
            "mapping_identity",
            "assessment_algorithm_version",
            name="uq_saq_assessment_identity",
        ),
        sa.UniqueConstraint("checksum", name="uq_saq_assessment_checksum"),
    )
    op.create_index("ix_saq_schema_assessments_observation_id", "saq_schema_assessments", ["observation_id"])
    op.create_index("ix_saq_schema_assessments_source_id", "saq_schema_assessments", ["source_id"])
    op.create_index(
        "ix_saq_assessments_source_status_created",
        "saq_schema_assessments",
        ["source_id", "schema_status", "created_at"],
    )
    op.create_index(
        "ix_saq_assessments_mapping_created",
        "saq_schema_assessments",
        ["mapping_revision_id", "created_at"],
    )
    op.create_index(
        "ix_saq_assessments_observation_created",
        "saq_schema_assessments",
        ["observation_id", "created_at"],
    )
    op.create_table(
        "saq_schema_drift_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("assessment_id", sa.String(36), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("change_kind", sa.String(40), nullable=False),
        sa.Column("expected_position", sa.Integer(), nullable=True),
        sa.Column("observed_position", sa.Integer(), nullable=True),
        sa.Column("expected_raw_value", sa.String(240), nullable=True),
        sa.Column("expected_canonical_value", sa.String(240), nullable=True),
        sa.Column("observed_raw_value", sa.String(240), nullable=True),
        sa.Column("observed_canonical_value", sa.String(240), nullable=True),
        sa.Column("confidence", sa.String(40), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("algorithm_version", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("sequence_number > 0", name="ck_saq_drift_sequence"),
        sa.CheckConstraint(
            "change_kind IN ('added','removed','reordered','rename_candidate','duplicate_header',"
            "'canonical_collision','required_field_missing','unsupported_shape')",
            name="ck_saq_drift_change_kind",
        ),
        sa.ForeignKeyConstraint(["assessment_id"], ["saq_schema_assessments.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("assessment_id", "sequence_number", name="uq_saq_drift_sequence"),
    )
    op.create_index("ix_saq_schema_drift_records_assessment_id", "saq_schema_drift_records", ["assessment_id"])
    op.create_index(
        "ix_saq_drift_assessment_sequence",
        "saq_schema_drift_records",
        ["assessment_id", "sequence_number"],
    )
    op.create_table(
        "saq_schema_diagnostics",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("assessment_id", sa.String(36), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("stage_id", sa.String(80), nullable=False),
        sa.Column("execution_status", sa.String(30), nullable=False),
        sa.Column("reason_code", sa.String(120), nullable=False),
        sa.Column("recommended_action_code", sa.String(120), nullable=False),
        sa.Column("action_parameters_json", sa.JSON(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("sequence_number > 0", name="ck_saq_diagnostic_sequence"),
        sa.ForeignKeyConstraint(["assessment_id"], ["saq_schema_assessments.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("assessment_id", "sequence_number", name="uq_saq_diagnostic_sequence"),
    )
    op.create_index("ix_saq_schema_diagnostics_assessment_id", "saq_schema_diagnostics", ["assessment_id"])
    op.create_index(
        "ix_saq_diagnostics_assessment_created",
        "saq_schema_diagnostics",
        ["assessment_id", "created_at"],
    )
    op.create_index(
        "ix_saq_diagnostics_reason_created",
        "saq_schema_diagnostics",
        ["reason_code", "created_at"],
    )


def downgrade() -> None:
    raise NotImplementedError(
        "FLOWHUB_027 is forward-only: downgrading would destroy immutable Source schema "
        "expectations, assessments, drift records, and diagnostics. Restore a verified backup instead."
    )
