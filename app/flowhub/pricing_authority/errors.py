"""Stable failures for per-Channel pricing authority enforcement."""

from __future__ import annotations


class PricingAuthorityError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class PricingAuthorityConflict(PricingAuthorityError):
    def __init__(self) -> None:
        super().__init__("pricing_authority_head_conflict")
