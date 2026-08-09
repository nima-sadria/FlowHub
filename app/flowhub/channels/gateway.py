"""Canonical Channel Gateway: resolves a channel_id to its write connector.

This is the single channel-resolution boundary between the Write Pipeline
(:class:`app.flowhub.write_pipeline.service.WritePipelineService`) and the
per-channel provider connectors implemented in
:mod:`app.flowhub.unified_workspace.connectors`. It intentionally holds no
provider logic of its own; it only maps a channel_id to the connector that
implements :class:`~app.flowhub.unified_workspace.connectors.WorkspaceChannelConnector`.
"""

from __future__ import annotations

from app.flowhub.commerce.service import CommerceHubService
from app.flowhub.product_pricing.service import ProductPricingService
from app.flowhub.unified_workspace.connectors import (
    SnappShopWorkspaceConnector,
    TapsiShopWorkspaceConnector,
    TechnolifeWorkspaceConnector,
    WooCommerceWorkspaceConnector,
    WorkspaceChannelConnector,
)
from app.flowhub.unified_workspace.domain import WorkspaceDomainError


class WorkspaceConnectorFactory:
    def __init__(self, pricing: ProductPricingService, commerce: CommerceHubService) -> None:
        self._connectors: dict[str, WorkspaceChannelConnector] = {
            "woocommerce:primary": WooCommerceWorkspaceConnector(pricing),
            "snappshop:main": SnappShopWorkspaceConnector(commerce),
            "tapsishop:main": TapsiShopWorkspaceConnector(commerce),
            "technolife:main": TechnolifeWorkspaceConnector(commerce),
        }
        self._product_pricing_connectors: dict[str, WorkspaceChannelConnector] = dict(
            self._connectors
        )

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
