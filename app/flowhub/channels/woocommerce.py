"""Read-only WooCommerce marketplace order connector."""

from __future__ import annotations

from typing import Any

from app.connectors.destinations.woocommerce.auth import WooCommerceCredentials
from app.connectors.destinations.woocommerce.rest_client import (
    get_order as read_order,
)
from app.connectors.destinations.woocommerce.rest_client import list_orders_paged
from app.flowhub.channels.contracts import (
    ChannelCapability,
    ChannelIdentifierSet,
    ChannelOrder,
    ChannelOrderItem,
    PageNumberPagination,
    PaginatedResult,
    Pagination,
)
from app.flowhub.channels.marketplace import BaseMarketplaceConnector


def build_woocommerce_order_connector(
    *,
    channel_id: str,
    settings: dict[str, Any],
) -> WooCommerceOrderConnector:
    """Build the read-only order connector behind the Channel boundary."""
    return WooCommerceOrderConnector(
        channel_id=channel_id,
        credentials=WooCommerceCredentials(
            url=str(settings["url"]).rstrip("/"),
            key=str(settings["key"]),
            secret=str(settings["secret"]),
        ),
    )


class WooCommerceOrderConnector(BaseMarketplaceConnector):
    """Normalize WooCommerce orders behind the shared read-only contract."""

    def __init__(
        self,
        *,
        channel_id: str,
        credentials: WooCommerceCredentials,
    ) -> None:
        super().__init__(
            connector_type="woocommerce",
            channel_id=channel_id,
            capabilities={ChannelCapability.ORDERS_READ},
        )
        self.credentials = credentials

    async def list_orders(
        self, pagination: Pagination | None = None
    ) -> PaginatedResult:
        page_request = (
            pagination
            if isinstance(pagination, PageNumberPagination)
            else PageNumberPagination()
        )
        rows, total, total_pages = await list_orders_paged(
            self.credentials,
            page=page_request.page,
            per_page=page_request.page_size,
        )
        return PaginatedResult(
            items=[self._normalize(row) for row in rows],
            pagination=PageNumberPagination(
                page=page_request.page,
                page_size=page_request.page_size,
                total=total,
                total_pages=total_pages,
                has_more=page_request.page < total_pages,
                next_page=page_request.page + 1
                if page_request.page < total_pages
                else None,
            ),
        )

    async def get_order(self, identifiers: dict[str, str]) -> ChannelOrder:
        order_id = identifiers.get("id") or identifiers.get("orderId")
        if not order_id:
            raise ValueError("WooCommerce order id is required.")
        return self._normalize(await read_order(self.credentials, order_id))

    def _normalize(self, raw: dict[str, Any]) -> ChannelOrder:
        order_id = str(raw.get("id") or "")
        currency = _text(raw.get("currency"))
        line_items = raw.get("line_items")
        items: list[ChannelOrderItem] = []
        if isinstance(line_items, list):
            for index, item in enumerate(line_items):
                if not isinstance(item, dict):
                    continue
                product_id = _text(item.get("product_id"))
                variation_id = _text(item.get("variation_id"))
                has_variation = variation_id not in {None, "", "0"}
                items.append(
                    ChannelOrderItem(
                        identifiers=ChannelIdentifierSet(
                            external_product_id=variation_id
                            if has_variation
                            else product_id,
                            sku=_text(item.get("sku")),
                            product_number=variation_id if has_variation else product_id,
                            parent_product_number=product_id if has_variation else None,
                            channel_reference_code=_text(item.get("id"))
                            or f"{order_id}:item:{index}",
                        ),
                        name=_text(item.get("name")) or "",
                        quantity=_number(item.get("quantity")) or 0,
                        unit_price=_number(item.get("price")),
                        currency=currency,
                        raw={
                            "id": item.get("id"),
                            "productId": product_id,
                            "variationId": variation_id,
                            "sku": item.get("sku"),
                            "quantity": item.get("quantity"),
                            "original_price": item.get("subtotal"),
                            "final_price": item.get("total"),
                        },
                    )
                )
        billing_value = raw.get("billing")
        billing: dict[str, Any] = (
            billing_value if isinstance(billing_value, dict) else {}
        )
        return ChannelOrder(
            channel_id=self.channel_id,
            connector_type="woocommerce",
            identifiers=ChannelIdentifierSet(
                external_product_id=order_id,
                order_number=_text(raw.get("number")) or order_id,
            ),
            status=_text(raw.get("status")) or "unknown",
            created_at=_text(raw.get("date_created_gmt")),
            updated_at=_text(raw.get("date_modified_gmt")),
            items=items,
            total=_number(raw.get("total")),
            currency=currency,
            raw={
                "id": raw.get("id"),
                "order_number": raw.get("number"),
                "status": raw.get("status"),
                "created_at": raw.get("date_created_gmt"),
                "updated_at": raw.get("date_modified_gmt"),
                "date_paid": raw.get("date_paid_gmt"),
                "payment_method_title": raw.get("payment_method_title"),
                "customer": {
                    "id": billing.get("email") or billing.get("phone"),
                    "display_name": " ".join(
                        str(billing.get(key) or "").strip()
                        for key in ("first_name", "last_name")
                    ).strip(),
                },
            },
        )


def _text(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _number(value: object) -> float | None:
    try:
        if value in (None, ""):
            return None
        if isinstance(value, (int, float, str)):
            return float(value)
        return None
    except (TypeError, ValueError):
        return None
