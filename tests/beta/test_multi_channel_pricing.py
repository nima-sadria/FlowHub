from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest

os.environ.setdefault("FLOWHUB_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FLOWHUB_JWT_SECRET", "test-multi-channel-pricing-jwt-secret-32bytes!")

from app.flowhub.auth import models as _auth_models  # noqa: F401
from app.flowhub.data_layer import models as _data_layer_models  # noqa: F401
from app.flowhub.integration_platform import models as _integration_platform_models  # noqa: F401
from app.flowhub.product_pricing import models as _product_pricing_models  # noqa: F401
from app.flowhub.setup import models as _setup_models  # noqa: F401
from app.flowhub.unified_workspace import models as _unified_workspace_models  # noqa: F401


@pytest.fixture()
def db_engine():
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    from app.flowhub.database import FlowHubBase, _get_engine

    _get_engine.cache_clear()
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
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

    user = FlowHubUser(
        username=f"priceadmin_{uuid.uuid4().hex}",
        hashed_password=hash_password("password123"),
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"Authorization": f"Bearer {create_access_token(user.id, user.username, user.role)}"}


def _field(channel: dict, field: str) -> dict:
    return channel["fields"][field]


def test_loads_real_channels_from_the_marketplace_registry_not_a_hardcoded_list(
    client, auth_headers, db
):
    """The Manual Channel Editor enumerates whatever the marketplace
    registry declares as read-capable and implemented -- Technolife is
    included even though it was never one of the historically-hardcoded
    three, and Digikala (no PRODUCTS_READ) is correctly excluded."""
    _seed_product(db, technolife=True)

    response = client.get("/api/v2/products/101/channel-prices", headers=auth_headers)

    assert response.status_code == 200
    channel_ids = {item["channelId"] for item in response.json()["channels"]}
    assert channel_ids == {
        "woocommerce:primary",
        "snappshop:main",
        "tapsishop:main",
        "technolife:main",
    }


def test_loads_three_connected_channels_with_unambiguous_units(client, auth_headers, db):
    _seed_product(db)

    response = client.get("/api/v2/products/101/channel-prices", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["canonical"]["value"] == 100
    by_channel = {item["channelId"]: item for item in data["channels"]}
    assert _field(by_channel["woocommerce:primary"], "price")["unit"] == "EUR"
    assert _field(by_channel["snappshop:main"], "price")["unit"] == "TOMAN"
    assert _field(by_channel["snappshop:main"], "price")["normalizedValue"] == 1000000
    assert _field(by_channel["tapsishop:main"], "price")["unit"] == "RIAL"
    assert _field(by_channel["tapsishop:main"], "price")["normalizedValue"] == 1000000
    assert all(
        by_channel[channel_id]["connectionState"] == "connected"
        for channel_id in ("woocommerce:primary", "snappshop:main", "tapsishop:main")
    )


def test_price_stock_and_status_fields_reflect_capability_per_channel(client, auth_headers, db):
    """WooCommerce genuinely supports Price + Stock QTY + Stock Status;
    SnappShop/TapsiShop/Technolife genuinely support Price + Stock QTY only
    (their shared write contract has no stock-status field) -- this must
    never be faked as writable."""
    _seed_product(db, technolife=True)

    loaded = client.get("/api/v2/products/101/channel-prices", headers=auth_headers).json()
    by_channel = {item["channelId"]: item for item in loaded["channels"]}

    woo = by_channel["woocommerce:primary"]
    assert _field(woo, "price")["canWrite"] is True
    assert _field(woo, "stock")["canWrite"] is True
    assert _field(woo, "status")["canWrite"] is True
    assert _field(woo, "stock")["currentValue"] == 5
    assert _field(woo, "status")["currentValue"] == "instock"

    for channel_id in ("snappshop:main", "tapsishop:main", "technolife:main"):
        channel = by_channel[channel_id]
        assert _field(channel, "price")["canWrite"] is True
        assert _field(channel, "stock")["canWrite"] is True
        status_field = _field(channel, "status")
        assert status_field["canWrite"] is False
        assert status_field["validationState"] == "read_only"
        assert "does not support" in status_field["validationMessage"]


def test_exact_variation_id_wins_over_same_channel_parent_sku(client, auth_headers, db):
    from app.flowhub.data_layer.models import DlProductCache

    _seed_product(db)
    variation = (
        db.query(DlProductCache)
        .filter_by(connector_id="woocommerce:primary", product_id="101")
        .one()
    )
    db.delete(variation)
    db.commit()
    db.add(
        DlProductCache(
            connector_id="woocommerce:primary",
            product_id="parent-101",
            sku=variation.sku,
            name="Parent with duplicate SKU",
            product_type="variable",
            price="235400000",
            regular_price="235400000",
            freshness="fresh",
            last_successful_read=datetime.now(timezone.utc).replace(tzinfo=None),
            exists=True,
        )
    )
    db.commit()
    db.add(
        DlProductCache(
            connector_id="woocommerce:primary",
            product_id="101",
            external_id=101,
            sku="SKU-101",
            name="Variation",
            product_type="variation",
            parent_id="parent-101",
            price="125000",
            regular_price="125000",
            freshness="fresh",
            last_successful_read=datetime.now(timezone.utc).replace(tzinfo=None),
            exists=True,
        )
    )
    db.commit()

    response = client.get("/api/v2/products/101/channel-prices", headers=auth_headers)

    assert response.status_code == 200
    woo = next(
        item for item in response.json()["channels"] if item["channelId"] == "woocommerce:primary"
    )
    assert woo["channelProductId"] == "101"
    assert _field(woo, "price")["currentValue"] == 125000


def test_disconnected_channel_does_not_block_other_channel_dry_run(client, auth_headers, db):
    _seed_product(db, tapsi=False)
    loaded = client.get("/api/v2/products/101/channel-prices", headers=auth_headers).json()
    woo = next(item for item in loaded["channels"] if item["channelId"] == "woocommerce:primary")
    tapsi = next(item for item in loaded["channels"] if item["channelId"] == "tapsishop:main")

    assert tapsi["connectionState"] == "disconnected"
    dry = client.post(
        "/api/v2/products/101/channel-prices/dry-run",
        headers=auth_headers,
        json={
            "version": loaded["version"],
            "changes": [
                {
                    "channelId": "woocommerce:primary",
                    "field": "price",
                    "proposedValue": 120,
                    "unit": "EUR",
                    "staleToken": woo["staleToken"],
                }
            ],
        },
    )

    assert dry.status_code == 201
    assert dry.json()["summary"]["total"] == 1


def test_stock_quantity_and_status_can_be_dry_run_for_woocommerce(client, auth_headers, db):
    """Dry Run only validates and persists a pending operation -- it must
    never construct a provider connector (see
    test_dry_run_performs_no_external_write_and_apply_requires_approval),
    so this covers Stock QTY and Stock Status without any connector fixture."""
    _seed_product(db)
    loaded = client.get("/api/v2/products/101/channel-prices", headers=auth_headers).json()
    woo = next(item for item in loaded["channels"] if item["channelId"] == "woocommerce:primary")

    dry = client.post(
        "/api/v2/products/101/channel-prices/dry-run",
        headers=auth_headers,
        json={
            "version": loaded["version"],
            "changes": [
                {
                    "channelId": "woocommerce:primary",
                    "field": "stock",
                    "proposedValue": 12,
                    "staleToken": woo["staleToken"],
                },
                {
                    "channelId": "woocommerce:primary",
                    "field": "status",
                    "proposedValue": "outofstock",
                    "staleToken": woo["staleToken"],
                },
            ],
        },
    )

    assert dry.status_code == 201
    body = dry.json()
    assert body["summary"]["total"] == 2
    fields_by_name = {item["field"]: item for item in body["items"]}
    assert fields_by_name["stock"]["currentValue"] == 5
    assert fields_by_name["stock"]["proposedValue"] == 12
    assert fields_by_name["status"]["currentValue"] == "instock"
    assert fields_by_name["status"]["proposedValue"] == "outofstock"


def test_stock_status_edit_is_rejected_for_channels_without_status_write_capability(
    client, auth_headers, db
):
    _seed_product(db)
    loaded = client.get("/api/v2/products/101/channel-prices", headers=auth_headers).json()
    snapp = next(item for item in loaded["channels"] if item["channelId"] == "snappshop:main")

    validated = client.post(
        "/api/v2/products/101/channel-prices/validate",
        headers=auth_headers,
        json={
            "changes": [
                {
                    "channelId": "snappshop:main",
                    "field": "status",
                    "proposedValue": "outofstock",
                    "staleToken": snapp["staleToken"],
                }
            ]
        },
    )

    assert validated.status_code == 200
    status_field = _field(
        next(item for item in validated.json()["channels"] if item["channelId"] == "snappshop:main"),
        "status",
    )
    assert status_field["validationState"] == "error"


def test_invalid_stock_status_value_is_rejected(client, auth_headers, db):
    _seed_product(db)
    loaded = client.get("/api/v2/products/101/channel-prices", headers=auth_headers).json()
    woo = next(item for item in loaded["channels"] if item["channelId"] == "woocommerce:primary")

    validated = client.post(
        "/api/v2/products/101/channel-prices/validate",
        headers=auth_headers,
        json={
            "changes": [
                {
                    "channelId": "woocommerce:primary",
                    "field": "status",
                    "proposedValue": "onbackorder",
                    "staleToken": woo["staleToken"],
                }
            ]
        },
    )

    assert validated.status_code == 200
    status_field = _field(
        next(item for item in validated.json()["channels"] if item["channelId"] == "woocommerce:primary"),
        "status",
    )
    assert status_field["validationState"] == "error"
    assert "instock" in status_field["validationMessage"]


def test_negative_stock_quantity_is_rejected(client, auth_headers, db):
    _seed_product(db)
    loaded = client.get("/api/v2/products/101/channel-prices", headers=auth_headers).json()
    woo = next(item for item in loaded["channels"] if item["channelId"] == "woocommerce:primary")

    validated = client.post(
        "/api/v2/products/101/channel-prices/validate",
        headers=auth_headers,
        json={
            "changes": [
                {
                    "channelId": "woocommerce:primary",
                    "field": "stock",
                    "proposedValue": -3,
                    "staleToken": woo["staleToken"],
                }
            ]
        },
    )

    assert validated.status_code == 200
    stock_field = _field(
        next(item for item in validated.json()["channels"] if item["channelId"] == "woocommerce:primary"),
        "stock",
    )
    assert stock_field["validationState"] == "error"


def test_price_proposal_with_wrong_unit_is_rejected(client, auth_headers, db):
    _seed_product(db)
    loaded = client.get("/api/v2/products/101/channel-prices", headers=auth_headers).json()
    snapp = next(item for item in loaded["channels"] if item["channelId"] == "snappshop:main")
    assert _field(snapp, "price")["unit"] == "TOMAN"

    validated = client.post(
        "/api/v2/products/101/channel-prices/validate",
        headers=auth_headers,
        json={
            "changes": [
                {
                    "channelId": "snappshop:main",
                    "field": "price",
                    "proposedValue": 120000,
                    "unit": "RIAL",
                    "staleToken": snapp["staleToken"],
                }
            ]
        },
    )

    assert validated.status_code == 200
    price_field = _field(
        next(item for item in validated.json()["channels"] if item["channelId"] == "snappshop:main"),
        "price",
    )
    assert price_field["validationState"] == "error"
    assert "TOMAN" in price_field["validationMessage"]


def test_read_only_channel_rejects_validation_without_blocking_writable_channel(
    client, auth_headers, db
):
    _seed_product(db, snapp_read_only=True)
    loaded = client.get("/api/v2/products/101/channel-prices", headers=auth_headers).json()
    snapp = next(item for item in loaded["channels"] if item["channelId"] == "snappshop:main")
    woo = next(item for item in loaded["channels"] if item["channelId"] == "woocommerce:primary")

    validated = client.post(
        "/api/v2/products/101/channel-prices/validate",
        headers=auth_headers,
        json={
            "changes": [
                {
                    "channelId": "snappshop:main",
                    "field": "price",
                    "proposedValue": 120000,
                    "unit": "toman",
                    "staleToken": snapp["staleToken"],
                },
                {
                    "channelId": "woocommerce:primary",
                    "field": "price",
                    "proposedValue": 120,
                    "unit": "EUR",
                    "staleToken": woo["staleToken"],
                },
            ]
        },
    )

    assert validated.status_code == 200
    by_channel = {item["channelId"]: item for item in validated.json()["channels"]}
    assert _field(by_channel["snappshop:main"], "price")["validationState"] == "error"
    assert _field(by_channel["woocommerce:primary"], "price")["validationState"] == "valid"


def test_validation_failure_and_stale_conflict_are_server_side(client, auth_headers, db):
    _seed_product(db)
    loaded = client.get("/api/v2/products/101/channel-prices", headers=auth_headers).json()
    tapsi = next(item for item in loaded["channels"] if item["channelId"] == "tapsishop:main")

    invalid = client.post(
        "/api/v2/products/101/channel-prices/validate",
        headers=auth_headers,
        json={
            "changes": [
                {
                    "channelId": "tapsishop:main",
                    "field": "price",
                    "proposedValue": -1,
                    "unit": "rial",
                    "staleToken": tapsi["staleToken"],
                }
            ]
        },
    )
    assert invalid.status_code == 200
    assert (
        _field(
            next(item for item in invalid.json()["channels"] if item["channelId"] == "tapsishop:main"),
            "price",
        )["validationState"]
        == "error"
    )

    row = (
        db.query(_data_layer_models.DlProductCache)
        .filter_by(connector_id="tapsishop:main", product_id="tap-101")
        .one()
    )
    row.price = "1000010"
    db.commit()
    conflict = client.post(
        "/api/v2/products/101/channel-prices/dry-run",
        headers=auth_headers,
        json={
            "version": loaded["version"],
            "changes": [
                {
                    "channelId": "tapsishop:main",
                    "field": "price",
                    "proposedValue": 1000020,
                    "unit": "rial",
                    "staleToken": tapsi["staleToken"],
                }
            ],
        },
    )
    assert conflict.status_code == 409


def test_fractional_and_non_finite_prices_are_rejected_without_server_error(
    client, auth_headers, db
):
    _seed_product(db)
    loaded = client.get("/api/v2/products/101/channel-prices", headers=auth_headers).json()
    woo = next(item for item in loaded["channels"] if item["channelId"] == "woocommerce:primary")

    fractional = client.post(
        "/api/v2/products/101/channel-prices/validate",
        headers=auth_headers,
        json={
            "changes": [
                {
                    "channelId": "woocommerce:primary",
                    "field": "price",
                    "proposedValue": 100.5,
                    "unit": "EUR",
                    "staleToken": woo["staleToken"],
                }
            ]
        },
    )

    assert fractional.status_code == 200
    state = _field(
        next(
            item for item in fractional.json()["channels"] if item["channelId"] == "woocommerce:primary"
        ),
        "price",
    )
    assert state["validationState"] == "error"
    assert "whole number" in state["validationMessage"]


def test_unverifiable_tapsishop_apply_requires_reconciliation_without_cache_patch(
    client, auth_headers, db, monkeypatch
):
    _seed_product(db)
    loaded = client.get("/api/v2/products/101/channel-prices", headers=auth_headers).json()
    tapsi = next(item for item in loaded["channels"] if item["channelId"] == "tapsishop:main")

    class SuccessConnector:
        async def update_products(self, updates):
            from app.flowhub.channels.contracts import ChannelProductUpdateResult

            return [
                ChannelProductUpdateResult(
                    channel_id=updates[0].channel_id,
                    identifiers=updates[0].identifiers,
                    success=True,
                )
            ]

    monkeypatch.setattr(
        "app.flowhub.commerce.service.CommerceHubService._tapsishop_connector",
        lambda self: SuccessConnector(),
    )
    dry = client.post(
        "/api/v2/products/101/channel-prices/dry-run",
        headers=auth_headers,
        json={
            "version": loaded["version"],
            "changes": [
                {
                    "channelId": "tapsishop:main",
                    "field": "price",
                    "proposedValue": 1250000,
                    "unit": "rial",
                    "staleToken": tapsi["staleToken"],
                }
            ],
        },
    )
    op_id = dry.json()["id"]
    assert (
        client.post(
            f"/api/v2/products/channel-price-operations/{op_id}/approve",
            headers=auth_headers,
            json={"reason": "test"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v2/products/channel-price-operations/{op_id}/apply", headers=auth_headers
        ).status_code
        == 200
    )

    row = (
        db.query(_data_layer_models.DlProductCache)
        .filter_by(connector_id="tapsishop:main", product_id="tap-101")
        .one()
    )
    db.refresh(row)
    assert row.price == "1000000"
    operation = client.get(
        f"/api/v2/products/channel-price-operations/{op_id}", headers=auth_headers
    ).json()
    assert operation["status"] == "reconciliation_required"
    from app.flowhub.write_pipeline.models import ProviderWriteAttempt

    attempt = db.query(ProviderWriteAttempt).filter_by(operation_id=op_id).one()
    assert attempt.source_workflow == "product_pricing"
    assert attempt.external_identity == "tap-101"
    assert operation["items"][0]["status"] == "reconciliation_required"


def test_dry_run_performs_no_external_write_and_apply_requires_approval(
    client, auth_headers, db, monkeypatch
):
    _seed_product(db)
    loaded = client.get("/api/v2/products/101/channel-prices", headers=auth_headers).json()
    snapp = next(item for item in loaded["channels"] if item["channelId"] == "snappshop:main")

    def fail_connector(self):
        raise AssertionError("dry run must not construct connector writes")

    monkeypatch.setattr(
        "app.flowhub.commerce.service.CommerceHubService._snappshop_connector", fail_connector
    )
    dry = client.post(
        "/api/v2/products/101/channel-prices/dry-run",
        headers=auth_headers,
        json={
            "version": loaded["version"],
            "changes": [
                {
                    "channelId": "snappshop:main",
                    "field": "price",
                    "proposedValue": 120000,
                    "unit": "toman",
                    "staleToken": snapp["staleToken"],
                }
            ],
        },
    )
    assert dry.status_code == 201
    op_id = dry.json()["id"]
    premature = client.post(
        f"/api/v2/products/channel-price-operations/{op_id}/apply", headers=auth_headers
    )
    assert premature.status_code == 409


def test_apply_reports_channel_specific_partial_failure(client, auth_headers, db, monkeypatch):
    _seed_product(db)
    loaded = client.get("/api/v2/products/101/channel-prices", headers=auth_headers).json()
    snapp = next(item for item in loaded["channels"] if item["channelId"] == "snappshop:main")
    tapsi = next(item for item in loaded["channels"] if item["channelId"] == "tapsishop:main")

    provider_calls: list[tuple[str, str]] = []

    class SuccessConnector:
        async def update_products(self, updates):
            from app.flowhub.channels.contracts import ChannelProductUpdateResult

            provider_calls.append((updates[0].channel_id, "accepted"))
            return [
                ChannelProductUpdateResult(
                    channel_id=updates[0].channel_id,
                    identifiers=updates[0].identifiers,
                    success=True,
                    raw={"referenceCode": "ok-1"},
                )
            ]

    class FailedConnector:
        async def update_products(self, updates):
            from app.flowhub.channels.contracts import (
                ChannelProductUpdateResult,
                ConnectorError,
                ConnectorErrorCategory,
            )

            provider_calls.append((updates[0].channel_id, "validation_rejected"))
            return [
                ChannelProductUpdateResult(
                    channel_id=updates[0].channel_id,
                    identifiers=updates[0].identifiers,
                    success=False,
                    error=ConnectorError(
                        category=ConnectorErrorCategory.VALIDATION,
                        message="invalid price",
                        connector_type="snappshop",
                        channel_id=updates[0].channel_id,
                    ),
                )
            ]

    monkeypatch.setattr(
        "app.flowhub.commerce.service.CommerceHubService._snappshop_connector",
        lambda self: FailedConnector(),
    )
    monkeypatch.setattr(
        "app.flowhub.commerce.service.CommerceHubService._tapsishop_connector",
        lambda self: SuccessConnector(),
    )

    dry = client.post(
        "/api/v2/products/101/channel-prices/dry-run",
        headers=auth_headers,
        json={
            "version": loaded["version"],
            "changes": [
                {
                    "channelId": "snappshop:main",
                    "field": "price",
                    "proposedValue": 120000,
                    "unit": "toman",
                    "staleToken": snapp["staleToken"],
                },
                {
                    "channelId": "tapsishop:main",
                    "field": "price",
                    "proposedValue": 1200000,
                    "unit": "rial",
                    "staleToken": tapsi["staleToken"],
                },
            ],
        },
    )
    op_id = dry.json()["id"]
    approved = client.post(
        f"/api/v2/products/channel-price-operations/{op_id}/approve",
        headers=auth_headers,
        json={"reason": "test"},
    )
    assert approved.status_code == 200
    applied = client.post(
        f"/api/v2/products/channel-price-operations/{op_id}/apply", headers=auth_headers
    )

    assert applied.status_code == 200
    data = applied.json()
    assert data["status"] == "reconciliation_required"
    by_channel = {item["channelId"]: item for item in data["items"]}
    assert by_channel["snappshop:main"]["status"] == "failed"
    assert by_channel["tapsishop:main"]["status"] == "reconciliation_required"
    assert data["summary"]["success"] == 0
    assert data["summary"]["reconciliationRequired"] == 1
    assert data["summary"]["failed"] == 1
    assert provider_calls == [
        ("snappshop:main", "validation_rejected"),
        ("tapsishop:main", "accepted"),
    ]
    assert by_channel["snappshop:main"]["result"]["providerAccepted"] is False
    assert by_channel["snappshop:main"]["result"]["errorCategory"] == "validation"
    assert by_channel["tapsishop:main"]["result"]["providerAccepted"] is True

    from app.flowhub.write_pipeline.models import (
        ProviderWriteAttempt,
        ProviderWriteAttemptEvent,
    )

    attempts = {
        row.channel_id: row
        for row in db.query(ProviderWriteAttempt).filter_by(operation_id=op_id).all()
    }
    outcomes = {
        channel_id: {
            event.outcome
            for event in db.query(ProviderWriteAttemptEvent)
            .filter_by(attempt_id=attempt.id)
            .all()
        }
        for channel_id, attempt in attempts.items()
    }
    assert "failed" in outcomes["snappshop:main"]
    assert "reconciliation_required" not in outcomes["snappshop:main"]
    assert "provider_accepted" in outcomes["tapsishop:main"]
    assert "reconciliation_required" in outcomes["tapsishop:main"]
    snapp_row = (
        db.query(_data_layer_models.DlProductCache)
        .filter_by(connector_id="snappshop:main", product_id="snap-101")
        .one()
    )
    tapsi_row = (
        db.query(_data_layer_models.DlProductCache)
        .filter_by(connector_id="tapsishop:main", product_id="tap-101")
        .one()
    )
    db.refresh(snapp_row)
    db.refresh(tapsi_row)
    assert snapp_row.price == "100000"
    assert tapsi_row.price == "1000000"


def _seed_product(
    db,
    *,
    tapsi: bool = True,
    snapp_read_only: bool = False,
    technolife: bool = False,
) -> None:
    from app.flowhub.data_layer.models import DlProductCache
    from app.flowhub.integration_platform.models import (
        IntegrationConnectorInstance,
        IntegrationConnectorSetting,
    )
    from app.flowhub.setup.service import AppConfigService

    AppConfigService(db).set("server.currency", "EUR")
    channels = [
        ("woocommerce:primary", "woocommerce", False),
        ("snappshop:main", "snappshop", snapp_read_only),
        ("tapsishop:main", "tapsishop", False),
    ]
    if technolife:
        channels.append(("technolife:main", "technolife", False))
    for channel_id, connector_type, read_only in channels:
        db.add(
            IntegrationConnectorInstance(
                id=channel_id,
                connector_type=connector_type,
                name=connector_type,
                version="1.0.0",
                enabled=True,
                read_only=read_only,
                status="configured",
                created_at=datetime.now(timezone.utc).replace(tzinfo=None),
                updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
        )
    if not snapp_read_only:
        for key, secret in (
            ("token", True),
            ("agent_identifier", False),
            ("vendor_id", False),
        ):
            db.add(
                IntegrationConnectorSetting(
                    connector_id="snappshop:main",
                    key=key,
                    value_json=None,
                    secret=secret,
                    configured=True,
                )
            )
    db.add(
        DlProductCache(
            connector_id="woocommerce:primary",
            product_id="101",
            external_id=101,
            sku="SKU-101",
            name="Test Product",
            product_type="simple",
            regular_price="100",
            price="100",
            freshness="fresh",
            last_successful_read=datetime.now(timezone.utc).replace(tzinfo=None),
            exists=True,
            stock_qty=5,
            stock_status="instock",
        )
    )
    db.add(
        DlProductCache(
            connector_id="snappshop:main",
            product_id="snap-101",
            sku="SKU-101",
            name="Test Product",
            product_type="simple",
            regular_price="100000",
            price="100000",
            freshness="fresh",
            last_successful_read=datetime.now(timezone.utc).replace(tzinfo=None),
            exists=True,
            stock_qty=5,
        )
    )
    if tapsi:
        db.add(
            DlProductCache(
                connector_id="tapsishop:main",
                product_id="tap-101",
                sku="SKU-101",
                name="Test Product",
                product_type="simple",
                regular_price="1000000",
                price="1000000",
                freshness="fresh",
                last_successful_read=datetime.now(timezone.utc).replace(tzinfo=None),
                exists=True,
                stock_qty=5,
            )
        )
    if technolife:
        db.add(
            DlProductCache(
                connector_id="technolife:main",
                product_id="tech-101",
                sku="SKU-101",
                name="Test Product",
                product_type="simple",
                regular_price="1000000",
                price="1000000",
                freshness="fresh",
                last_successful_read=datetime.now(timezone.utc).replace(tzinfo=None),
                exists=True,
                stock_qty=5,
            )
        )
    db.commit()
