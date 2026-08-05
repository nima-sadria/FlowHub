"""Deterministic quote eligibility, valuation, basis selection, and pricing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from fractions import Fraction

from app.flowhub.pricing_matrix.arithmetic import PricingArithmeticResult, calculate_price
from app.flowhub.pricing_matrix.contracts import PricingRule
from app.flowhub.pricing_matrix.guards import GuardEvaluation, evaluate_guards


@dataclass(frozen=True, slots=True)
class QuoteEvidence:
    quote_ref: str
    vendor_ref: str
    currency: str
    canonical_amount: int | None
    quoted_at: datetime | None


@dataclass(frozen=True, slots=True)
class QuoteAssessment:
    quote_ref: str
    vendor_ref: str
    eligible: bool
    exclusion_reason: str | None
    valued_numerator: int | None
    valued_denominator: int | None


@dataclass(frozen=True, slots=True)
class PricingTargetResult:
    outcome: str
    assessments: tuple[QuoteAssessment, ...]
    basis_quote_ref: str | None = None
    basis_numerator: int | None = None
    basis_denominator: int | None = None
    arithmetic: PricingArithmeticResult | None = None
    guard_evaluation: GuardEvaluation | None = None


def evaluate_pricing_target(
    *,
    quotes: tuple[QuoteEvidence, ...],
    computation_currency: str,
    valuation_rates: dict[str, Fraction],
    evaluated_at: datetime,
    max_quote_age_days: int,
    min_quote_count: int,
    rule: PricingRule,
    previous_applied_minor: int | None = None,
) -> PricingTargetResult:
    """Evaluate a target using only frozen Workspace inputs."""

    if evaluated_at.tzinfo is None:
        raise ValueError("evaluated_at must be timezone-aware")
    if max_quote_age_days < 0 or min_quote_count < 1:
        raise ValueError("eligibility bounds are invalid")
    cutoff = evaluated_at - timedelta(days=max_quote_age_days)
    assessments: list[QuoteAssessment] = []
    eligible: list[tuple[QuoteEvidence, Fraction]] = []

    for quote in quotes:
        reason: str | None = None
        valued: Fraction | None = None
        if quote.canonical_amount is None:
            reason = "excluded_absent"
        elif quote.canonical_amount <= 0:
            reason = "excluded_zero"
        elif quote.quoted_at is None:
            reason = "excluded_undated"
        elif quote.quoted_at.tzinfo is None:
            reason = "excluded_undated"
        elif quote.quoted_at > evaluated_at:
            reason = "excluded_future_dated"
        elif quote.quoted_at < cutoff:
            reason = "excluded_stale"
        else:
            currency = quote.currency.strip().upper()
            if currency == computation_currency.strip().upper():
                rate = Fraction(1)
            else:
                rate = valuation_rates.get(currency)
            if rate is None or rate <= 0:
                reason = "excluded_currency_unresolved"
            else:
                valued = Fraction(quote.canonical_amount) * rate
                eligible.append((quote, valued))
        assessments.append(
            QuoteAssessment(
                quote_ref=quote.quote_ref,
                vendor_ref=quote.vendor_ref,
                eligible=reason is None,
                exclusion_reason=reason,
                valued_numerator=valued.numerator if valued is not None else None,
                valued_denominator=valued.denominator if valued is not None else None,
            )
        )

    if len(eligible) < min_quote_count:
        exclusion_reasons = {
            item.exclusion_reason for item in assessments if item.exclusion_reason is not None
        }
        outcome = (
            "currency_unresolved"
            if exclusion_reasons == {"excluded_currency_unresolved"}
            else "insufficient_quotes"
        )
        return PricingTargetResult(outcome=outcome, assessments=tuple(assessments))

    basis_quote, basis = min(eligible, key=lambda item: (item[1], item[0].quote_ref))
    arithmetic = calculate_price(basis, rule)
    valued_amounts = [item[1] for item in eligible]
    guard_evaluation = evaluate_guards(
        final_minor=arithmetic.final_minor,
        basis_minor=basis,
        guards=rule.guards,
        previous_applied_minor=previous_applied_minor,
        worst_case_quote_minor=max(valued_amounts),
        lowest_quote_minor=min(valued_amounts),
        highest_quote_minor=max(valued_amounts),
    )
    return PricingTargetResult(
        outcome="priced" if guard_evaluation.accepted else "guard_rejected",
        assessments=tuple(assessments),
        basis_quote_ref=basis_quote.quote_ref,
        basis_numerator=basis.numerator,
        basis_denominator=basis.denominator,
        arithmetic=arithmetic,
        guard_evaluation=guard_evaluation,
    )
