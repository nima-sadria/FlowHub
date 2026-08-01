from __future__ import annotations

import os

import pytest

os.environ.setdefault("FLOWHUB_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FLOWHUB_JWT_SECRET", "test-marketplace-product-sync-secret-32bytes!")

from app.flowhub.channels.contracts import (  # noqa: E402
    ChannelIdentifierSet,
    ChannelProduct,
    ConnectorError,
    ConnectorErrorCategory,
    PageNumberPagination,
    PaginatedResult,
    RetryMetadata,
)
from app.flowhub.channels.marketplace_product_sync import (  # noqa: E402
    MarketplaceProductSyncService,
)
from app.flowhub.channels.tapsishop import TapsiShopConnectorError  # noqa: E402
from app.flowhub.data_layer.models import DlInventoryCache, DlProductCache  # noqa: E402


@pytest.fixture()
def db():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.flowhub.database import FlowHubBase, _get_engine

    _get_engine.cache_clear()
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    FlowHubBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    FlowHubBase.metadata.drop_all(engine)
    engine.dispose()
    _get_engine.cache_clear()


class FakeProductConnector:
    channel_id = "tapsishop:main"
    connector_type = "tapsishop"

    def __init__(self, responses):
        self.responses = list(responses)
        self.pages: list[int] = []

    async def list_products(self, pagination: PageNumberPagination) -> PaginatedResult:
        self.pages.append(pagination.page)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.mark.asyncio
async def test_paginated_marketplace_sync_atomically_caches_normalized_products(db):
    connector = FakeProductConnector(
        [
            _page(1, 2, [_product("tap-1", "SKU-1", "HS-1", 120000, 3)]),
            _page(2, 2, [_product("tap-2", "SKU-2", "HS-2", 240000, 0)]),
        ]
    )

    result = await MarketplaceProductSyncService(db).run(
        connector,
        actor="owner",
        page_size=100,
        max_pages=10,
        retry_attempts=0,
        page_delay_seconds=0,
    )

    assert result.failures == []
    assert result.pages_read == 2
    assert result.products_stored == 2
    assert connector.pages == [1, 2]
    rows = db.query(DlProductCache).order_by(DlProductCache.product_id).all()
    assert [(row.product_id, row.sku, row.price, row.stock_qty) for row in rows] == [
        ("tap-1", "SKU-1", "120000", 3),
        ("tap-2", "SKU-2", "240000", 0),
    ]
    assert rows[0].raw_data["product_number"] == "HS-1"
    assert rows[0].raw_data["currency"] == "IRR"
    assert rows[0].raw_data["price_unit"] == "rial"
    inventory = db.query(DlInventoryCache).order_by(DlInventoryCache.product_id).all()
    assert [(row.product_id, row.stock_status) for row in inventory] == [
        ("tap-1", "instock"),
        ("tap-2", "outofstock"),
    ]


@pytest.mark.asyncio
async def test_failed_later_page_preserves_last_known_complete_cache(db):
    db.add(
        DlProductCache(
            connector_id="tapsishop:main",
            product_id="old-product",
            sku="OLD",
            price="100",
            stock_qty=1,
            channel_id="tapsishop:main",
            freshness="fresh",
            exists=True,
        )
    )
    db.commit()
    connector = FakeProductConnector(
        [
            _page(1, 2, [_product("tap-1", "SKU-1", "HS-1", 120000, 3)]),
            _connector_error(ConnectorErrorCategory.AUTHENTICATION),
        ]
    )

    result = await MarketplaceProductSyncService(db).run(
        connector,
        actor="owner",
        page_size=100,
        max_pages=10,
        retry_attempts=2,
        page_delay_seconds=0,
    )

    assert result.failures == ["mock authentication"]
    assert result.products_stored == 0
    assert connector.pages == [1, 2]
    assert db.query(DlProductCache).filter_by(
        connector_id="tapsishop:main",
        product_id="old-product",
    ).count() == 1


@pytest.mark.asyncio
async def test_safe_transient_read_retries_are_bounded(db, monkeypatch):
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(
        "app.flowhub.channels.marketplace_product_sync.asyncio.sleep",
        fake_sleep,
    )
    connector = FakeProductConnector(
        [
            _connector_error(ConnectorErrorCategory.RATE_LIMIT, retry_after=2),
            _page(1, 1, [_product("tap-1", "SKU-1", "HS-1", 120000, 3)]),
        ]
    )

    result = await MarketplaceProductSyncService(db).run(
        connector,
        actor="owner",
        page_size=100,
        max_pages=10,
        retry_attempts=1,
        page_delay_seconds=0,
    )

    assert result.failures == []
    assert connector.pages == [1, 1]
    assert delays == [2.0]


def _page(
    page: int,
    total_pages: int,
    items: list[ChannelProduct],
) -> PaginatedResult:
    has_more = page < total_pages
    return PaginatedResult(
        items=items,
        pagination=PageNumberPagination(
            page=page,
            page_size=100,
            total=len(items) * total_pages,
            total_pages=total_pages,
            has_more=has_more,
            next_page=page + 1 if has_more else None,
        ),
    )


def _product(
    external_id: str,
    sku: str,
    hsin: str,
    price: int,
    stock: int,
) -> ChannelProduct:
    return ChannelProduct(
        channel_id="tapsishop:main",
        connector_type="tapsishop",
        identifiers=ChannelIdentifierSet(
            external_product_id=external_id,
            sku=sku,
            product_number=hsin,
        ),
        name=sku,
        current_price=price,
        currency="IRR",
        price_unit="rial",
        stock_quantity=stock,
        raw={"id": external_id, "sku": sku, "hsin": hsin},
    )


def _connector_error(
    category: ConnectorErrorCategory,
    *,
    retry_after: float | None = None,
) -> TapsiShopConnectorError:
    return TapsiShopConnectorError(
        ConnectorError(
            category=category,
            message=f"mock {category.value}",
            connector_type="tapsishop",
            channel_id="tapsishop:main",
            retry=RetryMetadata(
                retryable=category
                in {
                    ConnectorErrorCategory.RATE_LIMIT,
                    ConnectorErrorCategory.TIMEOUT,
                    ConnectorErrorCategory.UPSTREAM_UNAVAILABLE,
                },
                retry_after_seconds=retry_after,
                safe_to_retry=True,
            ),
        )
    )
