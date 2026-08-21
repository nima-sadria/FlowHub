from decimal import Decimal

import pytest

from app.flowhub.unified_workspace.domain import (
    AvailabilitySignal,
    ChannelCapabilities,
    DraftChange,
    Money,
    SourceInstruction,
    WorkspaceDomainError,
    deterministic_revision_checksum,
    finite_number,
    normalize_direct_price,
    normalize_quantity,
    normalize_stock_status,
    resolve_availability,
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


@pytest.mark.parametrize(
    ("raw", "instruction", "signal", "warning"),
    [
        (None, SourceInstruction.UNAVAILABLE, AvailabilitySignal.OUT_OF_STOCK, None),
        ("0.00", SourceInstruction.UNAVAILABLE, AvailabilitySignal.OUT_OF_STOCK, None),
        ("x", SourceInstruction.UNAVAILABLE, AvailabilitySignal.OUT_OF_STOCK, None),
        ("hello", SourceInstruction.UNUSABLE, AvailabilitySignal.OUT_OF_STOCK, "UNUSABLE_MAPPED_PRICE"),
        ("10O000", SourceInstruction.UNUSABLE, AvailabilitySignal.OUT_OF_STOCK, "UNUSABLE_MAPPED_PRICE"),
    ],
)
def test_direct_mapped_unusable_price_is_an_oos_instruction_not_a_blocker(
    raw, instruction, signal, warning
):
    result = normalize_direct_price(
        raw, currency="IRR", unit="RIAL", monetary_precision=0
    )
    assert result.instruction is instruction
    assert result.availability_signal is signal
    assert result.warning_code == warning
    assert result.blocker_code is None


def test_rial_zero_decimal_fix_and_strict_mode_are_exact():
    fixed = normalize_direct_price(
        "15758858.000", currency="IRR", unit="RIAL", monetary_precision=0,
        fix_zero_decimal_prices=True,
    )
    strict = normalize_direct_price(
        "15758858.00", currency="IRR", unit="RIAL", monetary_precision=0,
        fix_zero_decimal_prices=False,
    )
    fractional = normalize_direct_price(
        "15758858.50", currency="IRR", unit="RIAL", monetary_precision=0,
    )
    assert fixed.target == "15758858"
    assert fixed.fix_applied is True
    assert strict.instruction is SourceInstruction.UNUSABLE
    assert fractional.instruction is SourceInstruction.UNUSABLE
    assert fractional.target is None


def test_other_currency_precision_and_stock_precedence_are_exact():
    price = normalize_direct_price(
        "15,758,858.25", currency="USD", unit="USD", monetary_precision=2
    )
    quantity = normalize_quantity("5")
    status = normalize_stock_status("0")
    desired, blockers = resolve_availability(price, quantity, status)
    assert price.target == "15758858.25"
    assert desired is AvailabilitySignal.OUT_OF_STOCK
    assert blockers == ()


@pytest.mark.parametrize("raw", ["-1", "2.5", "hello", True])
def test_invalid_quantity_is_a_row_blocker(raw):
    result = normalize_quantity(raw)
    assert result.instruction is SourceInstruction.INVALID
    assert result.blocker_code == "INVALID_QUANTITY"


@pytest.mark.parametrize(
    ("raw", "target"), [(None, "IN_STOCK"), ("1.00", "IN_STOCK"), ("۰", "OUT_OF_STOCK")]
)
def test_status_normalizes_only_blank_zero_and_one(raw, target):
    assert normalize_stock_status(raw).target == target
    assert normalize_stock_status("active").blocker_code == "INVALID_STOCK_STATUS"
