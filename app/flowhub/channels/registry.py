"""Capability-aware marketplace connector registry."""

from __future__ import annotations

from dataclasses import dataclass

from app.flowhub.channels.contracts import ChannelCapability
from app.flowhub.channels.marketplace import MarketplaceConnector


@dataclass(frozen=True)
class MarketplaceConnectorDefinition:
    connector_type: str
    channel_id: str
    name: str
    capabilities: frozenset[ChannelCapability]
    implemented: bool = False


class MarketplaceConnectorRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, MarketplaceConnectorDefinition] = {}
        self._connectors: dict[str, MarketplaceConnector] = {}

    def register_definition(self, definition: MarketplaceConnectorDefinition) -> None:
        self._definitions[definition.channel_id] = definition

    def register_connector(self, connector: MarketplaceConnector, *, name: str | None = None) -> None:
        capabilities = connector.get_capabilities()
        definition = MarketplaceConnectorDefinition(
            connector_type=connector.connector_type,
            channel_id=connector.channel_id,
            name=name or connector.channel_id,
            capabilities=capabilities,
            implemented=True,
        )
        self.register_definition(definition)
        self._connectors[connector.channel_id] = connector

    def get_definition(self, channel_id: str) -> MarketplaceConnectorDefinition | None:
        return self._definitions.get(channel_id)

    def get_connector(self, channel_id: str) -> MarketplaceConnector | None:
        return self._connectors.get(channel_id)

    def list_definitions(self) -> tuple[MarketplaceConnectorDefinition, ...]:
        return tuple(self._definitions.values())

    def supports(self, channel_id: str, capability: ChannelCapability) -> bool:
        definition = self.get_definition(channel_id)
        return bool(definition and capability in definition.capabilities)


def default_marketplace_registry() -> MarketplaceConnectorRegistry:
    registry = MarketplaceConnectorRegistry()
    registry.register_definition(
        MarketplaceConnectorDefinition(
            connector_type="woocommerce",
            channel_id="woocommerce:primary",
            name="WooCommerce",
            capabilities=frozenset({
                ChannelCapability.PRODUCTS_READ,
                ChannelCapability.PRODUCTS_WRITE_PRICE,
                ChannelCapability.ORDERS_READ,
                ChannelCapability.ORDERS_EVENTS_POLL,
                ChannelCapability.ORDERS_WEBHOOK_RECEIVE,
            }),
            implemented=True,
        )
    )
    for connector_type, channel_id, name in (
        ("snappshop", "snappshop:main", "Snapp Shop"),
        ("tapsishop", "tapsishop:main", "Tapsi Shop"),
    ):
        registry.register_definition(
            MarketplaceConnectorDefinition(
                connector_type=connector_type,
                channel_id=channel_id,
                name=name,
                capabilities=frozenset({
                    ChannelCapability.PRODUCTS_READ,
                    ChannelCapability.ORDERS_READ,
                    ChannelCapability.ORDERS_EVENTS_POLL,
                }),
                implemented=False,
            )
        )
    return registry
