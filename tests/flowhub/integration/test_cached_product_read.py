from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.flowhub.data_layer.models import DlProductCache
from app.flowhub.database import FlowHubBase
from app.flowhub.integration_platform.service import IntegrationPlatformService
from app.flowhub.setup.service import AppConfigService


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    FlowHubBase.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()
    FlowHubBase.metadata.drop_all(engine)
    engine.dispose()


def _cached_product() -> DlProductCache:
    return DlProductCache(
        connector_id="woocommerce:primary",
        product_id="101",
        external_id=101,
        sku="SKU-101",
        name="Cached product",
        product_type="simple",
        regular_price="100",
        stock_qty=5,
        stock_status="instock",
        freshness="fresh",
        last_fetched_at=datetime.utcnow(),
        exists=True,
    )


def _configure_woocommerce(db: Session) -> None:
    config = AppConfigService(db)
    config.set("woocommerce.url", "https://shop.example.test")
    config.set("woocommerce.key", "consumer-key")
    config.set("woocommerce.secret", "consumer-secret")


def test_cached_products_do_not_depend_on_optional_connector_bootstrap(db, monkeypatch):
    db.add(_cached_product())
    db.commit()
    _configure_woocommerce(db)
    service = IntegrationPlatformService(db)

    def forbidden_bootstrap() -> None:
        raise AssertionError("cache reads must not run connector bootstrap")

    monkeypatch.setattr(service, "bootstrap_from_app_config", forbidden_bootstrap)

    result = service.list_products(page=1, page_size=50)

    assert result.total == 1
    assert result.configured is True
    assert result.items[0].productId == "101"


def test_product_configuration_is_independent_of_filtered_cache_count(db):
    db.add(_cached_product())
    db.commit()
    _configure_woocommerce(db)

    result = IntegrationPlatformService(db).list_products(search="does-not-match")

    assert result.total == 0
    assert result.configured is True


def test_cached_rows_do_not_fabricate_connector_configuration(db):
    db.add(_cached_product())
    db.commit()

    result = IntegrationPlatformService(db).list_products()

    assert result.total == 1
    assert result.configured is False


def test_cached_product_database_failures_are_not_swallowed(db, monkeypatch):
    service = IntegrationPlatformService(db)

    def broken_query(*_args, **_kwargs):
        raise RuntimeError("database query failed")

    monkeypatch.setattr(db, "query", broken_query)

    with pytest.raises(RuntimeError, match="database query failed"):
        service.list_products(page=1, page_size=50)
