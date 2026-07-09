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
        connector = await self._connected_connector(context)
        return await connector.update_price(int(item.channel_product_id), item.proposed_price)

    async def verify_item(self, item: WriteItem, context: ChannelWriteContext) -> dict:
        connector = await self._connected_connector(context)
        observed = await connector.read_product_price(int(item.channel_product_id))
        raw_observed = observed.get("regular_price")
        try:
            observed_price = float(str(raw_observed).replace(",", "").strip())
        except (TypeError, ValueError):
            observed_price = None
        expected = float(item.proposed_price)
        verified = observed_price is not None and abs(observed_price - expected) < 0.005
        return {
            "provider": "woocommerce",
            "verified": verified,
            "observed_price": observed_price,
            "expected_price": expected,
            "verification_error": None if verified else "observed_price_mismatch",
        }

    async def _connected_connector(self, context: ChannelWriteContext) -> WooCommerceConnector:
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
        return connector
