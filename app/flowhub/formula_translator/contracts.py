"""Closed contracts used by Phase D2 formula translator persistence."""

from __future__ import annotations

from enum import StrEnum


class FormulaTranslationStatus(StrEnum):
    """Canonical outcome status for a translator contract decision."""

    TRANSLATED = "translated"
    REVIEW_REQUIRED = "review_required"
    UNSUPPORTED = "unsupported"
    QUARANTINED = "quarantined"


class FormulaTranslationReason(StrEnum):
    """Stable, persisted reason code set for translation outcomes."""

    MATCHED_SUPPORTED = "matched_supported"
    REVIEW_REQUIRED = "review_required"
    SHAPE_UNSUPPORTED = "shape_unsupported"
    UNKNOWN_SHAPE = "unknown_shape"
    BROKEN_REFERENCE = "broken_reference"
    BROKEN_VALUE = "broken_value"
    ANOMALOUS_FORMULA = "anomalous_formula"
    SEMANTIC_GAP = "semantic_gap"


# ---------------------------------------------------------------------------
# Status -> reason contract.
# REVIEW_REQUIRED and QUARANTINED intentionally remain explicit reasons so manual
# and future automated review/audit can be deterministic.
# ---------------------------------------------------------------------------

STATUS_TO_DEFAULT_REASON: dict[FormulaTranslationStatus, FormulaTranslationReason] = {
    FormulaTranslationStatus.TRANSLATED: FormulaTranslationReason.MATCHED_SUPPORTED,
    FormulaTranslationStatus.REVIEW_REQUIRED: FormulaTranslationReason.REVIEW_REQUIRED,
    FormulaTranslationStatus.UNSUPPORTED: FormulaTranslationReason.SHAPE_UNSUPPORTED,
    FormulaTranslationStatus.QUARANTINED: FormulaTranslationReason.SEMANTIC_GAP,
}

FORMULA_TRANSLATOR_VERSION = "formula-translator-schema-v1"

FORMULA_SHAPE_REGISTRY_VERSION = "appendix-a-shape-registry-v1"
