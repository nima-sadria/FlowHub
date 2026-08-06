"""Checked-in Appendix A shape registry metadata for formula translation."""

from __future__ import annotations

from dataclasses import dataclass

from app.flowhub.formula_translator.contracts import (
    FORMULA_SHAPE_REGISTRY_VERSION,
    FormulaTranslationReason,
    FormulaTranslationStatus,
)
from app.flowhub.unified_workspace.domain import checksum


@dataclass(frozen=True, slots=True)
class FormulaShapeEntry:
    """Immutable shape registry identity and persistence metadata."""

    shape_id: str
    translation_status: FormulaTranslationStatus
    default_reason_code: FormulaTranslationReason
    is_price_target: bool
    formula_cell_count: int
    topology_hint: str
    notes: str


FORMULA_SHAPE_REGISTRY: tuple[FormulaShapeEntry, ...] = (
    FormulaShapeEntry(
        shape_id="A1",
        translation_status=FormulaTranslationStatus.TRANSLATED,
        default_reason_code=FormulaTranslationReason.MATCHED_SUPPORTED,
        is_price_target=True,
        formula_cell_count=2_291,
        topology_hint="price_target_candidate",
        notes="basis + percentage (+ optional fixed addend), floor 50,000, scale 1,000,000",
    ),
    FormulaShapeEntry(
        shape_id="A2",
        translation_status=FormulaTranslationStatus.TRANSLATED,
        default_reason_code=FormulaTranslationReason.MATCHED_SUPPORTED,
        is_price_target=False,
        formula_cell_count=1_840,
        topology_hint="basis_selection",
        notes="minimum non-zero basis candidate from row-wise vendor range",
    ),
    FormulaShapeEntry(
        shape_id="A3",
        translation_status=FormulaTranslationStatus.TRANSLATED,
        default_reason_code=FormulaTranslationReason.MATCHED_SUPPORTED,
        is_price_target=True,
        formula_cell_count=663,
        topology_hint="price_target_candidate",
        notes="basis + percentage, floor 100,000, scale 1,000",
    ),
    FormulaShapeEntry(
        shape_id="A4",
        translation_status=FormulaTranslationStatus.TRANSLATED,
        default_reason_code=FormulaTranslationReason.MATCHED_SUPPORTED,
        is_price_target=True,
        formula_cell_count=90,
        topology_hint="price_target_candidate",
        notes="A3 arithmetic with fixed surcharge added after floor",
    ),
    FormulaShapeEntry(
        shape_id="A5",
        translation_status=FormulaTranslationStatus.TRANSLATED,
        default_reason_code=FormulaTranslationReason.MATCHED_SUPPORTED,
        is_price_target=True,
        formula_cell_count=7,
        topology_hint="price_target_candidate",
        notes="basis + percentage, rounded up to two decimal places",
    ),
    FormulaShapeEntry(
        shape_id="A6",
        translation_status=FormulaTranslationStatus.QUARANTINED,
        default_reason_code=FormulaTranslationReason.SEMANTIC_GAP,
        is_price_target=True,
        formula_cell_count=327,
        topology_hint="price_target_candidate",
        notes="arithmetic proven; unsupported output semantics and /10 meaning remain unproven",
    ),
    FormulaShapeEntry(
        shape_id="A7",
        translation_status=FormulaTranslationStatus.UNSUPPORTED,
        default_reason_code=FormulaTranslationReason.SHAPE_UNSUPPORTED,
        is_price_target=False,
        formula_cell_count=319,
        topology_hint="display_metric",
        notes="ratio formula used as display metric; never a Channel price target",
    ),
    FormulaShapeEntry(
        shape_id="A8",
        translation_status=FormulaTranslationStatus.REVIEW_REQUIRED,
        default_reason_code=FormulaTranslationReason.REVIEW_REQUIRED,
        is_price_target=False,
        formula_cell_count=25,
        topology_hint="metadata_reference",
        notes="manual metadata copy; requires downstream provenance evidence before use",
    ),
    FormulaShapeEntry(
        shape_id="A9",
        translation_status=FormulaTranslationStatus.QUARANTINED,
        default_reason_code=FormulaTranslationReason.BROKEN_REFERENCE,
        is_price_target=True,
        formula_cell_count=254,
        topology_hint="price_target_candidate",
        notes="A1 variant with missing cached references, cached as broken references",
    ),
    FormulaShapeEntry(
        shape_id="A10",
        translation_status=FormulaTranslationStatus.TRANSLATED,
        default_reason_code=FormulaTranslationReason.MATCHED_SUPPORTED,
        is_price_target=True,
        formula_cell_count=94,
        topology_hint="price_target_candidate",
        notes="parenthesized syntax variant of A3",
    ),
    FormulaShapeEntry(
        shape_id="A11",
        translation_status=FormulaTranslationStatus.TRANSLATED,
        default_reason_code=FormulaTranslationReason.MATCHED_SUPPORTED,
        is_price_target=True,
        formula_cell_count=85,
        topology_hint="price_target_candidate",
        notes="basis + percentage + fixed addend; floor 100,000 after add operation",
    ),
    FormulaShapeEntry(
        shape_id="A12",
        translation_status=FormulaTranslationStatus.QUARANTINED,
        default_reason_code=FormulaTranslationReason.ANOMALOUS_FORMULA,
        is_price_target=False,
        formula_cell_count=1,
        topology_hint="anomalous_formula",
        notes="cross-row minimum formula cached as #VALUE!; not interpreted",
    ),
    FormulaShapeEntry(
        shape_id="A13",
        translation_status=FormulaTranslationStatus.QUARANTINED,
        default_reason_code=FormulaTranslationReason.BROKEN_REFERENCE,
        is_price_target=True,
        formula_cell_count=1,
        topology_hint="price_target_candidate",
        notes="A10-like formula with missing basis reference; cached as broken formula",
    ),
)


def formula_shape_registry_payload() -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "shape_id": shape.shape_id,
            "translation_status": shape.translation_status.value,
            "default_reason_code": shape.default_reason_code.value,
            "is_price_target": shape.is_price_target,
            "formula_cell_count": shape.formula_cell_count,
            "topology_hint": shape.topology_hint,
            "notes": shape.notes,
            "registry_version": FORMULA_SHAPE_REGISTRY_VERSION,
        }
        for shape in sorted(FORMULA_SHAPE_REGISTRY, key=lambda entry: entry.shape_id)
    )


def get_registry_entry(shape_id: str) -> FormulaShapeEntry:
    if not shape_id:
        raise KeyError(shape_id)
    for entry in FORMULA_SHAPE_REGISTRY:
        if entry.shape_id == shape_id:
            return entry
    raise KeyError(shape_id)


FORMULA_SHAPE_REGISTRY_CHECKSUM = checksum(
    {
        "registry_version": FORMULA_SHAPE_REGISTRY_VERSION,
        "shapes": formula_shape_registry_payload(),
    }
)
