"""WooCommerce Write Pipeline adapter.

This is the only WooCommerce-specific write adapter registered for FlowHub
1.0.0. It supports price updates only and accepts no stock payload fields.
"""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import HTTPException, status

from app.connectors.common.auth import AuthConfig
from app.connectors.destinations.woocommerce.connector import WooCommerceConnector
from app.flowhub.write_pipeline.adapters import ChannelWriteCapabilities, ChannelWriteContext
from app.flowhub.write_pipeline.models import WriteItem


class WooCommercePriceWriteAdapter:
    channel_id = "woocommerce:primary"
    channel_type = "woocommerce"
    operation_type = "price_update"

    def supports(self, channel_id: str, operation_type: str) -> bool:
        return channel_id == self.channel_id and operation_type == self.operation_type

    def get_capabilities(self) -> ChannelWriteCapabilities:
        return ChannelWriteCapabilities(
            channel_type=self.channel_type,
            channel_ids=(self.channel_id,),
            operation_types=(self.operation_type,),
            stock_write_supported=False,
            scheduler_supported=False,
            automatic_apply_supported=False,
        )

    def validate_item(self, item: Mapping[str, object]) -> None:
        product_id = str(item.get("productId") or "")
        if not product_id.isdigit():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "WooCommerce product ID must be numeric.")

    async def execute_item(self, item: WriteItem, context: ChannelWriteContext) -> dict:
        auth = AuthConfig(
            auth_type="api_key",
            credentials={
                "url": context.get_setting("woocommerce.url") or "",
                "key": context.get_setting("woocommerce.key") or "",
                "secret": context.get_setting("woocommerce.secret") or "",
            },
        )
        connector = WooCommerceConnector()
        await connector.connect(auth)
        return await connector.update_price(int(item.channel_product_id), item.proposed_price)
