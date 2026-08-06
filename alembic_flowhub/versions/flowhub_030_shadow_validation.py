"""Add Shadow Validation persistence schema (Pricing Migration C2)."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op


revision = "FLOWHUB_030"
down_revision = "FLOWHUB_029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sv_validation_windows",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_id", sa.String(120), nullable=False),
        sa.Column("scope_manifest_checksum", sa.String(64), nullable=False),
        sa.Column("formula_inventory_checksum", sa.String(64), nullable=False),
        sa.Column("acceptance_policy_revision", sa.String(120), nullable=False),
        sa.Column("pricing_policy_revision_id", sa.String(36), nullable=True),
        sa.Column("pricing_policy_activation_id", sa.String(36), nullable=True),
        sa.Column("pricing_authority_event_id", sa.String(36), nullable=False),
        sa.Column("pricing_authority_head_version", sa.Integer(), nullable=False),
        sa.Column("head_version_snapshot", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("opened_at", sa.DateTime(), nullable=False),
        sa.Column("closes_at", sa.DateTime(), nullable=True),
        sa.Column("evidence_freshness_seconds", sa.Integer(), nullable=True),
        sa.Column("required_distinct_matches", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("configuration_checksum", sa.String(64), nullable=False),
        sa.Column("predecessor_window_id", sa.String(36), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("required_distinct_matches >= 1", name="ck_sv_window_min_matches"),
        sa.CheckConstraint("pricing_authority_head_version >= 0", name="ck_sv_window_authority_head_version"),
        sa.CheckConstraint("head_version_snapshot >= 0", name="ck_sv_window_head_version_snapshot"),
        sa.CheckConstraint(
            "evidence_freshness_seconds IS NULL OR evidence_freshness_seconds > 0",
            name="ck_sv_window_freshness_seconds",
        ),
        sa.ForeignKeyConstraint(
            ["channel_id"], ["uw_channels.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["pricing_policy_revision_id"], ["pm_policy_revisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["pricing_policy_activation_id"], ["pm_policy_lifecycle_events.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["pricing_authority_event_id"], ["pm_channel_pricing_authority_events.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["predecessor_window_id"], ["sv_validation_windows.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["flowhub_users.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index("ix_sv_validation_windows_channel_id", "sv_validation_windows", ["channel_id"])
    op.create_index(
        "ix_sv_window_scope", "sv_validation_windows", ["scope_manifest_checksum"]
    )

    op.create_table(
        "sv_validation_window_heads",
        sa.Column("channel_id", sa.String(120), primary_key=True),
        sa.Column("current_window_id", sa.String(36), nullable=True),
        sa.Column(
            "current_state",
            sa.String(20),
            nullable=False,
            server_default="collecting",
        ),
        sa.Column("head_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("head_version >= 0", name="ck_sv_window_head_version"),
        sa.CheckConstraint(
            "current_state IN ('collecting','accepted','invalidated','closed')",
            name="ck_sv_window_head_state",
        ),
        sa.ForeignKeyConstraint(
            ["channel_id"], ["uw_channels.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["current_window_id"], ["sv_validation_windows.id"], ondelete="RESTRICT"
        ),
    )

    op.create_table(
        "sv_validation_window_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_id", sa.String(120), nullable=False),
        sa.Column("validation_window_id", sa.String(36), nullable=False),
        sa.Column("predecessor_event_id", sa.String(36), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_reference", sa.String(160), nullable=False, server_default=""),
        sa.Column("event_kind", sa.String(20), nullable=False),
        sa.Column("reason_code", sa.String(80), nullable=False),
        sa.Column("reason_payload_json", sa.JSON(), nullable=False),
        sa.Column("expected_head_version", sa.Integer(), nullable=False),
        sa.Column("head_version_snapshot", sa.Integer(), nullable=False),
        sa.Column("correlation_id", sa.String(120), nullable=False, server_default=""),
        sa.Column("configuration_checksum", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "event_kind IN ('opened','accepted','invalidated','closed','cas_conflict')",
            name="ck_sv_window_event_kind",
        ),
        sa.CheckConstraint(
            "reason_code IN ('comparison_not_possible',"
            "'comparison_contract_unavailable',"
            "'comparison_provenance_partial',"
            "'comparison_provenance_unavailable',"
            "'comparison_output_unavailable',"
            "'comparison_context_mismatch',"
            "'comparison_value_divergence',"
            "'comparison_derivation_divergence',"
            "'comparison_coverage_incomplete',"
            "'comparison_evidence_expired',"
            "'comparison_scope_invalidated',"
            "'comparison_cas_conflict',"
            "'comparison_legacy_output_unavailable',"
            "'comparison_matrix_output_unavailable',"
            "'comparison_effective_value_divergence',"
            "'comparison_candidate_value_divergence')",
            name="ck_sv_window_event_reason",
        ),
        sa.CheckConstraint("expected_head_version >= 0", name="ck_sv_window_event_head"),
        sa.CheckConstraint("head_version_snapshot >= 0", name="ck_sv_window_event_snapshot"),
        sa.ForeignKeyConstraint(["channel_id"], ["uw_channels.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["validation_window_id"], ["sv_validation_windows.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["predecessor_event_id"], ["sv_validation_window_events.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["flowhub_users.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_sv_window_event_channel", "sv_validation_window_events", ["channel_id"]
    )
    op.create_index(
        "ix_sv_window_event_validation_window_id",
        "sv_validation_window_events",
        ["validation_window_id"],
    )
    op.create_index(
        "ix_sv_window_event_predecessor",
        "sv_validation_window_events",
        ["predecessor_event_id"],
    )

    op.create_table(
        "sv_shape_comparison_contracts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("shape_id", sa.String(8), nullable=False),
        sa.Column("contract_revision", sa.String(120), nullable=False),
        sa.Column("contract_version", sa.String(40), nullable=False),
        sa.Column("formula_inventory_checksum", sa.String(64), nullable=False),
        sa.Column("contract_checksum", sa.String(64), nullable=False),
        sa.Column("target_kind", sa.String(20), nullable=False),
        sa.Column("stable_rule_identity_json", sa.JSON(), nullable=False),
        sa.Column("required_input_identity_json", sa.JSON(), nullable=False),
        sa.Column("required_output_lanes_json", sa.JSON(), nullable=False),
        sa.Column("canonical_context_json", sa.JSON(), nullable=False),
        sa.Column("equality_rule_json", sa.JSON(), nullable=False),
        sa.Column("required_trace_components_json", sa.JSON(), nullable=False),
        sa.Column("acceptance_effect", sa.String(20), nullable=False),
        sa.Column("classification_mapping_json", sa.JSON(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "target_kind IN ('price_target','non_price','quarantined','broken')",
            name="ck_sv_contract_target_kind",
        ),
        sa.CheckConstraint(
            "acceptance_effect IN ('may_count','diagnostic_only','blocks_readiness')",
            name="ck_sv_contract_acceptance_effect",
        ),
        sa.UniqueConstraint("shape_id", "contract_revision", name="uq_sv_contract_shape_revision"),
        sa.UniqueConstraint("contract_checksum", name="uq_sv_contract_checksum"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["flowhub_users.id"], ondelete="RESTRICT"
        ),
    )

    op.create_table(
        "sv_legacy_formula_captures",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_id", sa.String(120), nullable=False),
        sa.Column("frozen_evaluation_package_id", sa.String(36), nullable=False),
        sa.Column("legacy_formula_engine", sa.String(120), nullable=False),
        sa.Column("legacy_formula_engine_version", sa.String(80), nullable=False),
        sa.Column("formula_shape_id", sa.String(8), nullable=False),
        sa.Column("formula_rule_identity", sa.String(160), nullable=False),
        sa.Column("workbook_identity", sa.String(160), nullable=True),
        sa.Column("workbook_revision", sa.String(80), nullable=True),
        sa.Column("input_manifest_checksum", sa.String(64), nullable=False),
        sa.Column("pricing_authority_event_id", sa.String(36), nullable=False),
        sa.Column("pricing_authority_head_version", sa.Integer(), nullable=False),
        sa.Column("captured_at", sa.DateTime(), nullable=False),
        sa.Column("candidate_numerator", sa.BigInteger(), nullable=False),
        sa.Column("candidate_denominator", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("effective_numerator", sa.BigInteger(), nullable=False),
        sa.Column("effective_denominator", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("candidate_currency", sa.String(12), nullable=True),
        sa.Column("candidate_unit", sa.String(24), nullable=True),
        sa.Column("effective_currency", sa.String(12), nullable=True),
        sa.Column("effective_unit", sa.String(24), nullable=True),
        sa.Column("output_context_json", sa.JSON(), nullable=False),
        sa.Column("capture_checksum", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("candidate_denominator > 0", name="ck_sv_legacy_candidate_denom"),
        sa.CheckConstraint("effective_denominator > 0", name="ck_sv_legacy_effective_denom"),
        sa.UniqueConstraint(
            "frozen_evaluation_package_id",
            "formula_rule_identity",
            name="uq_sv_legacy_capture_package_rule",
        ),
        sa.ForeignKeyConstraint(
            ["channel_id"], ["uw_channels.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["frozen_evaluation_package_id"], ["pev_frozen_evaluation_packages.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["pricing_authority_event_id"],
            ["pm_channel_pricing_authority_events.id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_sv_legacy_formula_capture_channel", "sv_legacy_formula_captures", ["channel_id"]
    )
    op.create_index(
        "ix_sv_legacy_formula_capture_package",
        "sv_legacy_formula_captures",
        ["frozen_evaluation_package_id"],
    )

    op.create_table(
        "sv_shadow_comparisons",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_id", sa.String(120), nullable=False),
        sa.Column("validation_window_id", sa.String(36), nullable=False),
        sa.Column("frozen_evaluation_package_id", sa.String(36), nullable=False),
        sa.Column("legacy_formula_capture_id", sa.String(36), nullable=False),
        sa.Column("shape_id", sa.String(8), nullable=False),
        sa.Column("comparison_contract_id", sa.String(36), nullable=False),
        sa.Column("stable_rule_identity", sa.String(160), nullable=False),
        sa.Column("comparison_contract_revision", sa.String(120), nullable=False),
        sa.Column("comparison_contract_revision_checksum", sa.String(64), nullable=False),
        sa.Column("comparison_algorithm_version", sa.String(40), nullable=False),
        sa.Column("comparison_identity_checksum", sa.String(64), nullable=False),
        sa.Column("frozen_evaluation_package_checksum", sa.String(64), nullable=False),
        sa.Column("legacy_capture_checksum", sa.String(64), nullable=False),
        sa.Column("translator_version", sa.String(80), nullable=False),
        sa.Column("required_output_lanes", sa.String(20), nullable=False),
        sa.Column("confidence", sa.String(20), nullable=False),
        sa.Column("primary_classification", sa.String(80), nullable=False),
        sa.Column("secondary_classifications_json", sa.JSON(), nullable=False),
        sa.Column("legacy_vs_package_context_json", sa.JSON(), nullable=False),
        sa.Column("legacy_output_json", sa.JSON(), nullable=False),
        sa.Column("package_output_json", sa.JSON(), nullable=False),
        sa.Column("findings_json", sa.JSON(), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("reason_code", sa.String(80), nullable=True),
        sa.Column("correlation_id", sa.String(120), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "confidence IN ('verified','partial','unavailable')",
            name="ck_sv_comparison_confidence",
        ),
        sa.CheckConstraint(
            "primary_classification IN ('comparison_not_possible',"
            "'comparison_contract_unavailable',"
            "'comparison_legacy_output_unavailable',"
            "'comparison_matrix_output_unavailable',"
            "'comparison_context_mismatch',"
            "'comparison_effective_value_divergence',"
            "'comparison_candidate_value_divergence',"
            "'comparison_derivation_divergence',"
            "'comparison_match')",
            name="ck_sv_comparison_classification",
        ),
        sa.CheckConstraint(
            "reason_code IS NULL OR reason_code IN ('comparison_not_possible',"
            "'comparison_contract_unavailable',"
            "'comparison_provenance_partial',"
            "'comparison_provenance_unavailable',"
            "'comparison_output_unavailable',"
            "'comparison_context_mismatch',"
            "'comparison_value_divergence',"
            "'comparison_derivation_divergence',"
            "'comparison_coverage_incomplete',"
            "'comparison_evidence_expired',"
            "'comparison_scope_invalidated',"
            "'comparison_cas_conflict')",
            name="ck_sv_comparison_reason_code",
        ),
        sa.CheckConstraint(
            "required_output_lanes IN ('candidate','effective','both')",
            name="ck_sv_comparison_output_lanes",
        ),
        sa.ForeignKeyConstraint(
            ["channel_id"], ["uw_channels.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["validation_window_id"], ["sv_validation_windows.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["frozen_evaluation_package_id"],
            ["pev_frozen_evaluation_packages.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["legacy_formula_capture_id"], ["sv_legacy_formula_captures.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["comparison_contract_id"], ["sv_shape_comparison_contracts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["flowhub_users.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_sv_comparison_window", "sv_shadow_comparisons", ["validation_window_id"]
    )
    op.create_index(
        "ix_sv_shadow_comparisons_channel", "sv_shadow_comparisons", ["channel_id"]
    )

    op.create_table(
        "sv_validation_readiness_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("validation_window_id", sa.String(36), nullable=False),
        sa.Column("channel_id", sa.String(120), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("reason_code", sa.String(80), nullable=True),
        sa.Column("compared_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("aggregate_checksum", sa.String(64), nullable=False),
        sa.Column("required_comparison_count", sa.Integer(), nullable=False),
        sa.Column("comparison_ids_json", sa.JSON(), nullable=False),
        sa.Column("authority_event_id", sa.String(36), nullable=True),
        sa.Column("authority_head_version", sa.Integer(), nullable=True),
        sa.Column("scope_manifest_checksum", sa.String(64), nullable=False),
        sa.Column("readiness_payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "decision IN ('ready','not_ready')",
            name="ck_sv_readiness_state",
        ),
        sa.CheckConstraint(
            "reason_code IS NULL OR reason_code IN ("
            "'comparison_scope_invalidated',"
            "'comparison_evidence_expired',"
            "'comparison_coverage_incomplete',"
            "'comparison_contract_unavailable',"
            "'comparison_not_possible',"
            "'comparison_cas_conflict')",
            name="ck_sv_readiness_reason_code",
        ),
        sa.ForeignKeyConstraint(
            ["validation_window_id"], ["sv_validation_windows.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["channel_id"], ["uw_channels.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_sv_readiness_window", "sv_validation_readiness_decisions", ["validation_window_id"]
    )


def downgrade() -> None:
    raise NotImplementedError(
        "FLOWHUB_030 is forward-only: Shadow Validation evidence tables are immutable "
        "and cannot be safely downgraded."
    )
