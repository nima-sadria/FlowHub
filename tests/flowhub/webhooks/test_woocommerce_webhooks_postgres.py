"""Postgres concurrency coverage for WooCommerce webhook ingestion.

SQLite's StaticPool test setup serializes all sessions onto one connection,
so it cannot exercise a genuine race on the
(channel_id, provider, provider_event_id) unique constraint the way a real
Postgres backend can. This module targets exactly that race: two concurrent
deliveries of the *same* WooCommerce webhook (same X-WC-Webhook-ID +
X-WC-Webhook-Delivery-ID) must resolve to exactly one durable receipt, with
the loser hitting the IntegrityError-race fallback in
WebhookIngestionService.accept_woocommerce_event and returning the winner's
receipt as a duplicate — never raising, never double-writing.

Mirrors the schema-per-test-module / TRUNCATE-per-test pattern in
tests/flowhub/orders/test_order_sync_postgres.py.
"""

from __future__ import annotations

import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.flowhub.database import FlowHubBase
from app.flowhub.integration_platform.models import IntegrationConnectorInstance
from app.flowhub.webhooks.models import WebhookProviderEventIdentity, WebhookReceipt
from app.flowhub.webhooks.service import WebhookIngestionService

pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def postgres_engine() -> Engine:
    url = os.environ.get("FLOWHUB_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("FLOWHUB_TEST_POSTGRES_URL is not configured")

    admin_engine = sa.create_engine(url, pool_pre_ping=True)
    schema = f"wc_webhook_test_{uuid.uuid4().hex}"
    with admin_engine.begin() as connection:
        database_name = str(connection.execute(sa.text("select current_database()")).scalar_one())
        if "test" not in database_name.lower():
            pytest.fail("FLOWHUB_TEST_POSTGRES_URL must target an isolated database whose name contains 'test'")
        connection.execute(sa.schema.CreateSchema(schema))

    engine = sa.create_engine(
        url,
        connect_args={"options": f"-csearch_path={schema}"},
        pool_pre_ping=True,
    )
    FlowHubBase.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(sa.schema.DropSchema(schema, cascade=True))
        admin_engine.dispose()


@pytest.fixture()
def pg_sessions(postgres_engine: Engine) -> sessionmaker[Session]:
    with postgres_engine.begin() as connection:
        table_names = ", ".join(f'"{table.name}"' for table in FlowHubBase.metadata.sorted_tables)
        connection.execute(sa.text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))
    return sessionmaker(bind=postgres_engine, expire_on_commit=False)


def _seed_channel(db: Session, channel_id: str) -> None:
    from datetime import datetime, timezone

    db.add(IntegrationConnectorInstance(
        id=channel_id,
        connector_type="woocommerce",
        name=channel_id,
        version="1.0.0",
        enabled=True,
        read_only=False,
        status="configured",
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        updated_at=datetime.now(timezone.utc).replace(tzinfo=None),
    ))
    db.commit()


def _payload() -> dict:
    return {"id": 123, "sku": "SKU-1", "status": "publish", "type": "simple"}


def test_concurrent_duplicate_delivery_resolves_to_exactly_one_receipt(pg_sessions):
    with pg_sessions() as db:
        _seed_channel(db, "woocommerce:contended")

    barrier = threading.Barrier(2)
    raw_body = b'{"id": 123, "sku": "SKU-1", "status": "publish", "type": "simple"}'

    def deliver(_: int):
        with pg_sessions() as db:
            barrier.wait(timeout=10)
            service = WebhookIngestionService(db)
            accepted = service.accept_woocommerce_event(
                "woocommerce:contended",
                "product.updated",
                _payload(),
                raw_body,
                webhook_id="wh-race",
                delivery_id="dl-race",
            )
            return accepted.receipt.id, accepted.duplicate

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(deliver, range(2)))

    receipt_ids = {receipt_id for receipt_id, _ in results}
    duplicates = [is_duplicate for _, is_duplicate in results]

    assert len(receipt_ids) == 1, "Concurrent identical deliveries must converge on one receipt id"
    assert duplicates.count(True) == 1, "Exactly one concurrent writer should observe a duplicate"
    assert duplicates.count(False) == 1, "Exactly one concurrent writer should observe the original acceptance"

    with pg_sessions() as db:
        assert db.query(WebhookReceipt).filter_by(
            channel_id="woocommerce:contended", provider="woocommerce", provider_event_id="wh-race:dl-race"
        ).count() == 1
        assert db.query(WebhookProviderEventIdentity).filter_by(
            channel_id="woocommerce:contended", provider="woocommerce", provider_event_id="wh-race:dl-race"
        ).count() == 1


def test_concurrent_deliveries_for_different_channels_are_fully_independent(pg_sessions):
    with pg_sessions() as db:
        _seed_channel(db, "woocommerce:a")
        _seed_channel(db, "woocommerce:b")

    raw_body = b'{"id": 123, "sku": "SKU-1", "status": "publish", "type": "simple"}'
    barrier = threading.Barrier(2)

    def deliver(channel_id: str):
        with pg_sessions() as db:
            barrier.wait(timeout=10)
            service = WebhookIngestionService(db)
            accepted = service.accept_woocommerce_event(
                channel_id,
                "product.updated",
                _payload(),
                raw_body,
                webhook_id="wh-shared",
                delivery_id="dl-shared",
            )
            return channel_id, accepted.duplicate

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(deliver, ("woocommerce:a", "woocommerce:b")))

    assert all(is_duplicate is False for _, is_duplicate in results)
    with pg_sessions() as db:
        assert db.query(WebhookReceipt).filter_by(provider_event_id="wh-shared:dl-shared").count() == 2
