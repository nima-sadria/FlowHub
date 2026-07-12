from decimal import Decimal

import pytest

from app.flowhub.unified_workspace.domain import (
    ChannelCapabilities,
    DraftChange,
    Money,
    WorkspaceDomainError,
    deterministic_revision_checksum,
    finite_number,
    validate_product_editable,
    values_equal,
)


def test_money_keeps_currency_and_unit_separate_and_auditable():
    money = Money.create(
        "12,500",
        currency="IRR",
        unit="TOMAN",
        normalized_currency="IRR",
        normalized_unit="RIAL",
        conversion_factor="10",
        conversion_rule="explicit-v1",
        conversion_context="review-1",
        configuration_reference="snappshop:v1",
    )
    assert money.normalized_amount == Decimal("125000")
    assert money.currency == "IRR"
    assert money.unit == "TOMAN"
    assert money.as_dict()["conversion_rule"] == "explicit-v1"


def test_toman_is_not_accepted_as_currency_code():
    with pytest.raises(WorkspaceDomainError):
        Money.create(
            "10",
            currency="TOMAN",
            unit="TOMAN",
            normalized_currency="IRR",
            normalized_unit="RIAL",
            conversion_factor="10",
            conversion_rule="v1",
            conversion_context="test",
            configuration_reference="test",
        )


def test_revision_checksum_is_order_independent_and_channel_isolated():
    first = DraftChange("p1", "l1", "woocommerce:primary", "price", "100", "EUR", "EUR")
    second = DraftChange("p1", "l2", "snappshop:main", "stock", "5")
    assert deterministic_revision_checksum([first, second], {}) == deterministic_revision_checksum(
        [second, first], {}
    )
    changed = DraftChange("p1", "l2", "snappshop:main", "stock", "6")
    assert deterministic_revision_checksum([first, second], {}) != deterministic_revision_checksum(
        [first, changed], {}
    )


def test_variable_parent_is_never_editable():
    with pytest.raises(WorkspaceDomainError):
        validate_product_editable("variable")


@pytest.mark.parametrize(
    ("amount", "currency", "unit", "factor"),
    [
        ("1", "", "RIAL", "1"),
        ("not-a-number", "IRR", "RIAL", "1"),
        ("1", "IRR", "RIAL", "0"),
        ("NaN", "IRR", "RIAL", "1"),
    ],
)
def test_money_rejects_ambiguous_or_non_finite_inputs(amount, currency, unit, factor):
    with pytest.raises(WorkspaceDomainError):
        Money.create(
            amount,
            currency=currency,
            unit=unit,
            normalized_currency="IRR",
            normalized_unit="RIAL",
            conversion_factor=factor,
            conversion_rule="test",
            conversion_context="test",
            configuration_reference="test",
        )


@pytest.mark.parametrize(
    "arguments",
    [
        ("p", "l", "c", "unsupported", "1", None, None),
        ("", "l", "c", "stock", "1", None, None),
        ("p", "l", "c", "stock", "invalid", None, None),
        ("p", "l", "c", "stock", "-1", None, None),
        ("p", "l", "c", "price", "1", None, None),
    ],
)
def test_draft_change_rejects_invalid_identity_field_and_value(arguments):
    with pytest.raises(WorkspaceDomainError):
        DraftChange(*arguments)


def test_domain_comparison_capability_and_number_edge_cases():
    capabilities = ChannelCapabilities(
        channel_id="test",
        read_price=True,
        write_price=True,
        read_stock=True,
        write_stock=False,
        read_status=True,
        write_status=False,
        supports_bulk_update=False,
        supports_partial_update=True,
        supports_multiple_listings=False,
        supports_variations=True,
        requires_stock_management=False,
        maximum_batch_size=1,
        rate_limit_per_minute=None,
        health_state="configured",
        primary_identifier_type="id",
        supported_statuses=(),
        currency="EUR",
        unit="EUR",
        write_available=True,
        version="1",
    )
    assert capabilities.can_write("price") is True
    assert capabilities.can_write("unknown") is False
    assert values_equal("price", "1.00", "1") is True
    assert values_equal("price", "invalid", "1") is False
    assert values_equal("status", " Active ", "active") is True
    assert finite_number("1,000") is True
    assert finite_number("invalid") is False
    with pytest.raises(WorkspaceDomainError):
        validate_product_editable("bundle")
