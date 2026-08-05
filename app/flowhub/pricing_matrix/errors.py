"""Stable Pricing Matrix domain failures."""

from __future__ import annotations


class PricingMatrixError(ValueError):
    """A deterministic failure with a stable machine-readable code."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)
