"""Workspace connector strategies over existing provider adapters."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.connectors.common.errors import ConnectorError
from app.connectors.destinations.woocommerce.write_adapter import WooCommercePriceWriteAdapter
from app.flowhub.channels.contracts import ChannelIdentifierSet, ChannelProductUpdate
from app.flowhub.commerce.service import CommerceHubService
from app.flowhub.product_pricing.service import ProductPricingService
from app.flowhub.unified_workspace.domain import ChannelCapabilities, WorkspaceDomainError
from app.flowhub.write_pipeline.adapters import ChannelWriteContext
from app.flowhub.write_pipeline.workspace_contracts import (
    WorkspaceWriteResult as ListingUpdateResult,
)
from app.flowhub.write_pipeline.workspace_contracts import (
    WriteOutcome,
)


class ListingUpdateLike(Protocol):
    @property
    def listing_id(self) -> str: ...
    @property
    def external_primary_id(self) -> str: ...
    @property
    def sku(self) -> str | None: ...
    @property
    def product_type(self) -> str: ...
    @property
    def parent_external_id(self) -> str | None: ...
    @property
    def current_price(self) -> float | None: ...
    @property
    def current_stock(self) -> float | None: ...
    @property
    def current_status(self) -> str | None: ...
    @property
    def target_price(self) -> float | None: ...
    @property
    def target_stock(self) -> float | None: ...
    @property
    def target_status(self) -> str | None: ...
    @property
    def currency(self) -> str | None: ...
    @property
    def unit(self) -> str | None: ...
    @property
    def idempotency_key(self) -> str: ...


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


class WorkspaceChannelConnector(Protocol):
    channel_id: str

    def capabilities(self) -> ChannelCapabilities: ...

    def validate_update(self, update: ListingUpdateLike) -> None: ...

    async def apply_updates(
        self, updates: Sequence[ListingUpdateLike], *, requested_by: str
    ) -> list[ListingUpdateResult]: ...

    async def verify_updates(
        self, updates: Sequence[ListingUpdateLike], *, requested_by: str
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

    def validate_update(self, update: ListingUpdateLike) -> None:
        if update.target_stock is not None or update.target_status is not None:
            raise WorkspaceDomainError(
                "WooCommerce stock and status writes are unavailable in the approved existing connector contract."
            )
        if update.target_price is None:
            raise WorkspaceDomainError("WooCommerce update requires a target price.")
        if not update.external_primary_id.isdigit():
            raise WorkspaceDomainError("WooCommerce primary identifier must be numeric.")
        if update.product_type == "variation" and not str(
            update.parent_external_id or ""
        ).isdigit():
            raise WorkspaceDomainError(
                "WooCommerce variation writes require a mapped numeric parent product ID."
            )

    async def apply_updates(
        self, updates: Sequence[ListingUpdateLike], *, requested_by: str
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
            except ConnectorError as exc:
                # Deterministic provider rejections (authentication,
                # permission, validation, or not-found) did not create an
                # external state transition and are terminal failures.  Only
                # transport/timeout uncertainty requires verification-only
                # reconciliation.
                deterministic = exc.code.value in {
                    "auth_failed",
                    "permission",
                    "not_found",
                    "provider_error",
                }
                results.append(
                    ListingUpdateResult(
                        listing_id=update.listing_id,
                        outcome=(WriteOutcome.FAILED if deterministic else WriteOutcome.RECONCILIATION_REQUIRED),
                        response={},
                        error_category=exc.code.value,
                        error_message=self.pricing._safe_error(exc),
                        retry_eligible=bool(exc.retryable),
                    )
                )
            except Exception as exc:
                results.append(
                    ListingUpdateResult(
                        listing_id=update.listing_id,
                        outcome=WriteOutcome.RECONCILIATION_REQUIRED,
                        response={},
                        error_category="provider",
                        error_message=self.pricing._safe_error(exc),
                    )
                )
            else:
                try:
                    verification = await adapter.verify_item(_WooWriteItem(update), context)
                except Exception as exc:
                    results.append(
                        ListingUpdateResult(
                            listing_id=update.listing_id,
                            outcome=WriteOutcome.RECONCILIATION_REQUIRED,
                            provider_accepted=True,
                            response={**response, "verification": {"verified": False}},
                            external_response_id=_response_id(response),
                            error_category="verification",
                            error_message=self.pricing._safe_error(exc),
                        )
                    )
                    continue
                expected_product_id = int(update.external_primary_id)
                expected_parent_id = (
                    int(update.parent_external_id)
                    if update.product_type == "variation" and update.parent_external_id
                    else None
                )
                verified = (
                    verification.get("verified") is True
                    and verification.get("provider") == "woocommerce"
                    and verification.get("product_id") == expected_product_id
                    and verification.get("parent_product_id") == expected_parent_id
                    and verification.get("variation_id")
                    == (expected_product_id if expected_parent_id is not None else None)
                )
                results.append(
                    ListingUpdateResult(
                        listing_id=update.listing_id,
                        outcome=(
                            WriteOutcome.VERIFIED_APPLIED
                            if verified
                            else WriteOutcome.RECONCILIATION_REQUIRED
                        ),
                        provider_accepted=True,
                        response={**response, "verification": verification},
                        external_response_id=_response_id(response),
                        accepted_price=update.target_price if verified else None,
                    )
                )
        return results

    async def verify_updates(
        self, updates: Sequence[ListingUpdateLike], *, requested_by: str
    ) -> list[ListingUpdateResult]:
        adapter = WooCommercePriceWriteAdapter()
        context = ChannelWriteContext(
            get_setting=self.pricing.config.get, requested_by=requested_by
        )
        results: list[ListingUpdateResult] = []
        for update in updates:
            try:
                verification = await adapter.verify_item(_WooWriteItem(update), context)
            except Exception as exc:
                results.append(
                    ListingUpdateResult(
                        listing_id=update.listing_id,
                        outcome=WriteOutcome.RECONCILIATION_REQUIRED,
                        error_category="verification",
                        error_message=self.pricing._safe_error(exc),
                    )
                )
                continue
            expected_id = int(update.external_primary_id)
            expected_parent = (
                int(update.parent_external_id)
                if update.product_type == "variation" and update.parent_external_id
                else None
            )
            verified = (
                verification.get("verified") is True
                and verification.get("provider") == "woocommerce"
                and verification.get("product_id") == expected_id
                and verification.get("parent_product_id") == expected_parent
                and verification.get("variation_id")
                == (expected_id if expected_parent is not None else None)
            )
            results.append(
                ListingUpdateResult(
                    listing_id=update.listing_id,
                    outcome=(
                        WriteOutcome.VERIFIED_APPLIED
                        if verified
                        else WriteOutcome.RECONCILIATION_REQUIRED
                    ),
                    response={"verification": verification},
                    accepted_price=update.target_price if verified else None,
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

    def validate_update(self, update: ListingUpdateLike) -> None:
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
        self, updates: Sequence[ListingUpdateLike], *, requested_by: str
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
                            observed.channel_id == self.channel_id
                            and observed.identifiers.external_product_id
                            == update.external_primary_id
                            and observed.identifiers.parent_product_number
                            == update.parent_external_id
                            and observed.current_price == expected_price
                            and observed.stock_quantity == expected_stock
                            and observed.currency == "IRR"
                            and str(observed.price_unit or "").lower() == "toman"
                        )
                    except Exception:
                        verified = False
                output.append(
                    ListingUpdateResult(
                        listing_id=update.listing_id,
                        outcome=(
                            WriteOutcome.VERIFIED_APPLIED
                            if result.success and verified
                            else WriteOutcome.RECONCILIATION_REQUIRED
                            if result.success
                            else WriteOutcome.FAILED
                        ),
                        provider_accepted=result.success,
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
                    )
                )
        return output

    async def verify_updates(
        self, updates: Sequence[ListingUpdateLike], *, requested_by: str
    ) -> list[ListingUpdateResult]:
        del requested_by
        connector = self.commerce._snappshop_connector()
        if connector is None:
            raise WorkspaceDomainError("SnappShop connector is not configured.")
        output: list[ListingUpdateResult] = []
        for update in updates:
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
                    observed.channel_id == self.channel_id
                    and observed.identifiers.external_product_id
                    == update.external_primary_id
                    and observed.identifiers.parent_product_number
                    == update.parent_external_id
                    and observed.current_price == expected_price
                    and observed.stock_quantity == expected_stock
                    and observed.currency == "IRR"
                    and str(observed.price_unit or "").lower() == "toman"
                )
            except Exception as exc:
                output.append(
                    ListingUpdateResult(
                        listing_id=update.listing_id,
                        outcome=WriteOutcome.RECONCILIATION_REQUIRED,
                        error_category="verification",
                        error_message=str(exc),
                    )
                )
                continue
            output.append(
                ListingUpdateResult(
                    listing_id=update.listing_id,
                    outcome=(
                        WriteOutcome.VERIFIED_APPLIED
                        if verified
                        else WriteOutcome.RECONCILIATION_REQUIRED
                    ),
                    response={"verification": {"verified": verified}},
                    accepted_price=update.target_price if verified else None,
                    accepted_stock=update.target_stock if verified else None,
                )
            )
        return output


class TapsiShopProductPricingConnector:
    """Compatibility strategy kept outside the Unified Workspace channel set.

    TapsiShop has no exact product read-back endpoint in the current connector
    contract.  A successful transport response therefore remains uncertain and
    is never promoted to ``VERIFIED_APPLIED``.
    """

    channel_id = "tapsishop:main"

    def __init__(self, commerce: CommerceHubService) -> None:
        self.commerce = commerce

    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            channel_id=self.channel_id,
            read_price=False,
            write_price=True,
            read_stock=False,
            write_stock=False,
            read_status=False,
            write_status=False,
            supports_bulk_update=True,
            supports_partial_update=False,
            supports_multiple_listings=True,
            supports_variations=False,
            requires_stock_management=False,
            maximum_batch_size=1,
            rate_limit_per_minute=None,
            health_state=(
                "configured"
                if self.commerce._tapsishop_connector() is not None
                else "unconfigured"
            ),
            primary_identifier_type="tapsishop_product_id",
            supported_statuses=(),
            currency="IRR",
            unit="RIAL",
            write_available=True,
            version="product-pricing-compatibility-1",
        )

    def validate_update(self, update: ListingUpdateLike) -> None:
        if update.target_price is None:
            raise WorkspaceDomainError("TapsiShop update requires a target price.")
        if update.currency != "IRR" or str(update.unit or "").upper() != "RIAL":
            raise WorkspaceDomainError("TapsiShop prices require currency IRR and unit RIAL.")
        if update.target_stock is not None or update.target_status is not None:
            raise WorkspaceDomainError("TapsiShop compatibility writes support price only.")

    async def apply_updates(
        self, updates: Sequence[ListingUpdateLike], *, requested_by: str
    ) -> list[ListingUpdateResult]:
        del requested_by
        connector = self.commerce._tapsishop_connector()
        if connector is None:
            raise WorkspaceDomainError("TapsiShop connector is not configured.")
        output: list[ListingUpdateResult] = []
        for update in updates:
            self.validate_update(update)
            provider_results = await connector.update_products(
                [
                    ChannelProductUpdate(
                        channel_id=self.channel_id,
                        identifiers=ChannelIdentifierSet(
                            external_product_id=update.external_primary_id,
                            sku=update.sku,
                        ),
                        price=update.target_price,
                        currency="IRR",
                        price_unit="rial",
                        idempotency_key=update.idempotency_key,
                    )
                ]
            )
            if len(provider_results) != 1:
                output.append(
                    ListingUpdateResult(
                        listing_id=update.listing_id,
                        outcome=WriteOutcome.RECONCILIATION_REQUIRED,
                        error_category="provider_contract",
                        error_message="TapsiShop returned an ambiguous item count.",
                    )
                )
                continue
            result = provider_results[0]
            error = result.error
            output.append(
                ListingUpdateResult(
                    listing_id=update.listing_id,
                    outcome=(
                        WriteOutcome.RECONCILIATION_REQUIRED
                        if result.success
                        else WriteOutcome.FAILED
                    ),
                    provider_accepted=result.success,
                    response={**(result.raw or {}), "verification": {"verified": False}},
                    external_response_id=_response_id(result.raw or {}),
                    error_category=error.category.value if error else None,
                    error_message=(
                        error.message
                        if error
                        else "TapsiShop accepted the write but exact read-back is unavailable."
                    ),
                    retry_eligible=False,
                )
            )
        return output

    async def verify_updates(
        self, updates: Sequence[ListingUpdateLike], *, requested_by: str
    ) -> list[ListingUpdateResult]:
        del requested_by
        return [
            ListingUpdateResult(
                listing_id=update.listing_id,
                outcome=WriteOutcome.RECONCILIATION_REQUIRED,
                provider_accepted=True,
                error_category="verification_unavailable",
                error_message="TapsiShop has no exact product read-back endpoint.",
                retry_eligible=False,
            )
            for update in updates
        ]


class WorkspaceConnectorFactory:
    def __init__(self, pricing: ProductPricingService, commerce: CommerceHubService) -> None:
        self._connectors: dict[str, WorkspaceChannelConnector] = {
            "woocommerce:primary": WooCommerceWorkspaceConnector(pricing),
            "snappshop:main": SnappShopWorkspaceConnector(commerce),
        }
        self._product_pricing_connectors: dict[str, WorkspaceChannelConnector] = {
            **self._connectors,
            "tapsishop:main": TapsiShopProductPricingConnector(commerce),
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

    def get_product_pricing(self, channel_id: str) -> WorkspaceChannelConnector:
        connector = self._product_pricing_connectors.get(channel_id)
        if connector is None:
            raise WorkspaceDomainError(f"Channel {channel_id} has no approved write strategy.")
        return connector


class _WooWriteItem:
    def __init__(self, update: ListingUpdateLike) -> None:
        self.channel_product_id = update.external_primary_id
        self.proposed_price = float(update.target_price or 0)
        self.pre_write_snapshot_json: dict[str, object] = {
            "item_type": update.product_type,
            "parent_product_id": update.parent_external_id,
        }


def _response_id(response: dict[str, object]) -> str | None:
    for key in ("id", "request_id", "reference", "referenceCode"):
        if response.get(key) not in (None, ""):
            return str(response[key])
    return None
