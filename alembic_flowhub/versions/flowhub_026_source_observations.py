"""Add immutable Source Observations, evidence, and snapshot references.

Revision ID: FLOWHUB_026
Revises: FLOWHUB_025
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op


revision = "FLOWHUB_026"
down_revision = "FLOWHUB_025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saq_observation_version_heads",
        sa.Column("source_id", sa.String(36), primary_key=True),
        sa.Column("resource_scope", sa.String(240), primary_key=True),
        sa.Column("next_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sc_sources.id"], ondelete="RESTRICT"),
    )
    op.create_table(
        "saq_observations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("acquisition_run_id", sa.String(36), nullable=False),
        sa.Column("source_id", sa.String(36), nullable=False),
        sa.Column("resource_scope", sa.String(240), nullable=False),
        sa.Column("resource_identity", sa.String(240), nullable=False),
        sa.Column("resource_identity_hash", sa.String(64), nullable=False),
        sa.Column("observation_version", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("observation_version > 0", name="ck_saq_observation_version"),
        sa.ForeignKeyConstraint(["acquisition_run_id"], ["saq_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_id"], ["sc_sources.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("acquisition_run_id", name="uq_saq_observation_run"),
        sa.UniqueConstraint(
            "source_id",
            "resource_scope",
            "observation_version",
            name="uq_saq_observation_scope_version",
        ),
        sa.UniqueConstraint("checksum", name="uq_saq_observation_checksum"),
    )
    op.create_index("ix_saq_observations_acquisition_run_id", "saq_observations", ["acquisition_run_id"])
    op.create_index("ix_saq_observations_source_id", "saq_observations", ["source_id"])
    op.create_index(
        "ix_saq_observations_source_scope_observed",
        "saq_observations",
        ["source_id", "resource_scope", "observed_at"],
    )
    op.create_index(
        "ix_saq_observations_resource_identity_hash",
        "saq_observations",
        ["resource_identity_hash"],
    )
    op.create_table(
        "saq_observation_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("observation_id", sa.String(36), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("evidence_kind", sa.String(80), nullable=False),
        sa.Column("evidence_reference", sa.String(500), nullable=False),
        sa.Column("previous_evidence_checksum", sa.String(64), nullable=True),
        sa.Column("evidence_checksum", sa.String(64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("sequence_number > 0", name="ck_saq_evidence_sequence"),
        sa.ForeignKeyConstraint(["observation_id"], ["saq_observations.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("observation_id", "sequence_number", name="uq_saq_evidence_sequence"),
    )
    op.create_index("ix_saq_observation_evidence_observation_id", "saq_observation_evidence", ["observation_id"])
    op.create_index(
        "ix_saq_evidence_observation_recorded",
        "saq_observation_evidence",
        ["observation_id", "recorded_at"],
    )
    op.create_table(
        "saq_observation_snapshot_references",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("observation_id", sa.String(36), nullable=False),
        sa.Column("snapshot_kind", sa.String(80), nullable=False),
        sa.Column("snapshot_reference", sa.String(240), nullable=False),
        sa.Column("snapshot_checksum", sa.String(64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("linked_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["observation_id"], ["saq_observations.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "observation_id",
            "snapshot_kind",
            "snapshot_reference",
            name="uq_saq_observation_snapshot_reference",
        ),
    )
    op.create_index(
        "ix_saq_observation_snapshot_references_observation_id",
        "saq_observation_snapshot_references",
        ["observation_id"],
    )
    op.create_index(
        "ix_saq_snapshot_reference_observation",
        "saq_observation_snapshot_references",
        ["observation_id", "linked_at"],
    )


def downgrade() -> None:
    raise NotImplementedError(
        "FLOWHUB_026 is forward-only: downgrading would destroy immutable Source Observation, "
        "evidence, and snapshot-reference provenance. Restore a verified backup instead."
    )
