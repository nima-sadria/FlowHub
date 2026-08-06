"""Closed typed derived-value evaluation: DAG rules and exact arithmetic."""

from __future__ import annotations

from fractions import Fraction

import pytest

from app.flowhub.pricing_evaluation.contracts import DependencyRefKind, DerivedOperator
from app.flowhub.pricing_evaluation.derived import (
    DefinitionDraft,
    DependencyRef,
    evaluate_operator,
    topological_order,
    validate_dag,
)
from app.flowhub.pricing_evaluation.errors import DerivedValueError


def _ref(kind: DependencyRefKind, key: str) -> DependencyRef:
    return DependencyRef(kind=kind, key=key)


def test_multiply_percent_is_exact_not_floating_point():
    # 100000 * 1.10 = 110000 exactly, expressed as basis points (1000 = 10%).
    result = evaluate_operator(DerivedOperator.MULTIPLY_PERCENT, {"percent_bp": 1000}, (Fraction(100_000),))
    assert result == Fraction(110_000)


def test_floor_to_step_matches_pricing_matrix_semantics():
    result = evaluate_operator(DerivedOperator.FLOOR_TO_STEP, {"step_minor": 50_000}, (Fraction(274_999),))
    assert result == Fraction(250_000)


def test_round_up_to_step_rounds_up_on_any_remainder():
    result = evaluate_operator(DerivedOperator.ROUND_UP_TO_STEP, {"step_minor": 100}, (Fraction(250_001),))
    assert result == Fraction(250_100)
    exact = evaluate_operator(DerivedOperator.ROUND_UP_TO_STEP, {"step_minor": 100}, (Fraction(250_100),))
    assert exact == Fraction(250_100)


def test_min_nonzero_selection_ignores_zero_and_negative_candidates():
    result = evaluate_operator(
        DerivedOperator.MIN_NONZERO_SELECTION, {}, (Fraction(0), Fraction(500), Fraction(300))
    )
    assert result == Fraction(300)


def test_min_nonzero_selection_fails_closed_with_no_eligible_input():
    with pytest.raises(DerivedValueError, match="derived_no_eligible_input"):
        evaluate_operator(DerivedOperator.MIN_NONZERO_SELECTION, {}, (Fraction(0), Fraction(0)))


def test_multiply_and_divide_constant_are_exact_rationals():
    multiplied = evaluate_operator(
        DerivedOperator.MULTIPLY_CONSTANT,
        {"factor_numerator": 1, "factor_denominator": 3},
        (Fraction(9),),
    )
    assert multiplied == Fraction(3)
    divided = evaluate_operator(
        DerivedOperator.DIVIDE_CONSTANT, {"divisor_numerator": 10, "divisor_denominator": 1}, (Fraction(1000),)
    )
    assert divided == Fraction(100)


def test_add_constant_wrong_arity_fails_closed():
    with pytest.raises(DerivedValueError, match="derived_parameters_invalid"):
        evaluate_operator(DerivedOperator.ADD_CONSTANT, {"addend_minor": 1}, (Fraction(1), Fraction(2)))


def test_nested_dag_evaluates_deterministically_in_topological_order():
    # basis(100000) --MULTIPLY_PERCENT(10%)--> step1 --ADD_CONSTANT(5000)--> step2
    definitions = {
        "step1": DefinitionDraft(
            definition_key="step1",
            operator=DerivedOperator.MULTIPLY_PERCENT,
            parameters={"percent_bp": 1000},
            dependencies=(_ref(DependencyRefKind.OBSERVATION, "basis"),),
        ),
        "step2": DefinitionDraft(
            definition_key="step2",
            operator=DerivedOperator.ADD_CONSTANT,
            parameters={"addend_minor": 5_000},
            dependencies=(_ref(DependencyRefKind.DERIVED, "step1"),),
        ),
    }
    validate_dag(definitions)
    order = topological_order(definitions)
    assert order.index("step1") < order.index("step2")

    values = {"basis": Fraction(100_000)}
    for key in order:
        draft = definitions[key]
        inputs = tuple(
            values[ref.key] for ref in draft.dependencies
        )
        values[key] = evaluate_operator(draft.operator, draft.parameters, inputs)
    assert values["step1"] == Fraction(110_000)
    assert values["step2"] == Fraction(115_000)


def test_cycle_is_rejected_at_validation_time():
    definitions = {
        "a": DefinitionDraft(
            definition_key="a", operator=DerivedOperator.ADD_CONSTANT, parameters={"addend_minor": 1},
            dependencies=(_ref(DependencyRefKind.DERIVED, "b"),),
        ),
        "b": DefinitionDraft(
            definition_key="b", operator=DerivedOperator.ADD_CONSTANT, parameters={"addend_minor": 1},
            dependencies=(_ref(DependencyRefKind.DERIVED, "a"),),
        ),
    }
    with pytest.raises(DerivedValueError, match="derived_cycle_detected"):
        validate_dag(definitions)


def test_self_reference_is_a_cycle():
    definitions = {
        "a": DefinitionDraft(
            definition_key="a", operator=DerivedOperator.ADD_CONSTANT, parameters={"addend_minor": 1},
            dependencies=(_ref(DependencyRefKind.DERIVED, "a"),),
        ),
    }
    with pytest.raises(DerivedValueError, match="derived_cycle_detected"):
        validate_dag(definitions)


def test_bounded_depth_is_enforced():
    # A linear chain of 9 nested derived steps exceeds DERIVED_MAX_DEPTH (8).
    definitions: dict[str, DefinitionDraft] = {}
    previous_key = "leaf"
    for i in range(9):
        key = f"step{i}"
        kind = DependencyRefKind.OBSERVATION if i == 0 else DependencyRefKind.DERIVED
        definitions[key] = DefinitionDraft(
            definition_key=key,
            operator=DerivedOperator.ADD_CONSTANT,
            parameters={"addend_minor": 1},
            dependencies=(_ref(kind, previous_key),),
        )
        previous_key = key
    with pytest.raises(DerivedValueError, match="derived_depth_exceeded"):
        validate_dag(definitions)


def test_dependency_missing_from_the_draft_set_fails_closed():
    definitions = {
        "a": DefinitionDraft(
            definition_key="a", operator=DerivedOperator.ADD_CONSTANT, parameters={"addend_minor": 1},
            dependencies=(_ref(DependencyRefKind.DERIVED, "not-in-this-package"),),
        ),
    }
    with pytest.raises(DerivedValueError, match="derived_dependency_missing"):
        validate_dag(definitions)
