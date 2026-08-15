"""Workspace connector strategies over existing provider adapters."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from app.connectors.common.current_state import (
    CurrentStateError,
    CurrentStateIdentity,
    CurrentStateRecord,
    CurrentStateRequest,
    CurrentStateResult,
    CurrentStateStrategy,
    failed_current_state,
    unsupported_current_state,
)
from app.connectors.common.errors import ConnectorError
from app.connectors.destinations.woocommerce.write_adapter import WooCommercePriceWriteAdapter
from app.flowhub.channels.contracts import (
    ChannelIdentifierSet,
    ChannelProductUpdate,
    ChannelProductUpdateResult,
)
from app.flowhub.channels.write_validation import ProductWritePolicy, validate_product_write
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


logger = logging.getLogger(__name__)


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
            mapping_required_fields=("external_id",),
        )

    def validate_update(self, update: ListingUpdateLike) -> None:
        validate_product_write(
            update,
            ProductWritePolicy(
                channel_name="WooCommerce",
                write_price=True,
                write_stock=False,
                require_price=True,
                numeric_identifier=True,
            ),
        )
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
        completed: dict[str, ListingUpdateResult] = {}
        responses: dict[str, dict[str, object]] = {}
        successful: list[ListingUpdateLike] = []
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
                completed[update.listing_id] = ListingUpdateResult(
                    listing_id=update.listing_id,
                    outcome=(
                        WriteOutcome.FAILED
                        if deterministic
                        else WriteOutcome.RECONCILIATION_REQUIRED
                    ),
                    response={},
                    error_category=exc.code.value,
                    error_message=self.pricing._safe_error(exc),
                    retry_eligible=bool(exc.retryable),
                )
            except Exception as exc:
                completed[update.listing_id] = ListingUpdateResult(
                    listing_id=update.listing_id,
                    outcome=WriteOutcome.RECONCILIATION_REQUIRED,
                    response={},
                    error_category="provider",
                    error_message=self.pricing._safe_error(exc),
                )
            else:
                responses[update.listing_id] = response
                successful.append(update)

        state = await _fetch_current_state(
            adapter,
            _current_state_request(
                self.channel_id, successful, required_fields={"price"}
            ),
            context=context,
            strategy=CurrentStateStrategy.BATCH_BY_ID,
            safe_error=self.pricing._safe_error,
        )
        for update in successful:
            record = state.records.get(update.listing_id)
            error = state.errors.get(update.listing_id)
            verified = _woocommerce_state_matches(update, record)
            response = responses[update.listing_id]
            completed[update.listing_id] = ListingUpdateResult(
                listing_id=update.listing_id,
                outcome=(
                    WriteOutcome.VERIFIED_APPLIED
                    if verified
                    else WriteOutcome.RECONCILIATION_REQUIRED
                ),
                provider_accepted=True,
                response={
                    **response,
                    "verification": _verification_evidence(record, error, verified, state),
                },
                external_response_id=_response_id(response),
                error_category="verification" if error else None,
                error_message=error.message if error else None,
                retry_eligible=bool(error and error.retry_eligible),
                accepted_price=update.target_price if verified else None,
            )
        return [completed[update.listing_id] for update in updates]

    async def verify_updates(
        self, updates: Sequence[ListingUpdateLike], *, requested_by: str
    ) -> list[ListingUpdateResult]:
        adapter = WooCommercePriceWriteAdapter()
        context = ChannelWriteContext(
            get_setting=self.pricing.config.get, requested_by=requested_by
        )
        state = await _fetch_current_state(
            adapter,
            _current_state_request(
                self.channel_id, updates, required_fields={"price"}
            ),
            context=context,
            strategy=CurrentStateStrategy.BATCH_BY_ID,
            safe_error=self.pricing._safe_error,
        )
        results: list[ListingUpdateResult] = []
        for update in updates:
            record = state.records.get(update.listing_id)
            error = state.errors.get(update.listing_id)
            verified = _woocommerce_state_matches(update, record)
            results.append(
                ListingUpdateResult(
                    listing_id=update.listing_id,
                    outcome=(
                        WriteOutcome.VERIFIED_APPLIED
                        if verified
                        else WriteOutcome.RECONCILIATION_REQUIRED
                    ),
                    response={
                        "verification": _verification_evidence(
                            record, error, verified, state
                        )
                    },
                    error_category="verification" if error else None,
                    error_message=error.message if error else None,
                    retry_eligible=bool(error and error.retry_eligible),
                    accepted_price=update.target_price if verified else None,
                )
            )
        return results


class SnappShopWorkspaceConnector:
    channel_id = "snappshop:main"

    def __init__(self, commerce: CommerceHubService) -> None:
        self.commerce = commerce

    def capabilities(self) -> ChannelCapabilities:
        write_enabled = self.commerce.channel_write_enabled(self.channel_id)
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
            write_available=write_enabled,
            version="uw-1.2",
            mapping_required_fields=("external_id", "stock", "status"),
        )

    def validate_update(self, update: ListingUpdateLike) -> None:
        validate_product_write(
            update,
            ProductWritePolicy(
                channel_name="SnappShop",
                write_price=True,
                write_stock=True,
                require_complete_price_stock=True,
                currency="IRR",
                unit="TOMAN",
            ),
        )

    async def apply_updates(
        self, updates: Sequence[ListingUpdateLike], *, requested_by: str
    ) -> list[ListingUpdateResult]:
        if not self.commerce.channel_write_enabled(self.channel_id):
            raise WorkspaceDomainError(
                "SnappShop is Read-only. Enable channel writes before Apply."
            )
        connector = self.commerce._snappshop_connector()
        if connector is None:
            raise WorkspaceDomainError("SnappShop connector is not configured.")
        provider_outcomes: list[
            tuple[ListingUpdateLike, ChannelProductUpdateResult]
        ] = []
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
                provider_outcomes.append((update, result))

        successful = [update for update, result in provider_outcomes if result.success]
        state = await _fetch_current_state(
            connector,
            _current_state_request(
                self.channel_id, successful, required_fields={"price", "stock"}
            ),
            strategy=CurrentStateStrategy.COLLECTION_SCAN,
        )
        output: list[ListingUpdateResult] = []
        for update, result in provider_outcomes:
            write_error = result.error
            record = state.records.get(update.listing_id) if result.success else None
            state_error = state.errors.get(update.listing_id) if result.success else None
            verified = result.success and _snappshop_state_matches(update, record)
            output.append(
                ListingUpdateResult(
                    listing_id=update.listing_id,
                    outcome=(
                        WriteOutcome.VERIFIED_APPLIED
                        if verified
                        else WriteOutcome.RECONCILIATION_REQUIRED
                        if result.success
                        else WriteOutcome.FAILED
                    ),
                    provider_accepted=result.success,
                    response={
                        **result.raw,
                        "verification": (
                            _verification_evidence(record, state_error, verified, state)
                            if result.success
                            else {"verified": False, "skipped": "write_failed"}
                        ),
                    },
                    external_response_id=_response_id(result.raw),
                    error_category=(
                        write_error.category.value
                        if write_error
                        else "verification"
                        if state_error
                        else None
                    ),
                    error_message=(
                        write_error.message
                        if write_error
                        else state_error.message
                        if state_error
                        else None
                    ),
                    retry_eligible=(
                        bool(write_error.retry.safe_to_retry)
                        if write_error
                        else bool(state_error and state_error.retry_eligible)
                    ),
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
        state = await _fetch_current_state(
            connector,
            _current_state_request(
                self.channel_id, updates, required_fields={"price", "stock"}
            ),
            strategy=CurrentStateStrategy.COLLECTION_SCAN,
        )
        output: list[ListingUpdateResult] = []
        for update in updates:
            record = state.records.get(update.listing_id)
            error = state.errors.get(update.listing_id)
            verified = _snappshop_state_matches(update, record)
            output.append(
                ListingUpdateResult(
                    listing_id=update.listing_id,
                    outcome=(
                        WriteOutcome.VERIFIED_APPLIED
                        if verified
                        else WriteOutcome.RECONCILIATION_REQUIRED
                    ),
                    response={
                        "verification": _verification_evidence(
                            record, error, verified, state
                        )
                    },
                    error_category="verification" if error else None,
                    error_message=error.message if error else None,
                    retry_eligible=bool(error and error.retry_eligible),
                    accepted_price=update.target_price if verified else None,
                    accepted_stock=update.target_stock if verified else None,
                )
            )
        return output


class TapsiShopWorkspaceConnector:
    """Reviewed combined-state writes over the documented TapsiShop endpoint.

    The provider documents a body containing both price and stock and does not
    document partial-update semantics or an exact product read-back endpoint.
    FlowHub therefore sends an explicit complete state, limits batches to one,
    and keeps successful responses in reconciliation-required state.
    """

    channel_id = "tapsishop:main"

    def __init__(self, commerce: CommerceHubService) -> None:
        self.commerce = commerce

    def capabilities(self) -> ChannelCapabilities:
        write_enabled = self.commerce.channel_write_enabled(self.channel_id)
        return ChannelCapabilities(
            channel_id=self.channel_id,
            read_price=True,
            write_price=True,
            read_stock=True,
            write_stock=True,
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
            write_available=write_enabled,
            version="uw-1.2",
            mapping_required_fields=("external_id", "stock", "status"),
        )

    def validate_update(self, update: ListingUpdateLike) -> None:
        validate_product_write(
            update,
            ProductWritePolicy(
                channel_name="TapsiShop",
                write_price=True,
                write_stock=True,
                require_complete_price_stock=True,
                supports_variations=False,
                currency="IRR",
                unit="RIAL",
            ),
        )

    async def apply_updates(
        self, updates: Sequence[ListingUpdateLike], *, requested_by: str
    ) -> list[ListingUpdateResult]:
        del requested_by
        if not self.commerce.channel_write_enabled(self.channel_id):
            raise WorkspaceDomainError(
                "TapsiShop is Read-only. Enable channel writes before Apply."
            )
        connector = self.commerce._tapsishop_connector()
        if connector is None:
            raise WorkspaceDomainError("TapsiShop connector is not configured.")
        state = await _fetch_current_state(
            connector,
            _current_state_request(
                self.channel_id, updates, required_fields={"price", "stock"}
            ),
            strategy=CurrentStateStrategy.UNSUPPORTED,
        )
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
                        price=(
                            update.target_price
                            if update.target_price is not None
                            else update.current_price
                        ),
                        stock_quantity=(
                            update.target_stock
                            if update.target_stock is not None
                            else update.current_stock
                        ),
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
                    response={
                        **(result.raw or {}),
                        "verification": (
                            _verification_evidence(
                                None,
                                state.errors.get(update.listing_id),
                                False,
                                state,
                            )
                            if result.success
                            else {"verified": False, "skipped": "write_failed"}
                        ),
                    },
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
        connector = self.commerce._tapsishop_connector()
        request = _current_state_request(
            self.channel_id, updates, required_fields={"price", "stock"}
        )
        state = await _fetch_current_state(
            connector,
            request,
            strategy=CurrentStateStrategy.UNSUPPORTED,
        )
        return [
            ListingUpdateResult(
                listing_id=update.listing_id,
                outcome=WriteOutcome.RECONCILIATION_REQUIRED,
                provider_accepted=True,
                error_category="verification_unavailable",
                error_message="TapsiShop has no exact product read-back endpoint.",
                retry_eligible=False,
                response={
                    "verification": _verification_evidence(
                        None,
                        state.errors.get(update.listing_id),
                        False,
                        state,
                    )
                },
            )
            for update in updates
        ]


class TechnolifeWorkspaceConnector:
    channel_id = "technolife:main"

    def __init__(self, commerce: CommerceHubService) -> None:
        self.commerce = commerce

    def capabilities(self) -> ChannelCapabilities:
        write_enabled = self.commerce.channel_write_enabled(self.channel_id)
        return ChannelCapabilities(
            channel_id=self.channel_id,
            read_price=True,
            write_price=True,
            read_stock=True,
            write_stock=True,
            read_status=True,
            write_status=False,
            supports_bulk_update=False,
            supports_partial_update=True,
            supports_multiple_listings=True,
            supports_variations=True,
            requires_stock_management=False,
            maximum_batch_size=1,
            rate_limit_per_minute=None,
            health_state=(
                "configured"
                if self.commerce._technolife_connector() is not None
                else "unconfigured"
            ),
            primary_identifier_type="technolife_seller_item_code",
            supported_statuses=("active", "hidden"),
            currency="IRR",
            unit="RIAL",
            write_available=write_enabled,
            version="uw-1.3",
            mapping_required_fields=("external_id", "stock", "status"),
        )

    def validate_update(self, update: ListingUpdateLike) -> None:
        validate_product_write(
            update,
            ProductWritePolicy(
                channel_name="Technolife",
                write_price=True,
                write_stock=True,
                currency="IRR",
                unit="RIAL",
            ),
        )
        if not str(update.parent_external_id or "").strip():
            raise WorkspaceDomainError(
                "Technolife writes require the parent productCode for read-back verification."
            )

    async def apply_updates(
        self, updates: Sequence[ListingUpdateLike], *, requested_by: str
    ) -> list[ListingUpdateResult]:
        del requested_by
        if not self.commerce.channel_write_enabled(self.channel_id):
            raise WorkspaceDomainError(
                "Technolife is Read-only. Enable channel writes before Apply."
            )
        connector = self.commerce._technolife_connector()
        if connector is None:
            raise WorkspaceDomainError("Technolife connector is not configured.")
        requests: list[ChannelProductUpdate] = []
        for update in updates:
            self.validate_update(update)
            requests.append(
                ChannelProductUpdate(
                    channel_id=self.channel_id,
                    identifiers=ChannelIdentifierSet(
                        external_product_id=update.external_primary_id,
                        sku=update.sku,
                        product_number=update.parent_external_id,
                        parent_product_number=update.parent_external_id,
                    ),
                    price=update.target_price,
                    stock_quantity=update.target_stock,
                    currency="IRR",
                    price_unit="RIAL",
                    idempotency_key=update.idempotency_key,
                )
            )
        provider_results = await connector.update_products(requests)
        if len(provider_results) != len(updates):
            return [
                ListingUpdateResult(
                    listing_id=update.listing_id,
                    outcome=WriteOutcome.RECONCILIATION_REQUIRED,
                    error_category="provider_contract",
                    error_message="Technolife returned an ambiguous item count.",
                )
                for update in updates
            ]

        successful = [
            update
            for update, result in zip(updates, provider_results, strict=True)
            if result.success
        ]
        state = await _fetch_current_state(
            connector,
            _current_state_request(
                self.channel_id, successful, required_fields={"price", "stock"}
            ),
            strategy=CurrentStateStrategy.GROUPED_COLLECTION,
        )
        output: list[ListingUpdateResult] = []
        for update, result in zip(updates, provider_results, strict=True):
            write_error = result.error
            record = state.records.get(update.listing_id) if result.success else None
            state_error = state.errors.get(update.listing_id) if result.success else None
            verified = result.success and _technolife_state_matches(update, record)
            output.append(
                ListingUpdateResult(
                    listing_id=update.listing_id,
                    outcome=(
                        WriteOutcome.VERIFIED_APPLIED
                        if verified
                        else WriteOutcome.RECONCILIATION_REQUIRED
                        if result.success
                        else WriteOutcome.FAILED
                    ),
                    provider_accepted=result.success,
                    response={
                        **result.raw,
                        "verification": (
                            _verification_evidence(record, state_error, verified, state)
                            if result.success
                            else {"verified": False, "skipped": "write_failed"}
                        ),
                    },
                    external_response_id=_response_id(result.raw),
                    error_category=(
                        write_error.category.value
                        if write_error
                        else "verification"
                        if state_error
                        else None
                    ),
                    error_message=(
                        write_error.message
                        if write_error
                        else state_error.message
                        if state_error
                        else None
                    ),
                    retry_eligible=(
                        bool(write_error.retry.safe_to_retry)
                        if write_error
                        else bool(state_error and state_error.retry_eligible)
                    ),
                    accepted_price=update.target_price if verified else None,
                    accepted_stock=update.target_stock if verified else None,
                )
            )
        return output

    async def verify_updates(
        self, updates: Sequence[ListingUpdateLike], *, requested_by: str
    ) -> list[ListingUpdateResult]:
        del requested_by
        connector = self.commerce._technolife_connector()
        if connector is None:
            raise WorkspaceDomainError("Technolife connector is not configured.")
        state = await _fetch_current_state(
            connector,
            _current_state_request(
                self.channel_id, updates, required_fields={"price", "stock"}
            ),
            strategy=CurrentStateStrategy.GROUPED_COLLECTION,
        )
        output: list[ListingUpdateResult] = []
        for update in updates:
            record = state.records.get(update.listing_id)
            error = state.errors.get(update.listing_id)
            verified = _technolife_state_matches(update, record)
            output.append(
                ListingUpdateResult(
                    listing_id=update.listing_id,
                    outcome=(
                        WriteOutcome.VERIFIED_APPLIED
                        if verified
                        else WriteOutcome.RECONCILIATION_REQUIRED
                    ),
                    response={
                        "verification": _verification_evidence(
                            record, error, verified, state
                        )
                    },
                    error_category="verification" if error else None,
                    error_message=error.message if error else None,
                    retry_eligible=bool(error and error.retry_eligible),
                    accepted_price=update.target_price if verified else None,
                    accepted_stock=update.target_stock if verified else None,
                )
            )
        return output


def _current_state_request(
    channel_id: str,
    updates: Sequence[ListingUpdateLike],
    *,
    required_fields: set[str],
) -> CurrentStateRequest:
    return CurrentStateRequest(
        channel_id=channel_id,
        entities=tuple(
            CurrentStateIdentity(
                key=update.listing_id,
                external_id=update.external_primary_id,
                parent_external_id=update.parent_external_id,
                sku=update.sku,
            )
            for update in updates
        ),
        required_fields=frozenset(required_fields),
        purpose="post_apply_verification",
        max_staleness_seconds=0,
    )


async def _fetch_current_state(
    provider: object | None,
    request: CurrentStateRequest,
    *,
    strategy: CurrentStateStrategy,
    context: ChannelWriteContext | None = None,
    safe_error: Callable[[Exception], str] = str,
) -> CurrentStateResult:
    if not request.entities:
        return failed_current_state(
            request,
            strategy=strategy,
            category="verification",
            message="No current-state entities were requested.",
        )
    fetch = getattr(provider, "fetch_current_state", None)
    if not callable(fetch):
        result = unsupported_current_state(
            request,
            message="Connector does not provide grouped current-state retrieval.",
        )
    else:
        try:
            result = await fetch(request, context) if context is not None else await fetch(request)
        except Exception as exc:
            result = failed_current_state(
                request,
                strategy=strategy,
                category="verification",
                message=safe_error(exc),
            )
    report = result.transport
    logger.info(
        "current_state_transport operation_id=%s channel_id=%s strategy=%s entities=%d returned=%d "
        "requests=%d batches=%d retries=%d failed_requests=%d duration_ms=%.3f "
        "slowest_request_ms=%.3f bottleneck_stage=%s",
        report.operation_id,
        request.channel_id,
        report.strategy.value,
        report.entities_requested,
        report.entities_returned,
        report.requests_issued,
        report.batches_issued,
        report.retries,
        report.failed_requests,
        report.total_duration_ms,
        report.slowest_request_ms,
        report.bottleneck_stage,
    )
    return result


def _verification_evidence(
    record: CurrentStateRecord | None,
    error: CurrentStateError | None,
    verified: bool,
    result: CurrentStateResult,
) -> dict[str, object]:
    return {
        "verified": verified,
        "observed": (
            {
                "provider": record.provider,
                "external_id": record.external_id,
                "parent_external_id": record.parent_external_id,
                "price": record.price,
                "stock": record.stock,
                "status": record.status,
                "currency": record.currency,
                "unit": record.unit,
            }
            if record is not None
            else None
        ),
        "error": (
            {
                "category": error.category,
                "message": error.message,
                "retry_eligible": error.retry_eligible,
            }
            if error is not None
            else None
        ),
        "transport": result.transport.as_dict(),
    }


def _woocommerce_state_matches(
    update: ListingUpdateLike, record: CurrentStateRecord | None
) -> bool:
    expected_parent = (
        str(update.parent_external_id)
        if update.product_type == "variation" and update.parent_external_id is not None
        else None
    )
    expected_price = float(update.target_price or 0)
    return bool(
        record is not None
        and record.provider == "woocommerce"
        and record.external_id == update.external_primary_id
        and record.parent_external_id == expected_parent
        and record.price is not None
        and abs(record.price - expected_price) < 0.005
    )


def _snappshop_state_matches(
    update: ListingUpdateLike, record: CurrentStateRecord | None
) -> bool:
    expected_price = (
        update.target_price if update.target_price is not None else update.current_price
    )
    expected_stock = (
        update.target_stock if update.target_stock is not None else update.current_stock
    )
    return bool(
        record is not None
        and record.provider == "snappshop"
        and record.external_id == update.external_primary_id
        and record.parent_external_id == update.parent_external_id
        and record.price == expected_price
        and record.stock == expected_stock
        and record.currency == "IRR"
        and str(record.unit or "").lower() == "toman"
    )


def _technolife_state_matches(
    update: ListingUpdateLike, record: CurrentStateRecord | None
) -> bool:
    expected_price = (
        update.target_price if update.target_price is not None else update.current_price
    )
    expected_stock = (
        update.target_stock if update.target_stock is not None else update.current_stock
    )
    return bool(
        record is not None
        and record.provider == "technolife"
        and record.external_id == update.external_primary_id
        and record.parent_external_id == update.parent_external_id
        and record.price == expected_price
        and record.stock == expected_stock
        and record.currency == "IRR"
        and str(record.unit or "").upper() == "RIAL"
    )


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
