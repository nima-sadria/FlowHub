"""Stable domain failures for Business Observability."""

from __future__ import annotations


class BusinessObservabilityError(ValueError):
    """A deterministic failure with a machine-readable code."""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        super().__init__(message or code)
