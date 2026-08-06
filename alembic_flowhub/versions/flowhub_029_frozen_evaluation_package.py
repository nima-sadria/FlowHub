"""Add the Frozen Evaluation Package foundation (Pricing Migration Phase B).

Revision ID: FLOWHUB_029
Revises: FLOWHUB_028
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op


revision = "FLOWHUB_029"
down_revision = "FLOWHUB_028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pev_frozen_evaluation_packages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=True),
        sa.Column("channel_id", sa.String(120), nullable=False),
        sa.Column("product_ref", sa.String(120), nullable=False),
        sa.Column("workspace_pricing_evaluated_at", sa.DateTime(), nullable=False),
        sa.Column("pricing_policy_revision_id", sa.String(36), nullable=True),
        sa.Column("formula_shape_id", sa.String(8), nullable=False),
        sa.Column("translator_version", sa.String(80), nullable=False),
        sa.Column("fx_snapshot_id", sa.String(36), nullable=True),
        sa.Column("currency_unit_registry_version", sa.String(40), nullable=False),
        sa.Column("channel_config_revision_id", sa.String(36), nullable=True),
        sa.Column("mapping_revision_id", sa.String(36), nullable=True),
        sa.Column("product_metadata_fingerprint", sa.String(64), nullable=True),
        sa.Column("arithmetic_version", sa.String(40), nullable=False),
        sa.Column("dependency_fingerprint", sa.String(64), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "workspace_pricing_evaluated_at IS NOT NULL", name="ck_pev_package_evaluated_at"
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["uw_workspaces.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["channel_id"], ["uw_channels.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["pricing_policy_revision_id"], ["pm_policy_revisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["fx_snapshot_id"], ["fh_exchange_rate_snapshots.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["channel_config_revision_id"], ["pm_channel_config_revisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["mapping_revision_id"], ["sc_source_mapping_revisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["flowhub_users.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_pev_package_channel_product",
        "pev_frozen_evaluation_packages",
        ["channel_id", "product_ref"],
    )
    op.create_index(
        "ix_pev_package_workspace", "pev_frozen_evaluation_packages", ["workspace_id"]
    )
    op.create_index(
        "ix_pev_package_formula_shape", "pev_frozen_evaluation_packages", ["formula_shape_id"]
    )
    op.create_index(
        "ix_pev_frozen_evaluation_packages_channel_id",
        "pev_frozen_evaluation_packages",
        ["channel_id"],
    )
    op.create_index(
        "ix_pev_frozen_evaluation_packages_product_ref",
        "pev_frozen_evaluation_packages",
        ["product_ref"],
    )
    op.create_index(
        "ix_pev_frozen_evaluation_packages_dependency_fingerprint",
        "pev_frozen_evaluation_packages",
        ["dependency_fingerprint"],
    )

    op.create_table(
        "pev_package_source_observation_pins",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("frozen_evaluation_package_id", sa.String(36), nullable=False),
        sa.Column("source_role", sa.String(80), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("resource_binding_revision_id", sa.String(120), nullable=True),
        sa.Column("observation_id", sa.String(36), nullable=False),
        sa.Column("observation_checksum", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("selection_mode", sa.String(40), nullable=False),
        sa.Column("selection_policy_version", sa.String(40), nullable=True),
        sa.Column("as_of", sa.DateTime(), nullable=True),
        sa.Column("business_effective_date", sa.DateTime(), nullable=True),
        sa.Column("business_cycle_identity", sa.String(120), nullable=True),
        sa.Column("freshness_result", sa.String(20), nullable=False),
        sa.Column("cross_source_skew_result", sa.String(30), nullable=True),
        sa.Column("schema_unit_context_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "selection_mode IN ('latest_eligible_as_of','aligned_business_cycle',"
            "'business_effective_date','last_approved','explicit_observation',"
            "'legacy_consumed_observation')",
            name="ck_pev_pin_selection_mode",
        ),
        sa.CheckConstraint(
            "freshness_result IN ('fresh','stale','unknown')", name="ck_pev_pin_freshness"
        ),
        sa.CheckConstraint(
            "cross_source_skew_result IS NULL OR cross_source_skew_result IN "
            "('within_tolerance','violation','not_applicable')",
            name="ck_pev_pin_skew",
        ),
        sa.UniqueConstraint(
            "frozen_evaluation_package_id", "source_role", name="uq_pev_pin_package_role"
        ),
        sa.ForeignKeyConstraint(
            ["frozen_evaluation_package_id"],
            ["pev_frozen_evaluation_packages.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sc_sources.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["observation_id"], ["saq_observations.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_pev_package_source_observation_pins_frozen_evaluation_package_id",
        "pev_package_source_observation_pins",
        ["frozen_evaluation_package_id"],
    )
    op.create_index(
        "ix_pev_package_source_observation_pins_source_id",
        "pev_package_source_observation_pins",
        ["source_id"],
    )
    op.create_index(
        "ix_pev_pin_observation", "pev_package_source_observation_pins", ["observation_id"]
    )

    op.create_table(
        "pev_manual_input_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("channel_id", sa.String(120), nullable=True),
        sa.Column("product_ref", sa.String(120), nullable=True),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("currency", sa.String(12), nullable=True),
        sa.Column("unit", sa.String(24), nullable=True),
        sa.Column("effective_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('reference_price','pricing_factor','price_override',"
            "'pricing_adjustment','manual_metadata')",
            name="ck_pev_manual_input_kind",
        ),
        sa.UniqueConstraint(
            "kind", "channel_id", "product_ref", "revision_number",
            name="uq_pev_manual_input_revision_number",
        ),
        sa.UniqueConstraint("checksum", name="uq_pev_manual_input_checksum"),
        sa.ForeignKeyConstraint(["channel_id"], ["uw_channels.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["flowhub_users.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_pev_manual_input_scope",
        "pev_manual_input_revisions",
        ["kind", "channel_id", "product_ref"],
    )
    op.create_index(
        "ix_pev_manual_input_revisions_channel_id", "pev_manual_input_revisions", ["channel_id"]
    )
    op.create_index(
        "ix_pev_manual_input_revisions_product_ref", "pev_manual_input_revisions", ["product_ref"]
    )

    op.create_table(
        "pev_manual_input_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("manual_input_revision_id", sa.String(36), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("predecessor_decision_id", sa.String(36), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("effective_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "decision IN ('approved','rejected','revoked')", name="ck_pev_manual_decision_kind"
        ),
        sa.ForeignKeyConstraint(
            ["manual_input_revision_id"], ["pev_manual_input_revisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["predecessor_decision_id"], ["pev_manual_input_decisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["flowhub_users.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_pev_manual_decision_revision",
        "pev_manual_input_decisions",
        ["manual_input_revision_id", "created_at"],
    )
    op.create_index(
        "ix_pev_manual_input_decisions_manual_input_revision_id",
        "pev_manual_input_decisions",
        ["manual_input_revision_id"],
    )

    op.create_table(
        "pev_package_manual_input_pins",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("frozen_evaluation_package_id", sa.String(36), nullable=False),
        sa.Column("manual_input_revision_id", sa.String(36), nullable=False),
        sa.Column("manual_input_decision_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "frozen_evaluation_package_id", "manual_input_revision_id",
            name="uq_pev_manual_pin_package_revision",
        ),
        sa.ForeignKeyConstraint(
            ["frozen_evaluation_package_id"],
            ["pev_frozen_evaluation_packages.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["manual_input_revision_id"], ["pev_manual_input_revisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["manual_input_decision_id"], ["pev_manual_input_decisions.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index(
        "ix_pev_package_manual_input_pins_frozen_evaluation_package_id",
        "pev_package_manual_input_pins",
        ["frozen_evaluation_package_id"],
    )

    op.create_table(
        "pev_package_price_overrides",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("frozen_evaluation_package_id", sa.String(36), nullable=False),
        sa.Column("calculated_candidate_numerator", sa.BigInteger(), nullable=False),
        sa.Column(
            "calculated_candidate_denominator", sa.BigInteger(), nullable=False, server_default="1"
        ),
        sa.Column("override_value_numerator", sa.BigInteger(), nullable=True),
        sa.Column("override_value_denominator", sa.BigInteger(), nullable=True),
        sa.Column("override_manual_input_decision_id", sa.String(36), nullable=True),
        sa.Column("effective_output_numerator", sa.BigInteger(), nullable=False),
        sa.Column(
            "effective_output_denominator", sa.BigInteger(), nullable=False, server_default="1"
        ),
        sa.Column("effective_output_source", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "effective_output_source IN ('calculated_candidate','override_value')",
            name="ck_pev_override_effective_source",
        ),
        sa.CheckConstraint(
            "calculated_candidate_denominator > 0", name="ck_pev_override_candidate_denom"
        ),
        sa.CheckConstraint(
            "override_value_denominator IS NULL OR override_value_denominator > 0",
            name="ck_pev_override_value_denom",
        ),
        sa.UniqueConstraint("frozen_evaluation_package_id", name="uq_pev_override_package"),
        sa.ForeignKeyConstraint(
            ["frozen_evaluation_package_id"],
            ["pev_frozen_evaluation_packages.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["override_manual_input_decision_id"],
            ["pev_manual_input_decisions.id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_pev_package_price_overrides_frozen_evaluation_package_id",
        "pev_package_price_overrides",
        ["frozen_evaluation_package_id"],
    )

    op.create_table(
        "pev_derived_value_definitions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("operator", sa.String(30), nullable=False),
        sa.Column("parameters_json", sa.JSON(), nullable=False),
        sa.Column("dependency_refs_json", sa.JSON(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "operator IN ('add_constant','multiply_percent','floor_to_step',"
            "'round_up_to_step','min_nonzero_selection','multiply_constant',"
            "'divide_constant')",
            name="ck_pev_derived_operator",
        ),
        sa.UniqueConstraint("checksum", name="uq_pev_derived_definition_checksum"),
    )

    op.create_table(
        "pev_derived_value_evaluations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("frozen_evaluation_package_id", sa.String(36), nullable=False),
        sa.Column("derived_value_definition_id", sa.String(36), nullable=False),
        sa.Column("evaluation_order", sa.Integer(), nullable=False),
        sa.Column("result_numerator", sa.BigInteger(), nullable=False),
        sa.Column("result_denominator", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("inputs_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("result_denominator > 0", name="ck_pev_derived_eval_denom"),
        sa.CheckConstraint("evaluation_order >= 0", name="ck_pev_derived_eval_order"),
        sa.UniqueConstraint(
            "frozen_evaluation_package_id", "derived_value_definition_id",
            name="uq_pev_derived_eval_package_definition",
        ),
        sa.ForeignKeyConstraint(
            ["frozen_evaluation_package_id"],
            ["pev_frozen_evaluation_packages.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["derived_value_definition_id"],
            ["pev_derived_value_definitions.id"],
            ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_pev_derived_value_evaluations_frozen_evaluation_package_id",
        "pev_derived_value_evaluations",
        ["frozen_evaluation_package_id"],
    )
    op.create_index(
        "ix_pev_derived_value_evaluations_derived_value_definition_id",
        "pev_derived_value_evaluations",
        ["derived_value_definition_id"],
    )


def downgrade() -> None:
    raise NotImplementedError(
        "FLOWHUB_029 is forward-only: downgrading would destroy Frozen Evaluation "
        "Package evidence (Observation pins, manual input decisions, derived-value "
        "evaluations). Restore a verified backup instead."
    )
