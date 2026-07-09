from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest

os.environ.setdefault("FLOWHUB_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("FLOWHUB_JWT_SECRET", "test-rate-limiter-jwt-secret-32bytes!")

from app.flowhub.auth import models as _auth_models  # noqa: F401
from app.flowhub.data_layer import models as _data_layer_models  # noqa: F401
from app.flowhub.integration_platform import models as _integration_platform_models  # noqa: F401
from app.flowhub.setup import models as _setup_models  # noqa: F401
from app.flowhub.write_pipeline import models as _write_pipeline_models  # noqa: F401


@pytest.fixture()
def db_engine():
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    from app.flowhub.database import FlowHubBase, _get_engine

    _get_engine.cache_clear()
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    FlowHubBase.metadata.create_all(engine)
    yield engine
    FlowHubBase.metadata.drop_all(engine)
    engine.dispose()
    _get_engine.cache_clear()


@pytest.fixture()
def db(db_engine):
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture()
def client(db_engine):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    from app.flowhub.app import app
    from app.flowhub.database import get_db

    Session = sessionmaker(bind=db_engine)

    def _override_get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(client, db):
    from app.flowhub.auth.jwt_service import create_access_token
    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.auth.password import hash_password

    username = f"rateadmin_{uuid.uuid4().hex}"
    user = FlowHubUser(username=username, hashed_password=hash_password("password123"), role="admin")
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id, user.username, user.role)
    return {"Authorization": f"Bearer {token}"}


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.value

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds


@pytest.mark.asyncio
async def test_read_limiter_enforces_configured_rpm():
    from app.flowhub.rate_limit import AsyncTokenBucket

    clock = FakeClock()
    bucket = AsyncTokenBucket("woocommerce:primary", "read", 60, clock=clock.now, sleeper=clock.sleep)

    first = await bucket.acquire()
    second = await bucket.acquire()

    assert first.delay_seconds == 0
    assert second.delay_seconds == pytest.approx(1.0)
    assert clock.sleeps == [pytest.approx(1.0)]


@pytest.mark.asyncio
async def test_write_limiter_enforces_configured_rpm():
    from app.flowhub.rate_limit import AsyncTokenBucket

    clock = FakeClock()
    bucket = AsyncTokenBucket("woocommerce:primary", "write", 30, clock=clock.now, sleeper=clock.sleep)

    first = await bucket.acquire()
    second = await bucket.acquire()

    assert first.delay_seconds == 0
    assert second.delay_seconds == pytest.approx(2.0)
    assert clock.sleeps == [pytest.approx(2.0)]


@dataclass
class FakeCapabilities:
    supports_modified_since: bool = False
    supports_delta_sync: bool = False
    supports_updated_after: bool = False
    supports_pagination: bool = True
    supports_batch_read: bool = True


class FakeReadAdapter:
    connector_id = "woocommerce:primary"
    connector_type = "woocommerce"

    def __init__(self, pages, capabilities=None, fail_after: int | None = None) -> None:
        self.pages = pages
        self.capabilities = capabilities or FakeCapabilities()
        self.fail_after = fail_after
        self.calls: list[dict] = []

    async def fetch_products(self, *, modified_since=None, cursor=None, product_ids=None):
        from app.flowhub.read_engine.contracts import ReadPage

        self.calls.append({"modified_since": modified_since, "cursor": cursor, "product_ids": product_ids})
        if self.fail_after is not None and len(self.calls) > self.fail_after:
            raise RuntimeError("interrupted")
        index = int(cursor or "0")
        items = self.pages[index]
        next_cursor = str(index + 1) if index + 1 < len(self.pages) else None
        return ReadPage(items=items, next_cursor=next_cursor)

    async def fetch_metadata(self, *, cursor=None):
        from app.flowhub.read_engine.contracts import ReadPage

        return ReadPage(items=[], next_cursor=None, metadata_only=True)


@pytest.mark.asyncio
async def test_initial_sync_reads_all_products(db):
    from app.flowhub.read_engine.service import IncrementalReadEngine

    adapter = FakeReadAdapter([
        [{"id": "101", "sku": "A", "name": "Alpha", "price": "10.00"}],
        [{"id": "102", "sku": "B", "name": "Beta", "price": "20.00"}],
    ])

    progress = await IncrementalReadEngine(db).run_manual(adapter)

    assert progress.status == "completed"
    assert progress.strategy == "initial_full_read"
    assert progress.products_stored == 2
    assert {row.product_id for row in db.query(_data_layer_models.DlProductCache).all()} == {"101", "102"}


def test_incremental_sync_skips_products_without_previous_price(db):
    from app.flowhub.data_layer.models import DlProductCache
    from app.flowhub.read_engine.service import IncrementalReadEngine

    old = (datetime.utcnow() - timedelta(days=400)).isoformat()
    recent = (datetime.utcnow() - timedelta(days=5)).isoformat()
    db.add_all([
        DlProductCache(connector_id="woocommerce:primary", product_id="priced", last_price="9.00", last_modified=old),
        DlProductCache(connector_id="woocommerce:primary", product_id="old-empty", last_price=None, price=None, last_modified=old),
        DlProductCache(connector_id="woocommerce:primary", product_id="recent-empty", last_price=None, price=None, last_modified=recent),
    ])
    db.commit()

    ids = IncrementalReadEngine(db).eligible_cached_product_ids("woocommerce:primary")

    assert "priced" in ids
    assert "recent-empty" in ids
    assert "old-empty" not in ids


@pytest.mark.asyncio
async def test_incremental_sync_prefers_modified_since_when_supported(db):
    from app.flowhub.data_layer.models import DlProductCache
    from app.flowhub.read_engine.service import IncrementalReadEngine

    db.add(DlProductCache(
        connector_id="woocommerce:primary",
        product_id="101",
        last_price="10.00",
        last_successful_read=datetime.utcnow() - timedelta(hours=1),
    ))
    db.commit()
    adapter = FakeReadAdapter(
        [[{"id": "101", "sku": "A", "name": "Alpha", "price": "12.00"}]],
        capabilities=FakeCapabilities(supports_modified_since=True, supports_updated_after=True),
    )

    progress = await IncrementalReadEngine(db).run_manual(adapter)

    assert progress.strategy == "modified_since"
    assert adapter.calls[0]["modified_since"] is not None
    assert adapter.calls[0]["product_ids"] is None


@pytest.mark.asyncio
async def test_resume_works_and_queue_survives_interruption(db):
    from app.flowhub.data_layer.models import DlRefreshJob
    from app.flowhub.read_engine.service import IncrementalReadEngine

    interrupted = FakeReadAdapter(
        [
            [{"id": "101", "sku": "A", "name": "Alpha", "price": "10.00"}],
            [{"id": "102", "sku": "B", "name": "Beta", "price": "20.00"}],
        ],
        fail_after=1,
    )

    with pytest.raises(RuntimeError):
        await IncrementalReadEngine(db).run_manual(interrupted)

    job = db.query(DlRefreshJob).first()
    assert job is not None
    assert job.status == "pending"
    assert job.meta["resumable"] is True
    assert job.meta["queue_survives_interruption"] is True

    resumed = FakeReadAdapter([
        [{"id": "101", "sku": "A", "name": "Alpha", "price": "10.00"}],
        [{"id": "102", "sku": "B", "name": "Beta", "price": "20.00"}],
    ])
    progress = await IncrementalReadEngine(db).run_manual(resumed)

    assert progress.status == "completed"
    assert db.query(DlRefreshJob).first().status == "completed"


def test_rate_limit_settings_endpoint_validation(client, auth_headers):
    response = client.post(
        "/api/v2/settings/rate-limits",
        headers=auth_headers,
        json={"read_requests_per_minute": 120, "write_requests_per_minute": 45},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["read_requests_per_minute"] == 120
    assert data["write_requests_per_minute"] == 45
    assert data["per_connector_override_available"] is False
    assert data["scheduler_started"] is False

    invalid = client.post(
        "/api/v2/settings/rate-limits",
        headers=auth_headers,
        json={"read_requests_per_minute": 0, "write_requests_per_minute": 1001},
    )
    assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_diagnostics_updated_and_no_secret_leakage(client, auth_headers, db):
    from app.flowhub.rate_limit.service import RateLimitService

    service = RateLimitService(db)
    service.update_settings(90, 30, updated_by="test")
    await service.acquire("woocommerce:primary", "read", connector_type="woocommerce")

    response = client.get("/api/v2/diagnostics/status", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["rateLimiter"]["settings"]["read_requests_per_minute"] == 90
    assert data["rateLimiter"]["queue_length"] >= 0
    assert "secret" not in response.text.lower()
    assert "password" not in response.text.lower()
