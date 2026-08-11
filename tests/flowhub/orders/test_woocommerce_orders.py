from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.connectors.destinations.woocommerce.auth import WooCommerceCredentials
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.channels.contracts import PageNumberPagination, PaginatedResult
from app.flowhub.channels.woocommerce import WooCommerceOrderConnector
from app.flowhub.database import FlowHubBase
from app.flowhub.integration_platform.models import (
    IntegrationConnectorInstance,
    IntegrationConnectorSetting,
)
from app.flowhub.orders.models import (
    ChannelInventoryEffectRecord,
    ChannelOrderItemRecord,
    ChannelOrderRecord,
)
from app.flowhub.orders.service import OrderSyncService


def _raw_order() -> dict:
    return {
        "id": 901,
        "number": "WC-901",
        "status": "processing",
        "currency": "IRR",
        "total": "36550000",
        "date_created_gmt": "2026-07-17T08:00:00",
        "date_modified_gmt": "2026-07-17T08:05:00",
        "date_paid_gmt": "2026-07-17T08:01:00",
        "payment_method_title": "Card",
        "billing": {
            "first_name": "Test",
            "last_name": "Buyer",
            "email": "buyer@example.invalid",
        },
        "line_items": [
            {
                "id": 11,
                "name": "Simple product",
                "product_id": 51550,
                "variation_id": 0,
                "sku": "SIMPLE-1",
                "quantity": 1,
                "price": "100000",
                "subtotal": "100000",
                "total": "100000",
            },
            {
                "id": 12,
                "name": "Variation product",
                "product_id": 700,
                "variation_id": 701,
                "sku": "VAR-701",
                "quantity": 2,
                "price": "18225000",
                "subtotal": "36450000",
                "total": "36450000",
            },
        ],
    }


def _connector() -> WooCommerceOrderConnector:
    return WooCommerceOrderConnector(
        channel_id="woocommerce:test",
        credentials=WooCommerceCredentials(
            url="https://woocommerce.example.invalid",
            key="test-key",
            secret="test-secret",
        ),
    )


def _db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    FlowHubBase.metadata.create_all(engine)
    return Session(engine)


def test_normalizes_simple_and_variation_identity_without_provider_write() -> None:
    order = _connector()._normalize(_raw_order())

    assert order.identifiers.external_product_id == "901"
    assert order.identifiers.order_number == "WC-901"
    assert order.items[0].identifiers.external_product_id == "51550"
    assert order.items[0].identifiers.parent_product_number is None
    assert order.items[1].identifiers.external_product_id == "701"
    assert order.items[1].identifiers.product_number == "701"
    assert order.items[1].identifiers.parent_product_number == "700"
    assert order.raw["customer"]["display_name"] == "Test Buyer"


def test_repeated_read_only_reconciliation_is_idempotent() -> None:
    db = _db()
    connector = _connector()
    order = connector._normalize(_raw_order())

    class FakeWooCommerce:
        calls = 0

        async def list_orders(self, pagination: PageNumberPagination) -> PaginatedResult:
            self.calls += 1
            return PaginatedResult(
                items=[order],
                pagination=PageNumberPagination(
                    page=1, page_size=50, total=1, total_pages=1
                ),
            )

    fake = FakeWooCommerce()
    service = OrderSyncService(db)
    first = asyncio.run(service.reconcile_recent_orders("woocommerce:test", fake))
    second = asyncio.run(service.reconcile_recent_orders("woocommerce:test", fake))

    assert first.processed == second.processed == 1
    assert fake.calls == 2
    assert db.query(ChannelOrderRecord).count() == 1
    assert db.query(ChannelOrderItemRecord).count() == 2
    assert db.query(ChannelInventoryEffectRecord).count() == 0
    shape = service.list_orders(search="WC-901")["items"][0]
    assert shape["normalizedStatus"] == "processing"
    assert shape["customerDisplay"] == "Test Buyer"
    assert shape["paymentStatus"] == "paid"
    assert shape["fulfillmentStatus"] == "pending"


def test_order_list_filters_by_channel_status_search_and_date() -> None:
    db = _db()
    service = OrderSyncService(db)
    service.upsert_order(
        _connector()._normalize(_raw_order()),
        source="reconciliation",
    )

    assert service.list_orders(channel_id="woocommerce:test")["total"] == 1
    assert service.list_orders(normalized_status="processing")["total"] == 1
    assert service.list_orders(normalized_status="cancelled")["total"] == 0
    assert service.list_orders(search="901")["total"] == 1
    assert service.list_orders(date_from="2026-07-18")["total"] == 0
    assert service.list_orders(date_to="2026-07-16")["total"] == 0
    assert service.list_orders(date_to="2026-07-17")["total"] == 1
    assert service.list_orders(date_to="2026-07-17T07:59:59")["total"] == 0
    assert service.list_orders(date_to="2026-07-17T08:00:00")["total"] == 1


@pytest.mark.asyncio
async def test_manual_sync_is_read_only_and_operator_authorized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.flowhub.api.v2 import orders as orders_api

    db = _db()
    db.add(
        IntegrationConnectorInstance(
            id="woocommerce:test",
            connector_type="woocommerce",
            name="WooCommerce Test",
            enabled=True,
            read_only=True,
            status="configured",
        )
    )
    for key, value in {
        "url": "https://woocommerce.example.invalid",
        "key": "test-key",
        "secret": "test-secret",
    }.items():
        db.add(
            IntegrationConnectorSetting(
                connector_id="woocommerce:test",
                key=key,
                value_json=None if key in {"key", "secret"} else value,
                configured=True,
                secret=key in {"key", "secret"},
            )
        )
    db.commit()
    from app.flowhub.setup.service import AppConfigService

    AppConfigService(db).set_many(
        {
            "woocommerce.key": "test-key",
            "woocommerce.secret": "test-secret",
        },
        updated_by="test",
    )
    order = _connector()._normalize(_raw_order())

    class FakeReadOnlyConnector:
        def __init__(self, **_: object) -> None:
            self.calls = 0

        async def list_orders(self, pagination: PageNumberPagination) -> PaginatedResult:
            self.calls += 1
            return PaginatedResult(items=[order], pagination=pagination)

    resolved_settings: dict[str, object] = {}

    def build_fake_connector(**kwargs: object) -> FakeReadOnlyConnector:
        settings = kwargs["settings"]
        assert isinstance(settings, dict)
        resolved_settings.update(settings)
        return FakeReadOnlyConnector(
            channel_id=kwargs["channel_id"],
            credentials=WooCommerceCredentials(
                url=str(settings["url"]),
                key=str(settings["key"]),
                secret=str(settings["secret"]),
            ),
        )

    monkeypatch.setattr(
        orders_api,
        "build_woocommerce_order_connector",
        build_fake_connector,
    )
    operator = FlowHubUser(
        id=20,
        username="operator",
        hashed_password="not-returned",
        role="operator",
        is_active=True,
    )
    result = await orders_api.synchronize_channel_orders(
        "woocommerce:test",
        user=operator,
        service=OrderSyncService(db),
    )

    assert result["processed"] == 1
    assert result["providerMutationPerformed"] is False
    assert result["canonicalInventoryMutated"] is False
    assert result["productPricesWritten"] is False
    assert resolved_settings == {
        "url": "https://woocommerce.example.invalid",
        "key": "test-key",
        "secret": "test-secret",
    }
    assert db.query(ChannelInventoryEffectRecord).count() == 0
    masked_settings = (
        db.query(IntegrationConnectorSetting)
        .filter(
            IntegrationConnectorSetting.connector_id == "woocommerce:test",
            IntegrationConnectorSetting.key.in_(("key", "secret")),
        )
        .all()
    )
    assert len(masked_settings) == 2
    assert all(item.value_json is None for item in masked_settings)

    viewer = FlowHubUser(
        id=21,
        username="viewer",
        hashed_password="not-returned",
        role="viewer",
        is_active=True,
    )
    with pytest.raises(HTTPException) as forbidden:
        await orders_api.synchronize_channel_orders(
            "woocommerce:test",
            user=viewer,
            service=OrderSyncService(db),
        )
    assert forbidden.value.status_code == 403
