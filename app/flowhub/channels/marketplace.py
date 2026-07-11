"""Marketplace connector protocol and capability guardrails."""

from __future__ import annotations

from typing import Protocol

from app.flowhub.channels.contracts import (
    ChannelCapability,
    ChannelConnectorConfig,
    ChannelHealth,
    ChannelOrder,
    ChannelOrderEvent,
    ChannelProduct,
    ChannelProductUpdate,
    ChannelProductUpdateResult,
    ChannelVendor,
    ConnectorError,
    ConnectorErrorCategory,
    CursorPagination,
    PageNumberPagination,
    PaginatedResult,
    RetryMetadata,
)


class UnsupportedCapabilityError(Exception):
    def __init__(self, capability: ChannelCapability, channel_id: str, connector_type: str) -> None:
        self.capability = capability
        self.error = ConnectorError(
            category=ConnectorErrorCategory.UNSUPPORTED_CAPABILITY,
            message=f"Connector does not support {capability.value}.",
            connector_type=connector_type,
            channel_id=channel_id,
            retry=RetryMetadata(retryable=False, safe_to_retry=False),
        )
        super().__init__(self.error.message)


class MarketplaceConnector(Protocol):
    connector_type: str
    channel_id: str

    def validate_configuration(self, config: ChannelConnectorConfig) -> None:
        """Validate local connector configuration without exposing secrets."""

    def get_capabilities(self) -> frozenset[ChannelCapability]:
        """Return declared channel capabilities."""

    async def test_connection(self) -> ChannelHealth:
        """Perform a read-only connectivity probe."""

    async def get_vendor_information(self) -> ChannelVendor:
        """Return normalized vendor/store metadata."""

    async def list_products(
        self,
        pagination: PageNumberPagination | CursorPagination | None = None,
    ) -> PaginatedResult:
        """Return normalized products when products.read is supported."""

    async def get_product(self, identifiers: dict[str, str]) -> ChannelProduct:
        """Return one normalized product when products.read is supported."""

    async def update_products(self, updates: list[ChannelProductUpdate]) -> list[ChannelProductUpdateResult]:
        """Apply supported product writes. Implementations must not blindly retry unsafe writes."""

    async def list_order_events(
        self,
        pagination: PageNumberPagination | CursorPagination | None = None,
    ) -> PaginatedResult:
        """Return normalized order events when orders.events.poll is supported."""

    async def list_orders(
        self,
        pagination: PageNumberPagination | CursorPagination | None = None,
    ) -> PaginatedResult:
        """Return normalized orders when orders.read is supported."""

    async def get_order(self, identifiers: dict[str, str]) -> ChannelOrder:
        """Return one normalized order when orders.read is supported."""

    async def receive_webhook(self, payload: bytes, headers: dict[str, str]) -> ChannelOrderEvent:
        """Validate and normalize a webhook payload when orders.webhook.receive is supported."""

    async def refresh_credentials(self) -> ChannelHealth:
        """Refresh credentials when credentials.refresh is supported."""


def require_capability(connector: MarketplaceConnector, capability: ChannelCapability) -> None:
    if capability not in connector.get_capabilities():
        raise UnsupportedCapabilityError(capability, connector.channel_id, connector.connector_type)


class BaseMarketplaceConnector:
    connector_type: str
    channel_id: str

    def __init__(
        self,
        *,
        connector_type: str,
        channel_id: str,
        capabilities: set[ChannelCapability] | frozenset[ChannelCapability],
    ) -> None:
        self.connector_type = connector_type
        self.channel_id = channel_id
        self._capabilities = frozenset(capabilities)

    def validate_configuration(self, config: ChannelConnectorConfig) -> None:
        if config.connector_type != self.connector_type:
            raise ValueError("connector_type does not match connector")
        if config.channel_id != self.channel_id:
            raise ValueError("channel_id does not match connector")

    def get_capabilities(self) -> frozenset[ChannelCapability]:
        return self._capabilities

    async def test_connection(self) -> ChannelHealth:
        return ChannelHealth(status="disabled")

    async def get_vendor_information(self) -> ChannelVendor:
        raise UnsupportedCapabilityError(ChannelCapability.PRODUCTS_READ, self.channel_id, self.connector_type)

    async def list_products(
        self,
        pagination: PageNumberPagination | CursorPagination | None = None,
    ) -> PaginatedResult:
        raise UnsupportedCapabilityError(ChannelCapability.PRODUCTS_READ, self.channel_id, self.connector_type)

    async def get_product(self, identifiers: dict[str, str]) -> ChannelProduct:
        raise UnsupportedCapabilityError(ChannelCapability.PRODUCTS_READ, self.channel_id, self.connector_type)

    async def update_products(self, updates: list[ChannelProductUpdate]) -> list[ChannelProductUpdateResult]:
        write_caps = {
            ChannelCapability.PRODUCTS_WRITE_PRICE,
            ChannelCapability.PRODUCTS_WRITE_STOCK,
            ChannelCapability.PRODUCTS_WRITE_DISCOUNT,
            ChannelCapability.PRODUCTS_WRITE_CAPACITY,
        }
        supported = self.get_capabilities().intersection(write_caps)
        if not supported:
            raise UnsupportedCapabilityError(ChannelCapability.PRODUCTS_WRITE_PRICE, self.channel_id, self.connector_type)
        raise NotImplementedError("Connector must implement supported product writes.")

    async def list_order_events(
        self,
        pagination: PageNumberPagination | CursorPagination | None = None,
    ) -> PaginatedResult:
        raise UnsupportedCapabilityError(ChannelCapability.ORDERS_EVENTS_POLL, self.channel_id, self.connector_type)

    async def list_orders(
        self,
        pagination: PageNumberPagination | CursorPagination | None = None,
    ) -> PaginatedResult:
        raise UnsupportedCapabilityError(ChannelCapability.ORDERS_READ, self.channel_id, self.connector_type)

    async def get_order(self, identifiers: dict[str, str]) -> ChannelOrder:
        raise UnsupportedCapabilityError(ChannelCapability.ORDERS_READ, self.channel_id, self.connector_type)

    async def receive_webhook(self, payload: bytes, headers: dict[str, str]) -> ChannelOrderEvent:
        raise UnsupportedCapabilityError(ChannelCapability.ORDERS_WEBHOOK_RECEIVE, self.channel_id, self.connector_type)

    async def refresh_credentials(self) -> ChannelHealth:
        raise UnsupportedCapabilityError(ChannelCapability.CREDENTIALS_REFRESH, self.channel_id, self.connector_type)
