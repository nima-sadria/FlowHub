"""WooCommerce Write Pipeline adapter.

This is the only WooCommerce-specific write adapter registered for FlowHub
1.0.0. It supports price updates only and accepts no stock payload fields.
"""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import HTTPException, status

from app.connectors.common.auth import AuthConfig
from app.connectors.destinations.woocommerce.connector import WooCommerceConnector
from app.flowhub.write_pipeline.adapters import (
    ChannelWriteCapabilities,
    ChannelWriteContext,
    WriteItemContract,
)


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
        if str(item.get("itemType") or "simple") == "variation":
            parent_product_id = str(item.get("parentProductId") or "")
            if not parent_product_id.isdigit():
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "WooCommerce variation rows require a numeric parent product ID.")

    async def execute_item(
        self, item: WriteItemContract, context: ChannelWriteContext
    ) -> dict[str, object]:
        connector = await self._connected_connector(context)
        result = await connector.update_price(
            int(item.channel_product_id),
            item.proposed_price,
            parent_product_id=_parent_product_id(item),
        )
        return {str(key): value for key, value in result.items()}

    async def verify_item(
        self, item: WriteItemContract, context: ChannelWriteContext
    ) -> dict[str, object]:
        connector = await self._connected_connector(context)
        observed = await connector.read_product_price(
            int(item.channel_product_id),
            parent_product_id=_parent_product_id(item),
        )
        raw_observed = observed.get("regular_price")
        try:
            observed_price = float(str(raw_observed).replace(",", "").strip())
        except (TypeError, ValueError):
            observed_price = None
        expected = float(item.proposed_price)
        verified = observed_price is not None and abs(observed_price - expected) < 0.005
        expected_parent_id = _parent_product_id(item)
        expected_product_id = int(item.channel_product_id)
        identity_verified = (
            observed.get("provider") == "woocommerce"
            and observed.get("identity_complete") is True
            and observed.get("product_id") == expected_product_id
            and observed.get("parent_product_id") == expected_parent_id
            and observed.get("variation_id")
            == (expected_product_id if expected_parent_id is not None else None)
        )
        verified = verified and identity_verified
        return {
            "provider": "woocommerce",
            "verified": verified,
            "observed_price": observed_price,
            "expected_price": expected,
            "product_id": observed.get("product_id"),
            "parent_product_id": observed.get("parent_product_id"),
            "variation_id": observed.get("variation_id"),
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


def _parent_product_id(item: WriteItemContract) -> int | None:
    if not isinstance(item.pre_write_snapshot_json, dict):
        return None
    if item.pre_write_snapshot_json.get("item_type") != "variation":
        return None
    raw_parent = item.pre_write_snapshot_json.get("parent_product_id")
    parent_text = str(raw_parent or "")
    if not parent_text.isdigit():
        raise ValueError("WooCommerce variation writes require a numeric parent product ID.")
    return int(parent_text)
