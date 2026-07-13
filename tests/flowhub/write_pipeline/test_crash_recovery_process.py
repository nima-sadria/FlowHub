"""Hard-process recovery coverage for the provider-neutral execution engine.

The provider used here is deliberately a local PostgreSQL-backed fake.  The
worker is terminated with ``os._exit`` at the crash points; a normal exception
would not exercise durable recovery.
"""

from __future__ import annotations

import asyncio
import multiprocessing
import os
import uuid
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.flowhub.database import FlowHubBase
from app.flowhub.write_pipeline.models import WriteBatch, WriteItem
from app.flowhub.write_pipeline.workspace_contracts import WorkspaceWriteResult, WriteOutcome

pytestmark = pytest.mark.postgres


def _worker_engine(url: str, schema: str):
    return create_engine(
        url,
        connect_args={"options": f"-csearch_path={schema}"},
        pool_pre_ping=True,
    )


def _counter(engine, column: str) -> int:
    with engine.begin() as connection:
        return int(connection.execute(sa.text(f"SELECT {column} FROM fake_provider_counter WHERE id=1")).scalar_one())


def _crash_worker(url: str, schema: str, batch_id: str, mode: str) -> None:
    """Execute one worker and terminate at a deterministic provider boundary."""
    os.environ["DATABASE_URL"] = url
    os.environ["FLOWHUB_DATABASE_URL"] = url
    engine = _worker_engine(url, schema)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    db = SessionLocal()

    import app.flowhub.write_pipeline.service as pipeline_module
    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.write_pipeline.service import WritePipelineService

    class FakeLimiter:
        async def acquire(self, *args, **kwargs):
            return None

    class FakeConnector:
        def capabilities(self):
            return SimpleNamespace(channel_id="woocommerce:primary")

        async def apply_updates(self, updates, *, requested_by):
            if mode == "pre_dispatch":
                os._exit(17)
            with engine.begin() as connection:
                connection.execute(sa.text("UPDATE fake_provider_counter SET writes=writes+1 WHERE id=1"))
            if mode == "provider_commit":
                os._exit(18)
            return [
                WorkspaceWriteResult(
                    listing_id=update.listing_id,
                    outcome=WriteOutcome.VERIFIED_APPLIED,
                    provider_accepted=True,
                    response={"provider": "fake", "listing_id": update.listing_id},
                )
                for update in updates
            ]

        async def verify_updates(self, updates, *, requested_by):
            outcome = (
                WriteOutcome.VERIFIED_APPLIED
                if mode == "provider_commit"
                else WriteOutcome.RECONCILIATION_REQUIRED
            )
            return [
                WorkspaceWriteResult(
                    listing_id=update.listing_id,
                    outcome=outcome,
                    provider_accepted=outcome is WriteOutcome.VERIFIED_APPLIED,
                    response={"provider": "fake", "listing_id": update.listing_id},
                    error_category=None if outcome is WriteOutcome.VERIFIED_APPLIED else "uncertain_pre_dispatch",
                )
                for update in updates
            ]

    class FakeFactory:
        def __init__(self, *args, **kwargs):
            self.connector = FakeConnector()

        def get(self, channel_id):
            return self.connector

        def get_product_pricing(self, channel_id):
            return self.connector

    pipeline_module.RateLimitService = FakeLimiter
    # execute_workspace imports the factory lazily from this module.
    import app.flowhub.unified_workspace.connectors as connectors_module

    connectors_module.WorkspaceConnectorFactory = FakeFactory
    service = WritePipelineService(db)
    service._assert_batch_hash_matches = lambda batch: None
    service._assert_channel_write_enabled = lambda batch: None
    service._adapter_for = lambda *args, **kwargs: SimpleNamespace(
        get_capabilities=lambda: SimpleNamespace(channel_type="fake")
    )
    user = db.query(FlowHubUser).first()
    assert user is not None
    try:
        asyncio.run(service.execute(batch_id, user))
    except SystemExit:
        raise
    finally:
        db.close()
        engine.dispose()


@pytest.fixture()
def postgres_recovery_db():
    url = os.environ.get("FLOWHUB_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("FLOWHUB_TEST_POSTGRES_URL is not configured")
    admin_engine = create_engine(url, pool_pre_ping=True)
    schema = f"crash_test_{uuid.uuid4().hex}"
    with admin_engine.begin() as connection:
        database_name = str(connection.execute(sa.text("SELECT current_database()")).scalar_one())
        if "test" not in database_name.lower():
            pytest.fail("Crash recovery tests require an isolated PostgreSQL test database")
        connection.execute(sa.schema.CreateSchema(schema))
    engine = _worker_engine(url, schema)
    # Importing all model modules registers the complete metadata graph.
    import app.flowhub.auth.models  # noqa: F401
    import app.flowhub.integration_platform.models  # noqa: F401
    import app.flowhub.rate_limit.models  # noqa: F401
    import app.flowhub.setup.models  # noqa: F401
    import app.flowhub.unified_workspace.models  # noqa: F401
    import app.flowhub.write_pipeline.models  # noqa: F401
    FlowHubBase.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE fake_provider_counter (id INTEGER PRIMARY KEY, writes INTEGER NOT NULL, verifications INTEGER NOT NULL)"))
        connection.execute(sa.text("INSERT INTO fake_provider_counter(id,writes,verifications) VALUES (1,0,0)"))
    try:
        yield url, schema, engine
    finally:
        engine.dispose()
        with admin_engine.begin() as connection:
            connection.execute(sa.schema.DropSchema(schema, cascade=True))
        admin_engine.dispose()


def _seed_batch(engine) -> str:
    from app.flowhub.auth.models import FlowHubUser

    db = sessionmaker(bind=engine, expire_on_commit=False)()
    user = FlowHubUser(username=f"crash_{uuid.uuid4().hex}", hashed_password="test", role="admin")
    batch_id = f"crash-batch-{uuid.uuid4().hex}"
    batch = WriteBatch(
        id=batch_id,
        channel_id="woocommerce:primary",
        channel_type="woocommerce",
        operation_type="price_update",
        status="approved",
        batch_hash="a" * 64,
        item_count=1,
        currency="EUR",
        created_by=user.username,
        approved_by=user.username,
        approval_reason="isolated crash test",
        safety_summary_json={},
    )
    batch.items.append(
        WriteItem(
            channel_product_id="101",
            sku="SKU-101",
            product_name="Crash fixture",
            current_price=100.0,
            proposed_price=110.0,
            delta_amount=10.0,
            delta_percent=10.0,
            currency="EUR",
            pre_write_snapshot_json={"item_type": "simple", "source_fingerprint": "fixture"},
            status="pending",
        )
    )
    db.add(user)
    db.add(batch)
    db.commit()
    db.close()
    return batch_id


def _resume(url: str, schema: str, batch_id: str, mode: str) -> None:
    process = multiprocessing.get_context("spawn").Process(
        target=_crash_worker,
        args=(url, schema, batch_id, mode),
    )
    process.start()
    process.join(45)
    assert process.exitcode == 0, f"recovery worker exited with {process.exitcode}"


def test_hard_process_provider_commit_recovers_without_duplicate_write(postgres_recovery_db):
    url, schema, engine = postgres_recovery_db
    batch_id = _seed_batch(engine)
    crashed = multiprocessing.get_context("spawn").Process(
        target=_crash_worker, args=(url, schema, batch_id, "provider_commit")
    )
    crashed.start()
    crashed.join(45)
    assert crashed.exitcode in {17, 18}
    assert _counter(engine, "writes") == 1
    _resume(url, schema, batch_id, "provider_commit")
    assert _counter(engine, "writes") == 1
    with engine.begin() as connection:
        assert connection.execute(sa.text("SELECT status FROM flowhub_write_batches WHERE id=:id"), {"id": batch_id}).scalar_one() == "applied"


def test_hard_process_before_dispatch_is_recoverable_without_provider_write(postgres_recovery_db):
    url, schema, engine = postgres_recovery_db
    batch_id = _seed_batch(engine)
    crashed = multiprocessing.get_context("spawn").Process(
        target=_crash_worker, args=(url, schema, batch_id, "pre_dispatch")
    )
    crashed.start()
    crashed.join(45)
    assert crashed.exitcode == 17
    assert _counter(engine, "writes") == 0
    _resume(url, schema, batch_id, "pre_dispatch")
    assert _counter(engine, "writes") == 0
    with engine.begin() as connection:
        status = connection.execute(sa.text("SELECT status FROM flowhub_write_batches WHERE id=:id"), {"id": batch_id}).scalar_one()
        assert status == "reconciliation_required"
