"""Versioned exact currency-unit normalization for Pricing Matrix."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.flowhub.pricing_matrix.errors import PricingMatrixError

UNIT_REGISTRY_VERSION = "currency-unit-registry-v1"
MAX_RAW_LENGTH = 32
MAX_SIGNIFICANT_DIGITS = 18
MAX_DECIMAL_PLACES = 6
MAX_QUOTE_SCALE = 1_000_000_000

_RAW_NUMBER = re.compile(r"^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)$")


@dataclass(frozen=True, slots=True)
class CurrencyUnitSpec:
    currency: str
    unit: str
    canonical_unit: str
    canonical_factor: int
    registry_version: str = UNIT_REGISTRY_VERSION


_REGISTRY: dict[tuple[str, str], CurrencyUnitSpec] = {
    ("IRR", "RIAL"): CurrencyUnitSpec("IRR", "RIAL", "RIAL", 1),
    ("IRR", "TOMAN"): CurrencyUnitSpec("IRR", "TOMAN", "RIAL", 10),
    ("USD", "USD"): CurrencyUnitSpec("USD", "USD", "CENT", 100),
    ("EUR", "EUR"): CurrencyUnitSpec("EUR", "EUR", "CENT", 100),
    ("AED", "AED"): CurrencyUnitSpec("AED", "AED", "FILS", 100),
    ("JPY", "JPY"): CurrencyUnitSpec("JPY", "JPY", "JPY", 1),
}


def resolve_currency_unit(currency: str, unit: str) -> CurrencyUnitSpec:
    key = (str(currency).strip().upper(), str(unit).strip().upper())
    try:
        return _REGISTRY[key]
    except KeyError as exc:
        if key[0] == "IRR":
            raise PricingMatrixError("unit_unresolved", "IRR unit must be RIAL or TOMAN") from exc
        raise PricingMatrixError("currency_unit_unsupported") from exc


def normalize_raw_amount(raw_value: str, spec: CurrencyUnitSpec, *, quote_scale: int = 1) -> int:
    """Convert a source amount to its currency's canonical integer unit exactly."""

    if isinstance(quote_scale, bool) or not isinstance(quote_scale, int):
        raise PricingMatrixError("integer_required", "quote_scale must be an integer")
    if quote_scale < 1 or quote_scale > MAX_QUOTE_SCALE:
        raise PricingMatrixError("quote_scale_invalid")
    raw = str(raw_value).strip()
    if len(raw) > MAX_RAW_LENGTH or not _RAW_NUMBER.fullmatch(raw):
        raise PricingMatrixError("quote_format_invalid")
    unsigned = raw.lstrip("+-")
    whole, dot, fraction = unsigned.partition(".")
    decimal_places = len(fraction) if dot else 0
    significant_digits = len((whole + fraction).lstrip("0")) or 1
    if decimal_places > MAX_DECIMAL_PLACES or significant_digits > MAX_SIGNIFICANT_DIGITS:
        raise PricingMatrixError("quote_precision_invalid")
    digits = int((whole or "0") + fraction)
    if raw.startswith("-"):
        digits = -digits
    denominator = 10**decimal_places
    numerator = digits * quote_scale * spec.canonical_factor
    canonical, remainder = divmod(numerator, denominator)
    if remainder:
        raise PricingMatrixError("quote_precision_invalid")
    return canonical


def to_channel_unit(canonical_amount: int, spec: CurrencyUnitSpec) -> int:
    if isinstance(canonical_amount, bool) or not isinstance(canonical_amount, int):
        raise PricingMatrixError("integer_required")
    amount, remainder = divmod(canonical_amount, spec.canonical_factor)
    if remainder:
        raise PricingMatrixError("channel_unit_inexact")
    return amount


def validate_rule_channel_compatibility(
    *,
    round_step_minor: int,
    surcharge_minor: int,
    round_order: str,
    channel_spec: CurrencyUnitSpec,
) -> None:
    factor = channel_spec.canonical_factor
    if round_step_minor % factor:
        raise PricingMatrixError("round_step_channel_unit_incompatible")
    if round_order == "round_then_surcharge" and surcharge_minor % factor:
        raise PricingMatrixError("surcharge_channel_unit_incompatible")
