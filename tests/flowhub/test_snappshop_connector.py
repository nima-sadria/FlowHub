from __future__ import annotations

import httpx
import pytest

from app.flowhub.channels.contracts import (
    ChannelIdentifierSet,
    ChannelProductUpdate,
    ConnectorErrorCategory,
    CursorPagination,
    PageNumberPagination,
)
from app.flowhub.channels.snappshop import (
    InMemoryOrderEventCursorStore,
    SnappShopConfig,
    SnappShopConnector,
    SnappShopConnectorError,
    toman_amount,
)


class FakeResponse:
    def __init__(self, status_code: int, payload: object, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

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

    async def request(self, method, url, *, headers=None, params=None, json=None):
        self.requests.append({"method": method, "url": url, "headers": headers, "params": params, "json": json})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture(autouse=True)
def fake_http(monkeypatch):
    FakeAsyncClient.responses = []
    FakeAsyncClient.requests = []
    monkeypatch.setattr("app.flowhub.channels.snappshop.httpx.AsyncClient", FakeAsyncClient)


def connector(cursor_store: InMemoryOrderEventCursorStore | None = None) -> SnappShopConnector:
    return SnappShopConnector(
        channel_id="snappshop:main",
        config=SnappShopConfig(
            token="token-secret",
            agent_identifier="flowhub-agent",
            vendor_id="vendor-1",
            base_url="https://apix.snappshop.ir/automation/v1",
        ),
        cursor_store=cursor_store,
    )


@pytest.mark.asyncio
async def test_successful_authentication_uses_bearer_and_configured_agent_header():
    FakeAsyncClient.responses = [
        FakeResponse(200, {"status": True, "data": [{"id": "vendor-1", "title": "Shop"}]}),
        FakeResponse(200, {"status": True, "data": {"id": "vendor-1", "title": "Shop"}}),
    ]

    health = await connector().test_connection()

    assert health.status == "healthy"
    assert FakeAsyncClient.requests[0]["url"].endswith("/vendors")
    assert FakeAsyncClient.requests[0]["headers"]["Authorization"] == "Bearer token-secret"
    assert FakeAsyncClient.requests[0]["headers"]["User-Agent"] == "flowhub-agent"


@pytest.mark.asyncio
async def test_401_normalizes_to_authentication_error():
    FakeAsyncClient.responses = [FakeResponse(401, {"status": False, "message": "denied"})]

    health = await connector().test_connection()

    assert health.status == "unhealthy"
    assert health.error is not None
    assert health.error.category == ConnectorErrorCategory.AUTHENTICATION
    assert "token-secret" not in health.error.message


@pytest.mark.asyncio
async def test_vendor_listing_and_page_pagination():
    FakeAsyncClient.responses = [
        FakeResponse(200, {
            "status": True,
            "data": [{
                "id": "p1",
                "sku": "SKU-1",
                "product_number": 135,
                "parent_product_number": 120,
                "title": "Product",
                "price": 842330,
                "stock": 7,
                "active": True,
            }],
            "meta": {"pagination": {"total": 41, "count": 20, "per_page": 20, "current_page": 2, "total_pages": 3}},
        }),
    ]

    result = await connector().list_products(PageNumberPagination(page=2, page_size=20))

    assert result.pagination.page == 2
    assert result.pagination.page_size == 20
    assert result.pagination.total_pages == 3
    product = result.items[0]
    assert product.identifiers.external_product_id == "p1"
    assert product.identifiers.sku == "SKU-1"
    assert product.identifiers.product_number == "135"
    assert product.price_unit == "toman"
    assert product.currency == "IRR"


@pytest.mark.asyncio
async def test_product_pagination_follows_next_link_when_total_pages_is_missing():
    FakeAsyncClient.responses = [
        FakeResponse(200, {
            "status": True,
            "data": [{"id": "p1", "title": "One", "price": 1000, "stock": 1}],
            "meta": {
                "pagination": {
                    "count": 1,
                    "per_page": 20,
                    "current_page": 1,
                    "links": {"next": "https://apix.snappshop.ir/automation/v1/vendors/vendor-1/products?page=2"},
                }
            },
        }),
        FakeResponse(200, {
            "status": True,
            "data": [{"id": "p2", "title": "Two", "price": 2000, "stock": 2}],
            "meta": {"pagination": {"count": 1, "per_page": 20, "current_page": 2, "links": {"next": None}}},
        }),
    ]

    products = await connector().list_all_products()

    assert [item.identifiers.external_product_id for item in products] == ["p1", "p2"]
    assert [request["params"] for request in FakeAsyncClient.requests] == [{"page": 1}, {"page": 2}]


@pytest.mark.asyncio
async def test_product_update_partial_failure_and_sku_precedence():
    FakeAsyncClient.responses = [
        FakeResponse(200, {
            "status": True,
            "data": [
                {"id": "p1", "sku": "SKU-1", "status": True, "messages": []},
                {"id": "p2", "sku": "SKU-2", "status": False, "messages": ["invalid stock"]},
            ],
        }),
    ]

    results = await connector().update_products([
        ChannelProductUpdate(
            channel_id="snappshop:main",
            identifiers=ChannelIdentifierSet(external_product_id="p1", sku="SKU-1"),
            price=100000,
            stock_quantity=3,
            currency="IRR",
            price_unit="rial",
        ),
        ChannelProductUpdate(
            channel_id="snappshop:main",
            identifiers=ChannelIdentifierSet(external_product_id="p2", sku="SKU-2"),
            price=20000,
            stock_quantity=0,
            currency="TMN",
            price_unit="toman",
        ),
    ])

    sent = FakeAsyncClient.requests[0]["json"]["products"]
    assert sent[0] == {"sku": "SKU-1", "stock": 3, "price": 10000}
    assert "id" not in sent[0]
    assert results[0].success is True
    assert results[1].success is False
    assert results[1].error.category == ConnectorErrorCategory.VALIDATION


@pytest.mark.asyncio
async def test_http_422_is_validation_and_not_retryable():
    FakeAsyncClient.responses = [FakeResponse(422, {"status": False, "errors": ["invalid"]})]

    results = await connector().update_products([
        ChannelProductUpdate(
            channel_id="snappshop:main",
            identifiers=ChannelIdentifierSet(external_product_id="p1"),
            price=10000,
            stock_quantity=1,
            currency="TMN",
            price_unit="toman",
        )
    ])

    assert results[0].success is False
    assert results[0].error.category == ConnectorErrorCategory.VALIDATION
    assert results[0].error.retry.retryable is False


@pytest.mark.asyncio
async def test_rate_limit_timeout_and_malformed_upstream_response():
    FakeAsyncClient.responses = [FakeResponse(429, {"status": False}, {"Retry-After": "7"})]
    with pytest.raises(SnappShopConnectorError) as rate_limit:
        await connector().list_products()
    assert rate_limit.value.error.category == ConnectorErrorCategory.RATE_LIMIT
    assert rate_limit.value.error.retry.retry_after_seconds == 7

    FakeAsyncClient.responses = [httpx.TimeoutException("timeout")]
    with pytest.raises(SnappShopConnectorError) as timeout:
        await connector().list_products()
    assert timeout.value.error.category == ConnectorErrorCategory.TIMEOUT

    FakeAsyncClient.responses = [FakeResponse(200, ValueError("not json"))]
    with pytest.raises(SnappShopConnectorError) as malformed:
        await connector().list_products()
    assert malformed.value.error.category == ConnectorErrorCategory.UNEXPECTED_RESPONSE


def test_toman_conversion_prevents_rial_multiplication_errors():
    assert toman_amount(100000, currency="IRR", unit="rial") == 10000
    assert toman_amount(10000, currency="TMN", unit="toman") == 10000
    with pytest.raises(SnappShopConnectorError):
        toman_amount(100001, currency="IRR", unit="rial")


@pytest.mark.asyncio
async def test_cursor_pagination_duplicate_events_and_safe_cursor_advance():
    store = InMemoryOrderEventCursorStore()
    c = connector(store)
    payload = {
        "status": True,
        "data": [
            {"event_type": "NEW_ORDER", "order_number": 1, "event_at": "2025-11-01 10:00:00"},
            {"event_type": "NEW_ORDER", "order_number": 1, "event_at": "2025-11-01 10:00:00"},
        ],
        "meta": {"pagination": {"per_page": 20, "count": 2, "has_more": True, "next_cursor": "next-1"}},
    }
    FakeAsyncClient.responses = [FakeResponse(200, payload)]

    first = await c.list_order_events(CursorPagination(cursor=None, limit=20))

    assert first.pagination.next_cursor == "next-1"
    assert len(first.items) == 2
    assert store.get_cursor("snappshop:main") is None

    c.acknowledge_order_events(first)
    assert store.get_cursor("snappshop:main") == "next-1"

    FakeAsyncClient.responses = [FakeResponse(200, payload)]
    second = await c.list_order_events()
    assert second.items == []
    assert FakeAsyncClient.requests[-1]["params"] == {"cursor": "next-1"}


@pytest.mark.asyncio
async def test_order_details_and_history_date_filters_preserve_sensitive_nulls():
    order_payload = {
        "order_number": 727,
        "status": "CONFIRMED",
        "customer": {"phone": None, "national_id": None},
        "items": [{
            "sku": None,
            "vendor_product_info_id": "geW1VB",
            "product_number": 135654,
            "parent_product_number": 135125,
            "canceled_quantity": 1,
            "total_canceled_quantity": 1,
            "deliverable_quantity": 0,
            "final_price": 0,
            "item_status": "CANCELED",
        }],
    }
    FakeAsyncClient.responses = [
        FakeResponse(200, {"status": True, "data": order_payload}),
        FakeResponse(200, {
            "status": True,
            "data": [order_payload],
            "meta": {"pagination": {"has_more": False, "next_cursor": None, "per_page": 20, "count": 1}},
        }),
    ]

    order = await connector().get_order({"order_number": "727"})
    history = await connector().list_order_history(date_start="2025-09-23", date_end="2025-10-22")

    assert order.identifiers.order_number == "727"
    assert order.items[0].raw["vendor_product_info_id"] == "geW1VB"
    assert order.raw["customer"]["phone"] is None
    assert FakeAsyncClient.requests[-1]["params"] == {"start_date": "2025-09-23", "end_date": "2025-10-22"}
    assert len(history.items) == 1
