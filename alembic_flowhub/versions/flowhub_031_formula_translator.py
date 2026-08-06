"""Add Formula Translator persistence schema (Pricing Migration Phase D2)."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json

import sqlalchemy as sa

from alembic import op


revision = "FLOWHUB_031"
down_revision = "FLOWHUB_030"
branch_labels = None
depends_on = None

REGISTRY_VERSION = "appendix-a-shape-registry-v1"

_SHAPE_ROWS = (
    {
        "shape_id": "A1",
        "translation_status": "translated",
        "default_reason_code": "matched_supported",
        "is_price_target": True,
        "formula_cell_count": 2291,
        "topology_hint": "price_target_candidate",
        "notes": "basis + percentage (+ optional fixed addend), floor 50,000, scale 1,000,000",
        "record_payload": {
            "cell_role": "price_target_candidate",
            "requires_audit": False,
        },
    },
    {
        "shape_id": "A2",
        "translation_status": "translated",
        "default_reason_code": "matched_supported",
        "is_price_target": False,
        "formula_cell_count": 1840,
        "topology_hint": "basis_selection",
        "notes": "minimum non-zero basis candidate from row-wise vendor range",
        "record_payload": {
            "cell_role": "basis_selection",
            "requires_audit": False,
        },
    },
    {
        "shape_id": "A3",
        "translation_status": "translated",
        "default_reason_code": "matched_supported",
        "is_price_target": True,
        "formula_cell_count": 663,
        "topology_hint": "price_target_candidate",
        "notes": "basis + percentage, floor 100,000, scale 1,000",
        "record_payload": {
            "cell_role": "price_target_candidate",
            "requires_audit": False,
        },
    },
    {
        "shape_id": "A4",
        "translation_status": "translated",
        "default_reason_code": "matched_supported",
        "is_price_target": True,
        "formula_cell_count": 90,
        "topology_hint": "price_target_candidate",
        "notes": "A3 arithmetic with fixed surcharge added after floor",
        "record_payload": {
            "cell_role": "price_target_candidate",
            "requires_audit": False,
        },
    },
    {
        "shape_id": "A5",
        "translation_status": "translated",
        "default_reason_code": "matched_supported",
        "is_price_target": True,
        "formula_cell_count": 7,
        "topology_hint": "price_target_candidate",
        "notes": "basis + percentage, rounded up to two decimal places",
        "record_payload": {
            "cell_role": "price_target_candidate",
            "requires_audit": False,
        },
    },
    {
        "shape_id": "A6",
        "translation_status": "quarantined",
        "default_reason_code": "semantic_gap",
        "is_price_target": True,
        "formula_cell_count": 327,
        "topology_hint": "price_target_candidate",
        "notes": "arithmetic proven; unsupported output semantics and /10 meaning remain unproven",
        "record_payload": {
            "cell_role": "price_target_candidate",
            "requires_audit": True,
            "requires_manual_metadata": True,
        },
    },
    {
        "shape_id": "A7",
        "translation_status": "unsupported",
        "default_reason_code": "shape_unsupported",
        "is_price_target": False,
        "formula_cell_count": 319,
        "topology_hint": "display_metric",
        "notes": "ratio formula used as display metric; never a Channel price target",
        "record_payload": {
            "cell_role": "display_metric",
            "requires_audit": True,
        },
    },
    {
        "shape_id": "A8",
        "translation_status": "review_required",
        "default_reason_code": "review_required",
        "is_price_target": False,
        "formula_cell_count": 25,
        "topology_hint": "metadata_reference",
        "notes": "manual metadata copy; requires downstream provenance evidence before use",
        "record_payload": {
            "cell_role": "metadata_reference",
            "requires_audit": True,
            "requires_manual_metadata": True,
        },
    },
    {
        "shape_id": "A9",
        "translation_status": "quarantined",
        "default_reason_code": "broken_reference",
        "is_price_target": True,
        "formula_cell_count": 254,
        "topology_hint": "price_target_candidate",
        "notes": "A1 variant with missing cached references, cached as broken references",
        "record_payload": {
            "cell_role": "price_target_candidate",
            "requires_audit": True,
        },
    },
    {
        "shape_id": "A10",
        "translation_status": "translated",
        "default_reason_code": "matched_supported",
        "is_price_target": True,
        "formula_cell_count": 94,
        "topology_hint": "price_target_candidate",
        "notes": "parenthesized syntax variant of A3",
        "record_payload": {
            "cell_role": "price_target_candidate",
            "requires_audit": False,
        },
    },
    {
        "shape_id": "A11",
        "translation_status": "translated",
        "default_reason_code": "matched_supported",
        "is_price_target": True,
        "formula_cell_count": 85,
        "topology_hint": "price_target_candidate",
        "notes": "basis + percentage + fixed addend; floor 100,000 after add operation",
        "record_payload": {
            "cell_role": "price_target_candidate",
            "requires_audit": False,
        },
    },
    {
        "shape_id": "A12",
        "translation_status": "quarantined",
        "default_reason_code": "anomalous_formula",
        "is_price_target": False,
        "formula_cell_count": 1,
        "topology_hint": "anomalous_formula",
        "notes": "cross-row minimum formula cached as #VALUE!; not interpreted",
        "record_payload": {
            "cell_role": "anomalous_formula",
            "requires_audit": True,
        },
    },
    {
        "shape_id": "A13",
        "translation_status": "quarantined",
        "default_reason_code": "broken_reference",
        "is_price_target": True,
        "formula_cell_count": 1,
        "topology_hint": "price_target_candidate",
        "notes": "A10-like formula with missing basis reference; cached as broken formula",
        "record_payload": {
            "cell_role": "price_target_candidate",
            "requires_audit": True,
        },
    },
)


def _shape_registry_checksum() -> str:
    payload = {
        "registry_version": REGISTRY_VERSION,
        "shapes": tuple(
            {
                "shape_id": row["shape_id"],
                "translation_status": row["translation_status"],
                "default_reason_code": row["default_reason_code"],
                "is_price_target": row["is_price_target"],
                "formula_cell_count": row["formula_cell_count"],
                "topology_hint": row["topology_hint"],
                "notes": row["notes"],
                "registry_version": REGISTRY_VERSION,
            }
            for row in sorted(_SHAPE_ROWS, key=lambda item: item["shape_id"])
        ),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def upgrade() -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    op.create_table(
        "ft_formula_shape_registry",
        sa.Column("shape_id", sa.String(8), primary_key=True),
        sa.Column("translation_status", sa.String(20), nullable=False),
        sa.Column("default_reason_code", sa.String(40), nullable=False),
        sa.Column("is_price_target", sa.Boolean(), nullable=False),
        sa.Column("formula_cell_count", sa.Integer(), nullable=False),
        sa.Column("topology_hint", sa.String(80), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("record_payload_json", sa.JSON(), nullable=False),
        sa.Column("registry_version", sa.String(80), nullable=False),
        sa.Column("registry_checksum", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "translation_status IN ('translated','review_required','unsupported','quarantined')",
            name="ck_ft_shape_registry_translation_status",
        ),
        sa.CheckConstraint(
            "default_reason_code IN ('matched_supported','review_required','shape_unsupported',"
            "'unknown_shape','broken_reference','broken_value','anomalous_formula','semantic_gap')",
            name="ck_ft_shape_registry_reason_code",
        ),
        sa.CheckConstraint("formula_cell_count >= 0", name="ck_ft_shape_cell_count"),
        sa.CheckConstraint("registry_version != ''", name="ck_ft_shape_registry_version_nonempty"),
        sa.CheckConstraint("registry_checksum != ''", name="ck_ft_shape_registry_checksum_nonempty"),
    )

    registry_checksum = _shape_registry_checksum()
    shape_rows = [
        {
            **row,
            "registry_version": REGISTRY_VERSION,
            "registry_checksum": registry_checksum,
            "record_payload_json": row.pop("record_payload"),
            "created_at": now,
        }
        for row in [dict(item) for item in _SHAPE_ROWS]
    ]
    op.bulk_insert(
        sa.table(
            "ft_formula_shape_registry",
            sa.column("shape_id", sa.String),
            sa.column("translation_status", sa.String),
            sa.column("default_reason_code", sa.String),
            sa.column("is_price_target", sa.Boolean),
            sa.column("formula_cell_count", sa.Integer),
            sa.column("topology_hint", sa.String),
            sa.column("notes", sa.Text),
            sa.column("record_payload_json", sa.JSON),
            sa.column("registry_version", sa.String),
            sa.column("registry_checksum", sa.String),
            sa.column("created_at", sa.DateTime),
        ),
        shape_rows,
    )

    op.create_table(
        "ft_formula_translation_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("formula_rule_identity", sa.String(160), nullable=False),
        sa.Column("formula_shape_id", sa.String(8), nullable=True),
        sa.Column("translation_status", sa.String(20), nullable=False),
        sa.Column("reason_code", sa.String(40), nullable=False),
        sa.Column("translator_version", sa.String(80), nullable=False),
        sa.Column("registry_version", sa.String(80), nullable=False),
        sa.Column("registry_checksum", sa.String(64), nullable=False),
        sa.Column("translation_payload_json", sa.JSON(), nullable=False),
        sa.Column("translation_input_payload_json", sa.JSON(), nullable=False),
        sa.Column("translation_fingerprint", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "translation_status IN ('translated','review_required','unsupported','quarantined')",
            name="ck_ft_translation_status",
        ),
        sa.CheckConstraint(
            "reason_code IN ('matched_supported','review_required','shape_unsupported',"
            "'unknown_shape','broken_reference','broken_value','anomalous_formula','semantic_gap')",
            name="ck_ft_translation_reason_code",
        ),
        sa.CheckConstraint("formula_rule_identity != ''", name="ck_ft_translation_rule_identity_nonempty"),
        sa.CheckConstraint(
            "formula_shape_id IS NULL OR LENGTH(formula_shape_id) >= 1",
            name="ck_ft_translation_shape_id",
        ),
        sa.CheckConstraint("translator_version != ''", name="ck_ft_translation_translator_version"),
        sa.CheckConstraint("registry_version != ''", name="ck_ft_translation_registry_version_nonempty"),
        sa.CheckConstraint("registry_checksum != ''", name="ck_ft_translation_registry_checksum_nonempty"),
        sa.CheckConstraint(
            "translation_fingerprint != ''", name="ck_ft_translation_fingerprint_nonempty"
        ),
        sa.UniqueConstraint(
            "formula_rule_identity", "translator_version", name="uq_ft_translation_rule_and_version"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["flowhub_users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_ft_translation_status", "ft_formula_translation_results", ["translation_status"])
    op.create_index("ix_ft_translation_shape", "ft_formula_translation_results", ["formula_shape_id"])
    op.create_index("ix_ft_translation_rule", "ft_formula_translation_results", ["formula_rule_identity"])

    op.create_table(
        "ft_formula_translation_quarantine",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "formula_translation_result_id",
            sa.String(36),
            nullable=False,
        ),
        sa.Column("quarantine_reason", sa.String(40), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "quarantine_reason IN ('matched_supported','review_required','shape_unsupported',"
            "'unknown_shape','broken_reference','broken_value','anomalous_formula','semantic_gap')",
            name="ck_ft_quarantine_reason_code",
        ),
        sa.CheckConstraint("quarantine_reason != ''", name="ck_ft_quarantine_reason_nonempty"),
        sa.UniqueConstraint(
            "formula_translation_result_id", name="uq_ft_quarantine_result"
        ),
        sa.ForeignKeyConstraint(
            ["formula_translation_result_id"],
            ["ft_formula_translation_results.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["flowhub_users.id"], ondelete="RESTRICT"),
    )
    op.create_index("ix_ft_quarantine_result", "ft_formula_translation_quarantine", ["formula_translation_result_id"])


def downgrade() -> None:
    raise NotImplementedError(
        "FLOWHUB_031 is forward-only: Formula Translator persistence is immutable evidence. "
        "Downgrades are disabled."
    )
