"""Offline formula migration preview contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.flowhub.formula_translator.contracts import (
    FormulaTranslationReason,
    FormulaTranslationStatus,
)


class PreviewBatchState(StrEnum):
    """Terminal state for an assembled offline preview batch."""

    COMPLETED = "completed"


class FormulaMigrationReviewAction(StrEnum):
    """Append-only reviewer action records."""

    APPROVED = "approved"
    REJECTED = "rejected"
    NOTE = "note"


@dataclass(frozen=True, slots=True)
class DependencyManifest:
    """Resolved dependency binding manifest checksum source for one inventory cell."""

    source_roles: tuple[str, ...] = ()
    manual_roles: tuple[str, ...] = ()
    derived_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FormulaInventoryCell:
    """Immutable identity input from D1 formula inventory."""

    inventory_id: str
    formula_text: str
    worksheet: str | None = None
    row: int | None = None
    column: int | None = None


@dataclass(frozen=True, slots=True)
class FormulaMigrationInputCell:
    """One translator input row with all immutable evidence required by D6."""

    inventory_cell: FormulaInventoryCell
    translation_status: FormulaTranslationStatus
    reason_code: FormulaTranslationReason
    formula_shape_id: str | None
    translation_fingerprint: str
    translation_output_payload: dict[str, object]
    translation_input_payload: dict[str, object]
    binding_manifest: DependencyManifest
    binding_manifest_checksum: str
    translator_version: str
    registry_version: str
    registry_checksum: str
    formula_rule_identity: str
    translation_fingerprint_by_version: dict[str, str] = field(default_factory=dict)
    fixture_and_registry_evidence: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FormulaMigrationCellDecision:
    """Per-cell output row for one preview item."""

    inventory_cell_id: str
    formula_rule_identity: str
    formula_shape_id: str | None
    translation_status: FormulaTranslationStatus
    reason_code: FormulaTranslationReason
    translation_fingerprint: str
    binding_manifest_checksum: str
    target_fragment: dict[str, object]
    review_required: dict[str, object] | None
    quarantine_reason: dict[str, object] | None
    fixture_registry_evidence: dict[str, object]
    translator_version: str
    translator_version_diff: dict[str, object] | None
    blocking_operationally_active: bool
    formula_inventory_evidence: dict[str, object]
    report_row_checksum: str


@dataclass(frozen=True, slots=True)
class FormulaMigrationPreviewBatch:
    """One completed immutable preview batch output."""

    batch_id: str
    state: PreviewBatchState
    translator_version: str
    registry_version: str
    registry_checksum: str
    counts: dict[str, int]
    blocking_operationally_active: int
    cells: tuple[FormulaMigrationCellDecision, ...]
    report_checksum: str


__all__ = [
    "DependencyManifest",
    "FormulaInventoryCell",
    "FormulaMigrationCellDecision",
    "FormulaMigrationInputCell",
    "FormulaMigrationPreviewBatch",
    "FormulaMigrationReviewAction",
    "PreviewBatchState",
]
