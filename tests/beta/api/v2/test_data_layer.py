"""Tests for /api/v2/data-layer endpoints (Data Layer Foundation phase).

Covers:
  - All 6 GET endpoints return 200 with correct shape
  - Unauthenticated requests are rejected (401)
  - Empty-state responses when tables are unpopulated
  - read_only and apply_blocked flags are always true
  - No write mutations to external systems
  - Service layer (upsert, status, increment) works correctly
  - Invalidation event recording works
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("BETA_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("BETA_JWT_SECRET", "test-dl-jwt-secret-exactly-32-bytes!")

# Register all ORM models so BetaBase.metadata.create_all covers them.
from app.beta.auth import models as _auth_models  # noqa: F401
from app.beta.setup import models as _setup_models  # noqa: F401
from app.beta.data_layer import models as _dl_models  # noqa: F401


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def db_engine():
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    from app.beta.database import BetaBase, _get_engine

    _get_engine.cache_clear()
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    BetaBase.metadata.create_all(engine)
    yield engine
    BetaBase.metadata.drop_all(engine)
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
    from app.beta.app import app
    from app.beta.database import get_db

    Session = sessionmaker(bind=db_engine)

    def _override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(client, db):
    from app.beta.auth.password import hash_password
    from app.beta.auth.models import BetaUser

    user = BetaUser(username="dladmin", hashed_password=hash_password("dlpass1234"), role="admin")
    db.add(user)
    db.commit()

    r = client.post("/api/auth/login", json={"username": "dladmin", "password": "dlpass1234"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ── Auth guard tests ──────────────────────────────────────────────────────────

class TestDataLayerAuth:
    def test_status_requires_auth(self, client):
        assert client.get("/api/v2/data-layer/status").status_code == 401

    def test_products_status_requires_auth(self, client):
        assert client.get("/api/v2/data-layer/products/status").status_code == 401

    def test_sources_status_requires_auth(self, client):
        assert client.get("/api/v2/data-layer/sources/status").status_code == 401

    def test_connectors_status_requires_auth(self, client):
        assert client.get("/api/v2/data-layer/connectors/status").status_code == 401

    def test_refresh_jobs_requires_auth(self, client):
        assert client.get("/api/v2/data-layer/refresh-jobs").status_code == 401

    def test_invalidation_events_requires_auth(self, client):
        assert client.get("/api/v2/data-layer/invalidation-events").status_code == 401


# ── Empty-state responses ─────────────────────────────────────────────────────

class TestDataLayerEmptyState:
    def test_status_returns_200(self, client, auth_headers):
        r = client.get("/api/v2/data-layer/status", headers=auth_headers)
        assert r.status_code == 200

    def test_status_shape(self, client, auth_headers):
        data = client.get("/api/v2/data-layer/status", headers=auth_headers).json()
        assert "data_layer_version" in data
        assert "initialized" in data
        assert "read_only" in data
        assert "apply_blocked" in data
        assert "product_cache" in data
        assert "source_snapshots" in data
        assert "destination_snapshots" in data
        assert "connector_health" in data
        assert "connector_telemetry" in data
        assert "refresh_jobs" in data
        assert "invalidation_events" in data

    def test_read_only_always_true(self, client, auth_headers):
        data = client.get("/api/v2/data-layer/status", headers=auth_headers).json()
        assert data["read_only"] is True

    def test_apply_blocked_always_true(self, client, auth_headers):
        data = client.get("/api/v2/data-layer/status", headers=auth_headers).json()
        assert data["apply_blocked"] is True

    def test_empty_initialized_false(self, client, auth_headers):
        data = client.get("/api/v2/data-layer/status", headers=auth_headers).json()
        assert data["initialized"] is False

    def test_products_status_empty(self, client, auth_headers):
        data = client.get("/api/v2/data-layer/products/status", headers=auth_headers).json()
        assert data["initialized"] is False
        assert data["total"] == 0

    def test_sources_status_empty(self, client, auth_headers):
        data = client.get("/api/v2/data-layer/sources/status", headers=auth_headers).json()
        assert data["source"]["initialized"] is False
        assert data["destination"]["initialized"] is False
        assert data["source_snapshots"] == []
        assert data["destination_snapshots"] == []

    def test_connectors_status_empty(self, client, auth_headers):
        data = client.get("/api/v2/data-layer/connectors/status", headers=auth_headers).json()
        assert data["health"]["summary"]["total"] == 0
        assert data["health"]["connectors"] == []
        assert data["telemetry"]["summary"]["total_requests"] == 0

    def test_refresh_jobs_empty(self, client, auth_headers):
        data = client.get("/api/v2/data-layer/refresh-jobs", headers=auth_headers).json()
        assert "summary" in data
        assert "items" in data
        assert data["summary"]["total"] == 0
        assert data["items"] == []

    def test_invalidation_events_empty(self, client, auth_headers):
        data = client.get("/api/v2/data-layer/invalidation-events", headers=auth_headers).json()
        assert data["summary"]["total"] == 0
        assert data["items"] == []


# ── Service layer tests ───────────────────────────────────────────────────────

class TestProductReadModelService:
    def test_empty_status(self, db):
        from app.beta.data_layer.product_service import ProductReadModelService
        svc = ProductReadModelService(db)
        st = svc.get_status()
        assert st["initialized"] is False
        assert st["total"] == 0

    def test_upsert_creates_record(self, db):
        from app.beta.data_layer.product_service import ProductReadModelService
        svc = ProductReadModelService(db)
        svc.upsert("woocommerce:primary", "123", {"name": "Test Product", "price": "10.00"})
        st = svc.get_status()
        assert st["initialized"] is True
        assert st["total"] == 1

    def test_upsert_is_idempotent(self, db):
        from app.beta.data_layer.product_service import ProductReadModelService
        svc = ProductReadModelService(db)
        svc.upsert("woocommerce:primary", "123", {"name": "A"})
        svc.upsert("woocommerce:primary", "123", {"name": "B"})
        st = svc.get_status()
        assert st["total"] == 1

    def test_mark_stale(self, db):
        from app.beta.data_layer.product_service import ProductReadModelService
        svc = ProductReadModelService(db)
        svc.upsert("woocommerce:primary", "1", {}, freshness="fresh")
        svc.upsert("woocommerce:primary", "2", {}, freshness="fresh")
        count = svc.mark_stale()
        assert count == 2
        st = svc.get_status()
        assert st["fresh"] == 0
        assert st["stale"] == 2


class TestConnectorHealthService:
    def test_empty_summary(self, db):
        from app.beta.data_layer.health_service import ConnectorHealthService
        svc = ConnectorHealthService(db)
        s = svc.get_summary()
        assert s["initialized"] is False
        assert s["total"] == 0

    def test_upsert_healthy(self, db):
        from app.beta.data_layer.health_service import ConnectorHealthService
        svc = ConnectorHealthService(db)
        row = svc.upsert("woocommerce:primary", "destination", "healthy", latency_ms=42.5)
        assert row.status == "healthy"
        assert row.consecutive_failures == 0
        s = svc.get_summary()
        assert s["healthy"] == 1

    def test_consecutive_failures_increment(self, db):
        from app.beta.data_layer.health_service import ConnectorHealthService
        svc = ConnectorHealthService(db)
        svc.upsert("woocommerce:primary", "destination", "unhealthy")
        svc.upsert("woocommerce:primary", "destination", "unhealthy")
        rows = svc.get_all()
        assert rows[0]["consecutive_failures"] == 2

    def test_healthy_resets_failures(self, db):
        from app.beta.data_layer.health_service import ConnectorHealthService
        svc = ConnectorHealthService(db)
        svc.upsert("woocommerce:primary", "destination", "unhealthy")
        svc.upsert("woocommerce:primary", "destination", "unhealthy")
        svc.upsert("woocommerce:primary", "destination", "healthy")
        rows = svc.get_all()
        assert rows[0]["consecutive_failures"] == 0

    def test_invalid_status_raises(self, db):
        from app.beta.data_layer.health_service import ConnectorHealthService
        svc = ConnectorHealthService(db)
        with pytest.raises(ValueError):
            svc.upsert("woocommerce:primary", "destination", "broken")


class TestConnectorTelemetryService:
    def test_empty_summary(self, db):
        from app.beta.data_layer.telemetry_service import ConnectorTelemetryService
        svc = ConnectorTelemetryService(db)
        s = svc.get_summary()
        assert s["initialized"] is False
        assert s["total_requests"] == 0

    def test_increment_creates_record(self, db):
        from app.beta.data_layer.telemetry_service import ConnectorTelemetryService
        svc = ConnectorTelemetryService(db)
        svc.increment("woocommerce:primary", "destination", requests=5, products_fetched=100)
        s = svc.get_summary()
        assert s["initialized"] is True
        assert s["total_requests"] == 5
        assert s["total_products_fetched"] == 100

    def test_increment_accumulates(self, db):
        from app.beta.data_layer.telemetry_service import ConnectorTelemetryService
        svc = ConnectorTelemetryService(db)
        svc.increment("woocommerce:primary", "destination", requests=3)
        svc.increment("woocommerce:primary", "destination", requests=7)
        s = svc.get_summary()
        assert s["total_requests"] == 10


class TestSourceSnapshotService:
    def test_empty_status(self, db):
        from app.beta.data_layer.snapshot_service import SourceSnapshotService
        svc = SourceSnapshotService(db)
        assert svc.get_status()["initialized"] is False

    def test_upsert_increments_version(self, db):
        from app.beta.data_layer.snapshot_service import SourceSnapshotService
        svc = SourceSnapshotService(db)
        r1 = svc.upsert("nextcloud:primary", "/prices.xlsx", etag="abc", parsed_row_count=50)
        v1 = r1.version_seq  # capture before second upsert (identity map shares the object)
        r2 = svc.upsert("nextcloud:primary", "/prices.xlsx", etag="def", parsed_row_count=55)
        assert v1 == 1
        assert r2.version_seq == 2


class TestRefreshJobService:
    def test_empty_summary(self, db):
        from app.beta.data_layer.refresh_service import RefreshJobService
        svc = RefreshJobService(db)
        s = svc.get_summary()
        assert s["initialized"] is False
        assert s["total"] == 0

    def test_create_job(self, db):
        from app.beta.data_layer.refresh_service import RefreshJobService
        svc = RefreshJobService(db)
        job = svc.create("manual", "products", connector_id="woocommerce:primary")
        assert job.status == "pending"
        assert job.id is not None

    def test_update_status(self, db):
        from app.beta.data_layer.refresh_service import RefreshJobService
        svc = RefreshJobService(db)
        job = svc.create("manual", "source")
        updated = svc.update_status(job.id, "completed", duration_ms=123.4)
        assert updated is not None
        assert updated.status == "completed"
        assert updated.completed_at is not None

    def test_invalid_status_raises(self, db):
        from app.beta.data_layer.refresh_service import RefreshJobService
        svc = RefreshJobService(db)
        job = svc.create("manual", "products")
        with pytest.raises(ValueError):
            svc.update_status(job.id, "exploded")


class TestInvalidationService:
    def test_empty_summary(self, db):
        from app.beta.data_layer.invalidation_service import InvalidationService
        svc = InvalidationService(db)
        assert svc.get_summary()["total"] == 0

    def test_record_event(self, db):
        from app.beta.data_layer.invalidation_service import InvalidationService
        svc = InvalidationService(db)
        ev = svc.record("manual", "product", entity_id="123", connector_id="woocommerce:primary")
        assert ev.id is not None
        assert svc.get_summary()["total"] == 1

    def test_list_recent(self, db):
        from app.beta.data_layer.invalidation_service import InvalidationService
        svc = InvalidationService(db)
        svc.record("manual", "product", entity_id="1")
        svc.record("webhook", "source_snapshot", connector_id="nextcloud:primary")
        items = svc.list_recent(limit=10)
        assert len(items) == 2
        assert items[0]["event_type"] == "webhook"  # newest first

    def test_filter_by_entity_type(self, db):
        from app.beta.data_layer.invalidation_service import InvalidationService
        svc = InvalidationService(db)
        svc.record("manual", "product")
        svc.record("time", "connector_health")
        items = svc.list_recent(entity_type="product")
        assert len(items) == 1
        assert items[0]["entity_type"] == "product"


# ── No write paths to external systems ───────────────────────────────────────

class TestNoWritePaths:
    """Verify the data-layer router never imports or calls WC/NC write methods."""

    def test_router_does_not_import_httpx_directly(self):
        import ast
        import pathlib
        src = pathlib.Path(__file__).parents[4] / "app" / "beta" / "api" / "v2" / "data_layer_routes.py"
        tree = ast.parse(src.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "httpx" not in (alias.name or ""), "data_layer_routes imports httpx directly"
            elif isinstance(node, ast.ImportFrom):
                assert "httpx" not in (node.module or ""), "data_layer_routes imports from httpx directly"

    def test_service_modules_do_not_import_httpx(self):
        import ast
        import pathlib
        dl_dir = pathlib.Path(__file__).parents[4] / "app" / "beta" / "data_layer"
        for py_file in dl_dir.rglob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert "httpx" not in (alias.name or ""), f"{py_file.name} imports httpx"
                elif isinstance(node, ast.ImportFrom):
                    assert "httpx" not in (node.module or ""), f"{py_file.name} imports from httpx"
