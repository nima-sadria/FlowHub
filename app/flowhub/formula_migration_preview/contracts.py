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


class FormulaMigrationProjectionReason(StrEnum):
    """Fail-closed projection reasons used by D7 integration."""

    BINDING_MANIFEST_CHECKSUM_MISSING = "binding_manifest_checksum_missing"
    COMPARISON_CONTRACT_MISSING = "comparison_contract_missing"
    FINGERPRINT_MISMATCH = "translation_fingerprint_mismatch"
    PREVIEW_BATCH_MISSING = "preview_batch_missing"
    PREVIEW_ROW_CHECKSUM_MISMATCH = "preview_row_checksum_mismatch"
    PREVIEW_CHECKSUM_MISSING = "preview_checksum_missing"
    PREVIEW_REPORT_CHECKSUM_MISMATCH = "preview_report_checksum_mismatch"
    REGISTRY_CHECKSUM_MISMATCH = "registry_checksum_mismatch"
    REGISTRY_VERSION_MISMATCH = "registry_version_mismatch"
    REVIEW_REQUIRED_APPROVAL_MISSING = "review_required_approval_missing"
    SHAPE_TARGET_MISMATCH = "shape_target_mismatch"
    TRANSLATION_RESULT_MISSING = "translation_result_missing"
    TRANSLATOR_VERSION_MISMATCH = "translator_version_mismatch"
    STALE_OR_INCONSISTENT_RESULT = "stale_or_inconsistent_result"


@dataclass(frozen=True, slots=True)
class FormulaMigrationPreviewEvidenceProjection:
    """Read-only projection row consumed by Phase B/C integration."""

    preview_batch_id: str
    preview_cell_id: str
    inventory_cell_id: str
    formula_rule_identity: str
    formula_shape_id: str | None
    formula_translation_result_id: str
    translation_status: str
    reason_code: str
    translation_fingerprint: str
    translator_version: str
    registry_version: str
    registry_checksum: str
    binding_manifest_checksum: str
    preview_batch_report_checksum: str
    preview_row_checksum: str
    shape_is_price_target: bool
    shape_comparison_contract_id: str | None
    shape_comparison_contract_revision: str | None
    shape_comparison_contract_revision_checksum: str | None
    review_decision_id: str | None
    may_count: bool
    review_required: bool
    blocked: bool
    non_price_evidence_only: bool
    fail_reasons: tuple[str, ...]
    projection_row_checksum: str


@dataclass(frozen=True, slots=True)
class FormulaMigrationPreviewProjection:
    """Stable projection payload for one preview batch."""

    batch_id: str
    batch_report_checksum: str
    rows: tuple[FormulaMigrationPreviewEvidenceProjection, ...]
    projection_checksum: str


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
    "FormulaMigrationPreviewEvidenceProjection",
    "FormulaMigrationPreviewProjection",
    "FormulaMigrationProjectionReason",
    "FormulaMigrationReviewAction",
    "PreviewBatchState",
]
