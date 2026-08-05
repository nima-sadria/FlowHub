from fractions import Fraction

import pytest

from app.flowhub.pricing_matrix import (
    PricingMatrixError,
    PricingRule,
    RateMode,
    RoundingMode,
    RoundOrder,
    calculate_price,
    round_to_step,
)


@pytest.mark.parametrize(
    ("value", "mode", "expected"),
    [
        (Fraction(15, 2), RoundingMode.NEAREST, 10),
        (Fraction(-15, 2), RoundingMode.NEAREST, -10),
        (Fraction(-11, 2), RoundingMode.FLOOR, -10),
        (Fraction(-11, 2), RoundingMode.CEIL, 0),
        (Fraction(20), RoundingMode.NEAREST, 20),
    ],
)
def test_rounding_contract(value: Fraction, mode: RoundingMode, expected: int) -> None:
    assert round_to_step(value, 10, mode) == expected


def test_percent_rule_uses_one_round_then_surcharge() -> None:
    result = calculate_price(
        1_000_000,
        PricingRule(
            rate_mode=RateMode.PERCENT_BP,
            rate_value=1_250,
            fixed_addend_minor=333,
            round_mode=RoundingMode.FLOOR,
            round_step_minor=50_000,
            surcharge_minor=10_000,
        ),
    )

    assert result.exact_numerator == 1_125_333
    assert result.exact_denominator == 1
    assert result.rounded_minor == 1_100_000
    assert result.final_minor == 1_110_000


def test_surcharge_then_round_is_a_distinct_policy_choice() -> None:
    result = calculate_price(
        1_000_000,
        PricingRule(
            rate_mode=RateMode.MULTIPLIER_PPM,
            rate_value=1_000_000,
            round_mode=RoundingMode.NEAREST,
            round_step_minor=100_000,
            surcharge_minor=60_000,
            round_order=RoundOrder.SURCHARGE_THEN_ROUND,
        ),
    )

    assert result.final_minor == 1_100_000


def test_nonpositive_final_price_is_rejected() -> None:
    with pytest.raises(PricingMatrixError, match="nonpositive_price") as error:
        calculate_price(
            1_000,
            PricingRule(
                rate_mode=RateMode.PERCENT_BP,
                rate_value=-10_000,
            ),
        )

    assert error.value.code == "nonpositive_price"


def test_float_values_are_rejected_at_domain_boundary() -> None:
    with pytest.raises(PricingMatrixError) as error:
        PricingRule(rate_mode=RateMode.PERCENT_BP, rate_value=12.5)  # type: ignore[arg-type]

    assert error.value.code == "integer_required"


def test_fractional_fx_basis_is_not_materialized_before_rounding() -> None:
    result = calculate_price(
        Fraction(2001, 2),
        PricingRule(
            rate_mode=RateMode.MULTIPLIER_PPM,
            rate_value=1_000_000,
            round_mode=RoundingMode.NEAREST,
            round_step_minor=1,
        ),
    )
    assert (result.basis_numerator, result.basis_denominator) == (2001, 2)
    assert result.final_minor == 1001
