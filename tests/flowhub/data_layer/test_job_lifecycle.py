from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.flowhub.database import FlowHubBase
from app.flowhub.data_layer.job_lifecycle import (
    RefreshJobAlreadyRunning,
    RefreshJobLifecycle,
    utcnow,
)
from app.flowhub.data_layer.models import DlProductCache, DlRefreshJob
from app.flowhub.integration_platform.models import IntegrationConnectorEvent


def _job(status: str = "pending") -> DlRefreshJob:
    return DlRefreshJob(
        job_type="manual", entity_type="products", connector_id="woocommerce:primary",
        status=status, meta={"strategy": "initial_full_read", "products_stored": 1452}, created_at=utcnow(),
    )


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    FlowHubBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def test_fresh_lease_remains_running(db):
    job = _job()
    db.add(job); db.commit()
    lifecycle = RefreshJobLifecycle(db)
    lifecycle.start(job)
    assert RefreshJobLifecycle(db).recover_expired(now=utcnow()) == []
    assert db.get(DlRefreshJob, job.id).status == "running"


def test_expired_lease_becomes_recoverable_failure_without_deleting_rows(db):
    job = _job("running")
    job.started_at = utcnow() - timedelta(hours=2)
    job.heartbeat_at = job.started_at
    job.lease_expires_at = utcnow() - timedelta(seconds=1)
    db.add(job)
    db.add(DlProductCache(connector_id="woocommerce:primary", product_id="1452", exists=True))
    db.commit()

    recovered = RefreshJobLifecycle(db).recover_expired()

    assert [item.id for item in recovered] == [job.id]
    row = db.get(DlRefreshJob, job.id)
    assert row.status == "failed"
    assert row.recovery_reason == "execution_lease_expired"
    assert row.lease_expires_at is None
    assert db.query(DlProductCache).filter_by(connector_id="woocommerce:primary").count() == 1
    event = db.query(IntegrationConnectorEvent).one()
    assert event.event_name == "job_recovery_marked"
    assert event.metadata_json["provider_io_retried"] is False


def test_legacy_running_job_without_lease_is_recovered_after_its_policy_window(db):
    job = _job("running")
    job.started_at = utcnow() - timedelta(hours=2)
    db.add(job)
    db.commit()

    recovered = RefreshJobLifecycle(db).recover_expired()

    assert [item.id for item in recovered] == [job.id]
    assert db.get(DlRefreshJob, job.id).recovery_reason == "execution_lease_expired"


def test_active_lease_blocks_a_second_running_job_for_the_same_channel(db):
    active = _job()
    db.add(active)
    db.commit()
    RefreshJobLifecycle(db).start(active)

    contender = _job()
    db.add(contender)
    db.commit()

    with pytest.raises(RefreshJobAlreadyRunning):
        RefreshJobLifecycle(db).start(contender)

    row = db.get(DlRefreshJob, contender.id)
    assert row.status == "cancelled"
    assert "already owns this channel" in row.error_message


def test_completion_releases_the_lease_and_allows_a_new_job(db):
    first = _job()
    db.add(first)
    db.commit()
    lifecycle = RefreshJobLifecycle(db)
    lifecycle.start(first)
    lifecycle.finish(first)

    retry = _job()
    db.add(retry)
    db.commit()
    lifecycle.start(retry)

    assert db.get(DlRefreshJob, first.id).lease_expires_at is None
    assert db.get(DlRefreshJob, retry.id).status == "running"


@pytest.mark.asyncio
async def test_runner_recovers_abandoned_leases_on_every_tick_not_only_at_startup():
    """A dead owner must not hold a channel hostage for its whole lease window.

    `products:initial_full_read` leases for 1,800s. Recovering only at process
    start meant that after an owner died mid-refresh, every subsequent
    evaluator tick for up to 30 minutes hit `RefreshJobAlreadyRunning` against
    a job nothing was executing -- which is how a healthy WooCommerce store
    produced a continuous stream of "upstream" refresh failures.
    """

    from app.flowhub.orders.runner import OrderSyncRunner, OrderSyncRunnerSettings

    engine = create_engine("sqlite:///:memory:")
    FlowHubBase.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    stale_started = utcnow() - timedelta(hours=2)
    with session_factory() as db:
        db.add(
            DlRefreshJob(
                job_type="scheduled",
                entity_type="products",
                connector_id="woocommerce:primary",
                status="running",
                created_at=stale_started,
                started_at=stale_started,
                heartbeat_at=stale_started,
                # Lease already elapsed; the owning process is gone.
                lease_expires_at=stale_started + timedelta(minutes=30),
                meta={"strategy": "initial_full_read"},
            )
        )
        db.commit()

    settings = OrderSyncRunnerSettings(
        enabled=False,
        loop_interval_seconds=30,
        polling_interval_seconds=300,
        reconciliation_interval_seconds=900,
        lease_seconds=900,
        snappshop_max_pages=1,
        reconciliation_page_size=10,
        tapsishop_webhook_batch_size=10,
        operation_timeout_seconds=60,
        scheduled_diagnostics_enabled=False,
    )
    runner = OrderSyncRunner(session_factory, settings=settings)

    # One ordinary loop tick -- no restart involved.
    await runner.run_once()

    with session_factory() as db:
        recovered = db.query(DlRefreshJob).one()
        assert recovered.status == "failed"
        assert recovered.recovery_reason == "execution_lease_expired"
        assert recovered.lease_expires_at is None

    engine.dispose()


def test_startup_recovery_skips_a_pre_037_refresh_table() -> None:
    from app.flowhub.app import _has_refresh_lifecycle_schema

    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE dl_refresh_jobs (id INTEGER PRIMARY KEY, status VARCHAR(20) NOT NULL)"
        )

    assert _has_refresh_lifecycle_schema(engine) is False
