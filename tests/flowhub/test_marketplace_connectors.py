from __future__ import annotations

import pytest

from app.flowhub.channels.contracts import (
    ChannelCapability,
    ChannelConnectorConfig,
    ChannelIdentifierSet,
    ChannelProduct,
    ChannelProductUpdate,
    ChannelProductUpdateResult,
    CursorPagination,
    PageNumberPagination,
    PaginatedResult,
)
from app.flowhub.channels.marketplace import BaseMarketplaceConnector, require_capability, UnsupportedCapabilityError
from app.flowhub.channels.registry import MarketplaceConnectorRegistry, default_marketplace_registry


class FakeMarketplaceConnector(BaseMarketplaceConnector):
    def __init__(self) -> None:
        super().__init__(
            connector_type="fake_market",
            channel_id="fake_market:main",
            capabilities={
                ChannelCapability.PRODUCTS_READ,
                ChannelCapability.PRODUCTS_WRITE_PRICE,
            },
        )

    async def list_products(self, pagination=None) -> PaginatedResult:
        require_capability(self, ChannelCapability.PRODUCTS_READ)
        pagination = pagination or PageNumberPagination(page=1, page_size=50, total=1, total_pages=1)
        return PaginatedResult(
            items=[
                ChannelProduct(
                    channel_id=self.channel_id,
                    connector_type=self.connector_type,
                    identifiers=ChannelIdentifierSet(
                        canonical_product_id="dl_1",
                        external_product_id="ext-100",
                        sku="SKU-100",
                        product_number="P-100",
                        parent_product_number="PARENT-1",
                        channel_reference_code="REF-100",
                    ),
                    name="Fake product",
                    current_price=100.0,
                    currency="EUR",
                )
            ],
            pagination=pagination,
        )

    async def update_products(self, updates: list[ChannelProductUpdate]) -> list[ChannelProductUpdateResult]:
        require_capability(self, ChannelCapability.PRODUCTS_WRITE_PRICE)
        return [
            ChannelProductUpdateResult(
                channel_id=self.channel_id,
                identifiers=item.identifiers,
                success=True,
                applied_capabilities=[ChannelCapability.PRODUCTS_WRITE_PRICE],
                raw={"external_product_id": item.identifiers.external_product_id},
            )
            for item in updates
        ]


@pytest.mark.asyncio
async def test_fake_connector_normalizes_read_and_write_results():
    connector = FakeMarketplaceConnector()
    connector.validate_configuration(ChannelConnectorConfig(
        connector_type="fake_market",
        channel_id="fake_market:main",
        settings={"base_url": "https://market.example.test"},
        secrets_configured={"api_key": True},
    ))

    page_result = await connector.list_products(PageNumberPagination(page=2, page_size=25, total=1, total_pages=1))
    product = page_result.items[0]

    assert page_result.pagination.kind == "page"
    assert product.identifiers.canonical_product_id == "dl_1"
    assert product.identifiers.external_product_id == "ext-100"
    assert product.identifiers.product_number == "P-100"
    assert product.identifiers.parent_product_number == "PARENT-1"

    cursor_result = await connector.list_products(CursorPagination(cursor="abc", next_cursor="def", limit=10, has_more=True))
    assert cursor_result.pagination.kind == "cursor"
    assert cursor_result.pagination.next_cursor == "def"

    write_result = await connector.update_products([
        ChannelProductUpdate(
            channel_id="fake_market:main",
            identifiers=ChannelIdentifierSet(external_product_id="ext-100", sku="SKU-100"),
            price=110.0,
            currency="EUR",
            idempotency_key="idem-1",
        )
    ])

    assert write_result[0].success is True
    assert write_result[0].applied_capabilities == [ChannelCapability.PRODUCTS_WRITE_PRICE]
    assert write_result[0].identifiers.sku == "SKU-100"


def test_registry_registers_connectors_without_ui_code_and_uses_capabilities():
    registry = MarketplaceConnectorRegistry()
    connector = FakeMarketplaceConnector()
    registry.register_connector(connector, name="Fake Market")

    assert registry.get_connector("fake_market:main") is connector
    assert registry.supports("fake_market:main", ChannelCapability.PRODUCTS_READ) is True
    assert registry.supports("fake_market:main", ChannelCapability.PRODUCTS_WRITE_PRICE) is True
    assert registry.supports("fake_market:main", ChannelCapability.PRODUCTS_WRITE_STOCK) is False


def test_unsupported_capability_is_structured_and_not_retryable():
    connector = FakeMarketplaceConnector()

    with pytest.raises(UnsupportedCapabilityError) as exc_info:
        require_capability(connector, ChannelCapability.ORDERS_READ)

    error = exc_info.value.error
    assert error.category.value == "unsupported_capability"
    assert error.retry.retryable is False
    assert error.retry.safe_to_retry is False


def test_default_registry_keeps_future_marketplaces_unimplemented_and_woocommerce_price_only():
    registry = default_marketplace_registry()

    assert registry.supports("woocommerce:primary", ChannelCapability.PRODUCTS_READ) is True
    assert registry.supports("woocommerce:primary", ChannelCapability.PRODUCTS_WRITE_PRICE) is True
    assert registry.supports("woocommerce:primary", ChannelCapability.PRODUCTS_WRITE_STOCK) is False
    assert registry.get_definition("snappshop:main").implemented is True
    assert registry.supports("snappshop:main", ChannelCapability.PRODUCTS_WRITE_STOCK) is True
    assert registry.get_definition("tapsishop:main").implemented is False
