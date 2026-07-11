from __future__ import annotations

import os
from datetime import datetime

import pytest

os.environ.setdefault("FLOWHUB_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FLOWHUB_JWT_SECRET", "test-order-sync-jwt-secret-32bytes!")

from app.flowhub.auth import models as _auth_models  # noqa: F401
from app.flowhub.channels.contracts import (
    ChannelIdentifierSet,
    ChannelOrder,
    ChannelOrderEvent,
    ChannelOrderItem,
    CursorPagination,
    PaginatedResult,
)
from app.flowhub.integration_platform import models as _integration_models  # noqa: F401
from app.flowhub.orders import models as _order_models
from app.flowhub.webhooks import models as _webhook_models  # noqa: F401


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


class FakeSnappConnector:
    def __init__(self) -> None:
        self.calls: list[str | None] = []
        self.acknowledged: list[str | None] = []
        self.pages = {
            None: PaginatedResult(
                items=[
                    ChannelOrderEvent(
                        channel_id="snapp:1",
                        connector_type="snappshop",
                        event_id="event-new",
                        event_type="NEW_ORDER",
                        occurred_at="2026-07-11T10:00:00Z",
                        order_identifiers=ChannelIdentifierSet(order_number="S-100"),
                        raw={"event_id": "event-new", "event_type": "NEW_ORDER", "order_number": "S-100"},
                    ),
                    ChannelOrderEvent(
                        channel_id="snapp:1",
                        connector_type="snappshop",
                        event_id="event-cancel",
                        event_type="CANCELLATION",
                        occurred_at="2026-07-11T10:05:00Z",
                        order_identifiers=ChannelIdentifierSet(order_number="S-100"),
                        raw={"event_id": "event-cancel", "event_type": "CANCELLATION", "order_number": "S-100"},
                    ),
                ],
                pagination=CursorPagination(cursor=None, next_cursor="cursor-2", has_more=True, limit=50),
            ),
            "cursor-2": PaginatedResult(
                items=[
                    ChannelOrderEvent(
                        channel_id="snapp:1",
                        connector_type="snappshop",
                        event_id="event-status",
                        event_type="CHANGE_STATUS",
                        occurred_at="2026-07-11T10:10:00Z",
                        order_identifiers=ChannelIdentifierSet(order_number="S-100"),
                        raw={"event_id": "event-status", "event_type": "CHANGE_STATUS", "order_number": "S-100"},
                    )
                ],
                pagination=CursorPagination(cursor="cursor-2", next_cursor="cursor-3", has_more=False, limit=50),
            ),
            "cursor-3": PaginatedResult(
                items=[],
                pagination=CursorPagination(cursor="cursor-3", next_cursor="cursor-3", has_more=False, limit=50),
            ),
        }

    async def list_order_events(self, pagination):
        cursor = pagination.cursor if isinstance(pagination, CursorPagination) else None
        self.calls.append(cursor)
        return self.pages[cursor]

    def acknowledge_order_events(self, page):
        self.acknowledged.append(page.pagination.next_cursor)

    async def get_order(self, identifiers):
        order_number = identifiers["order_number"]
        return ChannelOrder(
            channel_id="snapp:1",
            connector_type="snappshop",
            identifiers=ChannelIdentifierSet(order_number=order_number),
            status="NEW_ORDER",
            created_at="2026-07-11T09:59:00Z",
            updated_at="2026-07-11T10:10:00Z",
            items=[
                ChannelOrderItem(
                    identifiers=ChannelIdentifierSet(
                        sku="SKU-1",
                        external_product_id="vpi-1",
                        product_number="P-1",
                        parent_product_number="PP-1",
                    ),
                    name="Snapp product",
                    quantity=2,
                    unit_price=1200,
                    currency="IRR",
                    raw={
                        "vendor_product_info_id": "vpi-1",
                        "sku": "SKU-1",
                        "product_number": "P-1",
                        "parent_product_number": "PP-1",
                        "quantity": 2,
                        "canceled_quantity": 1,
                        "deliverable_quantity": 1,
                        "final_price": 1200,
                        "item_status": "partial_cancel",
                    },
                )
            ],
            total=2400,
            currency="IRR",
            raw={"order_number": order_number, "status": "NEW_ORDER", "final_price": 2400, "customer": {"phone": None}},
        )


class FakeTapsiConnector:
    def __init__(self, status: str = "1") -> None:
        self.status = status

    async def get_order(self, identifiers):
        order_id = identifiers["id"]
        return ChannelOrder(
            channel_id="tapsi:1",
            connector_type="tapsishop",
            identifiers=ChannelIdentifierSet(external_product_id=order_id, order_number="T-200"),
            status=self.status,
            created_at="2026-07-11T11:00:00Z",
            updated_at="2026-07-11T11:01:00Z",
            items=[
                ChannelOrderItem(
                    identifiers=ChannelIdentifierSet(external_product_id="tap-prod-1", channel_reference_code="tap-item-1"),
                    name="No SKU product",
                    quantity=3,
                    unit_price=9000,
                    currency="IRR",
                    raw={"orderItemId": "tap-item-1", "productId": "tap-prod-1", "quantity": 3, "finalPrice": 9000},
                )
            ],
            total=27000,
            currency="IRR",
            raw={"order": {"id": order_id, "orderNumber": "T-200", "status": self.status}, "customer": {"phone": None, "nationalId": None}},
        )

    async def list_orders(self, pagination):
        return PaginatedResult(
            items=[await self.get_order({"id": "T-200"})],
            pagination=pagination,
        )


@pytest.mark.asyncio
async def test_snappshop_events_cursor_resume_duplicate_and_inventory_effects(db):
    from app.flowhub.orders.service import OrderSyncService

    connector = FakeSnappConnector()
    service = OrderSyncService(db)

    result = await service.sync_snappshop_events("snapp:1", connector)
    first_acknowledged = list(connector.acknowledged)
    repeat = await service.sync_snappshop_events("snapp:1", connector)

    assert result.processed == 3
    assert result.cursor == "cursor-3"
    assert first_acknowledged == ["cursor-2", "cursor-3"]
    assert repeat.processed == 0
    assert connector.calls[-1] == "cursor-3"
    assert db.query(_order_models.ChannelOrderRecord).filter_by(channel_id="snapp:1").count() == 1
    effects = db.query(_order_models.ChannelInventoryEffectRecord).filter_by(channel_id="snapp:1").all()
    assert len(effects) == 2
    assert {effect.effect_type for effect in effects} == {"purchase", "cancellation"}
    assert all(effect.applied_to_canonical_inventory is False for effect in effects)


@pytest.mark.asyncio
async def test_tapsishop_purchase_and_cancellation_webhooks_are_idempotent(db):
    from app.flowhub.orders.service import OrderSyncService

    _receipt(db, "req-purchase", 1)
    _receipt(db, "req-cancel", 2)
    service = OrderSyncService(db)

    result = await service.process_tapsishop_webhook_receipts("tapsi:1", FakeTapsiConnector())
    duplicate = await service.process_tapsishop_webhook_receipts("tapsi:1", FakeTapsiConnector())

    assert result.processed == 2
    assert duplicate.processed == 0
    order = db.query(_order_models.ChannelOrderRecord).filter_by(channel_id="tapsi:1", provider_order_id="T-200").one()
    assert order.order_number == "T-200"
    assert order.customer_reference is None
    effects = db.query(_order_models.ChannelInventoryEffectRecord).filter_by(channel_id="tapsi:1").all()
    assert len(effects) == 2
    assert sorted(effect.quantity_delta for effect in effects) == [-3.0, 3.0]
    assert db.query(_order_models.ChannelOrderItemRecord).filter_by(order_id=order.internal_id).one().sku is None


@pytest.mark.asyncio
async def test_out_of_order_events_do_not_overwrite_newer_order_state(db):
    from app.flowhub.orders.service import OrderSyncService

    service = OrderSyncService(db)
    newer = _order("snapp:late", "S-LATE", "DELIVERED", "2026-07-11T12:00:00Z")
    older = _order("snapp:late", "S-LATE", "CANCELLED", "2026-07-11T09:00:00Z")

    service.upsert_order(newer, source="snappshop_poll", source_event_id="newer", event_type="CHANGE_STATUS")
    service.upsert_order(older, source="snappshop_poll", source_event_id="older", event_type="CANCELLATION")

    row = db.query(_order_models.ChannelOrderRecord).filter_by(channel_id="snapp:late", provider_order_id="S-LATE").one()
    assert row.provider_status == "DELIVERED"
    assert db.query(_order_models.OrderSyncAuditRecord).filter_by(event_name="order_out_of_order_event_ignored").count() == 1


@pytest.mark.asyncio
async def test_overlapping_snappshop_scheduler_run_is_rejected(db):
    from fastapi import HTTPException
    from app.flowhub.orders.models import OrderSyncCheckpoint
    from app.flowhub.orders.service import OrderSyncService

    db.add(OrderSyncCheckpoint(
        channel_id="snapp:1",
        connector_type="snappshop",
        source="snappshop_events",
        cursor=None,
        locked_at=datetime.utcnow(),
        lock_owner="worker-1",
    ))
    db.commit()

    with pytest.raises(HTTPException) as exc:
        await OrderSyncService(db).sync_snappshop_events("snapp:1", FakeSnappConnector())
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_reconciliation_repairs_missing_order(db):
    from app.flowhub.orders.service import OrderSyncService

    result = await OrderSyncService(db).reconcile_recent_orders("tapsi:1", FakeTapsiConnector(status="3"))

    assert result.processed == 1
    row = db.query(_order_models.ChannelOrderRecord).filter_by(channel_id="tapsi:1", provider_order_id="T-200").one()
    assert row.normalized_status == "fulfilled"
    assert db.query(_order_models.OrderSyncAuditRecord).filter_by(event_name="order_reconciliation_repair").count() == 1


def test_orders_api_lists_and_details_without_customer_national_id(client_with_order):
    client, headers = client_with_order

    listing = client.get("/api/v2/orders", headers=headers)
    detail = client.get("/api/v2/orders/1", headers=headers)

    assert listing.status_code == 200
    assert listing.json()["items"][0]["orderNumber"] == "S-API"
    assert detail.status_code == 200
    assert detail.json()["items"][0]["sku"] == "SKU-API"
    assert "national" not in detail.text.lower()


@pytest.fixture()
def client_with_order(db_engine):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app.flowhub.app import app
    from app.flowhub.auth.jwt_service import create_access_token
    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.auth.password import hash_password
    from app.flowhub.database import get_db
    from app.flowhub.orders.service import OrderSyncService

    Session = sessionmaker(bind=db_engine)

    def override_get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    with Session() as seed:
        user = FlowHubUser(username="orders_admin", hashed_password=hash_password("password123"), role="admin")
        seed.add(user)
        seed.commit()
        seed.refresh(user)
        OrderSyncService(seed).upsert_order(_order("snapp:api", "S-API", "NEW_ORDER", "2026-07-11T12:00:00Z", sku="SKU-API"), source="test")
        headers = {"Authorization": f"Bearer {create_access_token(user.id, user.username, user.role)}"}

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c, headers
    app.dependency_overrides.clear()


def _order(channel_id: str, order_number: str, status: str, updated: str, *, sku: str | None = "SKU-1") -> ChannelOrder:
    return ChannelOrder(
        channel_id=channel_id,
        connector_type="snappshop",
        identifiers=ChannelIdentifierSet(order_number=order_number),
        status=status,
        created_at="2026-07-11T08:00:00Z",
        updated_at=updated,
        items=[
            ChannelOrderItem(
                identifiers=ChannelIdentifierSet(sku=sku, external_product_id="product-1"),
                name="Product",
                quantity=1,
                unit_price=100,
                currency="IRR",
                raw={"id": "item-1", "sku": sku, "quantity": 1, "final_price": 100},
            )
        ],
        total=100,
        currency="IRR",
        raw={"order_number": order_number, "status": status, "customer": {"nationalId": None}},
    )


def _receipt(db, request_id: str, change_type: int) -> None:
    db.add(_webhook_models.WebhookReceipt(
        channel_id="tapsi:1",
        provider="tapsishop",
        provider_event_id=request_id,
        payload_hash=request_id.ljust(64, "0")[:64],
        payload_summary_json={"requestId": request_id, "orderId": "T-200", "changeType": change_type, "itemCount": 1},
        normalized_event_json={
            "requestId": request_id,
            "orderId": "T-200",
            "changeType": change_type,
            "changeTypeLabel": "deducted_due_to_purchase" if change_type == 1 else "added_due_to_cancellation",
            "occurredAt": "2026-07-11T11:01:00Z",
            "orderDetail": {"orderId": "T-200", "orderNumber": "T-200", "status": str(change_type)},
            "items": [{"orderItemId": "tap-item-1", "productId": "tap-prod-1", "sku": None, "quantity": 3, "price": 9000}],
        },
        acknowledged_at=datetime.utcnow(),
        processing_state="queued",
    ))
    db.commit()
