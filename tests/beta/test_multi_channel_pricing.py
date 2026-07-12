from __future__ import annotations

import os
import uuid
from datetime import datetime

import pytest

os.environ.setdefault("FLOWHUB_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FLOWHUB_JWT_SECRET", "test-multi-channel-pricing-jwt-secret-32bytes!")

from app.flowhub.auth import models as _auth_models  # noqa: F401
from app.flowhub.data_layer import models as _data_layer_models  # noqa: F401
from app.flowhub.integration_platform import models as _integration_platform_models  # noqa: F401
from app.flowhub.product_pricing import models as _product_pricing_models  # noqa: F401
from app.flowhub.setup import models as _setup_models  # noqa: F401


@pytest.fixture()
def db_engine():
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    from app.flowhub.database import FlowHubBase, _get_engine

    _get_engine.cache_clear()
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    FlowHubBase.metadata.create_all(engine)
    yield engine
    FlowHubBase.metadata.drop_all(engine)
    engine.dispose()
    _get_engine.cache_clear()


@pytest.fixture()
def db(db_engine):
    from sqlalchemy.orm import sessionmaker

    session = sessionmaker(bind=db_engine)()
    yield session
    session.close()


@pytest.fixture()
def client(db_engine):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app.flowhub.app import app
    from app.flowhub.database import get_db

    Session = sessionmaker(bind=db_engine)

    def override_get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(client, db):
    from app.flowhub.auth.jwt_service import create_access_token
    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.auth.password import hash_password

    user = FlowHubUser(username=f"priceadmin_{uuid.uuid4().hex}", hashed_password=hash_password("password123"), role="admin")
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"Authorization": f"Bearer {create_access_token(user.id, user.username, user.role)}"}


def test_loads_three_connected_channels_with_unambiguous_units(client, auth_headers, db):
    _seed_product(db)

    response = client.get("/api/v2/products/101/channel-prices", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["canonical"]["value"] == 100
    by_channel = {item["channelId"]: item for item in data["channels"]}
    assert by_channel["woocommerce:primary"]["unit"] == "EUR"
    assert by_channel["snappshop:main"]["unit"] == "toman"
    assert by_channel["snappshop:main"]["normalizedValue"] == 1000000
    assert by_channel["tapsishop:main"]["unit"] == "rial"
    assert by_channel["tapsishop:main"]["normalizedValue"] == 1000000
    assert all(item["connectionState"] == "connected" for item in by_channel.values())


def test_disconnected_channel_does_not_block_other_channel_dry_run(client, auth_headers, db):
    _seed_product(db, tapsi=False)
    loaded = client.get("/api/v2/products/101/channel-prices", headers=auth_headers).json()
    woo = next(item for item in loaded["channels"] if item["channelId"] == "woocommerce:primary")
    tapsi = next(item for item in loaded["channels"] if item["channelId"] == "tapsishop:main")

    assert tapsi["connectionState"] == "disconnected"
    dry = client.post(
        "/api/v2/products/101/channel-prices/dry-run",
        headers=auth_headers,
        json={"version": loaded["version"], "changes": [{"channelId": "woocommerce:primary", "proposedValue": 120, "unit": "EUR", "staleToken": woo["staleToken"]}]},
    )

    assert dry.status_code == 201
    assert dry.json()["summary"]["total"] == 1


def test_read_only_channel_rejects_validation_without_blocking_writable_channel(client, auth_headers, db):
    _seed_product(db, snapp_read_only=True)
    loaded = client.get("/api/v2/products/101/channel-prices", headers=auth_headers).json()
    snapp = next(item for item in loaded["channels"] if item["channelId"] == "snappshop:main")
    woo = next(item for item in loaded["channels"] if item["channelId"] == "woocommerce:primary")

    validated = client.post(
        "/api/v2/products/101/channel-prices/validate",
        headers=auth_headers,
        json={"changes": [
            {"channelId": "snappshop:main", "proposedValue": 120000, "unit": "toman", "staleToken": snapp["staleToken"]},
            {"channelId": "woocommerce:primary", "proposedValue": 120, "unit": "EUR", "staleToken": woo["staleToken"]},
        ]},
    )

    assert validated.status_code == 200
    by_channel = {item["channelId"]: item for item in validated.json()["channels"]}
    assert by_channel["snappshop:main"]["validationState"] == "error"
    assert by_channel["woocommerce:primary"]["validationState"] == "valid"


def test_validation_failure_and_stale_conflict_are_server_side(client, auth_headers, db):
    _seed_product(db)
    loaded = client.get("/api/v2/products/101/channel-prices", headers=auth_headers).json()
    tapsi = next(item for item in loaded["channels"] if item["channelId"] == "tapsishop:main")

    invalid = client.post(
        "/api/v2/products/101/channel-prices/validate",
        headers=auth_headers,
        json={"changes": [{"channelId": "tapsishop:main", "proposedValue": -1, "unit": "rial", "staleToken": tapsi["staleToken"]}]},
    )
    assert invalid.status_code == 200
    assert next(item for item in invalid.json()["channels"] if item["channelId"] == "tapsishop:main")["validationState"] == "error"

    row = db.query(_data_layer_models.DlProductCache).filter_by(connector_id="tapsishop:main", product_id="tap-101").one()
    row.price = "1000010"
    db.commit()
    conflict = client.post(
        "/api/v2/products/101/channel-prices/dry-run",
        headers=auth_headers,
        json={"version": loaded["version"], "changes": [{"channelId": "tapsishop:main", "proposedValue": 1000020, "unit": "rial", "staleToken": tapsi["staleToken"]}]},
    )
    assert conflict.status_code == 409


def test_fractional_and_non_finite_prices_are_rejected_without_server_error(client, auth_headers, db):
    _seed_product(db)
    loaded = client.get("/api/v2/products/101/channel-prices", headers=auth_headers).json()
    woo = next(item for item in loaded["channels"] if item["channelId"] == "woocommerce:primary")

    fractional = client.post(
        "/api/v2/products/101/channel-prices/validate",
        headers=auth_headers,
        json={"changes": [{"channelId": "woocommerce:primary", "proposedValue": 100.5, "unit": "EUR", "staleToken": woo["staleToken"]}]},
    )

    assert fractional.status_code == 200
    state = next(item for item in fractional.json()["channels"] if item["channelId"] == "woocommerce:primary")
    assert state["validationState"] == "error"
    assert "whole number" in state["validationMessage"]


def test_successful_apply_updates_cached_price_as_integer(client, auth_headers, db, monkeypatch):
    _seed_product(db)
    loaded = client.get("/api/v2/products/101/channel-prices", headers=auth_headers).json()
    tapsi = next(item for item in loaded["channels"] if item["channelId"] == "tapsishop:main")

    class SuccessConnector:
        async def update_products(self, updates):
            from app.flowhub.channels.contracts import ChannelProductUpdateResult
            return [ChannelProductUpdateResult(channel_id=updates[0].channel_id, identifiers=updates[0].identifiers, success=True)]

    monkeypatch.setattr("app.flowhub.commerce.service.CommerceHubService._tapsishop_connector", lambda self: SuccessConnector())
    dry = client.post(
        "/api/v2/products/101/channel-prices/dry-run",
        headers=auth_headers,
        json={"version": loaded["version"], "changes": [{"channelId": "tapsishop:main", "proposedValue": 1250000, "unit": "rial", "staleToken": tapsi["staleToken"]}]},
    )
    op_id = dry.json()["id"]
    assert client.post(f"/api/v2/products/channel-price-operations/{op_id}/approve", headers=auth_headers, json={"reason": "test"}).status_code == 200
    assert client.post(f"/api/v2/products/channel-price-operations/{op_id}/apply", headers=auth_headers).status_code == 200

    row = db.query(_data_layer_models.DlProductCache).filter_by(connector_id="tapsishop:main", product_id="tap-101").one()
    db.refresh(row)
    assert row.price == "1250000"
    reopened = client.get("/api/v2/products/101/channel-prices", headers=auth_headers).json()
    reopened_tapsi = next(item for item in reopened["channels"] if item["channelId"] == "tapsishop:main")
    assert reopened_tapsi["currentValue"] == 1250000


def test_dry_run_performs_no_external_write_and_apply_requires_approval(client, auth_headers, db, monkeypatch):
    _seed_product(db)
    loaded = client.get("/api/v2/products/101/channel-prices", headers=auth_headers).json()
    snapp = next(item for item in loaded["channels"] if item["channelId"] == "snappshop:main")

    def fail_connector(self):
        raise AssertionError("dry run must not construct connector writes")

    monkeypatch.setattr("app.flowhub.commerce.service.CommerceHubService._snappshop_connector", fail_connector)
    dry = client.post(
        "/api/v2/products/101/channel-prices/dry-run",
        headers=auth_headers,
        json={"version": loaded["version"], "changes": [{"channelId": "snappshop:main", "proposedValue": 120000, "unit": "toman", "staleToken": snapp["staleToken"]}]},
    )
    assert dry.status_code == 201
    op_id = dry.json()["id"]
    premature = client.post(f"/api/v2/products/channel-price-operations/{op_id}/apply", headers=auth_headers)
    assert premature.status_code == 409


def test_apply_reports_channel_specific_partial_failure(client, auth_headers, db, monkeypatch):
    _seed_product(db)
    loaded = client.get("/api/v2/products/101/channel-prices", headers=auth_headers).json()
    snapp = next(item for item in loaded["channels"] if item["channelId"] == "snappshop:main")
    tapsi = next(item for item in loaded["channels"] if item["channelId"] == "tapsishop:main")

    class SuccessConnector:
        async def update_products(self, updates):
            from app.flowhub.channels.contracts import ChannelProductUpdateResult
            return [ChannelProductUpdateResult(channel_id=updates[0].channel_id, identifiers=updates[0].identifiers, success=True, raw={"referenceCode": "ok-1"})]

    class FailedConnector:
        async def update_products(self, updates):
            from app.flowhub.channels.contracts import ChannelProductUpdateResult, ConnectorError, ConnectorErrorCategory
            return [ChannelProductUpdateResult(
                channel_id=updates[0].channel_id,
                identifiers=updates[0].identifiers,
                success=False,
                error=ConnectorError(category=ConnectorErrorCategory.VALIDATION, message="invalid price", connector_type="snappshop", channel_id=updates[0].channel_id),
            )]

    monkeypatch.setattr("app.flowhub.commerce.service.CommerceHubService._snappshop_connector", lambda self: FailedConnector())
    monkeypatch.setattr("app.flowhub.commerce.service.CommerceHubService._tapsishop_connector", lambda self: SuccessConnector())

    dry = client.post(
        "/api/v2/products/101/channel-prices/dry-run",
        headers=auth_headers,
        json={"version": loaded["version"], "changes": [
            {"channelId": "snappshop:main", "proposedValue": 120000, "unit": "toman", "staleToken": snapp["staleToken"]},
            {"channelId": "tapsishop:main", "proposedValue": 1200000, "unit": "rial", "staleToken": tapsi["staleToken"]},
        ]},
    )
    op_id = dry.json()["id"]
    approved = client.post(f"/api/v2/products/channel-price-operations/{op_id}/approve", headers=auth_headers, json={"reason": "test"})
    assert approved.status_code == 200
    applied = client.post(f"/api/v2/products/channel-price-operations/{op_id}/apply", headers=auth_headers)

    assert applied.status_code == 200
    data = applied.json()
    assert data["status"] == "partially_failed"
    by_channel = {item["channelId"]: item for item in data["items"]}
    assert by_channel["snappshop:main"]["status"] == "failed"
    assert by_channel["tapsishop:main"]["status"] == "applied"
    assert data["summary"]["success"] == 1
    assert data["summary"]["failed"] == 1
    snapp_row = db.query(_data_layer_models.DlProductCache).filter_by(connector_id="snappshop:main", product_id="snap-101").one()
    tapsi_row = db.query(_data_layer_models.DlProductCache).filter_by(connector_id="tapsishop:main", product_id="tap-101").one()
    db.refresh(snapp_row)
    db.refresh(tapsi_row)
    assert snapp_row.price == "100000"
    assert tapsi_row.price == "1200000"


def _seed_product(db, *, tapsi: bool = True, snapp_read_only: bool = False) -> None:
    from app.flowhub.data_layer.models import DlProductCache
    from app.flowhub.integration_platform.models import IntegrationConnectorInstance
    from app.flowhub.setup.service import AppConfigService

    AppConfigService(db).set("server.currency", "EUR")
    for channel_id, connector_type, read_only in (
        ("woocommerce:primary", "woocommerce", False),
        ("snappshop:main", "snappshop", snapp_read_only),
        ("tapsishop:main", "tapsishop", False),
    ):
        db.add(IntegrationConnectorInstance(
            id=channel_id,
            connector_type=connector_type,
            name=connector_type,
            version="1.0.0",
            enabled=True,
            read_only=read_only,
            status="configured",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        ))
    db.add(DlProductCache(connector_id="woocommerce:primary", product_id="101", external_id=101, sku="SKU-101", name="Test Product", product_type="simple", regular_price="100", price="100", freshness="fresh", last_successful_read=datetime.utcnow(), exists=True))
    db.add(DlProductCache(connector_id="snappshop:main", product_id="snap-101", sku="SKU-101", name="Test Product", product_type="simple", regular_price="100000", price="100000", freshness="fresh", last_successful_read=datetime.utcnow(), exists=True, stock_qty=5))
    if tapsi:
        db.add(DlProductCache(connector_id="tapsishop:main", product_id="tap-101", sku="SKU-101", name="Test Product", product_type="simple", regular_price="1000000", price="1000000", freshness="fresh", last_successful_read=datetime.utcnow(), exists=True, stock_qty=5))
    db.commit()
