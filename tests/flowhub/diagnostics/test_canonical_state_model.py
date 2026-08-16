from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("FLOWHUB_DATABASE_URL", "sqlite:///:memory:")

from app.flowhub.auth import models as _auth_models  # noqa: F401
from app.flowhub.data_layer import models as _data_layer_models  # noqa: F401
from app.flowhub.data_layer.models import DlConnectorHealth, DlProductCache, DlRefreshJob
from app.flowhub.database import FlowHubBase
from app.flowhub.diagnostics.state_model import CanonicalDiagnosticsProjector
from app.flowhub.integration_platform import models as _integration_models  # noqa: F401
from app.flowhub.integration_platform.models import (
    IntegrationConnectorEvent,
    IntegrationConnectorInstance,
    IntegrationConnectorSetting,
)
from app.flowhub.orders import models as _order_models  # noqa: F401
from app.flowhub.orders.models import OrderSyncCheckpoint
from app.flowhub.source_acquisition import models as _acquisition_models  # noqa: F401
from app.flowhub.source_workspace import models as _source_models  # noqa: F401
from app.flowhub.source_workspace.models import SourceProfile
from app.flowhub.unified_workspace import models as _unified_workspace_models  # noqa: F401
from app.flowhub.webhooks import models as _webhook_models  # noqa: F401


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    FlowHubBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        FlowHubBase.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture(autouse=True)
def deterministic_policies(monkeypatch):
    monkeypatch.setenv("FLOWHUB_ORDER_SYNC_ENABLED", "false")
    for provider in ("WOOCOMMERCE", "SNAPPSHOP", "TAPSISHOP", "TECHNOLIFE"):
        monkeypatch.delenv(f"FLOWHUB_{provider}_PRODUCT_SYNC_ENABLED", raising=False)
        monkeypatch.delenv(f"FLOWHUB_{provider}_PRODUCT_SYNC_INTERVAL_SECONDS", raising=False)
        monkeypatch.delenv(f"FLOWHUB_{provider}_PRODUCT_SYNC_FRESHNESS_TTL_SECONDS", raising=False)


def test_coming_soon_is_excluded_from_operational_channel_denominator(db):
    now = _now()
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_health(db, "woocommerce:primary", now)
    _seed_product_cache(db, "woocommerce:primary", now)

    model = _project(db, now)

    assert model["summary"]["channels"] == pytest.approx(
        {
            "ready": 1,
            "operational": 1,
            "needsAttention": 0,
            "blocked": 0,
            "disabled": 3,
            "comingSoon": 1,
        }
    )
    digikala = _resource(model, "digikala:main")
    assert digikala["readiness"]["state"] == "COMING_SOON"
    assert digikala["denominatorEligible"] is False


def test_archived_source_is_historical_and_excluded_from_active_denominator(db):
    now = _now()
    _seed_source(db, "source-active", "Nextcloud — Price List", "nextcloud:price-list", "active")
    _seed_source(db, "source-archived", "Nextcloud — Legacy", "nextcloud:legacy", "archived")
    _seed_source_connector(db, "nextcloud:price-list", enabled=True)
    _seed_source_connector(db, "nextcloud:legacy", enabled=False)
    _seed_health(db, "nextcloud:price-list", now)
    _seed_health(db, "nextcloud:legacy", now - timedelta(days=10))

    model = _project(db, now)

    assert model["summary"]["sources"]["active"] == 1
    assert model["summary"]["sources"]["ready"] == 1
    assert model["summary"]["sources"]["archived"] == 1
    archived = _resource(model, "source-archived")
    assert archived["displayName"] == "Nextcloud — Legacy"
    assert archived["readiness"]["state"] == "ARCHIVED"
    assert archived["denominatorEligible"] is False


def test_disabled_resource_is_not_counted_as_failed_operational_resource(db):
    now = _now()
    _seed_channel(db, "woocommerce:primary", "woocommerce", enabled=False)
    _seed_health(db, "woocommerce:primary", now, status="unhealthy")

    model = _project(db, now)
    channel = _resource(model, "woocommerce:primary")

    assert channel["readiness"]["state"] == "DISABLED"
    assert channel["denominatorEligible"] is False
    assert model["summary"]["channels"]["blocked"] == 0


def test_disabled_source_connector_is_excluded_from_active_denominator(db):
    now = _now()
    _seed_source(db, "source-disabled", "Paused price list", "nextcloud:paused", "active")
    _seed_source_connector(db, "nextcloud:paused", enabled=False)
    _seed_health(db, "nextcloud:paused", now, status="unhealthy")

    model = _project(db, now)
    source = _resource(model, "source-disabled")

    assert source["readiness"]["state"] == "DISABLED"
    assert source["denominatorEligible"] is False
    assert model["summary"]["sources"]["active"] == 0
    assert model["summary"]["sources"]["blocked"] == 0


def test_healthy_connection_and_stale_scheduled_product_sync_needs_attention(db, monkeypatch):
    now = _now()
    _enable_product_schedule(monkeypatch, "WOOCOMMERCE", interval=3_600, freshness=7_200)
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_health(db, "woocommerce:primary", now)
    _seed_product_cache(db, "woocommerce:primary", now - timedelta(hours=3))
    _seed_refresh(db, "woocommerce:primary", now - timedelta(hours=3), status="completed")

    channel = _resource(_project(db, now), "woocommerce:primary")

    assert channel["connectivity"]["state"] == "HEALTHY"
    assert channel["readiness"]["state"] == "NEEDS_ATTENTION"
    assert channel["capabilities"]["productSynchronization"]["freshness"] == "STALE"
    assert channel["reasonCode"] == "product_sync_stale"


def test_healthy_connection_and_expected_product_sync_never_run_needs_attention(db, monkeypatch):
    now = _now()
    _enable_product_schedule(monkeypatch, "WOOCOMMERCE", interval=3_600)
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_health(db, "woocommerce:primary", now)

    channel = _resource(_project(db, now), "woocommerce:primary")

    assert channel["connectivity"]["state"] == "HEALTHY"
    assert channel["readiness"]["state"] == "NEEDS_ATTENTION"
    assert channel["capabilities"]["productSynchronization"]["freshness"] == "NEVER_RUN"


def test_product_sync_not_scheduled_is_neutral_when_cache_is_fresh(db):
    now = _now()
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_health(db, "woocommerce:primary", now)
    _seed_product_cache(db, "woocommerce:primary", now)
    _seed_refresh(db, "woocommerce:primary", now, status="completed")

    channel = _resource(_project(db, now), "woocommerce:primary")

    product = channel["capabilities"]["productSynchronization"]
    assert product["schedule"]["mode"] == "NOT_SCHEDULED"
    assert product["freshness"] == "NOT_SCHEDULED"
    assert channel["readiness"]["state"] == "READY"


def test_fresh_order_sync_does_not_make_product_fresh(db, monkeypatch):
    now = _now()
    monkeypatch.setenv("FLOWHUB_ORDER_SYNC_ENABLED", "true")
    _enable_product_schedule(monkeypatch, "WOOCOMMERCE", interval=3_600)
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_health(db, "woocommerce:primary", now)
    db.add(
        OrderSyncCheckpoint(
            channel_id="woocommerce:primary",
            connector_type="woocommerce",
            source="reconciliation",
            last_run_at=now,
            last_success_at=now,
            next_run_at=now + timedelta(minutes=15),
            updated_at=now,
        )
    )
    db.commit()

    channel = _resource(_project(db, now), "woocommerce:primary")

    assert channel["capabilities"]["orderSynchronization"]["freshness"] == "FRESH"
    assert channel["capabilities"]["productSynchronization"]["freshness"] == "NEVER_RUN"


def test_successful_cache_outcome_can_be_stale(db):
    now = _now()
    old = now - timedelta(days=3)
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_health(db, "woocommerce:primary", now)
    _seed_product_cache(db, "woocommerce:primary", old)
    _seed_refresh(db, "woocommerce:primary", old, status="completed")

    cache = _resource(_project(db, now), "woocommerce:primary")["capabilities"]["productCache"]

    assert cache["lastOutcome"] == "SUCCESSFUL"
    assert cache["freshness"] == "STALE"


def test_live_idle_runner_is_healthy_not_unknown(db):
    now = _now()
    db.add(
        IntegrationConnectorEvent(
            connector_id="flowhub:order-sync-runner",
            event_name="order_sync_runner_heartbeat",
            severity="info",
            message="Runner is idle.",
            metadata_json={"state": "idle", "runner_id": "runner-1"},
            created_at=now - timedelta(seconds=15),
        )
    )
    db.commit()

    runner = _project(db, now)["backgroundJobs"][0]

    assert runner["state"] == "IDLE"
    assert runner["health"] == "HEALTHY"
    assert runner["lastHeartbeatAt"] is not None


def test_next_action_is_derived_once_and_matches_detailed_evidence(db, monkeypatch):
    now = _now()
    _enable_product_schedule(monkeypatch, "WOOCOMMERCE", interval=3_600, freshness=7_200)
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_health(db, "woocommerce:primary", now)
    _seed_product_cache(db, "woocommerce:primary", now - timedelta(hours=3))
    _seed_refresh(db, "woocommerce:primary", now - timedelta(hours=3), status="completed")

    channel = _resource(_project(db, now), "woocommerce:primary")

    assert channel["recommendedAction"]["code"] == "NEXT_PRODUCT_SYNC_SCHEDULED"
    assert channel["recommendedAction"]["scheduledAt"] == channel["capabilities"]["productSynchronization"]["nextExpectedAt"]
    assert channel["recommendedAction"]["code"] != "NO_ACTION_REQUIRED"


def test_all_canonical_consumers_receive_the_same_overall_state(db):
    now = _now()
    model = _project(db, now)

    assert set(model["consumerStates"].values()) == {model["overallState"]}


def test_provider_capability_not_supported_is_not_applicable(db):
    now = _now()
    digikala = _resource(_project(db, now), "digikala:main")

    product = digikala["capabilities"]["productSynchronization"]
    assert product["support"] == "COMING_SOON"
    assert product["freshness"] == "NOT_APPLICABLE"


def test_freshness_threshold_comes_from_backend_policy(db, monkeypatch):
    now = _now()
    _enable_product_schedule(monkeypatch, "WOOCOMMERCE", interval=1_800, freshness=7_200)
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_health(db, "woocommerce:primary", now)
    _seed_product_cache(db, "woocommerce:primary", now - timedelta(hours=3))
    _seed_refresh(db, "woocommerce:primary", now - timedelta(hours=3), status="completed")

    product = _resource(_project(db, now), "woocommerce:primary")["capabilities"]["productSynchronization"]

    assert product["policy"]["freshnessTtlSeconds"] == 7_200
    assert product["freshness"] == "STALE"


def _project(db, now: datetime) -> dict:
    return CanonicalDiagnosticsProjector(db, now=now).project()


def _resource(model: dict, resource_id: str) -> dict:
    return next(item for item in model["resources"] if item["id"] == resource_id)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _seed_channel(db, channel_id: str, connector_type: str, *, enabled: bool = True) -> None:
    now = _now()
    db.add(
        IntegrationConnectorInstance(
            id=channel_id,
            connector_type=connector_type,
            name=connector_type,
            version="1.0.0",
            enabled=enabled,
            read_only=True,
            status="configured" if enabled else "disabled",
            created_at=now,
            updated_at=now,
        )
    )
    required = {
        "woocommerce": ("url", "key", "secret"),
        "snappshop": ("token", "agent_identifier", "vendor_id"),
        "tapsishop": ("token",),
        "technolife": ("api_key", "encryption_secret"),
    }.get(connector_type, ())
    for key in required:
        db.add(
            IntegrationConnectorSetting(
                connector_id=channel_id,
                key=key,
                value_json=None if key in {"key", "secret", "token", "api_key", "encryption_secret"} else "configured",
                secret=key in {"key", "secret", "token", "api_key", "encryption_secret"},
                configured=True,
                updated_at=now,
            )
        )
    db.commit()


def _seed_source_connector(db, connector_id: str, *, enabled: bool) -> None:
    now = _now()
    db.add(
        IntegrationConnectorInstance(
            id=connector_id,
            connector_type="nextcloud",
            name=connector_id,
            version="1.0.0",
            enabled=enabled,
            read_only=True,
            status="configured" if enabled else "disabled",
            created_at=now,
            updated_at=now,
        )
    )
    for key in ("url", "username", "password", "spreadsheet_path"):
        db.add(
            IntegrationConnectorSetting(
                connector_id=connector_id,
                key=key,
                value_json=None if key == "password" else "configured",
                secret=key == "password",
                configured=True,
                updated_at=now,
            )
        )
    db.commit()


def _seed_source(db, source_id: str, name: str, connector_id: str, status: str) -> None:
    now = _now()
    db.add(
        SourceProfile(
            id=source_id,
            name=name,
            source_kind="external",
            external_source_id=connector_id,
            status=status,
            archived_at=now if status == "archived" else None,
            owner_user_id=1,
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()


def _seed_health(db, connector_id: str, at: datetime, *, status: str = "healthy") -> None:
    db.add(
        DlConnectorHealth(
            connector_id=connector_id,
            connector_type=connector_id.split(":", 1)[0],
            status=status,
            checked_at=at,
            last_success_at=at if status == "healthy" else None,
        )
    )
    db.commit()


def _seed_product_cache(db, connector_id: str, at: datetime) -> None:
    db.add(
        DlProductCache(
            connector_id=connector_id,
            product_id=f"product-{connector_id}",
            name="Product",
            freshness="fresh",
            last_fetched_at=at,
            last_successful_read=at,
        )
    )
    db.commit()


def _seed_refresh(db, connector_id: str, at: datetime, *, status: str) -> None:
    db.add(
        DlRefreshJob(
            job_type="manual",
            entity_type="products",
            connector_id=connector_id,
            status=status,
            started_at=at - timedelta(minutes=1),
            completed_at=at if status.startswith("completed") else None,
            failed_at=at if status == "failed" else None,
            created_at=at - timedelta(minutes=1),
            meta={},
        )
    )
    db.commit()


def _enable_product_schedule(monkeypatch, provider: str, *, interval: int, freshness: int | None = None) -> None:
    monkeypatch.setenv(f"FLOWHUB_{provider}_PRODUCT_SYNC_ENABLED", "true")
    monkeypatch.setenv(f"FLOWHUB_{provider}_PRODUCT_SYNC_INTERVAL_SECONDS", str(interval))
    if freshness is not None:
        monkeypatch.setenv(f"FLOWHUB_{provider}_PRODUCT_SYNC_FRESHNESS_TTL_SECONDS", str(freshness))
