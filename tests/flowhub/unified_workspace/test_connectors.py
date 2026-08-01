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
    TapsiShopWorkspaceConnector,
    TechnolifeWorkspaceConnector,
    WooCommerceWorkspaceConnector,
    WorkspaceConnectorFactory,
)
from app.flowhub.unified_workspace.domain import WorkspaceDomainError
from app.flowhub.write_pipeline.workspace_contracts import WriteOutcome


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
        return {
            "provider": "woocommerce",
            "verified": True,
            "product_id": 101,
            "parent_product_id": None,
            "variation_id": None,
        }

    monkeypatch.setattr(
        "app.connectors.destinations.woocommerce.write_adapter.WooCommercePriceWriteAdapter.execute_item",
        execute,
    )
    monkeypatch.setattr(
        "app.connectors.destinations.woocommerce.write_adapter.WooCommercePriceWriteAdapter.verify_item",
        verify,
    )
    result = (await connector.apply_updates([_update()], requested_by="admin"))[0]
    assert result.outcome is WriteOutcome.VERIFIED_APPLIED
    assert result.accepted_price == 125.0
    assert result.external_response_id == "101"

    async def fail(_self, _item, _context):
        raise RuntimeError("provider failed")

    monkeypatch.setattr(
        "app.connectors.destinations.woocommerce.write_adapter.WooCommercePriceWriteAdapter.execute_item",
        fail,
    )
    failed = (await connector.apply_updates([_update()], requested_by="admin"))[0]
    assert failed.outcome is WriteOutcome.RECONCILIATION_REQUIRED
    assert failed.error_category == "provider"
    assert failed.error_message == "provider failed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "verification",
    [
        {
            "provider": "woocommerce",
            "verified": True,
            "product_id": 999,
            "parent_product_id": None,
            "variation_id": None,
        },
        {
            "provider": "snappshop",
            "verified": True,
            "product_id": 101,
            "parent_product_id": None,
            "variation_id": None,
        },
        {
            "provider": "woocommerce",
            "verified": False,
            "product_id": 101,
            "parent_product_id": None,
            "variation_id": None,
        },
    ],
)
async def test_woocommerce_never_accepts_stale_wrong_or_cross_channel_readback(
    monkeypatch, verification
):
    async def execute(_self, _item, _context):
        return {"id": 101}

    async def verify(_self, _item, _context):
        return verification

    monkeypatch.setattr(
        "app.connectors.destinations.woocommerce.write_adapter.WooCommercePriceWriteAdapter.execute_item",
        execute,
    )
    monkeypatch.setattr(
        "app.connectors.destinations.woocommerce.write_adapter.WooCommercePriceWriteAdapter.verify_item",
        verify,
    )
    result = (
        await WooCommerceWorkspaceConnector(_Pricing()).apply_updates(
            [_update()], requested_by="admin"
        )
    )[0]
    assert result.outcome is WriteOutcome.RECONCILIATION_REQUIRED
    assert result.accepted_price is None


@pytest.mark.asyncio
async def test_woocommerce_variation_cannot_verify_against_parent_readback(monkeypatch):
    async def execute(_self, _item, _context):
        return {"id": 501}

    async def parent_readback(_self, _item, _context):
        return {
            "provider": "woocommerce",
            "verified": True,
            "product_id": 500,
            "parent_product_id": None,
            "variation_id": None,
        }

    monkeypatch.setattr(
        "app.connectors.destinations.woocommerce.write_adapter.WooCommercePriceWriteAdapter.execute_item",
        execute,
    )
    monkeypatch.setattr(
        "app.connectors.destinations.woocommerce.write_adapter.WooCommercePriceWriteAdapter.verify_item",
        parent_readback,
    )
    update = _update(
        product_type="variation", external_primary_id="501", parent_external_id="500"
    )
    result = (
        await WooCommerceWorkspaceConnector(_Pricing()).apply_updates(
            [update], requested_by="admin"
        )
    )[0]
    assert result.outcome is WriteOutcome.RECONCILIATION_REQUIRED


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
            currency="IRR",
            price_unit="toman",
            stock_quantity=4.0,
        )


@pytest.mark.asyncio
async def test_snappshop_adapter_batches_at_fifty_and_only_accepts_verified_state():
    provider = _SnappProvider()
    commerce = SimpleNamespace(
        _snappshop_connector=lambda: provider,
        channel_write_enabled=lambda _channel_id: True,
    )
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
    assert all(item.outcome is WriteOutcome.VERIFIED_APPLIED for item in results)
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
@pytest.mark.parametrize("failure", ["timeout", "wrong_listing", "wrong_channel", "wrong_unit"])
async def test_snappshop_never_accepts_uncertain_or_mismatched_readback(failure):
    class Provider(_SnappProvider):
        async def get_product(self, identifiers):
            if failure == "timeout":
                raise TimeoutError("read-back timed out")
            product = await super().get_product(identifiers)
            if failure == "wrong_listing":
                product.identifiers.external_product_id = "unrelated"
            elif failure == "wrong_channel":
                product.channel_id = "woocommerce:primary"
            elif failure == "wrong_unit":
                product.price_unit = "rial"
            return product

    connector = SnappShopWorkspaceConnector(
        SimpleNamespace(
            _snappshop_connector=lambda: Provider(),
            channel_write_enabled=lambda _channel_id: True,
        )
    )
    result = (
        await connector.apply_updates(
            [_update(target_stock=4, currency="IRR", unit="TOMAN")], requested_by="admin"
        )
    )[0]
    assert result.outcome is WriteOutcome.RECONCILIATION_REQUIRED
    assert result.accepted_price is None
    assert result.accepted_stock is None


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
        SimpleNamespace(
            _snappshop_connector=lambda: FailedProvider(),
            channel_write_enabled=lambda _channel_id: True,
        )
    )
    result = (
        await connector.apply_updates(
            [_update(target_stock=4, currency="IRR", unit="TOMAN")], requested_by="admin"
        )
    )[0]
    assert result.retry_eligible is True
    assert result.error_category == "rate_limit"
    assert result.external_response_id == "req-1"
    assert result.outcome is WriteOutcome.FAILED

    unavailable = SnappShopWorkspaceConnector(
        SimpleNamespace(
            _snappshop_connector=lambda: None,
            channel_write_enabled=lambda _channel_id: False,
        )
    )
    assert unavailable.capabilities().health_state == "unconfigured"
    assert unavailable.capabilities().write_available is False
    with pytest.raises(WorkspaceDomainError, match="Read-only"):
        await unavailable.apply_updates([], requested_by="admin")


def test_factory_exposes_only_implemented_channels_and_rejects_coming_soon():
    commerce = SimpleNamespace(
        _snappshop_connector=lambda: None,
        _tapsishop_connector=lambda: None,
        _technolife_connector=lambda: None,
    )
    factory = WorkspaceConnectorFactory(_Pricing(), commerce)
    assert {connector.channel_id for connector in factory.implemented()} == {
        "woocommerce:primary",
        "snappshop:main",
        "tapsishop:main",
        "technolife:main",
    }
    with pytest.raises(WorkspaceDomainError):
        factory.get("digikala:main")


@pytest.mark.asyncio
async def test_tapsishop_workspace_sends_complete_reviewed_state_and_requires_reconciliation():
    requests = []

    class Provider:
        async def update_products(self, updates):
            requests.extend(updates)
            return [
                ChannelProductUpdateResult(
                    channel_id="tapsishop:main",
                    identifiers=update.identifiers,
                    success=True,
                    raw={"referenceCode": update.idempotency_key},
                )
                for update in updates
            ]

    connector = TapsiShopWorkspaceConnector(
        SimpleNamespace(
            _tapsishop_connector=lambda: Provider(),
            channel_write_enabled=lambda _channel_id: True,
        )
    )
    update = _update(
        currency="IRR",
        unit="RIAL",
        current_price=100000,
        target_price=120000,
        current_stock=7,
        target_stock=None,
    )

    result = (await connector.apply_updates([update], requested_by="admin"))[0]

    assert requests[0].price == 120000
    assert requests[0].stock_quantity == 7
    assert requests[0].idempotency_key == "idem-1"
    assert result.provider_accepted is True
    assert result.outcome is WriteOutcome.RECONCILIATION_REQUIRED
    with pytest.raises(WorkspaceDomainError, match="price and stock"):
        connector.validate_update(
            _update(
                currency="IRR",
                unit="RIAL",
                current_stock=None,
                target_stock=None,
            )
        )
    with pytest.raises(WorkspaceDomainError, match="variation"):
        connector.validate_update(
            _update(
                currency="IRR",
                unit="RIAL",
                product_type="variation",
                parent_external_id="parent-1",
            )
        )


@pytest.mark.asyncio
async def test_tapsishop_workspace_enforces_read_only_mode_before_provider_io():
    provider_called = False

    class Provider:
        async def update_products(self, updates):
            nonlocal provider_called
            provider_called = True
            return []

    connector = TapsiShopWorkspaceConnector(
        SimpleNamespace(
            _tapsishop_connector=lambda: Provider(),
            channel_write_enabled=lambda _channel_id: False,
        )
    )

    assert connector.capabilities().write_available is False
    with pytest.raises(WorkspaceDomainError, match="Read-only"):
        await connector.apply_updates(
            [_update(currency="IRR", unit="RIAL")],
            requested_by="admin",
        )
    assert provider_called is False


@pytest.mark.asyncio
async def test_technolife_workspace_requires_parent_and_exact_readback():
    requests = []

    class Provider:
        async def update_products(self, updates):
            requests.extend(updates)
            return [
                ChannelProductUpdateResult(
                    channel_id="technolife:main",
                    identifiers=updates[0].identifiers,
                    success=True,
                    raw={"request_id": "tech-1"},
                )
            ]

        async def get_product(self, identifiers):
            return ChannelProduct(
                channel_id="technolife:main",
                connector_type="technolife",
                identifiers=ChannelIdentifierSet(
                    external_product_id=identifiers["external_product_id"],
                    parent_product_number=identifiers["product_number"],
                ),
                name="Verified",
                current_price=125000,
                currency="IRR",
                price_unit="RIAL",
                stock_quantity=4,
            )

    connector = TechnolifeWorkspaceConnector(
        SimpleNamespace(
            _technolife_connector=lambda: Provider(),
            channel_write_enabled=lambda _channel_id: True,
        )
    )
    update = _update(
        external_primary_id="ITEM-1",
        parent_external_id="P-1",
        product_type="variation",
        current_price=100000,
        target_price=125000,
        target_stock=4,
        currency="IRR",
        unit="RIAL",
    )

    result = (await connector.apply_updates([update], requested_by="admin"))[0]

    assert requests[0].identifiers.external_product_id == "ITEM-1"
    assert requests[0].identifiers.parent_product_number == "P-1"
    assert result.outcome is WriteOutcome.VERIFIED_APPLIED
    assert result.accepted_price == 125000
    assert result.accepted_stock == 4
    with pytest.raises(WorkspaceDomainError, match="parent productCode"):
        connector.validate_update(_update(currency="IRR", unit="RIAL"))
