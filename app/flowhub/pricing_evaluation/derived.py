"""Closed typed derived-value evaluation. No expression strings, no generic AST.

Every operator here is a fixed Python function operating on already-resolved
``Fraction`` inputs plus a small typed parameter dict — never on a formula
string. Cycle detection and depth bounding run at save time, before any
persistence, matching Authoritative Architecture rule 9.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from app.flowhub.pricing_evaluation.contracts import DERIVED_MAX_DEPTH, DependencyRefKind, DerivedOperator
from app.flowhub.pricing_evaluation.errors import (
    REASON_DERIVED_CYCLE_DETECTED,
    REASON_DERIVED_DEPENDENCY_MISSING,
    REASON_DERIVED_DEPTH_EXCEEDED,
    REASON_DERIVED_NO_ELIGIBLE_INPUT,
    REASON_DERIVED_OPERATOR_UNSUPPORTED,
    REASON_DERIVED_PARAMETERS_INVALID,
    DerivedValueError,
)


@dataclass(frozen=True, slots=True)
class DependencyRef:
    kind: DependencyRefKind
    key: str
    """For OBSERVATION: the ``source_role``. For MANUAL_INPUT: the
    ``manual_input_revision_id``. For DERIVED: the referenced
    ``DerivedValueDefinition`` identity used only for graph-building
    (in ``DefinitionDraft.definition_key``, not necessarily a persisted id
    yet, since cycle detection must run before the first save)."""


@dataclass(frozen=True, slots=True)
class DefinitionDraft:
    """An in-memory, not-yet-persisted derived-value definition."""

    definition_key: str
    operator: DerivedOperator
    parameters: dict[str, Any]
    dependencies: tuple[DependencyRef, ...]


def dependency_ref_from_json(payload: dict[str, Any]) -> DependencyRef:
    return DependencyRef(kind=DependencyRefKind(payload["kind"]), key=payload["key"])


def dependency_ref_to_json(ref: DependencyRef) -> dict[str, Any]:
    return {"kind": ref.kind.value, "key": ref.key}


def validate_dag(definitions: dict[str, DefinitionDraft]) -> None:
    """Reject cycles and depth overruns before any definition is persisted.

    ``definitions`` maps ``definition_key`` to its draft. Only DERIVED
    dependency refs participate in this graph; OBSERVATION/MANUAL_INPUT refs
    are leaves.
    """

    # Depth is the longest DERIVED-dependency chain ending at a node, computed
    # via memoized DFS so the result does not depend on dict iteration order
    # (a naive "depth at first visit" approach undercounts whenever a deep
    # node is reached indirectly before being visited as an outer-loop root).
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = dict.fromkeys(definitions, WHITE)
    depth: dict[str, int] = {}

    def visit(key: str) -> int:
        if key in depth:
            return depth[key]
        color[key] = GRAY
        draft = definitions[key]
        max_dependency_depth = 0
        for ref in draft.dependencies:
            if ref.kind is not DependencyRefKind.DERIVED:
                continue
            if ref.key not in definitions:
                raise DerivedValueError(REASON_DERIVED_DEPENDENCY_MISSING)
            if color[ref.key] == GRAY:
                raise DerivedValueError(REASON_DERIVED_CYCLE_DETECTED)
            dependency_depth = visit(ref.key) if color[ref.key] == WHITE else depth[ref.key]
            max_dependency_depth = max(max_dependency_depth, dependency_depth)
        color[key] = BLACK
        this_depth = max_dependency_depth + 1
        if this_depth > DERIVED_MAX_DEPTH:
            raise DerivedValueError(REASON_DERIVED_DEPTH_EXCEEDED)
        depth[key] = this_depth
        return this_depth

    for key in definitions:
        if color[key] == WHITE:
            visit(key)


def topological_order(definitions: dict[str, DefinitionDraft]) -> list[str]:
    """Deterministic topological order (dependencies before dependents).

    Must be called only after ``validate_dag`` has proven the graph acyclic.
    Ties are broken by ``definition_key`` for reproducibility (Authoritative
    Architecture / Section G: replay determinism).
    """

    visited: set[str] = set()
    order: list[str] = []

    def visit(key: str) -> None:
        if key in visited:
            return
        visited.add(key)
        draft = definitions[key]
        for ref in sorted(draft.dependencies, key=lambda r: r.key):
            if ref.kind is DependencyRefKind.DERIVED:
                visit(ref.key)
        order.append(key)

    for key in sorted(definitions):
        visit(key)
    return order


def _require_single(values: tuple[Fraction, ...]) -> Fraction:
    if len(values) != 1:
        raise DerivedValueError(REASON_DERIVED_PARAMETERS_INVALID)
    return values[0]


def _int_param(parameters: dict[str, Any], key: str) -> int:
    value = parameters.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise DerivedValueError(REASON_DERIVED_PARAMETERS_INVALID)
    return value


def evaluate_operator(
    operator: DerivedOperator, parameters: dict[str, Any], values: tuple[Fraction, ...]
) -> Fraction:
    """Evaluate one closed operator against already-resolved input values."""

    if operator is DerivedOperator.ADD_CONSTANT:
        basis = _require_single(values)
        return basis + _int_param(parameters, "addend_minor")

    if operator is DerivedOperator.MULTIPLY_PERCENT:
        basis = _require_single(values)
        percent_bp = _int_param(parameters, "percent_bp")
        return basis * Fraction(10_000 + percent_bp, 10_000)

    if operator is DerivedOperator.FLOOR_TO_STEP:
        value = _require_single(values)
        step = _int_param(parameters, "step_minor")
        if step < 1:
            raise DerivedValueError(REASON_DERIVED_PARAMETERS_INVALID)
        units = value.numerator // (value.denominator * step)
        return Fraction(units * step)

    if operator is DerivedOperator.ROUND_UP_TO_STEP:
        value = _require_single(values)
        step = _int_param(parameters, "step_minor")
        if step < 1:
            raise DerivedValueError(REASON_DERIVED_PARAMETERS_INVALID)
        scaled_denominator = value.denominator * step
        units, remainder = divmod(value.numerator, scaled_denominator)
        if remainder != 0:
            units += 1
        return Fraction(units * step)

    if operator is DerivedOperator.MIN_NONZERO_SELECTION:
        eligible = tuple(v for v in values if v > 0)
        if not eligible:
            raise DerivedValueError(REASON_DERIVED_NO_ELIGIBLE_INPUT)
        return min(eligible)

    if operator is DerivedOperator.MULTIPLY_CONSTANT:
        value = _require_single(values)
        numerator = _int_param(parameters, "factor_numerator")
        denominator = _int_param(parameters, "factor_denominator")
        if denominator == 0:
            raise DerivedValueError(REASON_DERIVED_PARAMETERS_INVALID)
        return value * Fraction(numerator, denominator)

    if operator is DerivedOperator.DIVIDE_CONSTANT:
        value = _require_single(values)
        numerator = _int_param(parameters, "divisor_numerator")
        denominator = _int_param(parameters, "divisor_denominator")
        if denominator == 0 or numerator == 0:
            raise DerivedValueError(REASON_DERIVED_PARAMETERS_INVALID)
        return value / Fraction(numerator, denominator)

    raise DerivedValueError(REASON_DERIVED_OPERATOR_UNSUPPORTED)
