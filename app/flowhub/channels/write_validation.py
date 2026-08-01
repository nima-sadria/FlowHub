"""Shared validation gate for channel product writes."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from app.flowhub.unified_workspace.domain import WorkspaceDomainError


class ProductWriteCandidate(Protocol):
    external_primary_id: str
    product_type: str
    parent_external_id: str | None
    current_price: float | None
    current_stock: float | None
    target_price: float | None
    target_stock: float | None
    target_status: str | None
    currency: str | None
    unit: str | None


@dataclass(frozen=True, slots=True)
class ProductWritePolicy:
    channel_name: str
    write_price: bool
    write_stock: bool
    write_status: bool = False
    require_complete_price_stock: bool = False
    supports_variations: bool = True
    currency: str | None = None
    unit: str | None = None
    numeric_identifier: bool = False
    require_price: bool = False


def validate_product_write(update: ProductWriteCandidate, policy: ProductWritePolicy) -> None:
    """Apply provider-independent write invariants before adapter-specific checks."""

    identifier = str(update.external_primary_id or "").strip()
    if not identifier:
        raise WorkspaceDomainError(f"{policy.channel_name} product identifier is required.")
    if policy.numeric_identifier and not identifier.isdigit():
        raise WorkspaceDomainError(f"{policy.channel_name} primary identifier must be numeric.")
    if not policy.supports_variations and (
        update.product_type == "variation" or update.parent_external_id is not None
    ):
        raise WorkspaceDomainError(f"{policy.channel_name} variation writes are unavailable.")
    if update.target_price is not None and not policy.write_price:
        raise WorkspaceDomainError(f"{policy.channel_name} price writes are unavailable.")
    if update.target_stock is not None and not policy.write_stock:
        raise WorkspaceDomainError(f"{policy.channel_name} stock writes are unavailable.")
    if update.target_status is not None and not policy.write_status:
        raise WorkspaceDomainError(f"{policy.channel_name} status writes are unavailable.")

    price = update.target_price if update.target_price is not None else update.current_price
    stock = update.target_stock if update.target_stock is not None else update.current_stock
    if policy.require_price and update.target_price is None:
        raise WorkspaceDomainError(f"{policy.channel_name} update requires a target price.")
    if policy.require_complete_price_stock and (price is None or stock is None):
        raise WorkspaceDomainError(
            f"{policy.channel_name} updates require explicit price and stock state."
        )

    if price is not None and (not math.isfinite(float(price)) or float(price) < 0):
        raise WorkspaceDomainError(
            f"{policy.channel_name} price must be a non-negative finite number."
        )
    if stock is not None and (
        not math.isfinite(float(stock)) or float(stock) < 0 or not float(stock).is_integer()
    ):
        raise WorkspaceDomainError(f"{policy.channel_name} stock must be a non-negative integer.")
    if update.target_price is not None and policy.currency:
        if str(update.currency or "").upper() != policy.currency.upper():
            raise WorkspaceDomainError(
                f"{policy.channel_name} prices require currency {policy.currency}."
            )
        if policy.unit and str(update.unit or "").upper() != policy.unit.upper():
            raise WorkspaceDomainError(f"{policy.channel_name} prices require unit {policy.unit}.")
