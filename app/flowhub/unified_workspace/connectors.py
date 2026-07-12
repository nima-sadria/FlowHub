"""Workspace connector strategies over existing provider adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.connectors.destinations.woocommerce.write_adapter import WooCommercePriceWriteAdapter
from app.flowhub.channels.contracts import ChannelIdentifierSet, ChannelProductUpdate
from app.flowhub.commerce.service import CommerceHubService
from app.flowhub.product_pricing.service import ProductPricingService
from app.flowhub.unified_workspace.domain import ChannelCapabilities, WorkspaceDomainError
from app.flowhub.write_pipeline.adapters import ChannelWriteContext


@dataclass(frozen=True, slots=True)
class ListingUpdate:
    listing_id: str
    external_primary_id: str
    sku: str | None
    product_type: str
    parent_external_id: str | None
    current_price: float | None
    current_stock: float | None
    current_status: str | None
    target_price: float | None
    target_stock: float | None
    target_status: str | None
    currency: str | None
    unit: str | None
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class ListingUpdateResult:
    listing_id: str
    success: bool
    response: dict
    external_response_id: str | None = None
    error_category: str | None = None
    error_message: str | None = None
    retry_eligible: bool = False
    accepted_price: float | None = None
    accepted_stock: float | None = None
    accepted_status: str | None = None
    cache_verified: bool = False


class WorkspaceChannelConnector(Protocol):
    channel_id: str

    def capabilities(self) -> ChannelCapabilities: ...

    def validate_update(self, update: ListingUpdate) -> None: ...

    async def apply_updates(
        self, updates: list[ListingUpdate], *, requested_by: str
    ) -> list[ListingUpdateResult]: ...


class WooCommerceWorkspaceConnector:
    channel_id = "woocommerce:primary"

    def __init__(self, pricing: ProductPricingService) -> None:
        self.pricing = pricing

    def capabilities(self) -> ChannelCapabilities:
        currency = self.pricing.config.get("server.currency") or ""
        unit = self.pricing.config.get("server.currency_unit") or currency
        return ChannelCapabilities(
            channel_id=self.channel_id,
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
            requires_stock_management=True,
            maximum_batch_size=100,
            rate_limit_per_minute=None,
            health_state="configured"
            if self.pricing.config.get("woocommerce.url")
            else "unconfigured",
            primary_identifier_type="woocommerce_product_id",
            supported_statuses=("publish", "draft", "private"),
            currency=currency,
            unit=unit,
            write_available=True,
            version="uw-1.2",
        )

    def validate_update(self, update: ListingUpdate) -> None:
        if update.target_stock is not None or update.target_status is not None:
            raise WorkspaceDomainError(
                "WooCommerce stock and status writes are unavailable in the approved existing connector contract."
            )
        if update.target_price is None:
            raise WorkspaceDomainError("WooCommerce update requires a target price.")
        if not update.external_primary_id.isdigit():
            raise WorkspaceDomainError("WooCommerce primary identifier must be numeric.")

    async def apply_updates(
        self, updates: list[ListingUpdate], *, requested_by: str
    ) -> list[ListingUpdateResult]:
        adapter = WooCommercePriceWriteAdapter()
        context = ChannelWriteContext(
            get_setting=self.pricing.config.get, requested_by=requested_by
        )
        results: list[ListingUpdateResult] = []
        for update in updates:
            self.validate_update(update)
            try:
                response = await adapter.execute_item(_WooWriteItem(update), context)
            except Exception as exc:
                results.append(
                    ListingUpdateResult(
                        update.listing_id,
                        False,
                        {},
                        error_category="provider",
                        error_message=self.pricing._safe_error(exc),
                    )
                )
            else:
                verification = await adapter.verify_item(_WooWriteItem(update), context)
                verified = verification.get("verified") is True
                results.append(
                    ListingUpdateResult(
                        update.listing_id,
                        True,
                        {**response, "verification": verification},
                        external_response_id=_response_id(response),
                        accepted_price=update.target_price if verified else None,
                        cache_verified=verified,
                    )
                )
        return results


class SnappShopWorkspaceConnector:
    channel_id = "snappshop:main"

    def __init__(self, commerce: CommerceHubService) -> None:
        self.commerce = commerce

    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            channel_id=self.channel_id,
            read_price=True,
            write_price=True,
            read_stock=True,
            write_stock=True,
            read_status=True,
            write_status=False,
            supports_bulk_update=True,
            supports_partial_update=False,
            supports_multiple_listings=True,
            supports_variations=True,
            requires_stock_management=False,
            maximum_batch_size=50,
            rate_limit_per_minute=None,
            health_state="configured"
            if self.commerce._snappshop_connector() is not None
            else "unconfigured",
            primary_identifier_type="snappshop_product_number",
            supported_statuses=("active", "inactive"),
            currency="IRR",
            unit="TOMAN",
            write_available=True,
            version="uw-1.2",
        )

    def validate_update(self, update: ListingUpdate) -> None:
        if update.target_status is not None:
            raise WorkspaceDomainError(
                "SnappShop status writes are unavailable in the current official connector contract."
            )
        price = update.target_price if update.target_price is not None else update.current_price
        stock = update.target_stock if update.target_stock is not None else update.current_stock
        if price is None or stock is None:
            raise WorkspaceDomainError("SnappShop updates require explicit price and stock state.")
        if update.currency != "IRR" or str(update.unit or "").upper() != "TOMAN":
            raise WorkspaceDomainError("SnappShop prices require currency IRR and unit TOMAN.")

    async def apply_updates(
        self, updates: list[ListingUpdate], *, requested_by: str
    ) -> list[ListingUpdateResult]:
        connector = self.commerce._snappshop_connector()
        if connector is None:
            raise WorkspaceDomainError("SnappShop connector is not configured.")
        output: list[ListingUpdateResult] = []
        for offset in range(0, len(updates), 50):
            batch = updates[offset : offset + 50]
            requests: list[ChannelProductUpdate] = []
            for update in batch:
                self.validate_update(update)
                requests.append(
                    ChannelProductUpdate(
                        channel_id=self.channel_id,
                        identifiers=ChannelIdentifierSet(
                            external_product_id=update.external_primary_id,
                            sku=update.sku,
                        ),
                        price=update.target_price
                        if update.target_price is not None
                        else update.current_price,
                        stock_quantity=update.target_stock
                        if update.target_stock is not None
                        else update.current_stock,
                        currency="IRR",
                        price_unit="toman",
                        idempotency_key=update.idempotency_key,
                    )
                )
            provider_results = await connector.update_products(requests)
            for update, result in zip(batch, provider_results, strict=True):
                error = result.error
                verified = False
                observed = None
                if result.success:
                    try:
                        observed = await connector.get_product(
                            {"external_product_id": update.external_primary_id}
                        )
                        expected_price = (
                            update.target_price
                            if update.target_price is not None
                            else update.current_price
                        )
                        expected_stock = (
                            update.target_stock
                            if update.target_stock is not None
                            else update.current_stock
                        )
                        verified = (
                            observed.current_price == expected_price
                            and observed.stock_quantity == expected_stock
                        )
                    except Exception:
                        verified = False
                output.append(
                    ListingUpdateResult(
                        listing_id=update.listing_id,
                        success=result.success,
                        response={**result.raw, "verification": {"verified": verified}},
                        external_response_id=_response_id(result.raw),
                        error_category=error.category.value if error else None,
                        error_message=error.message if error else None,
                        retry_eligible=bool(error and error.retry.safe_to_retry),
                        accepted_price=(
                            update.target_price
                            if verified and update.target_price is not None
                            else None
                        ),
                        accepted_stock=(
                            update.target_stock
                            if verified and update.target_stock is not None
                            else None
                        ),
                        cache_verified=verified,
                    )
                )
        return output


class WorkspaceConnectorFactory:
    def __init__(self, pricing: ProductPricingService, commerce: CommerceHubService) -> None:
        self._connectors: dict[str, WorkspaceChannelConnector] = {
            "woocommerce:primary": WooCommerceWorkspaceConnector(pricing),
            "snappshop:main": SnappShopWorkspaceConnector(commerce),
        }

    def get(self, channel_id: str) -> WorkspaceChannelConnector:
        connector = self._connectors.get(channel_id)
        if connector is None:
            raise WorkspaceDomainError(
                f"Channel {channel_id} is Coming Soon and cannot participate in Workspace Apply."
            )
        return connector

    def implemented(self) -> tuple[WorkspaceChannelConnector, ...]:
        return tuple(self._connectors.values())


class _WooWriteItem:
    def __init__(self, update: ListingUpdate) -> None:
        self.channel_product_id = update.external_primary_id
        self.proposed_price = float(update.target_price or 0)
        self.pre_write_snapshot_json = {
            "item_type": update.product_type,
            "parent_product_id": update.parent_external_id,
        }


def _response_id(response: dict) -> str | None:
    for key in ("id", "request_id", "reference", "referenceCode"):
        if response.get(key) not in (None, ""):
            return str(response[key])
    return None
