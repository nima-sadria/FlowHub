"""Bounded Appendix A shape recognizer and declarative emitter."""

from __future__ import annotations

from dataclasses import dataclass
import re
from collections.abc import Callable, Mapping

from app.flowhub.formula_translator.contracts import (
    FORMULA_TRANSLATOR_VERSION,
    FormulaTranslationReason,
    FormulaTranslationStatus,
)
from app.flowhub.formula_translator.fingerprint import compute_translation_result_checksum
from app.flowhub.formula_translator.registry import (
    FORMULA_SHAPE_REGISTRY_CHECKSUM,
    FORMULA_SHAPE_REGISTRY_VERSION,
)

JsonPayload = dict[str, object]


@dataclass(frozen=True, slots=True)
class FormulaTranslationOutcome:
    """Deterministic contract for one formula-shape translation."""

    formula_shape_id: str | None
    translation_status: FormulaTranslationStatus
    reason_code: FormulaTranslationReason
    input_payload: JsonPayload
    output_payload: JsonPayload
    translation_fingerprint: str


_CELL = r"R(?:\[\-?\d+\]|\d+)?C(?:\[\-?\d+\]|\d+)?"
_MARK_X = '"x"'
_MARK_CROSS = '"(?:\u274c|\\\\u274c)"'


def _as_rational(value: int) -> JsonPayload:
    """Represent numeric factors as exact rational components."""

    return {"numerator": int(value), "denominator": 1}


def _emit_pricing_rule(
    *,
    basis_ref: str,
    rate_ref: str,
    fixed_addend_ref: str | None = None,
    fixed_addend_when_not_number: int = 0,
    round_step_minor: int,
    round_mode: str = "floor",
    surcharge_minor: int = 0,
    round_order: str = "round_then_surcharge",
    scale_factor_numerator: int = 1,
    scale_factor_denominator: int = 1,
) -> JsonPayload:
    return {
        "target_kind": "pricing_rule",
        "rate_mode": "percent_bp",
        "basis_reference": basis_ref,
        "rate_reference": rate_ref,
        "fixed_addend_reference": fixed_addend_ref,
        "fixed_addend_when_not_number": fixed_addend_when_not_number,
        "round_mode": round_mode,
        "round_step_minor": int(round_step_minor),
        "surcharge_minor": int(surcharge_minor),
        "round_order": round_order,
        "intermediate_scale": _as_rational(scale_factor_numerator)
        | {"denominator": int(scale_factor_denominator)},
    }


def _emit_a1(captures: Mapping[str, str]) -> JsonPayload:
    return _emit_pricing_rule(
        basis_ref=captures["basis_ref"],
        rate_ref=captures["rate_ref"],
        fixed_addend_ref=captures["addend_ref"],
        round_step_minor=50_000,
        round_order="round_then_surcharge",
        scale_factor_numerator=1_000_000,
        scale_factor_denominator=1,
    )


def _emit_a2(captures: Mapping[str, str]) -> JsonPayload:
    return {
        "target_kind": "basis_selection",
        "selection_mode": "min_non_zero",
        "candidate_range": {
            "start_ref": captures["range_start"],
            "end_ref": captures["range_end"],
        },
    }


def _emit_a3(captures: Mapping[str, str]) -> JsonPayload:
    return _emit_pricing_rule(
        basis_ref=captures["basis_ref"],
        rate_ref=captures["rate_ref"],
        round_step_minor=100_000,
        scale_factor_numerator=1_000,
        scale_factor_denominator=1,
    )


def _emit_a4(captures: Mapping[str, str]) -> JsonPayload:
    return _emit_pricing_rule(
        basis_ref=captures["basis_ref"],
        rate_ref=captures["rate_ref"],
        round_step_minor=100_000,
        surcharge_minor=500_000,
        round_order="round_then_surcharge",
        scale_factor_numerator=1_000,
        scale_factor_denominator=1,
    )


def _emit_a5(captures: Mapping[str, str]) -> JsonPayload:
    return _emit_pricing_rule(
        basis_ref=captures["basis_ref"],
        rate_ref=captures["rate_ref"],
        round_step_minor=100,
        round_mode="ceil",
    )


def _emit_a10(captures: Mapping[str, str]) -> JsonPayload:
    return _emit_a3(captures)


def _emit_a11(captures: Mapping[str, str]) -> JsonPayload:
    return _emit_pricing_rule(
        basis_ref=captures["basis_ref"],
        rate_ref=captures["rate_ref"],
        round_step_minor=100_000,
        surcharge_minor=500_000,
        round_order="surcharge_then_round",
        scale_factor_numerator=1_000,
        scale_factor_denominator=1,
    )


ShapeEmitter = Callable[[Mapping[str, str]], JsonPayload]


@dataclass(frozen=True, slots=True)
class _ShapeDefinition:
    shape_id: str
    pattern: re.Pattern[str]
    emitter: ShapeEmitter | None
    status: FormulaTranslationStatus
    reason: FormulaTranslationReason


def _build_pattern(body: str) -> re.Pattern[str]:
    return re.compile(rf"^{body}$")


def _xlfn_optional(function: str) -> str:
    return rf"(?:_xlfn\._xlws\.)?{function}"


_SHAPE_DEFINITIONS: tuple[_ShapeDefinition, ...] = (
    _ShapeDefinition(
        shape_id="A1",
        pattern=_build_pattern(
            rf'=IF\((?P<guard_ref>{_CELL})=\"\",\"x\",IFERROR\(FLOOR\(\('
            rf"(?P<basis_ref>{_CELL})\*\(1\+(?P<rate_ref>{_CELL})/100\)\+"
            rf"IF\(ISNUMBER\((?P<addend_ref>{_CELL})\),(?P=addend_ref),0\)\)\*1000000,50000\),{_MARK_X}\)\)"
        ),
        emitter=_emit_a1,
        status=FormulaTranslationStatus.TRANSLATED,
        reason=FormulaTranslationReason.MATCHED_SUPPORTED,
    ),
    _ShapeDefinition(
        shape_id="A2",
        pattern=_build_pattern(
            rf'=IFERROR\(MIN\({_xlfn_optional("FILTER")}\('
            rf"(?P<range_start>{_CELL}):(?P<range_end>{_CELL}),"
            rf"(?P=range_start):(?P=range_end)<>0\),{_MARK_CROSS}\)"
        ),
        emitter=_emit_a2,
        status=FormulaTranslationStatus.TRANSLATED,
        reason=FormulaTranslationReason.MATCHED_SUPPORTED,
    ),
    _ShapeDefinition(
        shape_id="A3",
        pattern=_build_pattern(
            rf'=IFERROR\(FLOOR\((?P<basis_ref>{_CELL})\*\(1\+(?P<rate_ref>{_CELL})/100\)\*1000,100000\),{_MARK_CROSS}\)'
        ),
        emitter=_emit_a3,
        status=FormulaTranslationStatus.TRANSLATED,
        reason=FormulaTranslationReason.MATCHED_SUPPORTED,
    ),
    _ShapeDefinition(
        shape_id="A4",
        pattern=_build_pattern(
            rf'=IFERROR\(FLOOR\((?P<basis_ref>{_CELL})\*\(1\+(?P<rate_ref>{_CELL})/100\)\*1000,100000\)\+500000,{_MARK_CROSS}\)'
        ),
        emitter=_emit_a4,
        status=FormulaTranslationStatus.TRANSLATED,
        reason=FormulaTranslationReason.MATCHED_SUPPORTED,
    ),
    _ShapeDefinition(
        shape_id="A5",
        pattern=_build_pattern(
            rf'=IFERROR\(ROUNDUP\((?P<basis_ref>{_CELL})\*\(1\+(?P<rate_ref>{_CELL})/100\),-2\),{_MARK_CROSS}\)'
        ),
        emitter=_emit_a5,
        status=FormulaTranslationStatus.TRANSLATED,
        reason=FormulaTranslationReason.MATCHED_SUPPORTED,
    ),
    _ShapeDefinition(
        shape_id="A6",
        pattern=_build_pattern(
            rf'=IF\((?P<guard_ref>{_CELL})=\"\",\"x\",IFERROR\(FLOOR\('
            rf"(?P<multiplier_ref>{_CELL})\*(?P<basis_ref>{_CELL}),50000\)/10,\"x\"\)\)"
        ),
        emitter=None,
        status=FormulaTranslationStatus.QUARANTINED,
        reason=FormulaTranslationReason.SEMANTIC_GAP,
    ),
    _ShapeDefinition(
        shape_id="A7",
        pattern=_build_pattern(
            rf'=IFERROR\((?P<numerator_ref>{_CELL})/(?P<denominator_ref>{_CELL}),{_MARK_X}\)'
        ),
        emitter=None,
        status=FormulaTranslationStatus.UNSUPPORTED,
        reason=FormulaTranslationReason.SHAPE_UNSUPPORTED,
    ),
    _ShapeDefinition(
        shape_id="A8",
        pattern=_build_pattern(rf'=(?P<manual_ref>{_CELL})'),
        emitter=None,
        status=FormulaTranslationStatus.REVIEW_REQUIRED,
        reason=FormulaTranslationReason.REVIEW_REQUIRED,
    ),
    _ShapeDefinition(
        shape_id="A9",
        pattern=_build_pattern(
            rf'=IF\((?P<guard_ref>{_CELL})=\"\",\"x\",IFERROR\(FLOOR\(\('
            rf"(?P<basis_ref>{_CELL})\*\(1\+#REF!/100\)\+IF\(ISNUMBER\(#REF!\),#REF!,0\)\)"
            rf"\*1000000,50000\),{_MARK_X}\)\)"
        ),
        emitter=None,
        status=FormulaTranslationStatus.QUARANTINED,
        reason=FormulaTranslationReason.BROKEN_REFERENCE,
    ),
    _ShapeDefinition(
        shape_id="A10",
        pattern=_build_pattern(
            rf'=IFERROR\(FLOOR\(\((?P<basis_ref>{_CELL})\*\(1\+(?P<rate_ref>{_CELL})/100\)\*1000\),100000\),{_MARK_CROSS}\)'
        ),
        emitter=_emit_a10,
        status=FormulaTranslationStatus.TRANSLATED,
        reason=FormulaTranslationReason.MATCHED_SUPPORTED,
    ),
    _ShapeDefinition(
        shape_id="A11",
        pattern=_build_pattern(
            rf'=IFERROR\(FLOOR\(\((?P<basis_ref>{_CELL})\*\(1\+(?P<rate_ref>{_CELL})/100\)\*1000\)\+500000,100000\),{_MARK_CROSS}\)'
        ),
        emitter=_emit_a11,
        status=FormulaTranslationStatus.TRANSLATED,
        reason=FormulaTranslationReason.MATCHED_SUPPORTED,
    ),
    _ShapeDefinition(
        shape_id="A12",
        pattern=_build_pattern(
            rf'=IFNA\(MIN\({_xlfn_optional("FILTER")}\('
            rf"(?P<range_start>{_CELL}):(?P<range_end>{_CELL}),"
            rf"(?P=range_start):(?P=range_end)<>0\),{_MARK_CROSS}\)"
        ),
        emitter=None,
        status=FormulaTranslationStatus.QUARANTINED,
        reason=FormulaTranslationReason.ANOMALOUS_FORMULA,
    ),
    _ShapeDefinition(
        shape_id="A13",
        pattern=_build_pattern(
            rf'=IFERROR\(FLOOR\(\(#REF!\*\(1\+(?P<rate_ref>{_CELL})/100\)\*1000\),100000\),{_MARK_CROSS}\)'
        ),
        emitter=None,
        status=FormulaTranslationStatus.QUARANTINED,
        reason=FormulaTranslationReason.BROKEN_REFERENCE,
    ),
)


def _find_shape(formula: str) -> tuple[_ShapeDefinition | None, re.Match[str] | None]:
    for definition in _SHAPE_DEFINITIONS:
        matches = definition.pattern.match(formula)
        if matches:
            return definition, matches
    return None, None


def _build_input_payload(
    *,
    formula: str,
    formula_shape_id: str | None,
    captures: Mapping[str, str],
) -> JsonPayload:
    payload: JsonPayload = {"formula": formula, "named_captures": dict(captures)}
    if formula_shape_id:
        payload["shape_id"] = formula_shape_id
    return payload


def translate_formula(
    formula: str,
    *,
    formula_rule_identity: str,
    reviewed_by: str | None = None,
    package_fingerprint: str | None = None,
) -> FormulaTranslationOutcome:
    """Translate one normalized legacy formula to a closed declarative contract."""

    formula_text = str(formula).strip()
    definition, matches = _find_shape(formula_text)

    if definition is None or matches is None:
        status = FormulaTranslationStatus.QUARANTINED
        reason = FormulaTranslationReason.UNKNOWN_SHAPE
        formula_shape_id: str | None = None
        captures: dict[str, str] = {}
        output_payload: JsonPayload = {}
    else:
        captures = dict(matches.groupdict())
        formula_shape_id = definition.shape_id
        status = definition.status
        reason = definition.reason
        output_payload = definition.emitter(captures) if definition.emitter else {}

    input_payload = _build_input_payload(
        formula=formula_text,
        formula_shape_id=formula_shape_id,
        captures=captures,
    )

    translation_fingerprint = compute_translation_result_checksum(
        formula_rule_identity=formula_rule_identity,
        translator_version=FORMULA_TRANSLATOR_VERSION,
        formula_shape_id=formula_shape_id,
        translation_status=status.value,
        reason_code=reason.value,
        registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
        registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
        translation_input_payload=input_payload,
        translation_output_payload=output_payload,
        package_fingerprint=package_fingerprint,
        reviewed_by=reviewed_by,
    )

    return FormulaTranslationOutcome(
        formula_shape_id=formula_shape_id,
        translation_status=status,
        reason_code=reason,
        input_payload=input_payload,
        output_payload=output_payload,
        translation_fingerprint=translation_fingerprint,
    )
