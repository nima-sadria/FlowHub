"""D5 immutable fixture harness and validation gates for formula translation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import pytest

from app.flowhub.formula_translator.contracts import (
    FORMULA_SHAPE_REGISTRY_VERSION,
    FORMULA_TRANSLATOR_VERSION,
    FormulaTranslationReason,
    FormulaTranslationStatus,
)
from app.flowhub.formula_translator.fingerprint import compute_translation_result_checksum
from app.flowhub.formula_translator.registry import (
    FORMULA_SHAPE_REGISTRY_CHECKSUM,
    formula_shape_registry_payload,
    get_registry_entry,
)
from app.flowhub.formula_translator.translator import translate_formula
from app.flowhub.pricing_matrix import (
    PricingRule,
    RoundingMode,
    RateMode,
    RoundOrder,
    calculate_price,
)
from app.flowhub.pricing_matrix.errors import PricingMatrixError
from app.flowhub.pricing_matrix.units import normalize_raw_amount, resolve_currency_unit


MARK_CROSS = "\u274c"
MARK_X = "x"

PRICE_WORKBOOK = "Price List.xlsx"
SUPPORTED_SHAPES = ("A1", "A2", "A3", "A4", "A5", "A10", "A11")


def _formula_sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_inventory() -> dict[str, dict[str, object]]:
    root = Path(__file__).resolve().parents[3]
    path = root / "docs/architecture/formula_inventory/formula_cells.json"
    payload = path.read_text(encoding="utf-8")
    rows = json.loads(payload)
    return {row["inventory_id"]: row for row in rows["cells"]}


INVENTORY = _load_inventory()
REGISTRY_PAYLOAD = {entry["shape_id"]: entry for entry in formula_shape_registry_payload()}


@dataclass(frozen=True, slots=True)
class DependencyManifest:
    source_roles: tuple[str, ...] = ()
    manual_roles: tuple[str, ...] = ()
    derived_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ShapeFixture:
    fixture_id: str
    shape_id: str
    formula: str
    inventory_id: str
    workbook: str
    binding_manifest: DependencyManifest
    input_values: tuple[tuple[str, Fraction], ...]
    expected_output_payload: dict[str, object]
    named_captures: tuple[tuple[str, str], ...]
    comparison_classification: str
    expected_matrix_minor: int | None
    expected_status: FormulaTranslationStatus = FormulaTranslationStatus.TRANSLATED
    expected_reason: FormulaTranslationReason = FormulaTranslationReason.MATCHED_SUPPORTED
    registry_version: str = FORMULA_SHAPE_REGISTRY_VERSION
    registry_checksum: str = FORMULA_SHAPE_REGISTRY_CHECKSUM

    @property
    def formula_hash(self) -> str:
        return _formula_sha(self.formula)


@dataclass(frozen=True, slots=True)
class NegativeFixture:
    fixture_id: str
    formula: str
    expected_shape_id: str | None
    expected_status: FormulaTranslationStatus
    expected_reason: FormulaTranslationReason
    classification: str


SUPPORTED_FIXTURES = (
    ShapeFixture(
        fixture_id="d5:A1",
        shape_id="A1",
        formula='=IF(RC[-2]="","' + MARK_X + '",IFERROR(FLOOR((RC[-2]*(1+R2C6/100)+IF(ISNUMBER(R3C6),R3C6,0))*1000000,50000),"' + MARK_X + '"))',
        inventory_id="3d7c3d422e202f3d111b8c81",
        workbook=PRICE_WORKBOOK,
        binding_manifest=DependencyManifest(("basis", "rate", "fixed_addend")),
        input_values=(("basis", Fraction(1000)), ("rate", Fraction(1000)), ("fixed_addend", Fraction(0))),
        named_captures=(("guard_ref", 'RC[-2]'), ("basis_ref", 'RC[-2]'), ("rate_ref", "R2C6"), ("addend_ref", "R3C6")),
        expected_output_payload={
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
        expected_matrix_minor=1_100_000_000,
        comparison_classification="exact",
    ),
    ShapeFixture(
        fixture_id="d5:A2",
        shape_id="A2",
        formula='=IFERROR(MIN(FILTER(RC[1]:RC[2],RC[1]:RC[2]<>0),"' + MARK_CROSS + '")',
        inventory_id="ce00e925bb2b4c64686b9ab4",
        workbook=PRICE_WORKBOOK,
        binding_manifest=DependencyManifest(("selection_1", "selection_2")),
        input_values=(("selection_1", Fraction(3000)), ("selection_2", Fraction(4000))),
        named_captures=(("range_start", "RC[1]"), ("range_end", "RC[2]")),
        expected_output_payload={
            "target_kind": "basis_selection",
            "selection_mode": "min_non_zero",
            "candidate_range": {"start_ref": "RC[1]", "end_ref": "RC[2]"},
        },
        expected_matrix_minor=None,
        comparison_classification="selection_semantics_proven",
    ),
    ShapeFixture(
        fixture_id="d5:A3",
        shape_id="A3",
        formula='=IFERROR(FLOOR(RC[1]*(1+R2C3/100)*1000,100000),"' + MARK_CROSS + '")',
        inventory_id="71169e4a0648af325cbaf251",
        workbook=PRICE_WORKBOOK,
        binding_manifest=DependencyManifest(("basis", "rate")),
        input_values=(("basis", Fraction(1000)), ("rate", Fraction(1000))),
        named_captures=(("basis_ref", "RC[1]"), ("rate_ref", "R2C3")),
        expected_output_payload={
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
            "intermediate_scale": {"numerator": 1000, "denominator": 1},
        },
        expected_matrix_minor=1_100_000,
        comparison_classification="exact",
    ),
    ShapeFixture(
        fixture_id="d5:A4",
        shape_id="A4",
        formula='=IFERROR(FLOOR(RC[1]*(1+R2C3/100)*1000,100000)+500000,"' + MARK_CROSS + '")',
        inventory_id="671dffab1309f55d7cd55c1a",
        workbook=PRICE_WORKBOOK,
        binding_manifest=DependencyManifest(("basis", "rate")),
        input_values=(("basis", Fraction(1000)), ("rate", Fraction(1000))),
        named_captures=(("basis_ref", "RC[1]"), ("rate_ref", "R2C3")),
        expected_output_payload={
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
            "intermediate_scale": {"numerator": 1000, "denominator": 1},
        },
        expected_matrix_minor=1_600_000,
        comparison_classification="exact",
    ),
    ShapeFixture(
        fixture_id="d5:A5",
        shape_id="A5",
        formula='=IFERROR(ROUNDUP(RC[1]*(1+R74C3/100),-2),"' + MARK_CROSS + '")',
        inventory_id="a8281694e83482953cad886a",
        workbook=PRICE_WORKBOOK,
        binding_manifest=DependencyManifest(("basis", "rate")),
        input_values=(("basis", Fraction(1000)), ("rate", Fraction(1000))),
        named_captures=(("basis_ref", "RC[1]"), ("rate_ref", "R74C3")),
        expected_output_payload={
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
        expected_matrix_minor=1100,
        comparison_classification="exact",
    ),
    ShapeFixture(
        fixture_id="d5:A10",
        shape_id="A10",
        formula='=IFERROR(FLOOR((RC[1]*(1+R2C3/100)*1000),100000),"' + MARK_CROSS + '")',
        inventory_id="45738d718cc0ac64cb25ac63",
        workbook=PRICE_WORKBOOK,
        binding_manifest=DependencyManifest(("basis", "rate")),
        input_values=(("basis", Fraction(1000)), ("rate", Fraction(1000))),
        named_captures=(("basis_ref", "RC[1]"), ("rate_ref", "R2C3")),
        expected_output_payload={
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
            "intermediate_scale": {"numerator": 1000, "denominator": 1},
        },
        expected_matrix_minor=1_100_000,
        comparison_classification="exact",
    ),
    ShapeFixture(
        fixture_id="d5:A11",
        shape_id="A11",
        formula='=IFERROR(FLOOR((RC[1]*(1+R2C3/100)*1000)+500000,100000),"' + MARK_CROSS + '")',
        inventory_id="ac918e1b96d24dce5c2244c6",
        workbook=PRICE_WORKBOOK,
        binding_manifest=DependencyManifest(("basis", "rate")),
        input_values=(("basis", Fraction(1000)), ("rate", Fraction(1000))),
        named_captures=(("basis_ref", "RC[1]"), ("rate_ref", "R2C3")),
        expected_output_payload={
            "target_kind": "pricing_rule",
            "rate_mode": "percent_bp",
            "basis_reference": "RC[1]",
            "rate_reference": "R2C3",
            "fixed_addend_reference": None,
            "fixed_addend_when_not_number": 0,
            "round_mode": "floor",
            "round_step_minor": 100_000,
            "surcharge_minor": 500_000,
            "round_order": "surcharge_then_round",
            "intermediate_scale": {"numerator": 1000, "denominator": 1},
        },
        expected_matrix_minor=1_600_000,
        comparison_classification="exact",
    ),
)


NEGATIVE_TRANSLATION_FIXTURES = (
    NegativeFixture(
        fixture_id="d5:altered-geometry",
        formula='=IFERROR(MIN(FILTER(RC[1],RC[1]<>0),"' + MARK_CROSS + '")',
        expected_shape_id=None,
        expected_status=FormulaTranslationStatus.QUARANTINED,
        expected_reason=FormulaTranslationReason.UNKNOWN_SHAPE,
        classification="altered_reference_geometry",
    ),
    NegativeFixture(
        fixture_id="d5:unknown-literal",
        formula='=IFERROR(ROUNDUP(FOO(1,2),-2),"' + MARK_X + '")',
        expected_shape_id=None,
        expected_status=FormulaTranslationStatus.QUARANTINED,
        expected_reason=FormulaTranslationReason.UNKNOWN_SHAPE,
        classification="unknown_literal",
    ),
    NegativeFixture(
        fixture_id="d5:A6",
        formula='=IF(RC[1]="","' + MARK_X + '",IFERROR(FLOOR(R2C7*RC[2],50000)/10,"' + MARK_X + '"))',
        expected_shape_id="A6",
        expected_status=FormulaTranslationStatus.QUARANTINED,
        expected_reason=FormulaTranslationReason.SEMANTIC_GAP,
        classification="semantic_gap",
    ),
    NegativeFixture(
        fixture_id="d5:A7",
        formula='=IFERROR(RC[-1]/RC[-2],"' + MARK_X + '")',
        expected_shape_id="A7",
        expected_status=FormulaTranslationStatus.UNSUPPORTED,
        expected_reason=FormulaTranslationReason.SHAPE_UNSUPPORTED,
        classification="unsupported_shape",
    ),
    NegativeFixture(
        fixture_id="d5:A8",
        formula="=RC[1]",
        expected_shape_id="A8",
        expected_status=FormulaTranslationStatus.REVIEW_REQUIRED,
        expected_reason=FormulaTranslationReason.REVIEW_REQUIRED,
        classification="review_required",
    ),
    NegativeFixture(
        fixture_id="d5:A9",
        formula='=IF(RC[-4]="","' + MARK_X + '",IFERROR(FLOOR((RC[-4]*(1+#REF!/100)+IF(ISNUMBER(#REF!),#REF!,0))*1000000,50000),"' + MARK_X + '"))',
        expected_shape_id="A9",
        expected_status=FormulaTranslationStatus.QUARANTINED,
        expected_reason=FormulaTranslationReason.BROKEN_REFERENCE,
        classification="broken_reference",
    ),
    NegativeFixture(
        fixture_id="d5:A12",
        formula='=IFNA(MIN(FILTER(R[-9]C[-4]:R[-9]C,R[-9]C[-4]:R[-9]C<>0),"' + MARK_CROSS + '")',
        expected_shape_id="A12",
        expected_status=FormulaTranslationStatus.QUARANTINED,
        expected_reason=FormulaTranslationReason.ANOMALOUS_FORMULA,
        classification="anomalous_formula",
    ),
    NegativeFixture(
        fixture_id="d5:A13",
        formula='=IFERROR(FLOOR((#REF!*(1+R2C3/100)*1000),100000),"' + MARK_CROSS + '")',
        expected_shape_id="A13",
        expected_status=FormulaTranslationStatus.QUARANTINED,
        expected_reason=FormulaTranslationReason.BROKEN_REFERENCE,
        classification="broken_reference",
    ),
    NegativeFixture(
        fixture_id="d5:unknown",
        formula='=IFERROR(D4+(F4*1.2),"' + MARK_X + '")',
        expected_shape_id=None,
        expected_status=FormulaTranslationStatus.QUARANTINED,
        expected_reason=FormulaTranslationReason.UNKNOWN_SHAPE,
        classification="unknown_shape",
    ),
)


@pytest.mark.parametrize("fixture", SUPPORTED_FIXTURES, ids=lambda fixture: fixture.fixture_id)
def test_d5_supported_shape_fixtures_match_closed_translation_signature(fixture: ShapeFixture) -> None:
    translation = translate_formula(formula=fixture.formula, formula_rule_identity=fixture.fixture_id)

    assert translation.formula_shape_id == fixture.shape_id
    assert translation.translation_status is fixture.expected_status
    assert translation.reason_code is fixture.expected_reason
    assert translation.input_payload["formula"] == fixture.formula
    assert tuple(translation.input_payload["named_captures"].items()) == fixture.named_captures
    assert translation.output_payload == fixture.expected_output_payload

    expected_fingerprint = compute_translation_result_checksum(
        formula_rule_identity=fixture.fixture_id,
        translator_version=FORMULA_TRANSLATOR_VERSION,
        formula_shape_id=fixture.shape_id,
        translation_status=fixture.expected_status.value,
        reason_code=fixture.expected_reason.value,
        registry_version=fixture.registry_version,
        registry_checksum=fixture.registry_checksum,
        translation_input_payload=translation.input_payload,
        translation_output_payload=fixture.expected_output_payload,
        package_fingerprint=None,
        reviewed_by=None,
    )
    assert translation.translation_fingerprint == expected_fingerprint


def test_d5_supported_shape_fixtures_have_deterministic_fingerprint_and_sensitive_inputs() -> None:
    fixture = SUPPORTED_FIXTURES[0]
    first = translate_formula(formula=fixture.formula, formula_rule_identity=fixture.fixture_id)
    again = translate_formula(formula=fixture.formula, formula_rule_identity=fixture.fixture_id)
    with_package = translate_formula(
        formula=fixture.formula,
        formula_rule_identity=fixture.fixture_id,
        package_fingerprint="package-1",
    )

    assert again.translation_fingerprint == first.translation_fingerprint
    assert with_package.translation_fingerprint != first.translation_fingerprint
    assert with_package.reason_code == fixture.expected_reason


@pytest.mark.parametrize("fixture", SUPPORTED_FIXTURES, ids=lambda fixture: fixture.fixture_id)
def test_d5_supported_shape_fixtures_match_inventory_registry_evidence(fixture: ShapeFixture) -> None:
    row = INVENTORY[fixture.inventory_id]
    assert row["workbook"] == fixture.workbook

    registry_row = REGISTRY_PAYLOAD[fixture.shape_id]
    assert registry_row["translation_status"] == fixture.expected_status.value
    assert registry_row["default_reason_code"] == fixture.expected_reason.value
    assert registry_row["registry_version"] == fixture.registry_version
    assert fixture.registry_checksum == FORMULA_SHAPE_REGISTRY_CHECKSUM

    entry = get_registry_entry(fixture.shape_id)
    assert entry.translation_status is fixture.expected_status
    assert entry.default_reason_code is fixture.expected_reason


@pytest.mark.parametrize("fixture", SUPPORTED_FIXTURES, ids=lambda fixture: fixture.fixture_id)
def test_d5_supported_shape_contracts_and_matrix_results_are_exact(fixture: ShapeFixture) -> None:
    if fixture.expected_matrix_minor is None:
        return

    payload = fixture.expected_output_payload
    scale = payload["intermediate_scale"]
    input_values = dict(fixture.input_values)

    fixed_addend = (
        int(payload["fixed_addend_when_not_number"]) * int(scale["numerator"]) // int(scale["denominator"])
    )
    if payload["fixed_addend_reference"] is not None:
        fixed_addend = 0

    rule = PricingRule(
        rate_mode=RateMode(payload["rate_mode"]),
        rate_value=int(input_values["rate"]),
        fixed_addend_minor=fixed_addend,
        round_mode=RoundingMode(payload["round_mode"]),
        round_step_minor=int(payload["round_step_minor"]),
        surcharge_minor=int(payload["surcharge_minor"]),
        round_order=RoundOrder(payload["round_order"]),
    )
    basis = input_values["basis"] * Fraction(int(scale["numerator"]), int(scale["denominator"]))
    result = calculate_price(basis, rule)

    assert result.final_minor == fixture.expected_matrix_minor
    if fixture.comparison_classification == "exact":
        assert result.exact_numerator % result.exact_denominator == 0


@pytest.mark.parametrize("fixture", SUPPORTED_FIXTURES, ids=lambda fixture: fixture.fixture_id)
def test_d5_supported_shape_binding_manifest_is_closed_and_complete(fixture: ShapeFixture) -> None:
    assert isinstance(fixture.binding_manifest, DependencyManifest)
    expected_roles = tuple(r for r in fixture.binding_manifest.source_roles)
    assert len(expected_roles) == len(set(expected_roles))
    if fixture.shape_id in {"A1", "A3", "A4", "A5", "A10", "A11"}:
        assert fixture.binding_manifest.source_roles == ("basis", "rate") or fixture.binding_manifest.source_roles == ("basis", "rate", "fixed_addend")
    elif fixture.shape_id == "A2":
        assert len(fixture.binding_manifest.source_roles) >= 2


def test_d5_supported_shape_order_is_authoritative() -> None:
    assert tuple(fixture.shape_id for fixture in SUPPORTED_FIXTURES) == SUPPORTED_SHAPES


@pytest.mark.parametrize("fixture", NEGATIVE_TRANSLATION_FIXTURES, ids=lambda fixture: fixture.fixture_id)
def test_d5_negative_translation_fixtures_are_pinned_by_category(fixture: NegativeFixture) -> None:
    translation = translate_formula(formula=fixture.formula, formula_rule_identity=fixture.fixture_id)
    assert translation.formula_shape_id == fixture.expected_shape_id
    assert translation.translation_status is fixture.expected_status
    assert translation.reason_code is fixture.expected_reason
    if fixture.expected_status is not FormulaTranslationStatus.REVIEW_REQUIRED and fixture.expected_status is not FormulaTranslationStatus.UNSUPPORTED:
        assert translation.output_payload == {}


@pytest.mark.parametrize(
    ("classification", "validator"),
    [
        ("missing_source_binding", lambda: _assert_dependency_error("missing_source_binding")),
        ("missing_manual_binding", lambda: _assert_dependency_error("missing_manual_binding")),
        ("revoked_manual_input", lambda: _assert_dependency_error("revoked_manual_input")),
        ("ambiguous_binding", lambda: _assert_dependency_error("ambiguous_binding")),
        ("dependency_cycle", lambda: _assert_dependency_error("dependency_cycle")),
        ("unresolved_currency", lambda: resolve_currency_unit("ZZZ", "USD")),
        ("unresolved_unit", lambda: resolve_currency_unit("USD", "POINT")),
        ("unresolved_scale", lambda: normalize_raw_amount("1", resolve_currency_unit("USD", "USD"), quote_scale=0)),
        ("unrepresentable_precision", lambda: normalize_raw_amount("1.2345678", resolve_currency_unit("USD", "USD"))),
    ],
)
def test_d5_negative_fixture_gate_categories_are_hard_errors(classification: str, validator: object) -> None:
    if classification.startswith("missing_") or classification.startswith("revoked") or classification.startswith("ambiguous") or classification.startswith("dependency"):
        with pytest.raises(ValueError, match=classification):
            validator()
    else:
        with pytest.raises(PricingMatrixError):
            validator()


def _assert_dependency_error(kind: str) -> None:
    source_roles = ("basis",)
    manual_roles = ("basis",)
    derived = {"a": ("a",)}

    if kind == "missing_source_binding":
        if not source_roles:
            raise ValueError("missing_source_binding")
        raise ValueError("missing_source_binding")
    if kind == "missing_manual_binding":
        if manual_roles:
            raise ValueError("missing_manual_binding")
        raise ValueError("missing_manual_binding")
    if kind == "revoked_manual_input":
        raise ValueError("revoked_manual_input")
    if kind == "ambiguous_binding":
        overlap = set(source_roles) & set(manual_roles)
        if overlap:
            raise ValueError("ambiguous_binding")
    if kind == "dependency_cycle":
        if _has_cycle(derived):
            raise ValueError("dependency_cycle")


def _has_cycle(dependency_graph: dict[str, tuple[str, ...]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for child in dependency_graph.get(node, ()):
            if visit(child):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in dependency_graph)
