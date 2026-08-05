"""Add immutable Pricing Matrix policies, units, activations, and bindings.

Revision ID: FLOWHUB_024
Revises: FLOWHUB_023
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "FLOWHUB_024"
down_revision = "FLOWHUB_023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pm_policy_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("policy_id", sa.String(36), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("computation_currency", sa.String(12), nullable=False),
        sa.Column("basis_strategy", sa.String(20), nullable=False),
        sa.Column("round_order", sa.String(40), nullable=False),
        sa.Column("max_quote_age_days", sa.Integer(), nullable=False),
        sa.Column("min_quote_count", sa.Integer(), nullable=False),
        sa.Column("evaluation_timezone", sa.String(64), nullable=False),
        sa.Column("arithmetic_version", sa.String(40), nullable=False),
        sa.Column("unit_registry_version", sa.String(40), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("basis_strategy = 'min'", name="ck_pm_policy_basis_strategy"),
        sa.CheckConstraint(
            "round_order IN ('round_then_surcharge','surcharge_then_round')",
            name="ck_pm_policy_round_order",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["flowhub_users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("policy_id", "revision_number", name="uq_pm_policy_revision_number"),
        sa.UniqueConstraint("checksum", name="uq_pm_policy_revision_checksum"),
    )
    op.create_index("ix_pm_policy_revisions_policy_id", "pm_policy_revisions", ["policy_id"])

    op.create_table(
        "pm_product_group_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("product_group_id", sa.String(36), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(240), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["flowhub_users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "product_group_id", "revision_number", name="uq_pm_group_revision_number"
        ),
        sa.UniqueConstraint("checksum", name="uq_pm_group_revision_checksum"),
    )
    op.create_index(
        "ix_pm_product_group_revisions_product_group_id",
        "pm_product_group_revisions",
        ["product_group_id"],
    )

    op.create_table(
        "pm_product_group_members",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("product_group_revision_id", sa.String(36), nullable=False),
        sa.Column("canonical_product_id", sa.String(36), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_group_revision_id"], ["pm_product_group_revisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["canonical_product_id"], ["uw_canonical_products.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "product_group_revision_id",
            "canonical_product_id",
            name="uq_pm_group_revision_member",
        ),
    )
    op.create_index(
        "ix_pm_product_group_members_group",
        "pm_product_group_members",
        ["product_group_revision_id"],
    )
    op.create_index(
        "ix_pm_product_group_members_product",
        "pm_product_group_members",
        ["canonical_product_id"],
    )

    op.create_table(
        "pm_rule_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("policy_revision_id", sa.String(36), nullable=False),
        sa.Column("channel_id", sa.String(120), nullable=True),
        sa.Column("product_ref", sa.String(120), nullable=True),
        sa.Column("product_group_revision_id", sa.String(36), nullable=True),
        sa.Column("rate_mode", sa.String(30), nullable=False),
        sa.Column("rate_value", sa.BigInteger(), nullable=False),
        sa.Column("fixed_addend_minor", sa.BigInteger(), nullable=False),
        sa.Column("round_mode", sa.String(20), nullable=False),
        sa.Column("round_step_minor", sa.BigInteger(), nullable=False),
        sa.Column("surcharge_minor", sa.BigInteger(), nullable=False),
        sa.Column("guards_json", sa.JSON(), nullable=False),
        sa.Column("scope_rank", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "rate_mode IN ('percent_bp','multiplier_ppm')", name="ck_pm_rule_rate_mode"
        ),
        sa.CheckConstraint("round_mode IN ('floor','ceil','nearest')", name="ck_pm_rule_round_mode"),
        sa.CheckConstraint("round_step_minor > 0", name="ck_pm_rule_round_step"),
        sa.ForeignKeyConstraint(
            ["policy_revision_id"], ["pm_policy_revisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["channel_id"], ["uw_channels.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["product_group_revision_id"], ["pm_product_group_revisions.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("checksum", name="uq_pm_rule_entry_checksum"),
    )
    op.create_index("ix_pm_rule_entries_policy", "pm_rule_entries", ["policy_revision_id"])
    op.create_index("ix_pm_rule_entries_channel", "pm_rule_entries", ["channel_id"])
    op.create_index("ix_pm_rule_entries_product", "pm_rule_entries", ["product_ref"])
    op.create_index(
        "ix_pm_rule_scope", "pm_rule_entries", ["policy_revision_id", "channel_id", "product_ref"]
    )
    op.create_index(
        "ix_pm_rule_entries_product_group_revision_id",
        "pm_rule_entries",
        ["product_group_revision_id"],
    )

    op.create_table(
        "pm_channel_config_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_id", sa.String(120), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("currency_profile_id", sa.String(36), nullable=False),
        sa.Column("currency", sa.String(12), nullable=False),
        sa.Column("currency_unit", sa.String(24), nullable=False),
        sa.Column("unit_registry_version", sa.String(40), nullable=False),
        sa.Column("connector_config_version", sa.String(80), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["uw_channels.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["currency_profile_id"], ["uw_currency_profiles.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["flowhub_users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("channel_id", "revision_number", name="uq_pm_channel_config_revision"),
        sa.UniqueConstraint("checksum", name="uq_pm_channel_config_checksum"),
    )
    op.create_index(
        "ix_pm_channel_config_revisions_channel", "pm_channel_config_revisions", ["channel_id"]
    )

    op.create_table(
        "pm_policy_lifecycle_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("channel_id", sa.String(120), nullable=False),
        sa.Column("event_kind", sa.String(20), nullable=False),
        sa.Column("predecessor_event_id", sa.String(36), nullable=True),
        sa.Column("effective_activation_id", sa.String(36), nullable=True),
        sa.Column("policy_revision_id", sa.String(36), nullable=True),
        sa.Column("channel_config_revision_id", sa.String(36), nullable=True),
        sa.Column("supersedes_activation_id", sa.String(36), nullable=True),
        sa.Column("actor_user_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("event_kind IN ('activate','deactivate')", name="ck_pm_event_kind"),
        sa.ForeignKeyConstraint(["channel_id"], ["uw_channels.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["predecessor_event_id"], ["pm_policy_lifecycle_events.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["policy_revision_id"], ["pm_policy_revisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["channel_config_revision_id"], ["pm_channel_config_revisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["flowhub_users.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_pm_policy_lifecycle_events_channel", "pm_policy_lifecycle_events", ["channel_id"]
    )
    op.create_index(
        "ix_pm_policy_lifecycle_events_effective",
        "pm_policy_lifecycle_events",
        ["effective_activation_id"],
    )
    op.create_index(
        "ix_pm_policy_lifecycle_events_event_kind",
        "pm_policy_lifecycle_events",
        ["event_kind"],
    )
    op.create_index(
        "ix_pm_policy_lifecycle_events_policy_revision_id",
        "pm_policy_lifecycle_events",
        ["policy_revision_id"],
    )

    op.create_table(
        "pm_channel_policy_heads",
        sa.Column("channel_id", sa.String(120), primary_key=True),
        sa.Column("current_event_id", sa.String(36), nullable=True),
        sa.Column("effective_activation_id", sa.String(36), nullable=True),
        sa.Column("head_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["uw_channels.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["current_event_id"], ["pm_policy_lifecycle_events.id"], ondelete="RESTRICT"
        ),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO pm_channel_policy_heads (channel_id, head_version, updated_at)
            SELECT channel.id, 0, CURRENT_TIMESTAMP
            FROM uw_channels AS channel
            WHERE NOT EXISTS (
                SELECT 1
                FROM pm_channel_policy_heads AS head
                WHERE head.channel_id = channel.id
            )
            """
        )
    )

    op.create_table(
        "pm_workspace_bindings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("channel_id", sa.String(120), nullable=False),
        sa.Column("policy_revision_id", sa.String(36), nullable=False),
        sa.Column("pricing_policy_activation_id", sa.String(36), nullable=False),
        sa.Column("channel_config_revision_id", sa.String(36), nullable=False),
        sa.Column("execution_policy_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("workspace_pricing_evaluated_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["uw_workspaces.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["channel_id"], ["uw_channels.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["policy_revision_id"], ["pm_policy_revisions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["pricing_policy_activation_id"],
            ["pm_policy_lifecycle_events.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["channel_config_revision_id"], ["pm_channel_config_revisions.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("workspace_id", "channel_id", name="uq_pm_workspace_channel_binding"),
    )
    op.create_index("ix_pm_workspace_bindings_workspace", "pm_workspace_bindings", ["workspace_id"])
    op.create_index("ix_pm_workspace_bindings_channel", "pm_workspace_bindings", ["channel_id"])

    op.create_table(
        "pm_attention_signals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("channel_id", sa.String(120), nullable=False),
        sa.Column("outcome_code", sa.String(120), nullable=False),
        sa.Column("policy_revision_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("status IN ('open','resolved','superseded')", name="ck_pm_attention_status"),
        sa.ForeignKeyConstraint(["channel_id"], ["uw_channels.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["policy_revision_id"], ["pm_policy_revisions.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "source_id",
            "channel_id",
            "outcome_code",
            "policy_revision_id",
            name="uq_pm_attention_dedup",
        ),
    )
    op.create_index("ix_pm_attention_signals_source", "pm_attention_signals", ["source_id"])
    op.create_index("ix_pm_attention_signals_channel", "pm_attention_signals", ["channel_id"])
    op.create_index("ix_pm_attention_signals_outcome_code", "pm_attention_signals", ["outcome_code"])
    op.create_index("ix_pm_attention_signals_status", "pm_attention_signals", ["status"])


def downgrade() -> None:
    raise NotImplementedError(
        "FLOWHUB_024 is forward-only: downgrading would destroy immutable Pricing Matrix "
        "policy, activation, and Workspace binding audit records. Restore a verified backup instead."
    )
