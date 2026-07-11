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


class MetadataFilterAdapter:
    connector_id = "woocommerce:primary"
    connector_type = "woocommerce"

    def __init__(self) -> None:
        self.capabilities = FakeCapabilities(supports_batch_read=True)
        self.calls: list[tuple[str, dict]] = []

    async def fetch_metadata(self, *, cursor=None):
        from app.flowhub.read_engine.contracts import ReadPage

        self.calls.append(("metadata", {"cursor": cursor}))
        recent = (datetime.utcnow() - timedelta(days=5)).isoformat()
        old = (datetime.utcnow() - timedelta(days=400)).isoformat()
        return ReadPage(
            items=[
                {"product_id": "priced", "last_modified": old},
                {"product_id": "recent-empty", "last_modified": recent},
                {"product_id": "old-empty", "last_modified": old},
            ],
            next_cursor=None,
            metadata_only=True,
        )

    async def fetch_products(self, *, modified_since=None, cursor=None, product_ids=None):
        from app.flowhub.read_engine.contracts import ReadPage

        self.calls.append(("products", {"modified_since": modified_since, "cursor": cursor, "product_ids": product_ids}))
        assert product_ids is not None
        assert set(product_ids) == {"priced", "recent-empty"}
        return ReadPage(
            items=[{"id": item, "sku": item, "name": item, "price": "1.00"} for item in product_ids],
            next_cursor=None,
        )


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


def test_manual_read_service_resolves_real_read_adapters(db):
    from app.connectors.read import NextcloudSpreadsheetReadAdapter, WooCommerceProductReadAdapter
    from app.flowhub.read_engine.manual import ManualReadService
    from app.flowhub.setup.service import AppConfigService

    cfg = AppConfigService(db)
    cfg.set_many(
        {
            "woocommerce.url": "https://store.example.test",
            "woocommerce.key": "ck_test",
            "woocommerce.secret": "cs_test",
            "nextcloud.url": "https://cloud.example.test",
            "nextcloud.username": "user",
            "nextcloud.password": "password",
            "nextcloud.spreadsheet_path": "/prices.xlsx",
        },
        updated_by="test",
    )

    service = ManualReadService(db)

    assert isinstance(service.adapter_for("woocommerce:primary"), WooCommerceProductReadAdapter)
    assert isinstance(service.adapter_for("nextcloud:primary"), NextcloudSpreadsheetReadAdapter)


def test_woocommerce_read_adapter_capabilities_are_incremental_safe():
    from app.connectors.read import WooCommerceProductReadAdapter

    adapter = WooCommerceProductReadAdapter(url="https://store.example.test", key="ck_test", secret="cs_test")

    assert adapter.uses_http_boundary_limiter is True
    assert adapter.capabilities.supports_modified_since is True
    assert adapter.capabilities.supports_updated_after is True
    assert adapter.capabilities.supports_batch_read is True
    assert adapter.capabilities.supports_pagination is True


@pytest.mark.asyncio
async def test_woocommerce_manual_read_uses_single_http_boundary_read_token(db, monkeypatch):
    from app.connectors.read.woocommerce import WooCommerceProductReadAdapter
    from app.flowhub.rate_limit import acquire_connector_rate_limit, global_rate_limiter_registry
    from app.flowhub.rate_limit.service import RateLimitService
    from app.flowhub.read_engine.service import IncrementalReadEngine

    global_rate_limiter_registry.reset_for_tests()
    engine_acquires: list[tuple[str, str]] = []

    async def fail_engine_acquire(self, connector_id, operation, *, connector_type=None):
        _ = (self, connector_type)
        engine_acquires.append((connector_id, operation))
        raise AssertionError("WooCommerce reads must be limited at the HTTP boundary only")

    async def fake_list_products_paged(*args, **kwargs):
        _ = (args, kwargs)
        await acquire_connector_rate_limit("woocommerce:primary", "read")
        return ([{"id": "101", "sku": "A", "name": "Alpha", "price": "10.00"}], 1, 1)

    monkeypatch.setattr(RateLimitService, "acquire", fail_engine_acquire)
    monkeypatch.setattr("app.connectors.read.woocommerce.list_products_paged", fake_list_products_paged)

    adapter = WooCommerceProductReadAdapter(url="https://store.example.test", key="ck_test", secret="cs_test")
    progress = await IncrementalReadEngine(db).run_manual(adapter)

    assert progress.status == "completed"
    assert progress.requests_completed == 1
    assert engine_acquires == []
    assert global_rate_limiter_registry.snapshot()["requests_completed"] == 1


def test_nextcloud_read_adapter_fails_closed_for_incremental_products():
    from app.connectors.read import NextcloudSpreadsheetReadAdapter

    adapter = NextcloudSpreadsheetReadAdapter()

    assert adapter.capabilities.supports_batch_read is False
    assert adapter.capabilities.supports_modified_since is False


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
async def test_metadata_filter_fetches_metadata_before_selected_products(db):
    from app.flowhub.data_layer.models import DlProductCache
    from app.flowhub.read_engine.service import IncrementalReadEngine

    old = (datetime.utcnow() - timedelta(days=400)).isoformat()
    db.add_all([
        DlProductCache(connector_id="woocommerce:primary", product_id="priced", last_price="9.00", last_modified=old),
        DlProductCache(connector_id="woocommerce:primary", product_id="recent-empty", last_price=None, price=None, last_modified=old),
        DlProductCache(connector_id="woocommerce:primary", product_id="old-empty", last_price=None, price=None, last_modified=old),
    ])
    db.commit()
    adapter = MetadataFilterAdapter()

    progress = await IncrementalReadEngine(db).run_manual(adapter)

    assert progress.strategy == "metadata_filter"
    assert [name for name, _ in adapter.calls] == ["metadata", "products"]
    product_call = adapter.calls[1][1]
    assert set(product_call["product_ids"]) == {"priced", "recent-empty"}
    assert product_call["product_ids"] != []
    assert progress.products_stored == 2


@pytest.mark.asyncio
async def test_metadata_filter_unsupported_fails_closed_without_full_fetch(db):
    from app.flowhub.data_layer.models import DlProductCache
    from app.flowhub.read_engine.exceptions import IncrementalReadUnsupported
    from app.flowhub.read_engine.service import IncrementalReadEngine

    db.add(DlProductCache(connector_id="woocommerce:primary", product_id="101", last_price="9.00"))
    db.commit()
    adapter = FakeReadAdapter(
        [[{"id": "101", "sku": "A", "name": "Alpha", "price": "10.00"}]],
        capabilities=FakeCapabilities(supports_batch_read=False),
    )

    with pytest.raises(IncrementalReadUnsupported, match="incremental_read_unsupported"):
        await IncrementalReadEngine(db).run_manual(adapter)

    assert adapter.calls == []


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


@pytest.mark.asyncio
async def test_run_seen_guard_avoids_duplicate_unique_product_counts(db):
    from app.flowhub.read_engine.service import IncrementalReadEngine

    adapter = FakeReadAdapter([
        [
            {"id": "101", "sku": "A", "name": "Alpha", "price": "10.00"},
            {"id": "101", "sku": "A", "name": "Alpha", "price": "10.00"},
        ],
    ])

    progress = await IncrementalReadEngine(db).run_manual(adapter)

    assert progress.products_stored == 1
    assert db.query(_data_layer_models.DlProductCache).count() == 1


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


def test_production_manual_read_endpoint_calls_incremental_engine(client, auth_headers, db, monkeypatch):
    from app.flowhub.read_engine.service import ReadProgress
    from app.flowhub.setup.service import AppConfigService

    cfg = AppConfigService(db)
    cfg.set_many(
        {
            "woocommerce.url": "https://store.example.test",
            "woocommerce.key": "ck_test",
            "woocommerce.secret": "cs_test",
        },
        updated_by="test",
    )
    calls = {"adapter_type": None, "triggered_by": None}

    async def fake_run_manual(self, adapter, *, triggered_by="manual"):
        calls["adapter_type"] = adapter.connector_type
        calls["triggered_by"] = triggered_by
        return ReadProgress(
            job_id=1,
            connector_id=adapter.connector_id,
            strategy="initial_full_read",
            status="completed",
            requests_completed=1,
            requests_delayed=0,
            products_stored=0,
            remaining_queue=0,
            estimated_completion_seconds=None,
        )

    monkeypatch.setattr("app.flowhub.read_engine.service.IncrementalReadEngine.run_manual", fake_run_manual)

    response = client.post("/api/v2/read/manual/woocommerce:primary", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["manual_triggered"] is True
    assert data["scheduler_started"] is False
    assert data["automatic_sync"] is False
    assert calls["adapter_type"] == "woocommerce"
    assert calls["triggered_by"].startswith("rateadmin_")


def test_nextcloud_manual_read_fails_closed(client, auth_headers):
    response = client.post("/api/v2/read/manual/nextcloud:primary", headers=auth_headers)

    assert response.status_code == 409
    assert "incremental_read_unsupported" in response.text


def test_connection_http_and_auth_paths_use_global_limiter(monkeypatch):
    from app.flowhub.connections.adapters import RealNetworkAdapter

    calls: list[str] = []
    monkeypatch.setattr("app.flowhub.connections.adapters._acquire_global_read_limit", lambda connector_id: calls.append(connector_id))

    class FakeResponse:
        status_code = 200
        content = b"ok"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, *args, **kwargs):
            return FakeResponse()

        def get(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr("httpx.Client", FakeClient)

    adapter = RealNetworkAdapter()
    assert adapter.http_request("HEAD", "https://example.test", 1, {}, None) == (200, b"ok")
    assert adapter.check_auth("https://example.test", "user", "password", 1) == (True, 200)
    assert calls == ["connection-test:http", "connection-test:auth"]


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
    assert data["rateLimiter"]["average_request_duration_ms"] is None
    assert data["rateLimiter"]["estimated_completion_seconds"] is None
    assert "secret" not in response.text.lower()
    assert "password" not in response.text.lower()


def test_diagnostics_status_full_payload_uses_null_for_unavailable_metrics(client, auth_headers, db):
    from app.flowhub.setup.service import AppConfigService

    AppConfigService(db).set_many(
        {
            "woocommerce.url": "https://store.example.test",
            "woocommerce.key": "ck_test",
            "woocommerce.secret": "cs_test",
        },
        updated_by="test",
    )

    response = client.get("/api/v2/diagnostics/status", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["checks"]
    assert all(isinstance(item["duration_ms"], (int, float)) for item in data["checks"])
    assert data["telemetryContract"]["items"]
    for item in data["telemetryContract"]["items"]:
        assert item["latency_ms_p50"] is None
        assert item["latency_ms_p95"] is None
        assert item["refresh_duration_ms"] is None
        assert item["bucket_start"] is None
    for connector in data["connectors"]:
        assert connector["health"]["latency_ms"] is None


def test_diagnostics_status_uses_data_layer_health_detail_without_http_500(client, auth_headers, db):
    from app.flowhub.data_layer.models import DlConnectorHealth
    from app.flowhub.integration_platform.models import IntegrationConnectorInstance

    now = datetime.utcnow()
    db.add(IntegrationConnectorInstance(
        id="snappshop:main", connector_type="snappshop", name="Snapp Shop",
        version="1.0.0", enabled=False, read_only=True, status="disabled",
        created_at=now, updated_at=now,
    ))
    db.add(DlConnectorHealth(
        connector_id="snappshop:main", connector_type="channel", status="unknown",
        detail="Channel is not configured.", checked_at=now,
    ))
    db.commit()

    response = client.get("/api/v2/diagnostics/status", headers=auth_headers)

    assert response.status_code == 200
    connector = next(item for item in response.json()["connectors"] if item["id"] == "snappshop:main")
    assert connector["health"]["message"] == "Channel is not configured."


def test_diagnostics_status_isolates_one_connector_contract_failure(client, auth_headers, db, monkeypatch, caplog):
    from app.flowhub.integration_platform.models import IntegrationConnectorInstance
    from app.flowhub.integration_platform.service import IntegrationPlatformService

    now = datetime.utcnow()
    for channel_id, connector_type in (("snappshop:main", "snappshop"), ("tapsishop:main", "tapsishop")):
        db.add(IntegrationConnectorInstance(
            id=channel_id, connector_type=connector_type, name=channel_id,
            version="1.0.0", enabled=False, read_only=True, status="disabled",
            created_at=now, updated_at=now,
        ))
    db.commit()
    original = IntegrationPlatformService._instance_to_contract

    def fail_one(self, row):
        if row.id == "snappshop:main":
            raise RuntimeError("Authorization: Bearer should-not-leak")
        return original(self, row)

    monkeypatch.setattr(IntegrationPlatformService, "_instance_to_contract", fail_one)
    response = client.get("/api/v2/diagnostics/status", headers=auth_headers)

    assert response.status_code == 200
    items = response.json()["connectors"]
    failed = next(item for item in items if item["id"] == "snappshop:main")
    assert failed["health"]["error_code"] == "diagnostic_unavailable"
    assert "should-not-leak" not in response.text
    assert "should-not-leak" not in caplog.text
    assert any(item["id"] == "tapsishop:main" for item in items)


def test_integration_platform_test_connection_returns_null_latency_when_unmeasured(client, auth_headers, db):
    from app.flowhub.setup.service import AppConfigService

    AppConfigService(db).set_many(
        {
            "woocommerce.url": "https://store.example.test",
            "woocommerce.key": "ck_test",
            "woocommerce.secret": "cs_test",
        },
        updated_by="test",
    )

    response = client.post("/api/v2/integration-platform/connectors/woocommerce:primary/test", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["latency_ms"] is None


def test_integration_platform_event_metadata_is_redacted_on_persist_and_response(db):
    from app.flowhub.integration_platform.service import IntegrationPlatformService

    service = IntegrationPlatformService(db)
    event = service.record_event(
        connector_id="woocommerce:primary",
        event_name="redaction_check",
        message="metadata redaction check",
        metadata={
            "consumer_secret_value": "hide-me",
            "nested": {"access_token": "hide-token", "display_name": "keep-me"},
        },
    )

    assert event.metadata_json["consumer_secret_value"] == "[REDACTED]"
    assert event.metadata_json["nested"]["access_token"] == "[REDACTED]"
    assert event.metadata_json["nested"]["display_name"] == "keep-me"
    telemetry = service.telemetry(connector_id="woocommerce:primary")
    assert telemetry.items[0].metadata["consumer_secret_value"] == "[REDACTED]"
    assert telemetry.items[0].metadata["nested"]["access_token"] == "[REDACTED]"
    assert "hide-me" not in telemetry.model_dump_json()
    assert "hide-token" not in telemetry.model_dump_json()


def test_marker_based_redaction_handles_substring_secret_fields():
    from app.flowhub.security.redaction import redact_sensitive

    payload = {
        "consumer_secret_value": "hide-me",
        "nested": {"access_token_expires": "hide-token", "display_name": "keep-me"},
        "key": "hide-key",
        "monkey": "keep-word-containing-key",
    }

    redacted = redact_sensitive(payload)

    assert redacted["consumer_secret_value"] == "[REDACTED]"
    assert redacted["nested"]["access_token_expires"] == "[REDACTED]"
    assert redacted["nested"]["display_name"] == "keep-me"
    assert redacted["key"] == "[REDACTED]"
    assert redacted["monkey"] == "keep-word-containing-key"
