"""Add Business Observability v1 persistence schema.

Two tables:

- ``bo_business_events`` — the immutable, insert-only fact record. A producer
  (Write Pipeline, Pricing, Channels, Source Acquisition) writes one row per
  business outcome. Rows are never updated or deleted after insert.
- ``bo_business_event_lifecycle_transitions`` — the append-only lifecycle
  log. Acknowledge/resolve actions append a transition row; they never
  mutate the fact row. Current effective status is a read-time projection
  over the latest transition per event (see
  ``app/flowhub/business_observability/service.py``), not a third mutable
  table.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op


revision = "FLOWHUB_032"
down_revision = "FLOWHUB_031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bo_business_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("domain", sa.String(40), nullable=False),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("business_impact", sa.String(30), nullable=False),
        sa.Column("reason_code", sa.String(120), nullable=False),
        sa.Column("reason_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("primary_scope_type", sa.String(40), nullable=False),
        sa.Column("primary_scope_id", sa.String(160), nullable=False),
        sa.Column("primary_scope_label", sa.String(240), nullable=True),
        sa.Column("secondary_scopes_json", sa.JSON(), nullable=False),
        sa.Column("recommended_action", sa.Text(), nullable=False, server_default=""),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("action_route_key", sa.String(80), nullable=True),
        sa.Column("action_route_params_json", sa.JSON(), nullable=False),
        sa.Column("correlation_id", sa.String(120), nullable=False, server_default=""),
        sa.Column("producer", sa.String(120), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "domain IN ('source_acquisition','pricing','channels','write_pipeline')",
            name="ck_bo_event_domain",
        ),
        sa.CheckConstraint("event_type != ''", name="ck_bo_event_type_nonempty"),
        sa.CheckConstraint(
            "severity IN ('info','warning','degraded','error','critical')",
            name="ck_bo_event_severity",
        ),
        sa.CheckConstraint(
            "business_impact IN ('none','degraded','blocking','partial_failure',"
            "'critical_business_failure')",
            name="ck_bo_event_business_impact",
        ),
        sa.CheckConstraint("reason_code != ''", name="ck_bo_event_reason_code_nonempty"),
        sa.CheckConstraint(
            "primary_scope_type IN ('source','worksheet','workspace','product','revision',"
            "'pricing_run','review','changeset','channel','order','connector','batch')",
            name="ck_bo_event_primary_scope_type",
        ),
        sa.CheckConstraint("primary_scope_id != ''", name="ck_bo_event_primary_scope_id_nonempty"),
        sa.CheckConstraint("producer != ''", name="ck_bo_event_producer_nonempty"),
    )
    op.create_index("ix_bo_events_domain", "bo_business_events", ["domain"])
    op.create_index("ix_bo_events_event_type", "bo_business_events", ["event_type"])
    op.create_index("ix_bo_events_correlation_id", "bo_business_events", ["correlation_id"])
    op.create_index("ix_bo_events_occurred_at", "bo_business_events", ["occurred_at"])
    op.create_index(
        "ix_bo_events_primary_scope",
        "bo_business_events",
        ["primary_scope_type", "primary_scope_id"],
    )

    op.create_table(
        "bo_business_event_lifecycle_transitions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "business_event_id",
            sa.String(36),
            sa.ForeignKey("bo_business_events.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("from_status", sa.String(20), nullable=True),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("actor", sa.String(160), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "from_status IS NULL OR from_status IN ('open','acknowledged','resolved')",
            name="ck_bo_transition_from_status",
        ),
        sa.CheckConstraint(
            "to_status IN ('open','acknowledged','resolved')",
            name="ck_bo_transition_to_status",
        ),
        sa.CheckConstraint("actor != ''", name="ck_bo_transition_actor_nonempty"),
    )
    op.create_index(
        "ix_bo_transitions_event", "bo_business_event_lifecycle_transitions", ["business_event_id"]
    )
    op.create_index(
        "ix_bo_transitions_event_occurred",
        "bo_business_event_lifecycle_transitions",
        ["business_event_id", "occurred_at"],
    )


def downgrade() -> None:
    raise NotImplementedError(
        "FLOWHUB_032 is forward-only: Business Event history is immutable evidence. "
        "Downgrades are disabled."
    )
