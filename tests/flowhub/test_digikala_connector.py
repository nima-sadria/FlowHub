from __future__ import annotations

import httpx
import pytest

from app.flowhub.channels.contracts import ConnectorErrorCategory, PageNumberPagination
from app.flowhub.channels.digikala import (
    DIGIKALA_BASE_URL,
    DIGIKALA_DOCUMENTED_NOT_IMPLEMENTED,
    DIGIKALA_MAX_SAFE_READ_ATTEMPTS,
    DigikalaConfig,
    DigikalaConnector,
    DigikalaConnectorError,
)
from app.flowhub.channels.marketplace import UnsupportedCapabilityError


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: object | None = None,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.content = b"" if payload is None else b"json"
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

    async def request(self, method, url, *, headers=None, json=None):
        self.requests.append(
            {"method": method, "url": url, "headers": headers, "json": json}
        )
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture(autouse=True)
def fake_http(monkeypatch):
    FakeAsyncClient.responses = []
    FakeAsyncClient.requests = []
    monkeypatch.setattr("app.flowhub.channels.digikala.httpx.AsyncClient", FakeAsyncClient)


def connector(*, allow_token_refresh: bool = True, **overrides) -> DigikalaConnector:
    return DigikalaConnector(
        channel_id="digikala:main",
        config=DigikalaConfig(
            access_token="access-secret",
            refresh_token="refresh-secret",
            **overrides,
        ),
        allow_token_refresh=allow_token_refresh,
    )


def test_configuration_requires_a_write_only_access_token_and_documented_base_url():
    config = DigikalaConfig.from_values(
        settings={}, secrets={"access_token": "access-secret"}
    )

    assert config.base_url == DIGIKALA_BASE_URL
    assert config.refresh_token is None
    with pytest.raises(ValueError, match="access token is required"):
        DigikalaConfig.from_values(settings={}, secrets={})
    with pytest.raises(ValueError, match="documented HTTPS Open API"):
        DigikalaConfig.from_values(
            settings={"base_url": "https://example.test/open-api/v1"},
            secrets={"access_token": "access-secret"},
        )
    with pytest.raises(ValueError, match="documented HTTPS Open API"):
        DigikalaConfig.from_values(
            settings={"base_url": f"{DIGIKALA_BASE_URL}/uncontracted-path"},
            secrets={"access_token": "access-secret"},
        )
    # Credentials deliberately do not fall back to ordinary configuration.
    with pytest.raises(ValueError, match="access token is required"):
        DigikalaConfig.from_values(
            settings={"access_token": "leak-prone-setting"}, secrets={}
        )


@pytest.mark.asyncio
async def test_exact_documented_raw_reads_use_bearer_auth_and_do_not_guess_pagination():
    pager_payload = {
        "status": "ok",
        "data": {
            "pager": {"page": 1, "item_per_page": 50, "total_pages": 4, "total_rows": 183},
            "items": [],
        },
    }
    FakeAsyncClient.responses = [
        FakeResponse(200, {"status": "ok", "data": []}),
        FakeResponse(200, pager_payload),
        FakeResponse(200, {"status": "ok", "data": {"inventory": []}}),
        FakeResponse(200, pager_payload),
        FakeResponse(200, {"status": "ok", "data": {"detail": {}}}),
        FakeResponse(200, {"status": "ok", "data": []}),
    ]
    c = connector()

    await c.read_categories_payload()
    assert await c.read_seller_products_payload() == pager_payload
    await c.read_inventory_payload("variant / 1")
    assert await c.read_orders_payload() == pager_payload
    await c.read_order_payload("order/item")
    await c.read_scopes_payload()

    assert [request["method"] for request in FakeAsyncClient.requests] == ["GET"] * 6
    assert [request["url"] for request in FakeAsyncClient.requests] == [
        f"{DIGIKALA_BASE_URL}/categories/tree",
        f"{DIGIKALA_BASE_URL}/products/seller",
        f"{DIGIKALA_BASE_URL}/inventories/variant%20%2F%201",
        f"{DIGIKALA_BASE_URL}/orders",
        f"{DIGIKALA_BASE_URL}/orders/order%2Fitem",
        f"{DIGIKALA_BASE_URL}/auth/scopes",
    ]
    for request in FakeAsyncClient.requests:
        assert request["headers"] == {
            "Authorization": "Bearer access-secret",
            "Content-Type": "application/json",
        }
        assert request["json"] is None


@pytest.mark.asyncio
async def test_auth_code_exchange_and_refresh_use_only_documented_json_bodies():
    updated: list[tuple[str, str]] = []
    c = DigikalaConnector(
        channel_id="digikala:main",
        config=DigikalaConfig(access_token="old-access", refresh_token="old-refresh"),
        token_updater=lambda access, refresh: updated.append((access, refresh)),
    )
    FakeAsyncClient.responses = [
        FakeResponse(200, {"access_token": "issued-access", "refresh_token": "issued-refresh"}),
        FakeResponse(200, {"data": {"access_token": "new-access", "refresh_token": "new-refresh"}}),
    ]

    issued = await c.exchange_authorization_code("callback-code")
    health = await c.refresh_credentials()

    assert issued.access_token == "issued-access"
    assert issued.refresh_token == "issued-refresh"
    assert health.status == "healthy"
    exchange, refresh = FakeAsyncClient.requests
    assert exchange == {
        "method": "POST",
        "url": f"{DIGIKALA_BASE_URL}/auth/token",
        "headers": {"Content-Type": "application/json"},
        "json": {"authorization_code": "callback-code"},
    }
    assert refresh == {
        "method": "POST",
        "url": f"{DIGIKALA_BASE_URL}/auth/refresh-token",
        "headers": {"Content-Type": "application/json"},
        "json": {"access_token": "old-access", "refresh_token": "old-refresh"},
    }
    assert updated == [("new-access", "new-refresh")]


@pytest.mark.asyncio
async def test_read_only_401_refreshes_once_then_retries_with_replacement_tokens():
    updated: list[tuple[str, str]] = []
    c = DigikalaConnector(
        channel_id="digikala:main",
        config=DigikalaConfig(access_token="old-access", refresh_token="old-refresh"),
        token_updater=lambda access, refresh: updated.append((access, refresh)),
    )
    FakeAsyncClient.responses = [
        FakeResponse(401, {"code": "expired"}),
        FakeResponse(200, {"access_token": "new-access", "refresh_token": "new-refresh"}),
        FakeResponse(200, {"status": "ok", "data": {"items": []}}),
    ]

    await c.read_orders_payload()

    assert [request["method"] for request in FakeAsyncClient.requests] == ["GET", "POST", "GET"]
    assert FakeAsyncClient.requests[0]["url"] == f"{DIGIKALA_BASE_URL}/orders"
    assert FakeAsyncClient.requests[1]["url"] == f"{DIGIKALA_BASE_URL}/auth/refresh-token"
    assert FakeAsyncClient.requests[2]["headers"]["Authorization"] == "Bearer new-access"
    assert updated == [("new-access", "new-refresh")]


@pytest.mark.asyncio
async def test_connection_probe_is_one_read_only_orders_get_and_never_rotates_tokens():
    # Even a normally configured connector must keep Test Connection
    # observational; the service-level no-refresh guard is defense in depth.
    c = connector()
    FakeAsyncClient.responses = [FakeResponse(401, {"code": "expired"})]

    health = await c.test_connection()

    assert health.status == "unhealthy"
    assert health.error is not None
    assert health.error.category == ConnectorErrorCategory.AUTHENTICATION
    assert [request["method"] for request in FakeAsyncClient.requests] == ["GET"]
    assert FakeAsyncClient.requests[0]["url"] == f"{DIGIKALA_BASE_URL}/orders"


@pytest.mark.asyncio
async def test_safe_raw_read_retries_documented_500_with_bounded_backoff():
    delays: list[float] = []

    async def no_sleep(seconds: float) -> None:
        delays.append(seconds)

    FakeAsyncClient.responses = [
        FakeResponse(500, {"code": "temporarily_unavailable"}),
        FakeResponse(200, {"status": "ok", "data": {"items": []}}),
    ]
    c = DigikalaConnector(
        channel_id="digikala:main",
        config=DigikalaConfig(access_token="access-secret"),
        allow_token_refresh=False,
        sleeper=no_sleep,
    )

    assert await c.read_orders_payload() == {"status": "ok", "data": {"items": []}}

    assert [request["method"] for request in FakeAsyncClient.requests] == ["GET", "GET"]
    assert [request["url"] for request in FakeAsyncClient.requests] == [
        f"{DIGIKALA_BASE_URL}/orders",
        f"{DIGIKALA_BASE_URL}/orders",
    ]
    assert delays == [0.25]


@pytest.mark.asyncio
async def test_safe_raw_read_honors_documented_rate_limit_delay_before_one_retry():
    delays: list[float] = []

    async def no_sleep(seconds: float) -> None:
        delays.append(seconds)

    FakeAsyncClient.responses = [
        FakeResponse(429, {"code": "rate_limited"}, headers={"Retry-After": "7"}),
        FakeResponse(200, {"status": "ok", "data": {"items": []}}),
    ]
    c = DigikalaConnector(
        channel_id="digikala:main",
        config=DigikalaConfig(access_token="access-secret"),
        allow_token_refresh=False,
        sleeper=no_sleep,
    )

    await c.read_orders_payload()

    assert [request["method"] for request in FakeAsyncClient.requests] == ["GET", "GET"]
    assert delays == [7]


@pytest.mark.asyncio
async def test_connection_probe_does_not_retry_a_rate_limit_response():
    FakeAsyncClient.responses = [
        FakeResponse(429, {"code": "rate_limited"}, headers={"Retry-After": "7"})
    ]

    health = await connector().test_connection()

    assert health.status == "unhealthy"
    assert health.error is not None
    assert health.error.category == ConnectorErrorCategory.RATE_LIMIT
    assert len(FakeAsyncClient.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected_category", "retryable"),
    [
        (400, ConnectorErrorCategory.VALIDATION, False),
        (401, ConnectorErrorCategory.AUTHENTICATION, False),
        (403, ConnectorErrorCategory.AUTHORIZATION, False),
        (404, ConnectorErrorCategory.NOT_FOUND, False),
        (429, ConnectorErrorCategory.RATE_LIMIT, True),
        (500, ConnectorErrorCategory.UPSTREAM_UNAVAILABLE, True),
    ],
)
async def test_documented_http_errors_are_structured_and_secret_safe(
    status_code, expected_category, retryable
):
    FakeAsyncClient.responses = [
        FakeResponse(
            status_code,
            {"code": "provider-code", "message": "provider text access-secret"},
            headers={"Retry-After": "7"} if status_code == 429 else None,
        )
    ]

    health = await connector(allow_token_refresh=False).test_connection()

    assert health.status == "unhealthy"
    assert health.error is not None
    assert health.error.category == expected_category
    assert health.error.provider_code == "provider-code"
    assert health.error.retry.retryable is retryable
    assert health.error.retry.safe_to_retry is retryable
    assert health.error.retry.retry_after_seconds == (7 if status_code == 429 else None)
    assert health.error.retry.max_attempts == (
        DIGIKALA_MAX_SAFE_READ_ATTEMPTS if retryable else 0
    )
    assert "access-secret" not in health.error.message


@pytest.mark.asyncio
async def test_timeout_is_structured_and_safe_get_is_retry_eligible():
    FakeAsyncClient.responses = [httpx.TimeoutException("timeout")]

    health = await connector().test_connection()

    assert health.status == "unhealthy"
    assert health.error is not None
    assert health.error.category == ConnectorErrorCategory.TIMEOUT
    assert health.error.retry.retryable is True
    assert health.error.retry.safe_to_retry is True


@pytest.mark.asyncio
async def test_product_and_order_normalization_and_all_writes_remain_fail_closed():
    c = connector()

    with pytest.raises(UnsupportedCapabilityError) as product_exc:
        await c.list_products(PageNumberPagination(page=1, page_size=10))
    with pytest.raises(UnsupportedCapabilityError) as order_exc:
        await c.list_orders(PageNumberPagination(page=1, page_size=10))
    with pytest.raises(UnsupportedCapabilityError):
        await c.update_products([])
    rejected_requests = [
        ("POST", "/orders"),
        ("POST", "orders"),
        ("POST", "/variants/123"),
        ("GET", "/variants/123"),
        # The supplied contract does not define order date/status query keys;
        # raw transport must not guess or forward them.
        ("GET", "/orders?status=approved"),
        ("GET", "/orders?date_from=2026-08-01"),
        ("POST", "/auth/token"),
    ]
    for method, path in rejected_requests:
        with pytest.raises(DigikalaConnectorError) as mutation_exc:
            await c._request(method, path, safe_to_retry=False)
        assert mutation_exc.value.error.category == ConnectorErrorCategory.UNSUPPORTED_CAPABILITY

    with pytest.raises(DigikalaConnectorError) as revoke_exc:
        await c._token_request(
            "POST",
            "/auth/revoke",
            json={"refresh_token": "refresh-secret"},
            operation="token revoke",
        )
    with pytest.raises(DigikalaConnectorError) as direct_transport_exc:
        await c._send(
            "POST",
            "/orders",
            headers={"Authorization": "Bearer access-secret"},
            authorized=True,
        )

    assert product_exc.value.error.category == ConnectorErrorCategory.UNSUPPORTED_CAPABILITY
    assert order_exc.value.error.category == ConnectorErrorCategory.UNSUPPORTED_CAPABILITY
    assert revoke_exc.value.error.category == ConnectorErrorCategory.UNSUPPORTED_CAPABILITY
    assert direct_transport_exc.value.error.category == ConnectorErrorCategory.UNSUPPORTED_CAPABILITY
    assert FakeAsyncClient.requests == []
    assert {
        "normalized_product_and_inventory_cache",
        "normalized_order_sync_and_incremental_filters",
        "variant_price_activation_and_inventory_writes",
        "package_and_shipment_operations",
    }.issubset(DIGIKALA_DOCUMENTED_NOT_IMPLEMENTED)
