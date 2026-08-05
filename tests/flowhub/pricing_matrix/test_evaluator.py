from datetime import UTC, datetime, timedelta
from fractions import Fraction

from app.flowhub.pricing_matrix import PricingRule, RateMode
from app.flowhub.pricing_matrix.evaluator import QuoteEvidence, evaluate_pricing_target


NOW = datetime(2026, 8, 5, 12, tzinfo=UTC)
RULE = PricingRule(rate_mode=RateMode.PERCENT_BP, rate_value=1_000)


def quote(ref: str, amount: int | None, *, age_days: int | None = 0, currency: str = "IRR") -> QuoteEvidence:
    return QuoteEvidence(
        quote_ref=ref,
        vendor_ref=f"vendor-{ref}",
        currency=currency,
        canonical_amount=amount,
        quoted_at=None if age_days is None else NOW - timedelta(days=age_days),
    )


def test_eligibility_is_frozen_and_max_age_is_inclusive() -> None:
    result = evaluate_pricing_target(
        quotes=(quote("fresh-boundary", 100, age_days=7), quote("stale", 90, age_days=8)),
        computation_currency="IRR",
        valuation_rates={},
        evaluated_at=NOW,
        max_quote_age_days=7,
        min_quote_count=1,
        rule=RULE,
    )
    assert result.outcome == "priced"
    assert result.basis_quote_ref == "fresh-boundary"
    assert result.assessments[1].exclusion_reason == "excluded_stale"


def test_fx_remains_an_exact_fraction_until_single_round() -> None:
    result = evaluate_pricing_target(
        quotes=(quote("usd", 1001, currency="USD"),),
        computation_currency="IRR",
        valuation_rates={"USD": Fraction(3, 2)},
        evaluated_at=NOW,
        max_quote_age_days=1,
        min_quote_count=1,
        rule=PricingRule(rate_mode=RateMode.MULTIPLIER_PPM, rate_value=1_000_000),
    )
    assert (result.basis_numerator, result.basis_denominator) == (3003, 2)
    assert result.arithmetic is not None
    assert result.arithmetic.final_minor == 1501


def test_missing_fx_for_one_quote_does_not_hide_valid_quotes() -> None:
    result = evaluate_pricing_target(
        quotes=(quote("valid", 100), quote("missing-fx", 1, currency="USD")),
        computation_currency="IRR",
        valuation_rates={},
        evaluated_at=NOW,
        max_quote_age_days=1,
        min_quote_count=1,
        rule=RULE,
    )
    assert result.outcome == "priced"
    assert result.basis_quote_ref == "valid"


def test_currency_unresolved_requires_a_single_exclusion_cause() -> None:
    unresolved = evaluate_pricing_target(
        quotes=(quote("usd", 100, currency="USD"),),
        computation_currency="IRR",
        valuation_rates={},
        evaluated_at=NOW,
        max_quote_age_days=1,
        min_quote_count=1,
        rule=RULE,
    )
    mixed = evaluate_pricing_target(
        quotes=(quote("usd", 100, currency="USD"), quote("undated", 100, age_days=None)),
        computation_currency="IRR",
        valuation_rates={},
        evaluated_at=NOW,
        max_quote_age_days=1,
        min_quote_count=1,
        rule=RULE,
    )
    assert unresolved.outcome == "currency_unresolved"
    assert mixed.outcome == "insufficient_quotes"
