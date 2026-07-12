from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.flowhub.channels.contracts import (
    ChannelIdentifierSet,
    ChannelProduct,
    ChannelVendor,
    ConnectorError,
    ConnectorErrorCategory,
    PageNumberPagination,
    PaginatedResult,
    RetryMetadata,
)
from app.flowhub.channels.snappshop import SnappShopConfig, SnappShopConnectorError
from app.flowhub.channels.snappshop_product_sync import SnappShopProductSyncService
from app.flowhub.commerce.service import CommerceHubService
from app.flowhub.data_layer.models import DlInventoryCache, DlProductCache, DlRefreshJob
from app.flowhub.database import FlowHubBase
from app.flowhub.integration_platform.service import IntegrationPlatformService
from app.flowhub.integration_platform.models import IntegrationConnectorEvent, IntegrationConnectorInstance
from app.flowhub.setup.models import FlowHubAppConfig


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    FlowHubBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    FlowHubBase.metadata.drop_all(engine)
    engine.dispose()


class FakeConnector:
    channel_id = "snappshop:main"

    def __init__(self, pages):
        self.config = SimpleNamespace(vendor_id="vendor-1")
        self.pages = list(pages)
        self.requested_pages: list[int] = []

    async def list_products(self, pagination):
        self.requested_pages.append(pagination.page)
        response = self.pages.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def product(product_id: str, *, sku: str, title: str, stock: int, price: int) -> ChannelProduct:
    return ChannelProduct(
        channel_id="snappshop:main",
        connector_type="snappshop",
        identifiers=ChannelIdentifierSet(
            external_product_id=product_id,
            sku=sku,
            product_number=f"number-{product_id}",
            parent_product_number=None,
        ),
        name=title,
        current_price=float(price),
        currency="IRR",
        price_unit="toman",
        stock_quantity=float(stock),
        status="active",
        raw={
            "id": product_id,
            "sku": sku,
            "product_number": f"number-{product_id}",
            "active": True,
            "capacity": 5,
            "stock": stock,
            "warehouse_stock": stock + 2,
            "title": title,
            "title_en": f"{title} EN",
            "thumbnail": f"https://images.example/{product_id}.jpg",
            "price": price,
            "warranty": "Vendor warranty",
            "discount": {"special_price": price - 100},
            "variation_attributes": [{"name": "Color", "value": "Black"}],
        },
    )


def page(items, *, number: int, total_pages: int, next_page: int | None = None):
    return PaginatedResult(
        items=items,
        pagination=PageNumberPagination(
            page=number,
            page_size=20,
            total=None,
            total_pages=total_pages,
            has_more=number < total_pages,
            next_page=next_page,
        ),
    )


@pytest.mark.asyncio
async def test_multi_page_sync_replaces_cache_atomically_and_products_filter_reads_it(db):
    db.add(DlProductCache(connector_id="snappshop:main", product_id="old", name="Old", exists=True))
    db.commit()
    connector = FakeConnector([
        page([product("p1", sku="SKU-1", title="Product 1", stock=4, price=1000)], number=1, total_pages=2, next_page=2),
        page([product("p2", sku="SKU-2", title="Product 2", stock=0, price=2000)], number=2, total_pages=2),
    ])

    result = await SnappShopProductSyncService(db).run(
        connector, actor="admin", max_pages=10, retry_attempts=0, page_delay_seconds=0
    )

    assert result.failures == []
    assert result.pages_read == 2
    assert result.products_received == 2
    assert result.products_stored == 2
    assert connector.requested_pages == [1, 2]
    assert {row.product_id for row in db.query(DlProductCache).all()} == {"p1", "p2"}
    assert db.query(DlInventoryCache).filter_by(connector_id="snappshop:main").count() == 2
    p1 = db.query(DlProductCache).filter_by(product_id="p1").one()
    assert p1.channel_id == "snappshop:main"
    assert p1.raw_data["vendor_id"] == "vendor-1"
    assert p1.raw_data["warehouse_stock"] == 6
    assert p1.sale_price == "900"
    listed = IntegrationPlatformService(db).list_products(connector_id="snappshop:main")
    assert listed.total == 2
    assert {item.connectorId for item in listed.items} == {"snappshop:main"}
    assert {item.currency for item in listed.items} == {"TMN"}


@pytest.mark.asyncio
async def test_partial_page_failure_preserves_previous_cache(db):
    db.add(DlProductCache(connector_id="snappshop:main", product_id="old", name="Old", exists=True))
    db.commit()
    error = SnappShopConnectorError(
        ConnectorError(
            category=ConnectorErrorCategory.AUTHENTICATION,
            message="SnappShop authentication failed.",
            connector_type="snappshop",
            channel_id="snappshop:main",
            http_status=401,
            retry=RetryMetadata(retryable=False, safe_to_retry=False),
        )
    )
    connector = FakeConnector([
        page([product("p1", sku="SKU-1", title="Product 1", stock=4, price=1000)], number=1, total_pages=2, next_page=2),
        error,
    ])

    result = await SnappShopProductSyncService(db).run(
        connector, actor="admin", max_pages=10, retry_attempts=2, page_delay_seconds=0
    )

    assert result.failures == ["SnappShop authentication failed."]
    assert result.pages_read == 1
    assert result.products_received == 1
    assert result.products_stored == 0
    assert connector.requested_pages == [1, 2]
    assert [row.product_id for row in db.query(DlProductCache).all()] == ["old"]
    latest = db.query(DlRefreshJob).order_by(DlRefreshJob.id.desc()).first()
    assert latest.status == "failed"
    assert latest.meta["error_category"] == "authentication"


@pytest.mark.asyncio
async def test_product_sync_paces_pages_below_upstream_rate_limit(db, monkeypatch):
    delays: list[float] = []

    async def record_sleep(seconds: float) -> None:
        delays.append(seconds)

    monkeypatch.setattr("app.flowhub.channels.snappshop_product_sync.asyncio.sleep", record_sleep)
    connector = FakeConnector([
        page([product("p1", sku="SKU-1", title="Product 1", stock=4, price=1000)], number=1, total_pages=2, next_page=2),
        page([product("p2", sku="SKU-2", title="Product 2", stock=2, price=2000)], number=2, total_pages=2),
    ])

    result = await SnappShopProductSyncService(db).run(
        connector,
        actor="admin",
        max_pages=10,
        retry_attempts=0,
        page_delay_seconds=1.1,
    )

    assert result.failures == []
    assert delays == [1.1]


@pytest.mark.asyncio
async def test_rate_limit_without_retry_after_uses_bounded_read_backoff(db, monkeypatch):
    delays: list[float] = []

    async def record_sleep(seconds: float) -> None:
        delays.append(seconds)

    monkeypatch.setattr("app.flowhub.channels.snappshop_product_sync.asyncio.sleep", record_sleep)
    rate_limit = SnappShopConnectorError(
        ConnectorError(
            category=ConnectorErrorCategory.RATE_LIMIT,
            message="SnappShop rate limit was reached.",
            connector_type="snappshop",
            channel_id="snappshop:main",
            http_status=429,
            retry=RetryMetadata(retryable=True, retry_after_seconds=None, safe_to_retry=False),
        )
    )
    connector = FakeConnector([
        rate_limit,
        page([product("p1", sku="SKU-1", title="Product 1", stock=4, price=1000)], number=1, total_pages=1),
    ])

    result = await SnappShopProductSyncService(db).run(
        connector,
        actor="admin",
        max_pages=10,
        retry_attempts=1,
        page_delay_seconds=0,
        rate_limit_backoff_seconds=30,
    )

    assert result.failures == []
    assert delays == [30]


def test_snappshop_defaults_and_integer_timeout_contract():
    config = SnappShopConfig.from_values(
        settings={"agent_identifier": "agent"},
        secrets={"token": "secret"},
    )
    assert config.base_url == "https://apix.snappshop.ir/automation/v1"
    assert config.agent_header_name == "User-Agent"
    assert config.timeout_seconds == 30

    assert SnappShopConfig.from_values(
        settings={"agent_identifier": "agent", "request_timeout": 29},
        secrets={"token": "secret"},
    ).timeout_seconds == 29
    with pytest.raises(ValueError, match="integer between 1 and 120"):
        SnappShopConfig.from_values(
            settings={"agent_identifier": "agent", "request_timeout": 29.1},
            secrets={"token": "secret"},
        )


class FakeVendorConnector:
    def __init__(self, vendors=None, error: Exception | None = None):
        self.vendors = vendors or []
        self.error = error

    async def list_vendors(self):
        if self.error:
            raise self.error
        return self.vendors


def vendor(vendor_id: str, *, status: str = "ACTIVE") -> ChannelVendor:
    return ChannelVendor(
        channel_id="snappshop:main",
        connector_type="snappshop",
        vendor_id=vendor_id,
        name=f"Vendor {vendor_id}",
        metadata={"status": status, "title": f"Vendor {vendor_id}", "title_en": None},
    )


def configuration_body(vendor_id: str) -> dict:
    return {
        "display_name": "SnappShop",
        "enabled": True,
        "access_mode": "read_only",
        "settings": {
            "agent_identifier": "flowhub-agent",
            "vendor_id": vendor_id,
            "request_timeout": 30,
        },
        "secrets": {"token": "write-only-secret"},
    }


@pytest.mark.asyncio
async def test_vendor_discovery_failure_persists_no_partial_configuration(db, monkeypatch):
    error = SnappShopConnectorError(
        ConnectorError(
            category=ConnectorErrorCategory.AUTHENTICATION,
            message="SnappShop authentication failed.",
            connector_type="snappshop",
            channel_id="snappshop:main",
            http_status=401,
        )
    )
    service = CommerceHubService(db)
    monkeypatch.setattr(service, "_snappshop_connector", lambda body=None: FakeVendorConnector(error=error))

    with pytest.raises(Exception) as exc:
        await service.update_channel_settings(
            "snappshop:main",
            configuration_body("vendor-1"),
            actor="admin",
        )

    assert getattr(exc.value, "status_code", None) == 422
    db.expire_all()
    assert db.get(FlowHubAppConfig, "snappshop.token") is None
    assert db.get(IntegrationConnectorInstance, "snappshop:main") is None
    assert db.query(IntegrationConnectorEvent).filter_by(connector_id="snappshop:main").count() == 0


@pytest.mark.asyncio
async def test_selected_active_vendor_is_persisted_and_marks_configuration_complete(db, monkeypatch):
    service = CommerceHubService(db)
    monkeypatch.setattr(service, "_snappshop_connector", lambda body=None: FakeVendorConnector([vendor("vendor-1")]))

    result = await service.update_channel_settings(
        "snappshop:main",
        configuration_body("vendor-1"),
        actor="admin",
    )

    assert result["channel_id"] == "snappshop:main"
    assert db.get(FlowHubAppConfig, "snappshop.vendor_id").value == "vendor-1"
    assert db.get(FlowHubAppConfig, "snappshop.request_timeout").value == "30"
    configuration = service.get_channel_configuration("snappshop:main")
    assert configuration["configured"] is True
    assert configuration["settings"]["vendor_id"] == "vendor-1"
    assert configuration["settings"]["request_timeout"] == 30
    assert configuration["credentials_returned"] is False
    audit = db.query(IntegrationConnectorEvent).filter_by(
        connector_id="snappshop:main",
        event_name="channel_configuration_changed",
    ).one()
    assert "write-only-secret" not in str(audit.metadata_json)


@pytest.mark.asyncio
async def test_inactive_vendor_cannot_be_saved(db, monkeypatch):
    service = CommerceHubService(db)
    monkeypatch.setattr(
        service,
        "_snappshop_connector",
        lambda body=None: FakeVendorConnector([vendor("vendor-1", status="INACTIVE")]),
    )

    with pytest.raises(Exception) as exc:
        await service.update_channel_settings(
            "snappshop:main",
            configuration_body("vendor-1"),
            actor="admin",
        )

    assert getattr(exc.value, "status_code", None) == 422
    assert db.get(FlowHubAppConfig, "snappshop.token") is None
