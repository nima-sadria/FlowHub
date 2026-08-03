from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.connectors.common.current_state import CurrentStateIdentity, CurrentStateRequest
from app.flowhub.channels.contracts import (
    ChannelIdentifierSet,
    ChannelProductUpdate,
    PageNumberPagination,
)
from app.flowhub.channels.technolife import (
    TECHNOLIFE_BASE_URL,
    TechnolifeConfig,
    TechnolifeConnector,
    encrypt_endpoint,
)

SECRET_BYTES = b"0123456789abcdef"
SECRET = base64.b64encode(SECRET_BYTES).decode("ascii")


class FakeResponse:
    def __init__(self, status_code: int, payload: object | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.content = b"" if payload is None else b"json"

    def json(self):
        return self._payload


class FakeAsyncClient:
    responses: list[FakeResponse] = []
    requests: list[dict] = []

    def __init__(self, *args, **kwargs) -> None:
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def request(self, method, url, *, headers=None, params=None, json=None):
        self.requests.append(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "params": params,
                "json": json,
            }
        )
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def fake_http(monkeypatch):
    FakeAsyncClient.responses = []
    FakeAsyncClient.requests = []
    monkeypatch.setattr("app.flowhub.channels.technolife.httpx.AsyncClient", FakeAsyncClient)


def connector() -> TechnolifeConnector:
    return TechnolifeConnector(
        channel_id="technolife:main",
        config=TechnolifeConfig(api_key="api-key", encryption_secret=SECRET),
    )


def test_endpoint_encryption_matches_documented_iv_tag_ciphertext_format():
    iv = bytes(range(12))

    encrypted = encrypt_endpoint(SECRET, "/v1/products", iv=iv)

    encoded_iv, encoded_tag, encoded_ciphertext = encrypted.split(":")
    assert base64.b64decode(encoded_iv) == iv
    plaintext = AESGCM(SECRET_BYTES).decrypt(
        iv,
        base64.b64decode(encoded_ciphertext) + base64.b64decode(encoded_tag),
        None,
    )
    assert plaintext == b"/v1/products"


def test_config_accepts_only_documented_credentials_and_official_endpoint():
    config = TechnolifeConfig.from_values(
        settings={},
        secrets={"api_key": "api-key", "encryption_secret": SECRET},
    )
    assert config.base_url == TECHNOLIFE_BASE_URL

    with pytest.raises(ValueError, match="16 bytes"):
        TechnolifeConfig.from_values(
            settings={},
            secrets={
                "api_key": "api-key",
                "encryption_secret": base64.b64encode(b"short").decode(),
            },
        )
    with pytest.raises(ValueError, match="official HTTPS"):
        TechnolifeConfig.from_values(
            settings={"base_url": "https://example.test"},
            secrets={"api_key": "api-key", "encryption_secret": SECRET},
        )


@pytest.mark.asyncio
async def test_product_listing_reads_seller_items_and_normalizes_rial_values():
    FakeAsyncClient.responses = [
        FakeResponse(
            200,
            {"data": {"products": [{"code": "P-1", "title": "Phone"}], "count": 1}},
        ),
        FakeResponse(
            200,
            {
                "data": [
                    {
                        "code": "ITEM-1",
                        "SalesCode": "SKU-1",
                        "variation": "Black",
                        "guarantee": "18 months",
                        "cash": {"price": 1250000},
                        "available": 7,
                        "hide": False,
                    }
                ]
            },
        ),
    ]

    result = await connector().list_products(PageNumberPagination(page=1, page_size=20))

    assert result.pagination.total == 1
    product = result.items[0]
    assert product.identifiers.external_product_id == "ITEM-1"
    assert product.identifiers.parent_product_number == "P-1"
    assert product.current_price == 1250000
    assert product.stock_quantity == 7
    assert product.currency == "IRR"
    assert product.price_unit == "RIAL"
    assert FakeAsyncClient.requests[0]["params"] == {"page": 1, "limit": 20}
    assert FakeAsyncClient.requests[1]["url"].endswith("/v1/products/P-1/items")


@pytest.mark.asyncio
async def test_current_state_groups_seller_items_by_parent_with_item_diagnostics():
    FakeAsyncClient.responses = [
        FakeResponse(
            200,
            {
                "data": [
                    {
                        "code": "ITEM-1",
                        "cash": {"price": 1250000},
                        "available": 7,
                    }
                ]
            },
        ),
        FakeResponse(
            200,
            {
                "data": [
                    {
                        "code": "ITEM-2",
                        "cash": {"price": 2250000},
                        "available": 3,
                    }
                ]
            },
        ),
    ]
    request = CurrentStateRequest(
        channel_id="technolife:main",
        entities=(
            CurrentStateIdentity(
                key="listing-1", external_id="ITEM-1", parent_external_id="P-1"
            ),
            CurrentStateIdentity(
                key="listing-2", external_id="ITEM-2", parent_external_id="P-2"
            ),
            CurrentStateIdentity(
                key="listing-missing",
                external_id="ITEM-X",
                parent_external_id="P-2",
            ),
        ),
        required_fields=frozenset({"price", "stock"}),
    )

    result = await connector().fetch_current_state(request)

    assert result.records["listing-1"].price == 1250000
    assert result.records["listing-2"].stock == 3
    assert result.errors["listing-missing"].category == "not_found"
    assert result.transport.requests_issued == 2
    assert result.transport.batches_issued == 2
    assert result.transport.entities_returned == 2
    assert {request["url"].rsplit("/", 2)[-2] for request in FakeAsyncClient.requests} == {
        "P-1",
        "P-2",
    }


@pytest.mark.asyncio
async def test_current_state_isolates_failed_parent_collection():
    FakeAsyncClient.responses = [
        FakeResponse(
            200,
            {"data": [{"code": "ITEM-1", "cash": {"price": 1250000}, "available": 7}]},
        ),
        FakeResponse(503, {"message": "unavailable"}),
    ]
    request = CurrentStateRequest(
        channel_id="technolife:main",
        entities=(
            CurrentStateIdentity(
                key="listing-1", external_id="ITEM-1", parent_external_id="P-1"
            ),
            CurrentStateIdentity(
                key="listing-2", external_id="ITEM-2", parent_external_id="P-2"
            ),
        ),
        required_fields=frozenset({"price", "stock"}),
    )

    result = await connector().fetch_current_state(request)

    assert set(result.records) == {"listing-1"}
    assert result.errors["listing-2"].category == "upstream_unavailable"
    assert result.transport.requests_issued == 2
    assert result.transport.failed_requests == 1


@pytest.mark.asyncio
async def test_price_and_stock_updates_use_separate_documented_endpoints_and_auth():
    FakeAsyncClient.responses = [FakeResponse(200, {"ok": True}), FakeResponse(204)]

    results = await connector().update_products(
        [
            ChannelProductUpdate(
                channel_id="technolife:main",
                identifiers=ChannelIdentifierSet(external_product_id="ITEM-1"),
                price=1250000,
                stock_quantity=4,
                currency="IRR",
                price_unit="RIAL",
            )
        ]
    )

    assert results[0].success is True
    price_request, stock_request = FakeAsyncClient.requests
    assert price_request["url"].endswith("/v1/pricing/ITEM-1/info")
    assert price_request["json"] == {"cash": {"price": 1250000}}
    assert stock_request["url"].endswith("/v1/products/ITEM-1/info")
    assert stock_request["json"] == {"available": 4}
    for request in FakeAsyncClient.requests:
        assert request["headers"]["Authorization"] == "Bearer api-key"
        assert request["headers"]["encrypted-secret"].count(":") == 2
