"""Fail-closed guard evaluation over canonical integer amounts."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from app.flowhub.pricing_matrix.contracts import PricingGuardSet


@dataclass(frozen=True, slots=True)
class GuardEvaluation:
    accepted: bool
    reason_codes: tuple[str, ...]


def evaluate_guards(
    *,
    final_minor: int,
    basis_minor: int | Fraction,
    guards: PricingGuardSet,
    previous_applied_minor: int | None = None,
    worst_case_quote_minor: int | Fraction | None = None,
    lowest_quote_minor: int | Fraction | None = None,
    highest_quote_minor: int | Fraction | None = None,
) -> GuardEvaluation:
    """Evaluate guards without changing the proposed price."""

    failures: list[str] = []
    basis = Fraction(basis_minor)
    if guards.min_price_minor is not None and final_minor < guards.min_price_minor:
        failures.append("min_price")
    if guards.max_price_minor is not None and final_minor > guards.max_price_minor:
        failures.append("max_price")

    if previous_applied_minor is not None:
        if previous_applied_minor <= 0 and (
            guards.max_increase_bp is not None or guards.max_decrease_bp is not None
        ):
            failures.append("previous_price_zero")
        else:
            delta = final_minor - previous_applied_minor
            if (
                delta > 0
                and guards.max_increase_bp is not None
                and delta * 10_000 > previous_applied_minor * guards.max_increase_bp
            ):
                failures.append("max_increase")
            if (
                delta < 0
                and guards.max_decrease_bp is not None
                and (-delta) * 10_000 > previous_applied_minor * guards.max_decrease_bp
            ):
                failures.append("max_decrease")

    if guards.min_markup_bp is not None:
        if basis <= 0:
            failures.append("basis_zero")
        elif (Fraction(final_minor) - basis) * 10_000 < basis * guards.min_markup_bp:
            failures.append("min_markup")

    if guards.min_markup_worst_case_bp is not None:
        worst_case = Fraction(worst_case_quote_minor) if worst_case_quote_minor is not None else None
        if worst_case is None or worst_case <= 0:
            failures.append("worst_case_basis_unavailable")
        elif (Fraction(final_minor) - worst_case) * 10_000 < (
            worst_case * guards.min_markup_worst_case_bp
        ):
            failures.append("min_markup_worst_case")

    if guards.max_basis_spread_bp is not None:
        lowest = Fraction(lowest_quote_minor) if lowest_quote_minor is not None else None
        highest = Fraction(highest_quote_minor) if highest_quote_minor is not None else None
        if lowest is None or highest is None:
            failures.append("quote_spread_unavailable")
        elif lowest <= 0:
            failures.append("basis_zero")
        elif (highest - lowest) * 10_000 > (
            lowest * guards.max_basis_spread_bp
        ):
            failures.append("max_basis_spread")

    return GuardEvaluation(not failures, tuple(dict.fromkeys(failures)))
