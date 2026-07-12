"""Direct provider-adapter contract tests for Unified Workspace."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.flowhub.channels.contracts import (
    ChannelIdentifierSet,
    ChannelProduct,
    ChannelProductUpdateResult,
    ConnectorError,
    ConnectorErrorCategory,
    RetryMetadata,
)
from app.flowhub.unified_workspace.connectors import (
    ListingUpdate,
    SnappShopWorkspaceConnector,
    WooCommerceWorkspaceConnector,
    WorkspaceConnectorFactory,
)
from app.flowhub.unified_workspace.domain import WorkspaceDomainError


class _Config:
    values = {
        "server.currency": "EUR",
        "server.currency_unit": "EUR",
        "woocommerce.url": "https://shop.example.test",
    }

    def get(self, key):
        return self.values.get(key)


class _Pricing:
    config = _Config()

    @staticmethod
    def _safe_error(exc):
        return str(exc)


def _update(**overrides) -> ListingUpdate:
    values = {
        "listing_id": "listing-1",
        "external_primary_id": "101",
        "sku": "SKU-101",
        "product_type": "simple",
        "parent_external_id": None,
        "current_price": 100.0,
        "current_stock": 5.0,
        "current_status": "active",
        "target_price": 125.0,
        "target_stock": None,
        "target_status": None,
        "currency": "EUR",
        "unit": "EUR",
        "idempotency_key": "idem-1",
    }
    values.update(overrides)
    return ListingUpdate(**values)


@pytest.mark.asyncio
async def test_woocommerce_adapter_validates_verifies_and_redacts_provider_failures(monkeypatch):
    connector = WooCommerceWorkspaceConnector(_Pricing())
    capabilities = connector.capabilities()
    assert capabilities.primary_identifier_type == "woocommerce_product_id"
    assert capabilities.health_state == "configured"
    with pytest.raises(WorkspaceDomainError):
        connector.validate_update(_update(target_stock=4))
    with pytest.raises(WorkspaceDomainError):
        connector.validate_update(_update(target_price=None))
    with pytest.raises(WorkspaceDomainError):
        connector.validate_update(_update(external_primary_id="not-numeric"))

    async def execute(_self, item, context):
        assert item.channel_product_id == "101"
        assert context.requested_by == "admin"
        return {"id": 101}

    async def verify(_self, item, _context):
        assert item.proposed_price == 125.0
        return {"verified": True}

    monkeypatch.setattr(
        "app.connectors.destinations.woocommerce.write_adapter.WooCommercePriceWriteAdapter.execute_item",
        execute,
    )
    monkeypatch.setattr(
        "app.connectors.destinations.woocommerce.write_adapter.WooCommercePriceWriteAdapter.verify_item",
        verify,
    )
    result = (await connector.apply_updates([_update()], requested_by="admin"))[0]
    assert result.success is True
    assert result.cache_verified is True
    assert result.accepted_price == 125.0
    assert result.external_response_id == "101"

    async def fail(_self, _item, _context):
        raise RuntimeError("provider failed")

    monkeypatch.setattr(
        "app.connectors.destinations.woocommerce.write_adapter.WooCommercePriceWriteAdapter.execute_item",
        fail,
    )
    failed = (await connector.apply_updates([_update()], requested_by="admin"))[0]
    assert failed.success is False
    assert failed.error_category == "provider"
    assert failed.error_message == "provider failed"


class _SnappProvider:
    def __init__(self):
        self.batch_sizes = []

    async def update_products(self, requests):
        self.batch_sizes.append(len(requests))
        return [
            ChannelProductUpdateResult(
                channel_id="snappshop:main",
                identifiers=request.identifiers,
                success=True,
                raw={"referenceCode": f"ref-{request.identifiers.external_product_id}"},
            )
            for request in requests
        ]

    async def get_product(self, identifiers):
        return ChannelProduct(
            channel_id="snappshop:main",
            connector_type="snappshop",
            identifiers=ChannelIdentifierSet(
                external_product_id=identifiers["external_product_id"]
            ),
            name="Verified",
            current_price=125.0,
            stock_quantity=4.0,
        )


@pytest.mark.asyncio
async def test_snappshop_adapter_batches_at_fifty_and_only_accepts_verified_state():
    provider = _SnappProvider()
    commerce = SimpleNamespace(_snappshop_connector=lambda: provider)
    connector = SnappShopWorkspaceConnector(commerce)
    capabilities = connector.capabilities()
    assert capabilities.maximum_batch_size == 50
    assert capabilities.primary_identifier_type == "snappshop_product_number"

    updates = [
        _update(
            listing_id=f"listing-{index}",
            external_primary_id=str(index),
            target_stock=4.0,
            currency="IRR",
            unit="TOMAN",
        )
        for index in range(51)
    ]
    results = await connector.apply_updates(updates, requested_by="admin")
    assert provider.batch_sizes == [50, 1]
    assert len(results) == 51
    assert all(item.cache_verified for item in results)
    assert results[0].accepted_price == 125.0
    assert results[0].accepted_stock == 4.0

    with pytest.raises(WorkspaceDomainError):
        connector.validate_update(_update(target_stock=4, currency="IRR", unit="RIAL"))
    with pytest.raises(WorkspaceDomainError):
        connector.validate_update(
            _update(
                target_price=None, current_price=None, target_stock=4, currency="IRR", unit="TOMAN"
            )
        )
    with pytest.raises(WorkspaceDomainError):
        connector.validate_update(_update(target_status="inactive", currency="IRR", unit="TOMAN"))


@pytest.mark.asyncio
async def test_snappshop_adapter_preserves_retry_metadata_and_rejects_unconfigured_channel():
    error = ConnectorError(
        category=ConnectorErrorCategory.RATE_LIMIT,
        message="rate limited",
        connector_type="snappshop",
        channel_id="snappshop:main",
        retry=RetryMetadata(retryable=True, safe_to_retry=True, retry_after_seconds=2),
    )

    class FailedProvider(_SnappProvider):
        async def update_products(self, requests):
            return [
                ChannelProductUpdateResult(
                    channel_id="snappshop:main",
                    identifiers=request.identifiers,
                    success=False,
                    error=error,
                    raw={"request_id": "req-1"},
                )
                for request in requests
            ]

    connector = SnappShopWorkspaceConnector(
        SimpleNamespace(_snappshop_connector=lambda: FailedProvider())
    )
    result = (
        await connector.apply_updates(
            [_update(target_stock=4, currency="IRR", unit="TOMAN")], requested_by="admin"
        )
    )[0]
    assert result.retry_eligible is True
    assert result.error_category == "rate_limit"
    assert result.external_response_id == "req-1"
    assert result.cache_verified is False

    unavailable = SnappShopWorkspaceConnector(SimpleNamespace(_snappshop_connector=lambda: None))
    assert unavailable.capabilities().health_state == "unconfigured"
    with pytest.raises(WorkspaceDomainError):
        await unavailable.apply_updates([], requested_by="admin")


def test_factory_exposes_only_implemented_channels_and_rejects_coming_soon():
    commerce = SimpleNamespace(_snappshop_connector=lambda: None)
    factory = WorkspaceConnectorFactory(_Pricing(), commerce)
    assert {connector.channel_id for connector in factory.implemented()} == {
        "woocommerce:primary",
        "snappshop:main",
    }
    with pytest.raises(WorkspaceDomainError):
        factory.get("digikala:main")
