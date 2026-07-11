from __future__ import annotations

import asyncio
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.flowhub.orders.models import OrderSyncCheckpoint
from app.flowhub.orders.service import (
    CHANNEL_LEASE_SOURCE,
    OrderSyncLease,
    OrderSyncLeaseError,
    OrderSyncService,
)


pytestmark = pytest.mark.postgres


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@pytest.fixture(scope="module")
def postgres_engine() -> Engine:
    url = os.environ.get("FLOWHUB_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("FLOWHUB_TEST_POSTGRES_URL is not configured")

    admin_engine = sa.create_engine(url, pool_pre_ping=True)
    schema = f"lease_test_{uuid.uuid4().hex}"
    with admin_engine.begin() as connection:
        database_name = str(connection.execute(sa.text("select current_database()" )).scalar_one())
        if "test" not in database_name.lower():
            pytest.fail("FLOWHUB_TEST_POSTGRES_URL must target an isolated database whose name contains 'test'")
        connection.execute(sa.schema.CreateSchema(schema))

    engine = sa.create_engine(
        url,
        connect_args={"options": f"-csearch_path={schema}"},
        pool_pre_ping=True,
    )
    OrderSyncCheckpoint.__table__.create(engine)
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
        connection.execute(sa.delete(OrderSyncCheckpoint))
    return sessionmaker(bind=postgres_engine, expire_on_commit=False)


def _lease_row(db: Session, channel_id: str) -> OrderSyncCheckpoint:
    return db.query(OrderSyncCheckpoint).filter_by(channel_id=channel_id, source=CHANNEL_LEASE_SOURCE).one()


def _stale_lease(active: OrderSyncLease, owner: str) -> OrderSyncLease:
    return OrderSyncLease(
        checkpoint_id=active.checkpoint_id,
        channel_id=active.channel_id,
        source=active.source,
        owner=owner,
        acquired_at=active.acquired_at,
        expires_at=active.expires_at,
    )


def test_concurrent_acquisition_has_one_winner_and_loser_cannot_advance(pg_sessions):
    barrier = threading.Barrier(2)

    def acquire(owner: str):
        with pg_sessions() as db:
            barrier.wait(timeout=10)
            try:
                lease = OrderSyncService(db).acquire_checkpoint_lease(
                    "snappshop:contended", "snappshop", "snappshop_events", owner=owner
                )
                return owner, lease, None
            except HTTPException as exc:
                return owner, None, exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(acquire, ("worker-a", "worker-b")))

    winners = [result for result in results if result[1] is not None]
    losers = [result for result in results if result[1] is None]
    assert len(winners) == 1
    assert len(losers) == 1
    assert losers[0][2] == 409

    winner_lease = winners[0][1]
    loser_lease = _stale_lease(winner_lease, losers[0][0])

    class ConnectorThatMustNotRun:
        calls = 0

        async def list_order_events(self, pagination):
            self.calls += 1
            raise AssertionError("lease loser reached connector processing")

    connector = ConnectorThatMustNotRun()
    with pg_sessions() as db:
        service = OrderSyncService(db)
        with pytest.raises(HTTPException) as sync_error:
            asyncio.run(service.sync_snappshop_events("snappshop:contended", connector))
        assert sync_error.value.status_code == 409
        assert connector.calls == 0

        with pytest.raises(OrderSyncLeaseError) as heartbeat_error:
            service.heartbeat_checkpoint_lease(loser_lease)
        assert heartbeat_error.value.category == "lease_lost"

        checkpoint = service._ensure_checkpoint("snappshop:contended", "snappshop", "snappshop_events")
        checkpoint.cursor = "loser-cursor"
        with pytest.raises(OrderSyncLeaseError) as commit_error:
            service._commit_checkpoint_progress(checkpoint, loser_lease)
        assert commit_error.value.category == "lease_lost"

    with pg_sessions() as db:
        checkpoint = db.query(OrderSyncCheckpoint).filter_by(
            channel_id="snappshop:contended", source="snappshop_events"
        ).one()
        assert checkpoint.cursor is None
        assert OrderSyncService(db).release_checkpoint_lease(winner_lease) is True


def test_expiry_blocks_heartbeat_and_cursor_then_allows_replacement(pg_sessions):
    with pg_sessions() as db:
        service = OrderSyncService(db)
        old = service.acquire_checkpoint_lease(
            "snappshop:expiry", "snappshop", "snappshop_events", owner="old-owner"
        )
        checkpoint = service._ensure_checkpoint("snappshop:expiry", "snappshop", "snappshop_events")
        checkpoint.cursor = "committed"
        service._commit_checkpoint_progress(checkpoint, old)
        row = _lease_row(db, "snappshop:expiry")
        row.lease_expires_at = _utcnow() - timedelta(seconds=1)
        db.commit()

    with pg_sessions() as db:
        service = OrderSyncService(db)
        with pytest.raises(OrderSyncLeaseError) as heartbeat_error:
            service.heartbeat_checkpoint_lease(old)
        assert heartbeat_error.value.category == "lease_expired"
        expired_at = _lease_row(db, "snappshop:expiry").lease_expires_at

        checkpoint = service._ensure_checkpoint("snappshop:expiry", "snappshop", "snappshop_events")
        checkpoint.cursor = "expired-owner"
        with pytest.raises(OrderSyncLeaseError) as commit_error:
            service._commit_checkpoint_progress(checkpoint, old)
        assert commit_error.value.category == "lease_expired"
        assert _lease_row(db, "snappshop:expiry").lease_expires_at == expired_at

    with pg_sessions() as db:
        replacement = OrderSyncService(db).acquire_checkpoint_lease(
            "snappshop:expiry", "snappshop", "reconciliation", owner="new-owner"
        )

    with pg_sessions() as db:
        stale_service = OrderSyncService(db)
        assert stale_service.release_checkpoint_lease(old) is False
        with pytest.raises(OrderSyncLeaseError) as heartbeat_error:
            stale_service.heartbeat_checkpoint_lease(old)
        assert heartbeat_error.value.category == "lease_lost"
        checkpoint = stale_service._ensure_checkpoint("snappshop:expiry", "snappshop", "snappshop_events")
        checkpoint.cursor = "stale-owner"
        with pytest.raises(OrderSyncLeaseError) as commit_error:
            stale_service._commit_checkpoint_progress(checkpoint, old)
        assert commit_error.value.category == "lease_lost"

    with pg_sessions() as db:
        assert db.query(OrderSyncCheckpoint).filter_by(
            channel_id="snappshop:expiry", source="snappshop_events"
        ).one().cursor == "committed"
        assert _lease_row(db, "snappshop:expiry").lock_owner == "new-owner"
        assert OrderSyncService(db).release_checkpoint_lease(replacement) is True


def test_valid_heartbeat_extends_expiry_and_expired_heartbeat_cannot_revive(pg_sessions):
    with pg_sessions() as db:
        service = OrderSyncService(db)
        lease = service.acquire_checkpoint_lease(
            "tapsishop:heartbeat", "tapsishop", "tapsishop_webhook", owner="worker"
        )
        original_expiry = _lease_row(db, "tapsishop:heartbeat").lease_expires_at
        assert service.heartbeat_checkpoint_lease(lease, lease_seconds=1800) is True
        renewed_expiry = _lease_row(db, "tapsishop:heartbeat").lease_expires_at
        assert renewed_expiry > original_expiry
        row = _lease_row(db, "tapsishop:heartbeat")
        row.lease_expires_at = _utcnow() - timedelta(seconds=1)
        db.commit()
        expired_at = row.lease_expires_at

        with pytest.raises(OrderSyncLeaseError) as exc:
            service.heartbeat_checkpoint_lease(lease, lease_seconds=3600)
        assert exc.value.category == "lease_expired"
        db.expire_all()
        assert _lease_row(db, "tapsishop:heartbeat").lease_expires_at == expired_at


def test_different_channels_acquire_concurrently(pg_sessions):
    barrier = threading.Barrier(2)

    def acquire(channel_id: str):
        with pg_sessions() as db:
            barrier.wait(timeout=10)
            return OrderSyncService(db).acquire_checkpoint_lease(
                channel_id, "snappshop", "snappshop_events", owner=f"owner-{channel_id}"
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        leases = list(pool.map(acquire, ("snappshop:one", "snappshop:two")))

    assert {lease.channel_id for lease in leases} == {"snappshop:one", "snappshop:two"}
    with pg_sessions() as db:
        assert {_lease_row(db, channel).lock_owner for channel in ("snappshop:one", "snappshop:two")} == {
            "owner-snappshop:one",
            "owner-snappshop:two",
        }


def test_failed_contender_rollback_leaves_no_false_lease(pg_sessions):
    with pg_sessions() as holder_db:
        holder = OrderSyncService(holder_db).acquire_checkpoint_lease(
            "snappshop:rollback", "snappshop", "snappshop_events", owner="holder"
        )

    with pg_sessions() as loser_db:
        with pytest.raises(HTTPException):
            OrderSyncService(loser_db).acquire_checkpoint_lease(
                "snappshop:rollback", "snappshop", "reconciliation", owner="loser"
            )
        loser_db.rollback()

    with pg_sessions() as verify_db:
        row = _lease_row(verify_db, "snappshop:rollback")
        assert row.lock_owner == "holder"
        assert OrderSyncService(verify_db).release_checkpoint_lease(holder) is True
