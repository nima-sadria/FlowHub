"""WooCommerce Write Pipeline adapter.

This is the only WooCommerce-specific write adapter registered for FlowHub.
It executes the exact governed price, quantity, and stock-status fields from
an immutable Workspace intent.
"""

from __future__ import annotations

from collections.abc import Mapping

from fastapi import HTTPException, status

from app.connectors.common.auth import AuthConfig
from app.connectors.common.current_state import (
    CurrentStateError,
    CurrentStateRequest,
    CurrentStateResult,
    CurrentStateStrategy,
    TransportRecorder,
)
from app.connectors.common.errors import ConnectorError
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
            stock_write_supported=True,
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
        result = await connector.update_fields(
            int(item.channel_product_id),
            price=getattr(item, "proposed_price", None),
            stock_quantity=getattr(item, "proposed_stock", None),
            stock_status=getattr(item, "proposed_stock_status", None),
            parent_product_id=_parent_product_id(item),
        )
        return {str(key): value for key, value in result.items()}

    async def fetch_current_state(
        self, request: CurrentStateRequest, context: ChannelWriteContext
    ) -> CurrentStateResult:
        recorder = TransportRecorder(
            strategy=CurrentStateStrategy.BATCH_BY_ID,
            purpose=request.purpose,
            entities_requested=len(request.entities),
        )
        try:
            connector = await self._connected_connector(context, transport=recorder)
            return await connector.fetch_current_state(request, transport=recorder)
        except ConnectorError as exc:
            errors = {
                entity.key: CurrentStateError(
                    key=entity.key,
                    category=exc.code.value,
                    message=exc.message,
                    retry_eligible=exc.retryable,
                )
                for entity in request.entities
            }
            return CurrentStateResult(
                records={},
                errors=errors,
                transport=recorder.finish(entities_returned=0),
            )

    async def _connected_connector(
        self,
        context: ChannelWriteContext,
        *,
        transport: TransportRecorder | None = None,
    ) -> WooCommerceConnector:
        auth = AuthConfig(
            auth_type="api_key",
            credentials={
                "url": context.get_setting("woocommerce.url") or "",
                "key": context.get_setting("woocommerce.key") or "",
                "secret": context.get_setting("woocommerce.secret") or "",
            },
        )
        connector = WooCommerceConnector()
        # The operation immediately performs an authenticated provider request,
        # so a separate preflight ping would add one remote call per operation.
        await connector.connect(
            auth,
            verify_connection=False,
            transport=transport,
        )
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
