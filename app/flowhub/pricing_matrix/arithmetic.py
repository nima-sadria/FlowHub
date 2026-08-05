"""Exact Pricing Matrix arithmetic with one explicit rounding step."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from app.flowhub.pricing_matrix.contracts import (
    PricingRule,
    RateMode,
    RoundingMode,
    RoundOrder,
)
from app.flowhub.pricing_matrix.errors import PricingMatrixError

PRICING_ARITHMETIC_VERSION = "pricing-arithmetic-v1"


@dataclass(frozen=True, slots=True)
class PricingArithmeticResult:
    basis_numerator: int
    basis_denominator: int
    exact_numerator: int
    exact_denominator: int
    rounded_minor: int
    final_minor: int
    arithmetic_version: str = PRICING_ARITHMETIC_VERSION


def round_to_step(value: Fraction, step: int, mode: RoundingMode) -> int:
    """Round an exact rational to a step using the documented v1 semantics."""

    if isinstance(step, bool) or not isinstance(step, int) or step < 1:
        raise PricingMatrixError("round_step_invalid")
    scaled_numerator = value.numerator
    scaled_denominator = value.denominator * step
    floor_units, remainder = divmod(scaled_numerator, scaled_denominator)
    if mode is RoundingMode.FLOOR:
        units = floor_units
    elif mode is RoundingMode.CEIL:
        units = floor_units if remainder == 0 else floor_units + 1
    else:
        absolute_numerator = abs(scaled_numerator)
        absolute_units, absolute_remainder = divmod(absolute_numerator, scaled_denominator)
        if absolute_remainder * 2 >= scaled_denominator:
            absolute_units += 1
        units = absolute_units if scaled_numerator >= 0 else -absolute_units
    return units * step


def calculate_price(basis_minor: int | Fraction, rule: PricingRule) -> PricingArithmeticResult:
    """Apply one immutable rule to an integer basis without floating-point math."""

    if isinstance(basis_minor, bool) or not isinstance(basis_minor, (int, Fraction)):
        raise PricingMatrixError("exact_number_required", "basis must be an integer or Fraction")
    basis = Fraction(basis_minor)
    if basis < 0:
        raise PricingMatrixError("basis_invalid", "basis must be non-negative")

    if rule.rate_mode is RateMode.PERCENT_BP:
        exact = basis * Fraction(10_000 + rule.rate_value, 10_000)
    else:
        exact = basis * Fraction(rule.rate_value, 1_000_000)
    exact += rule.fixed_addend_minor

    if rule.round_order is RoundOrder.SURCHARGE_THEN_ROUND:
        exact += rule.surcharge_minor
        rounded = round_to_step(exact, rule.round_step_minor, rule.round_mode)
        final = rounded
    else:
        rounded = round_to_step(exact, rule.round_step_minor, rule.round_mode)
        final = rounded + rule.surcharge_minor

    if final <= 0:
        raise PricingMatrixError("nonpositive_price")
    return PricingArithmeticResult(
        basis_numerator=basis.numerator,
        basis_denominator=basis.denominator,
        exact_numerator=exact.numerator,
        exact_denominator=exact.denominator,
        rounded_minor=rounded,
        final_minor=final,
    )
