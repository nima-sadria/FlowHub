"""Bounded shape recognizer and bounded emitter tests for Phase D3."""

from __future__ import annotations

import pytest

from app.flowhub.formula_translator.contracts import (
    FormulaTranslationReason,
    FormulaTranslationStatus,
)
from app.flowhub.formula_translator.translator import FormulaTranslationOutcome, translate_formula


_MARK_X = "x"
_MARK_CROSS = "\u274c"


@pytest.mark.parametrize(
    ("shape_id", "formula", "expected_payload"),
    [
        (
            "A1",
            '=IF(RC[-2]="","x",IFERROR(FLOOR((RC[-2]*(1+R2C6/100)+IF(ISNUMBER(R3C6),R3C6,0))*1000000,50000),"x"))',
            {
                "target_kind": "pricing_rule",
                "rate_mode": "percent_bp",
                "basis_reference": "RC[-2]",
                "rate_reference": "R2C6",
                "fixed_addend_reference": "R3C6",
                "fixed_addend_when_not_number": 0,
                "round_mode": "floor",
                "round_step_minor": 50_000,
                "surcharge_minor": 0,
                "round_order": "round_then_surcharge",
                "intermediate_scale": {"numerator": 1_000_000, "denominator": 1},
            },
        ),
        (
            "A2",
            '=IFERROR(MIN(FILTER(RC[1]:RC[2],RC[1]:RC[2]<>0),"' + _MARK_CROSS + '")',
            {
                "target_kind": "basis_selection",
                "selection_mode": "min_non_zero",
                "candidate_range": {"start_ref": "RC[1]", "end_ref": "RC[2]"},
            },
        ),
        (
            "A3",
            '=IFERROR(FLOOR(RC[1]*(1+R2C3/100)*1000,100000),"' + _MARK_CROSS + '")',
            {
                "target_kind": "pricing_rule",
                "rate_mode": "percent_bp",
                "basis_reference": "RC[1]",
                "rate_reference": "R2C3",
                "fixed_addend_reference": None,
                "fixed_addend_when_not_number": 0,
                "round_mode": "floor",
                "round_step_minor": 100_000,
                "surcharge_minor": 0,
                "round_order": "round_then_surcharge",
                "intermediate_scale": {"numerator": 1_000, "denominator": 1},
            },
        ),
        (
            "A4",
            '=IFERROR(FLOOR(RC[1]*(1+R2C3/100)*1000,100000)+500000,"'
            + _MARK_CROSS
            + '")',
            {
                "target_kind": "pricing_rule",
                "rate_mode": "percent_bp",
                "basis_reference": "RC[1]",
                "rate_reference": "R2C3",
                "fixed_addend_reference": None,
                "fixed_addend_when_not_number": 0,
                "round_mode": "floor",
                "round_step_minor": 100_000,
                "surcharge_minor": 500_000,
                "round_order": "round_then_surcharge",
                "intermediate_scale": {"numerator": 1_000, "denominator": 1},
            },
        ),
        (
            "A5",
            '=IFERROR(ROUNDUP(RC[1]*(1+R74C3/100),-2),"' + _MARK_CROSS + '")',
            {
                "target_kind": "pricing_rule",
                "rate_mode": "percent_bp",
                "basis_reference": "RC[1]",
                "rate_reference": "R74C3",
                "fixed_addend_reference": None,
                "fixed_addend_when_not_number": 0,
                "round_mode": "ceil",
                "round_step_minor": 100,
                "surcharge_minor": 0,
                "round_order": "round_then_surcharge",
                "intermediate_scale": {"numerator": 1, "denominator": 1},
            },
        ),
        (
            "A10",
            '=IFERROR(FLOOR((RC[1]*(1+R2C3/100)*1000),100000),"' + _MARK_CROSS + '")',
            {
                "target_kind": "pricing_rule",
                "rate_mode": "percent_bp",
                "basis_reference": "RC[1]",
                "rate_reference": "R2C3",
                "fixed_addend_reference": None,
                "fixed_addend_when_not_number": 0,
                "round_mode": "floor",
                "round_step_minor": 100_000,
                "surcharge_minor": 0,
                "round_order": "round_then_surcharge",
                "intermediate_scale": {"numerator": 1_000, "denominator": 1},
            },
        ),
        (
            "A11",
            '=IFERROR(FLOOR((RC[1]*(1+R10C3/100)*1000)+500000,100000),"' + _MARK_CROSS + '")',
            {
                "target_kind": "pricing_rule",
                "rate_mode": "percent_bp",
                "basis_reference": "RC[1]",
                "rate_reference": "R10C3",
                "fixed_addend_reference": None,
                "fixed_addend_when_not_number": 0,
                "round_mode": "floor",
                "round_step_minor": 100_000,
                "surcharge_minor": 500_000,
                "round_order": "surcharge_then_round",
                "intermediate_scale": {"numerator": 1_000, "denominator": 1},
            },
        ),
    ],
)
def test_translate_formula_emits_supported_shapes(
    shape_id: str, formula: str, expected_payload: dict[str, object]
) -> None:
    result = translate_formula(formula=formula, formula_rule_identity="rule:A1")

    assert result.formula_shape_id == shape_id
    assert result.translation_status is FormulaTranslationStatus.TRANSLATED
    assert result.reason_code is FormulaTranslationReason.MATCHED_SUPPORTED
    assert result.output_payload == expected_payload


@pytest.mark.parametrize(
    ("shape_id", "formula", "expected_status", "expected_reason"),
    [
        (
            "A6",
            '=IF(RC[1]="","x",IFERROR(FLOOR(R2C7*RC[2],50000)/10,"x"))',
            FormulaTranslationStatus.QUARANTINED,
            FormulaTranslationReason.SEMANTIC_GAP,
        ),
        (
            "A7",
            '=IFERROR(RC[-1]/RC[-2],"' + _MARK_X + '")',
            FormulaTranslationStatus.UNSUPPORTED,
            FormulaTranslationReason.SHAPE_UNSUPPORTED,
        ),
        (
            "A8",
            "=RC[1]",
            FormulaTranslationStatus.REVIEW_REQUIRED,
            FormulaTranslationReason.REVIEW_REQUIRED,
        ),
        (
            "A9",
            '=IF(RC[-4]="","x",IFERROR(FLOOR((RC[-4]*(1+#REF!/100)+IF(ISNUMBER(#REF!),#REF!,0))*1000000,50000),"x"))',
            FormulaTranslationStatus.QUARANTINED,
            FormulaTranslationReason.BROKEN_REFERENCE,
        ),
        (
            "A12",
            '=IFNA(MIN(FILTER(R[-9]C[-4]:R[-9]C,R[-9]C[-4]:R[-9]C<>0),"' + _MARK_CROSS + '")',
            FormulaTranslationStatus.QUARANTINED,
            FormulaTranslationReason.ANOMALOUS_FORMULA,
        ),
        (
            "A13",
            '=IFERROR(FLOOR((#REF!*(1+R2C3/100)*1000),100000),"' + _MARK_CROSS + '")',
            FormulaTranslationStatus.QUARANTINED,
            FormulaTranslationReason.BROKEN_REFERENCE,
        ),
        (
            None,
            '=IFERROR(D4+(F4*1.2),"oops")',
            FormulaTranslationStatus.QUARANTINED,
            FormulaTranslationReason.UNKNOWN_SHAPE,
        ),
    ],
)
def test_translate_formula_dispositions(
    shape_id: str | None,
    formula: str,
    expected_status: FormulaTranslationStatus,
    expected_reason: FormulaTranslationReason,
) -> None:
    result = translate_formula(formula=formula, formula_rule_identity="rule:A1")

    assert result.formula_shape_id == shape_id
    assert result.translation_status == expected_status
    assert result.reason_code == expected_reason
    if expected_status is not FormulaTranslationStatus.REVIEW_REQUIRED and expected_status is not FormulaTranslationStatus.UNSUPPORTED:
        assert result.output_payload == {}


def test_translate_formula_fingerprint_is_deterministic_and_sensitive() -> None:
    formula = '=IFERROR(FLOOR(RC[1]*(1+R2C3/100)*1000,100000),"\u274c")'
    first = translate_formula(
        formula=formula,
        formula_rule_identity="rule:F1",
        package_fingerprint=None,
        reviewed_by=None,
    )
    second = translate_formula(
        formula=formula,
        formula_rule_identity="rule:F1",
        package_fingerprint=None,
        reviewed_by=None,
    )
    changed = translate_formula(
        formula=formula,
        formula_rule_identity="rule:F1",
        package_fingerprint="pkg-1",
        reviewed_by=None,
    )

    assert first.translation_fingerprint == second.translation_fingerprint
    assert changed.translation_fingerprint != first.translation_fingerprint
