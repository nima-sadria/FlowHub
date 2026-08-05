import pytest

from app.flowhub.pricing_matrix.errors import PricingMatrixError
from app.flowhub.pricing_matrix.units import (
    normalize_raw_amount,
    resolve_currency_unit,
    to_channel_unit,
    validate_rule_channel_compatibility,
)


def test_toman_normalizes_to_canonical_rial_exactly() -> None:
    spec = resolve_currency_unit("IRR", "TOMAN")
    assert normalize_raw_amount("1200000", spec) == 12_000_000


def test_usd_decimal_normalizes_to_cents() -> None:
    spec = resolve_currency_unit("USD", "USD")
    assert normalize_raw_amount("100.50", spec) == 10_050


def test_precision_that_cannot_reach_canonical_integer_is_rejected() -> None:
    spec = resolve_currency_unit("USD", "USD")
    with pytest.raises(PricingMatrixError) as error:
        normalize_raw_amount("1.001", spec)
    assert error.value.code == "quote_precision_invalid"


def test_channel_conversion_requires_exact_division() -> None:
    spec = resolve_currency_unit("IRR", "TOMAN")
    assert to_channel_unit(1_000_000, spec) == 100_000
    with pytest.raises(PricingMatrixError) as error:
        to_channel_unit(1_000_005, spec)
    assert error.value.code == "channel_unit_inexact"


def test_round_then_surcharge_validates_both_values_for_toman() -> None:
    spec = resolve_currency_unit("IRR", "TOMAN")
    with pytest.raises(PricingMatrixError) as error:
        validate_rule_channel_compatibility(
            round_step_minor=50_000,
            surcharge_minor=5,
            round_order="round_then_surcharge",
            channel_spec=spec,
        )
    assert error.value.code == "surcharge_channel_unit_incompatible"


def test_irr_unit_is_never_inferred() -> None:
    with pytest.raises(PricingMatrixError) as error:
        resolve_currency_unit("IRR", "")
    assert error.value.code == "unit_unresolved"
