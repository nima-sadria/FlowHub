from __future__ import annotations

import httpx
import pytest

from app.flowhub.channels.contracts import (
    ChannelCapability,
    ChannelIdentifierSet,
    ChannelProductUpdate,
    ConnectorErrorCategory,
    PageNumberPagination,
)
from app.flowhub.channels.marketplace import UnsupportedCapabilityError
from app.flowhub.channels.tapsishop import (
    TAPSISHOP_AUTH_HEADER,
    TAPSISHOP_BASE_URL,
    TAPSISHOP_COURIER_REVIEW_METHOD,
    TAPSISHOP_WEBHOOK_AUTH_HEADER,
    TapsiShopConfig,
    TapsiShopConnector,
    TapsiShopConnectorError,
    rial_amount,
)


class FakeResponse:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = {}

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeAsyncClient:
    responses: list[FakeResponse | Exception] = []
    requests: list[dict] = []

    def __init__(self, *args, **kwargs) -> None:
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def request(self, method, url, *, headers=None, json=None):
        self.requests.append({"method": method, "url": url, "headers": headers, "json": json})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture(autouse=True)
def fake_http(monkeypatch):
    FakeAsyncClient.responses = []
    FakeAsyncClient.requests = []
    monkeypatch.setattr("app.flowhub.channels.tapsishop.httpx.AsyncClient", FakeAsyncClient)


def connector(**overrides) -> TapsiShopConnector:
    config = TapsiShopConfig(
        token="tapsi-secret-token",
        webhook_token="webhook-secret-token",
        base_url=TAPSISHOP_BASE_URL,
        **overrides,
    )
    return TapsiShopConnector(channel_id="tapsishop:main", config=config)


@pytest.mark.asyncio
async def test_vendor_information_probe_uses_documented_auth_header():
    FakeAsyncClient.responses = [
        FakeResponse(200, {"success": True, "data": {
            "vendorId": 12,
            "vendorName": "Vendor",
            "storeName": "Store",
            "storeLink": "https://store.example.test",
            "storeNumber": "S-12",
        }}),
    ]

    vendor = await connector().get_vendor_information()

    request = FakeAsyncClient.requests[0]
    assert request["method"] == "GET"
    assert request["url"] == f"{TAPSISHOP_BASE_URL}/vendor-information"
    assert request["headers"][TAPSISHOP_AUTH_HEADER] == "tapsi-secret-token"
    assert vendor.vendor_id == "12"
    assert vendor.name == "Store"
    assert vendor.identifiers.channel_reference_code == "S-12"


@pytest.mark.asyncio
async def test_401_normalizes_to_authentication_error_without_token_leakage():
    FakeAsyncClient.responses = [FakeResponse(401, {"success": False})]

    health = await connector().test_connection()

    assert health.status == "unhealthy"
    assert health.error is not None
    assert health.error.category == ConnectorErrorCategory.AUTHENTICATION
    assert "tapsi-secret-token" not in health.error.message


@pytest.mark.asyncio
async def test_health_validates_selected_vendor_identity():
    FakeAsyncClient.responses = [
        FakeResponse(200, {"success": True, "data": {"vendorId": 12, "storeName": "Store", "storeNumber": "S-12"}}),
        FakeResponse(200, {"success": True, "data": {"vendorId": 12, "storeName": "Store", "storeNumber": "S-12"}}),
    ]

    assert (await connector(selected_vendor_id="12").test_connection()).status == "healthy"
    failed = await connector(selected_vendor_id="different").test_connection()

    assert failed.status == "unhealthy"
    assert failed.error is not None
    assert failed.error.category == ConnectorErrorCategory.NOT_FOUND


@pytest.mark.asyncio
async def test_paginated_product_listing_normalizes_rial_fields():
    FakeAsyncClient.responses = [
        FakeResponse(200, {"success": True, "data": {
            "page": 2,
            "pageSize": 20,
            "totalCount": 41,
            "items": [{
                "id": "prod-1",
                "hsin": "HS-1",
                "sku": "SKU-1",
                "originalPrice": 500000,
                "finalPrice": 450000,
                "minimalPerOrder": 1,
                "maximalPerOrder": 5,
                "onHandQuantity": 9,
            }],
        }}),
    ]

    result = await connector().list_products(PageNumberPagination(page=2, page_size=20))

    assert result.pagination.page == 2
    assert result.pagination.total == 41
    assert result.pagination.total_pages == 3
    product = result.items[0]
    assert product.identifiers.external_product_id == "prod-1"
    assert product.identifiers.product_number == "HS-1"
    assert product.current_price == 450000
    assert product.currency == "IRR"
    assert product.price_unit == "rial"
    assert FakeAsyncClient.requests[0]["url"].endswith("/products/2/20")


@pytest.mark.asyncio
async def test_product_update_success_and_partial_failure_preserve_reference_code():
    FakeAsyncClient.responses = [
        FakeResponse(200, {"success": True, "data": {
            "status": True,
            "data": [
                {"id": "SKU-1", "sku": "SKU-1", "status": True, "messages": [], "currentOriginalPrice": 100000, "currentFinalPrice": 90000, "currentOnHandQuantity": 3, "referenceCode": "ref-1"},
                {"id": "SKU-2", "sku": "SKU-2", "status": False, "messages": ["invalid stock"], "currentOriginalPrice": 200000, "currentFinalPrice": 200000, "currentOnHandQuantity": 0, "referenceCode": "ref-2"},
            ],
        }}),
    ]

    results = await connector().update_products([
        ChannelProductUpdate(
            channel_id="tapsishop:main",
            identifiers=ChannelIdentifierSet(sku="SKU-1"),
            price=100000,
            discount_price=90000,
            stock_quantity=3,
            currency="IRR",
            price_unit="rial",
            idempotency_key="ref-1",
        ),
        ChannelProductUpdate(
            channel_id="tapsishop:main",
            identifiers=ChannelIdentifierSet(sku="SKU-2"),
            price=200000,
            stock_quantity=0,
            currency="IRR",
            price_unit="rial",
            idempotency_key="ref-2",
        ),
    ])

    sent = FakeAsyncClient.requests[0]["json"]["products"]
    assert sent[0] == {"id": "SKU-1", "stock": 3, "price": 100000, "referenceCode": "ref-1", "specialPrice": 90000}
    assert results[0].success is True
    assert results[0].raw["referenceCode"] == "ref-1"
    assert results[1].success is False
    assert results[1].error.category == ConnectorErrorCategory.VALIDATION
    assert results[1].raw["referenceCode"] == "ref-2"


@pytest.mark.asyncio
async def test_unauthorized_safe_request_refreshes_token_once_and_retries():
    updated_tokens: list[str] = []
    c = TapsiShopConnector(
        channel_id="tapsishop:main",
        config=TapsiShopConfig(
            token="old-token",
            base_url=TAPSISHOP_BASE_URL,
            refresh_enabled=True,
            refresh_token_name="FlowHub",
            refresh_revoke_current_token=False,
            refresh_expired_at="2027-01-01T00:00:00Z",
        ),
        token_updater=updated_tokens.append,
    )
    FakeAsyncClient.responses = [
        FakeResponse(401, {"success": False}),
        FakeResponse(200, {"success": True, "data": {"token": "new-token", "expireDate": "2027-01-01T00:00:00Z"}}),
        FakeResponse(200, {"success": True, "data": {"vendorId": 1, "storeName": "Store"}}),
    ]

    vendor = await c.get_vendor_information()

    assert vendor.vendor_id == "1"
    assert [request["method"] for request in FakeAsyncClient.requests] == ["GET", "POST", "GET"]
    assert FakeAsyncClient.requests[1]["url"].endswith("/refresh-token")
    assert FakeAsyncClient.requests[1]["json"]["token"] == "old-token"
    assert FakeAsyncClient.requests[1]["json"]["revokeCurrentToken"] is False
    assert FakeAsyncClient.requests[2]["headers"][TAPSISHOP_AUTH_HEADER] == "new-token"
    assert updated_tokens == ["new-token"]


@pytest.mark.asyncio
async def test_token_refresh_failure_does_not_loop():
    FakeAsyncClient.responses = [
        FakeResponse(401, {"success": False}),
        FakeResponse(401, {"success": False}),
    ]

    with pytest.raises(TapsiShopConnectorError) as exc_info:
        await connector(refresh_enabled=True).get_vendor_information()

    assert exc_info.value.error.category == ConnectorErrorCategory.AUTHENTICATION
    assert len(FakeAsyncClient.requests) == 2


@pytest.mark.asyncio
async def test_timeout_malformed_and_422_responses_are_normalized():
    FakeAsyncClient.responses = [httpx.TimeoutException("timeout")]
    with pytest.raises(TapsiShopConnectorError) as timeout:
        await connector().list_products()
    assert timeout.value.error.category == ConnectorErrorCategory.TIMEOUT

    FakeAsyncClient.responses = [FakeResponse(200, ValueError("not json"))]
    with pytest.raises(TapsiShopConnectorError) as malformed:
        await connector().list_products()
    assert malformed.value.error.category == ConnectorErrorCategory.UNEXPECTED_RESPONSE

    FakeAsyncClient.responses = [FakeResponse(422, {"success": False})]
    with pytest.raises(TapsiShopConnectorError) as validation:
        await connector().update_products([
            ChannelProductUpdate(
                channel_id="tapsishop:main",
                identifiers=ChannelIdentifierSet(sku="SKU-1"),
                price=100000,
                stock_quantity=1,
                currency="IRR",
                price_unit="rial",
            )
        ])
    assert validation.value.error.category == ConnectorErrorCategory.VALIDATION


@pytest.mark.asyncio
async def test_order_filters_and_detail_normalization_preserve_codes_and_settlement_fields():
    FakeAsyncClient.responses = [
        FakeResponse(200, {"success": True, "data": {
            "pageNumber": 3,
            "pageSize": 10,
            "totalItems": 21,
            "items": [{
                "id": 77,
                "orderNumber": "ORD-77",
                "stateCode": "READY_TO_SHIP",
                "stateTitle": "Ready",
                "finalPrice": 300000,
                "createdOn": "2026-01-01T10:00:00Z",
            }],
        }}),
        FakeResponse(200, {"success": True, "data": {
            "order": {
                "orderNumber": "ORD-77",
                "orderDate": "2026-01-01T10:00:00Z",
                "status": "READY_TO_SHIP",
                "amountAfterDiscount": 300000,
                "invoices": [{"number": "INV-1"}],
            },
            "shipments": [{"number": "SHIP-1", "status": "READY"}],
            "items": [{
                "name": "Product",
                "sku": "SKU-1",
                "finalPrice": 300000,
                "commissionPrice": 30000,
                "effectiveDate": "2026-01-02",
                "cancelReason": None,
            }],
            "settlement": {"status": "pending"},
        }}),
    ]

    orders = await connector().list_orders(
        PageNumberPagination(page=3, page_size=10),
        filters={"fromDate": "2026-01-01", "toDate": "2026-01-31", "orderStatusId": 4},
    )
    detail = await connector().get_order({"orderId": "77"})

    assert FakeAsyncClient.requests[0]["json"] == {
        "pageNumber": 3,
        "pageSize": 10,
        "fromDate": "2026-01-01",
        "toDate": "2026-01-31",
        "orderStatusId": 4,
    }
    assert orders.items[0].status == "READY_TO_SHIP"
    assert detail.identifiers.order_number == "ORD-77"
    assert detail.items[0].raw["commissionPrice"] == 30000
    assert detail.raw["shipments"][0]["number"] == "SHIP-1"
    assert detail.raw["settlement"]["status"] == "pending"


def test_rial_value_handling_rejects_toman_or_fractional_values():
    assert rial_amount(100000, currency="IRR", unit="rial") == 100000
    with pytest.raises(TapsiShopConnectorError):
        rial_amount(10000, currency="TMN", unit="toman")
    with pytest.raises(TapsiShopConnectorError):
        rial_amount(100000.5, currency="IRR", unit="rial")
    with pytest.raises(TapsiShopConnectorError):
        rial_amount(101, currency="IRR", unit="rial")


@pytest.mark.asyncio
async def test_webhook_authorization_and_success_response():
    event = await connector().receive_webhook(
        b'{"orderDetail":{"requestId":"req-1","orderId":77,"orderNumber":"ORD-77","changeType":"CHANGE_STATUS","createdOnTimestamp":"2026-01-01T10:00:00Z"}}',
        {TAPSISHOP_WEBHOOK_AUTH_HEADER: "webhook-secret-token"},
    )

    assert event.event_id == "req-1"
    assert event.event_type == "CHANGE_STATUS"
    assert event.order_identifiers.order_number == "ORD-77"
    assert connector().webhook_success_response()["succeed"] is True

    with pytest.raises(TapsiShopConnectorError) as exc_info:
        await connector().receive_webhook(b"{}", {TAPSISHOP_WEBHOOK_AUTH_HEADER: "wrong"})
    assert exc_info.value.error.category == ConnectorErrorCategory.AUTHENTICATION


@pytest.mark.asyncio
async def test_courier_read_is_supported_but_review_remains_capability_gated():
    FakeAsyncClient.responses = [FakeResponse(200, {"success": True, "data": {"pickupCode": "P-1", "courierName": "Courier"}})]

    c = connector()
    courier = await c.get_courier("P-1")

    assert courier["pickupCode"] == "P-1"
    assert ChannelCapability.COURIER_REVIEW not in c.get_capabilities()
    assert TAPSISHOP_COURIER_REVIEW_METHOD == "PUT"
    with pytest.raises(UnsupportedCapabilityError):
        await c.review_courier(pickup_code="P-1", is_acceptable=True, include_details=False)
