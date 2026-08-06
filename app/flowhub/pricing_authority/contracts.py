"""Closed pricing authority identities shared by all write callers."""

from __future__ import annotations

from enum import StrEnum


class PricingAuthority(StrEnum):
    LEGACY_FORMULA_ENGINE = "legacy_formula_engine"
    MIGRATION_LOCKED = "migration_locked"
    PRICING_MATRIX = "pricing_matrix"


class PricingOrigin(StrEnum):
    LEGACY_FORMULA_ENGINE = "legacy_formula_engine"
    PRICING_MATRIX = "pricing_matrix"
