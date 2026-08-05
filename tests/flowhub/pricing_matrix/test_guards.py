from app.flowhub.pricing_matrix import PricingGuardSet, evaluate_guards


def test_guards_use_exact_cross_multiplication_at_boundary() -> None:
    accepted = evaluate_guards(
        final_minor=110,
        basis_minor=100,
        guards=PricingGuardSet(min_markup_bp=1_000),
    )
    rejected = evaluate_guards(
        final_minor=109,
        basis_minor=100,
        guards=PricingGuardSet(min_markup_bp=1_000),
    )

    assert accepted.accepted is True
    assert rejected.reason_codes == ("min_markup",)


def test_zero_basis_is_a_guard_rejection_not_an_infinite_ratio() -> None:
    result = evaluate_guards(
        final_minor=100,
        basis_minor=0,
        guards=PricingGuardSet(min_markup_bp=1),
    )
    assert result.accepted is False
    assert result.reason_codes == ("basis_zero",)


def test_multiple_failures_are_preserved_for_diagnostics() -> None:
    result = evaluate_guards(
        final_minor=80,
        basis_minor=100,
        previous_applied_minor=100,
        guards=PricingGuardSet(
            min_price_minor=90,
            max_decrease_bp=1_000,
            min_markup_bp=100,
        ),
    )
    assert result.reason_codes == ("min_price", "max_decrease", "min_markup")
