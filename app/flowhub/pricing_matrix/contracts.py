"""Immutable contracts for deterministic pricing arithmetic."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.flowhub.pricing_matrix.errors import PricingMatrixError

MAX_RATE_BP = 10_000_000
MAX_MULTIPLIER_PPM = 1_000_000_000_000
MAX_ABSOLUTE_ADJUSTMENT = 1_000_000_000_000_000_000
MAX_ROUND_STEP = 1_000_000_000_000_000


class RateMode(StrEnum):
    PERCENT_BP = "percent_bp"
    MULTIPLIER_PPM = "multiplier_ppm"


class RoundingMode(StrEnum):
    FLOOR = "floor"
    CEIL = "ceil"
    NEAREST = "nearest"


class RoundOrder(StrEnum):
    ROUND_THEN_SURCHARGE = "round_then_surcharge"
    SURCHARGE_THEN_ROUND = "surcharge_then_round"


@dataclass(frozen=True, slots=True)
class PricingGuardSet:
    min_price_minor: int | None = None
    max_price_minor: int | None = None
    max_increase_bp: int | None = None
    max_decrease_bp: int | None = None
    min_markup_bp: int | None = None
    min_markup_worst_case_bp: int | None = None
    max_basis_spread_bp: int | None = None

    def __post_init__(self) -> None:
        for name in ("min_price_minor", "max_price_minor"):
            value = getattr(self, name)
            if value is not None:
                _require_integer(name, value)
                if value < 0:
                    raise PricingMatrixError("guard_value_invalid", f"{name} must be non-negative")
        for name in (
            "max_increase_bp",
            "max_decrease_bp",
            "min_markup_bp",
            "min_markup_worst_case_bp",
            "max_basis_spread_bp",
        ):
            value = getattr(self, name)
            if value is not None:
                _require_integer(name, value)
                if value < 0 or value > MAX_RATE_BP:
                    raise PricingMatrixError("guard_value_invalid", f"{name} is outside the supported range")
        if (
            self.min_price_minor is not None
            and self.max_price_minor is not None
            and self.min_price_minor > self.max_price_minor
        ):
            raise PricingMatrixError("guard_range_invalid", "minimum price exceeds maximum price")


@dataclass(frozen=True, slots=True)
class PricingRule:
    rate_mode: RateMode
    rate_value: int
    fixed_addend_minor: int = 0
    round_mode: RoundingMode = RoundingMode.FLOOR
    round_step_minor: int = 1
    surcharge_minor: int = 0
    round_order: RoundOrder = RoundOrder.ROUND_THEN_SURCHARGE
    guards: PricingGuardSet = PricingGuardSet()

    def __post_init__(self) -> None:
        _require_integer("rate_value", self.rate_value)
        _require_integer("fixed_addend_minor", self.fixed_addend_minor)
        _require_integer("round_step_minor", self.round_step_minor)
        _require_integer("surcharge_minor", self.surcharge_minor)
        if self.rate_mode is RateMode.PERCENT_BP:
            if self.rate_value < -10_000 or self.rate_value > MAX_RATE_BP:
                raise PricingMatrixError("rate_value_invalid", "percent rate is outside the supported range")
        elif self.rate_value < 0 or self.rate_value > MAX_MULTIPLIER_PPM:
            raise PricingMatrixError("rate_value_invalid", "multiplier is outside the supported range")
        if abs(self.fixed_addend_minor) > MAX_ABSOLUTE_ADJUSTMENT:
            raise PricingMatrixError("fixed_addend_invalid")
        if abs(self.surcharge_minor) > MAX_ABSOLUTE_ADJUSTMENT:
            raise PricingMatrixError("surcharge_invalid")
        if self.round_step_minor < 1 or self.round_step_minor > MAX_ROUND_STEP:
            raise PricingMatrixError("round_step_invalid")


def _require_integer(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PricingMatrixError("integer_required", f"{name} must be an integer")
