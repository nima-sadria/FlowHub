from __future__ import annotations

import itertools
import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("FLOWHUB_DATABASE_URL", "sqlite:///:memory:")

from app.flowhub.auth import models as _auth_models  # noqa: F401
from app.flowhub.data_layer import models as _data_layer_models  # noqa: F401
from app.flowhub.data_layer.models import (
    DlChannelEntityWork,
    DlConnectorHealth,
    DlProductCache,
    DlRefreshJob,
)
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
from app.flowhub.webhooks.models import WebhookDeadLetter, WebhookReceipt


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


def test_supported_optional_not_scheduled_product_sync_is_ready(db):
    now = _now()
    _seed_channel(db, "snappshop:main", "snappshop")
    _seed_health(db, "snappshop:main", now)

    channel = _resource(_project(db, now), "snappshop:main")
    product = channel["capabilities"]["productSynchronization"]

    assert product["schedule"]["mode"] == "NOT_SCHEDULED"
    assert channel["readiness"]["state"] == "READY"
    assert channel["recommendedAction"]["code"] == "NO_ACTION_REQUIRED"


def test_required_product_sync_with_no_schedule_needs_configuration(db, monkeypatch):
    now = _now()
    monkeypatch.setenv("FLOWHUB_SNAPPSHOP_PRODUCT_SYNC_REQUIRED", "true")
    _seed_channel(db, "snappshop:main", "snappshop")
    _seed_health(db, "snappshop:main", now)

    channel = _resource(_project(db, now), "snappshop:main")

    assert channel["capabilities"]["productSynchronization"]["schedule"]["mode"] == "NOT_SCHEDULED"
    assert channel["readiness"]["state"] == "NEEDS_ATTENTION"
    assert channel["reasonCode"] == "product_cache_never_run"
    assert channel["recommendedAction"]["code"] == "CONFIGURE_PRODUCT_SYNC_SCHEDULE"


def test_manual_only_optional_product_sync_never_run_is_not_a_failure(db, monkeypatch):
    now = _now()
    monkeypatch.setenv("FLOWHUB_SNAPPSHOP_PRODUCT_SYNC_MANUAL", "true")
    _seed_channel(db, "snappshop:main", "snappshop")
    _seed_health(db, "snappshop:main", now)

    channel = _resource(_project(db, now), "snappshop:main")

    assert channel["capabilities"]["productSynchronization"]["schedule"]["mode"] == "MANUAL"
    assert channel["readiness"]["state"] == "READY"
    assert channel["recommendedAction"]["code"] == "NO_ACTION_REQUIRED"


def test_manual_required_product_sync_never_run_is_actionable_refresh(db, monkeypatch):
    now = _now()
    monkeypatch.setenv("FLOWHUB_SNAPPSHOP_PRODUCT_SYNC_MANUAL", "true")
    monkeypatch.setenv("FLOWHUB_SNAPPSHOP_PRODUCT_SYNC_REQUIRED", "true")
    _seed_channel(db, "snappshop:main", "snappshop")
    _seed_health(db, "snappshop:main", now)

    channel = _resource(_project(db, now), "snappshop:main")

    assert channel["capabilities"]["productSynchronization"]["schedule"]["mode"] == "MANUAL"
    assert channel["readiness"]["state"] == "NEEDS_ATTENTION"
    assert channel["reasonCode"] == "product_cache_never_run"
    assert channel["recommendedAction"]["code"] == "REFRESH_PRODUCTS"


def test_stale_manual_evidence_stays_actionable_regardless_of_schedule(db):
    # Mirrors WooCommerce's real default configuration: product sync is not
    # scheduled, but a prior manual refresh exists and has gone stale. Once a
    # manual cadence is evidenced, staleness must remain actionable.
    now = _now()
    old = now - timedelta(days=3)
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_health(db, "woocommerce:primary", now)
    _seed_product_cache(db, "woocommerce:primary", old)
    _seed_refresh(db, "woocommerce:primary", old, status="completed")

    channel = _resource(_project(db, now), "woocommerce:primary")

    assert channel["capabilities"]["productSynchronization"]["schedule"]["mode"] == "NOT_SCHEDULED"
    assert channel["readiness"]["state"] == "NEEDS_ATTENTION"
    assert channel["reasonCode"] == "product_cache_stale"
    assert channel["recommendedAction"]["code"] == "REFRESH_PRODUCTS"


def test_archived_source_recent_check_is_archived_not_healthy(db):
    now = _now()
    _seed_source(db, "source-archived", "Nextcloud — Legacy", "nextcloud:legacy", "archived")
    _seed_source_connector(db, "nextcloud:legacy", enabled=False)
    _seed_health(db, "nextcloud:legacy", now - timedelta(days=10))

    model = _project(db, now)
    archived = _resource(model, "source-archived")
    check = _recent_check(model, "source-archived")

    assert archived["overallState"] == "ARCHIVED"
    assert check["state"] == "ARCHIVED"


def test_coming_soon_recent_check_is_coming_soon_not_healthy(db):
    now = _now()
    model = _project(db, now)
    digikala = _resource(model, "digikala:main")
    check = _recent_check(model, "digikala:main")

    assert digikala["overallState"] == "COMING_SOON"
    assert check["state"] == "COMING_SOON"


def test_disabled_channel_recent_check_is_disabled_not_healthy(db):
    now = _now()
    _seed_channel(db, "woocommerce:primary", "woocommerce", enabled=False)

    model = _project(db, now)
    channel = _resource(model, "woocommerce:primary")
    check = _recent_check(model, "woocommerce:primary")

    assert channel["overallState"] == "DISABLED"
    assert check["state"] == "DISABLED"


def test_lifecycle_state_takes_precedence_over_healthy_connectivity(db):
    # A Coming Soon channel with (hypothetically) healthy connectivity
    # evidence must still present as COMING_SOON, never HEALTHY.
    now = _now()
    _seed_health(db, "digikala:main", now, status="healthy")

    model = _project(db, now)
    check = _recent_check(model, "digikala:main")

    assert check["state"] == "COMING_SOON"
    assert check["state"] != "HEALTHY"


def test_channel_denominator_recovers_once_not_scheduled_is_no_longer_needs_attention(db):
    now = _now()
    _seed_channel(db, "snappshop:main", "snappshop")
    _seed_health(db, "snappshop:main", now)

    model = _project(db, now)

    assert model["summary"]["channels"]["ready"] == 1
    assert model["summary"]["channels"]["needsAttention"] == 0


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


# ---------------------------------------------------------------------------
# Observation Confidence: distinct axis from freshness above, see
# ADR_CHANNEL_READ_ARCHITECTURE.md.
# ---------------------------------------------------------------------------


def test_observation_confidence_is_unknown_with_no_cache_rows(db):
    now = _now()
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_health(db, "woocommerce:primary", now)

    confidence = _resource(_project(db, now), "woocommerce:primary")["observationConfidence"]

    assert confidence["value"] == "UNKNOWN"
    assert confidence["reasonCode"] == "never_observed"
    assert confidence["recoveryRequiredCount"] == 0


def test_observation_confidence_is_confirmed_when_every_row_is_confirmed(db):
    now = _now()
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_health(db, "woocommerce:primary", now)
    for product_id in ("1", "2"):
        db.add(
            DlProductCache(
                connector_id="woocommerce:primary", product_id=product_id, name=f"Product {product_id}",
                freshness="fresh", last_fetched_at=now, observation_confidence="CONFIRMED",
            )
        )
    db.commit()

    confidence = _resource(_project(db, now), "woocommerce:primary")["observationConfidence"]

    assert confidence["value"] == "CONFIRMED"
    assert confidence["reasonCode"] == "zero_staleness_read"


def test_observation_confidence_rolls_up_to_worst_stored_value(db):
    """A mix of CONFIRMED and STALE rows must roll up to STALE -- worst
    value wins, a single good row cannot mask a bad one."""
    now = _now()
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_health(db, "woocommerce:primary", now)
    db.add(
        DlProductCache(
            connector_id="woocommerce:primary", product_id="1", name="Confirmed",
            freshness="fresh", last_fetched_at=now, observation_confidence="CONFIRMED",
        )
    )
    db.add(
        DlProductCache(
            connector_id="woocommerce:primary", product_id="2", name="Stale",
            freshness="stale", last_fetched_at=now - timedelta(days=2), observation_confidence="STALE",
        )
    )
    db.commit()

    confidence = _resource(_project(db, now), "woocommerce:primary")["observationConfidence"]

    assert confidence["value"] == "STALE"
    assert confidence["reasonCode"] == "beyond_channel_ttl"


def test_observation_confidence_decays_past_ttl_even_with_a_likely_fresh_stored_value(db):
    """Diagnostics must recompute live rather than trust a write-time
    snapshot that has since aged past the channel's TTL."""
    now = _now()
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_health(db, "woocommerce:primary", now)
    db.add(
        DlProductCache(
            connector_id="woocommerce:primary", product_id="1", name="Aged",
            freshness="fresh",
            # Written as LIKELY_FRESH at the time, but that was 2 days ago --
            # well beyond the default 24h product-cache TTL.
            last_fetched_at=now - timedelta(days=2),
            observation_confidence="LIKELY_FRESH",
        )
    )
    db.commit()

    confidence = _resource(_project(db, now), "woocommerce:primary")["observationConfidence"]

    assert confidence["value"] == "STALE"


def test_observation_confidence_is_recovery_required_when_entity_work_exhausts_retries(db):
    now = _now()
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_health(db, "woocommerce:primary", now)
    db.add(
        DlProductCache(
            connector_id="woocommerce:primary", product_id="1", name="Confirmed",
            freshness="fresh", last_fetched_at=now, observation_confidence="CONFIRMED",
        )
    )
    db.add(
        DlChannelEntityWork(
            connector_id="woocommerce:primary", entity_type="products", entity_id="57926",
            status="failed", strategy="LIGHT", reason="WEBHOOK_PRODUCT_UPDATED",
            latest_reason="WEBHOOK_PRODUCT_UPDATED", latest_event_at=now,
            attempt_count=5, max_attempts=5, created_at=now, updated_at=now,
        )
    )
    db.commit()

    confidence = _resource(_project(db, now), "woocommerce:primary")["observationConfidence"]

    # Even one exhausted entity-work row overrides an otherwise-CONFIRMED
    # channel -- FlowHub tried and failed to observe a real change, and that
    # must not be silently masked by unrelated healthy rows.
    assert confidence["value"] == "RECOVERY_REQUIRED"
    assert confidence["reasonCode"] == "entity_work_exhausted_retries"
    assert confidence["recoveryRequiredCount"] == 1


def test_observation_confidence_ignores_entity_work_still_retrying(db):
    now = _now()
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_health(db, "woocommerce:primary", now)
    db.add(
        DlProductCache(
            connector_id="woocommerce:primary", product_id="1", name="Confirmed",
            freshness="fresh", last_fetched_at=now, observation_confidence="CONFIRMED",
        )
    )
    db.add(
        DlChannelEntityWork(
            connector_id="woocommerce:primary", entity_type="products", entity_id="57926",
            status="failed", strategy="LIGHT", reason="WEBHOOK_PRODUCT_UPDATED",
            latest_reason="WEBHOOK_PRODUCT_UPDATED", latest_event_at=now,
            attempt_count=2, max_attempts=5, created_at=now, updated_at=now,
        )
    )
    db.commit()

    confidence = _resource(_project(db, now), "woocommerce:primary")["observationConfidence"]

    assert confidence["value"] != "RECOVERY_REQUIRED"


def test_observation_confidence_is_not_applicable_for_disabled_channel(db):
    now = _now()
    _seed_channel(db, "woocommerce:primary", "woocommerce", enabled=False)

    confidence = _resource(_project(db, now), "woocommerce:primary")["observationConfidence"]

    assert confidence["value"] == "UNKNOWN"
    assert confidence["reasonCode"] == "not_applicable"


def test_observation_confidence_is_a_distinct_axis_from_freshness(db):
    """The existing freshness axis and the new confidence axis must be able
    to disagree -- neither is derived from the other."""
    now = _now()
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_health(db, "woocommerce:primary", now)
    _seed_product_cache(db, "woocommerce:primary", now)
    _seed_refresh(db, "woocommerce:primary", now, status="completed")
    db.query(DlProductCache).filter_by(connector_id="woocommerce:primary").update(
        {"observation_confidence": "STALE"}
    )
    db.commit()

    channel = _resource(_project(db, now), "woocommerce:primary")

    assert channel["capabilities"]["productCache"]["freshness"] == "FRESH"
    assert channel["observationConfidence"]["value"] == "STALE"


def test_source_resources_report_observation_confidence_as_not_applicable(db):
    now = _now()
    _seed_source_connector(db, "nextcloud:primary", enabled=True)
    _seed_source(db, "src-1", "Primary Sheet", "nextcloud:primary", "active")

    confidence = _resource(_project(db, now), "src-1")["observationConfidence"]

    assert confidence["value"] == "UNKNOWN"
    assert confidence["reasonCode"] == "not_applicable"


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


# ----------------------------------------------------------------------
# Composed product-synchronization scheduling semantics
# ----------------------------------------------------------------------


def test_event_driven_channel_is_not_reported_as_not_scheduled(db):
    """A: webhook capability + accepted evidence means EVENT_DRIVEN."""

    now = _now()
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_webhook_secret(db, "woocommerce:primary")
    _seed_health(db, "woocommerce:primary", now)
    _seed_webhook_receipt(db, "woocommerce:primary", now, state="processed")
    _seed_product_cache(db, "woocommerce:primary", now)
    _seed_refresh(db, "woocommerce:primary", now, status="completed")

    channel = _resource(_project(db, now), "woocommerce:primary")
    product = channel["capabilities"]["productSynchronization"]

    assert product["schedule"]["mode"] == "EVENT_DRIVEN"
    assert product["schedule"]["mode"] != "NOT_SCHEDULED"
    assert product["freshness"] == "FRESH"
    assert product["freshness"] != "NOT_SCHEDULED"
    assert channel["capabilities"]["webhookProcessing"]["schedule"]["mode"] == "EVENT_DRIVEN"
    # The product-sync axis is now required, so stale product data on an
    # event-driven channel can still surface NEEDS_ATTENTION.
    assert product["required"] is True


def test_event_driven_with_scheduled_reconciliation_reports_both_facts(db, monkeypatch):
    """B: composed mode carries its own next-reconciliation timestamp."""

    now = _now()
    _enable_product_schedule(monkeypatch, "WOOCOMMERCE", interval=3_600, freshness=7_200)
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_webhook_secret(db, "woocommerce:primary")
    _seed_health(db, "woocommerce:primary", now)
    _seed_webhook_receipt(db, "woocommerce:primary", now, state="processed")
    _seed_product_cache(db, "woocommerce:primary", now)
    _seed_refresh(db, "woocommerce:primary", now, status="completed")

    channel = _resource(_project(db, now), "woocommerce:primary")
    product = channel["capabilities"]["productSynchronization"]

    assert product["schedule"]["mode"] == "EVENT_DRIVEN_WITH_RECONCILIATION"
    assert product["reconciliation"]["mode"] == "SCHEDULED"
    assert product["reconciliation"]["nextReconciliationAt"] is not None
    assert product["freshness"] == "FRESH"


def test_event_driven_without_a_poll_reports_manual_reconciliation(db):
    """C: reconciliation is a separate sub-fact, not folded into the mode."""

    now = _now()
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_webhook_secret(db, "woocommerce:primary")
    _seed_health(db, "woocommerce:primary", now)
    _seed_webhook_receipt(db, "woocommerce:primary", now, state="processed")
    _seed_product_cache(db, "woocommerce:primary", now)
    _seed_refresh(db, "woocommerce:primary", now, status="completed")

    product = _resource(_project(db, now), "woocommerce:primary")["capabilities"][
        "productSynchronization"
    ]

    assert product["schedule"]["mode"] == "EVENT_DRIVEN"
    assert product["reconciliation"]["mode"] == "MANUAL"
    assert product["reconciliation"]["nextReconciliationAt"] is None


def test_unsupported_provider_reconciliation_is_disabled(db):
    now = _now()
    _seed_channel(db, "technolife:main", "technolife")
    _seed_health(db, "technolife:main", now)

    product = _resource(_project(db, now), "technolife:main")["capabilities"][
        "productSynchronization"
    ]

    assert product["schedule"]["mode"] == "NOT_SCHEDULED"
    assert product["reconciliation"]["mode"] == "DISABLED"


def test_configured_webhook_without_accepted_evidence_is_not_event_driven(db):
    # Configuration alone is a claim; only a durably accepted receipt is
    # evidence that the provider is actually delivering.
    now = _now()
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_webhook_secret(db, "woocommerce:primary")
    _seed_health(db, "woocommerce:primary", now)
    _seed_product_cache(db, "woocommerce:primary", now)
    _seed_refresh(db, "woocommerce:primary", now, status="completed")

    product = _resource(_project(db, now), "woocommerce:primary")["capabilities"][
        "productSynchronization"
    ]

    assert product["schedule"]["mode"] == "NOT_SCHEDULED"


def test_fresh_cache_is_preserved_when_the_latest_attempt_failed(db):
    """D: cache freshness comes from last success, outcome from last attempt."""

    now = _now()
    success_at = now - timedelta(hours=2)
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_webhook_secret(db, "woocommerce:primary")
    _seed_health(db, "woocommerce:primary", now)
    _seed_webhook_receipt(db, "woocommerce:primary", now, state="processed")
    _seed_product_cache(db, "woocommerce:primary", success_at)
    _seed_refresh(db, "woocommerce:primary", success_at, status="completed")
    _seed_refresh(db, "woocommerce:primary", now, status="failed")

    channel = _resource(_project(db, now), "woocommerce:primary")
    cache = channel["capabilities"]["productCache"]
    product = channel["capabilities"]["productSynchronization"]

    assert cache["freshness"] == "FRESH"
    assert cache["lastOutcome"] == "FAILED"
    assert cache["lastSuccessAt"] is not None
    assert product["lastSuccessAt"] == cache["lastSuccessAt"]
    # The live symptom: still fresh, but the newest reconciliation attempt
    # failed, so the action must be to retry it -- not a blanket refresh.
    assert channel["reasonCode"] == "product_cache_refresh_failed"
    assert channel["recommendedAction"]["code"] == "RETRY_RECONCILIATION"


def test_unresolved_dead_letter_keeps_the_channel_needing_attention(db):
    now = _now()
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_webhook_secret(db, "woocommerce:primary")
    _seed_health(db, "woocommerce:primary", now)
    _seed_webhook_receipt(db, "woocommerce:primary", now, state="processed")
    _seed_product_cache(db, "woocommerce:primary", now)
    _seed_refresh(db, "woocommerce:primary", now, status="completed")
    _seed_dead_letter(db, "woocommerce:primary", now, receipt_state="dead_letter")

    channel = _resource(_project(db, now), "woocommerce:primary")
    webhook = channel["capabilities"]["webhookProcessing"]

    assert webhook["deadLetterCount"] == 1
    assert webhook["actionableDeadLetterCount"] == 1
    assert channel["readiness"]["state"] == "NEEDS_ATTENTION"
    assert channel["reasonCode"] == "webhook_dead_letters"


def test_replayed_dead_letter_stops_pinning_the_channel_but_keeps_the_evidence(db):
    """A dead letter that is no longer actionable must release readiness.

    The 13 WooCommerce dead letters from the 2026-08-18 incident would
    otherwise hold the channel at NEEDS_ATTENTION permanently, because the
    projection counted every dead-letter row that had ever been written. The
    row itself is retained evidence and is never deleted.
    """

    now = _now()
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_webhook_secret(db, "woocommerce:primary")
    _seed_health(db, "woocommerce:primary", now)
    _seed_webhook_receipt(db, "woocommerce:primary", now, state="processed")
    _seed_product_cache(db, "woocommerce:primary", now)
    _seed_refresh(db, "woocommerce:primary", now, status="completed")
    # The dead letter was replayed and has since reprocessed successfully.
    _seed_dead_letter(db, "woocommerce:primary", now, receipt_state="processed")

    channel = _resource(_project(db, now), "woocommerce:primary")
    webhook = channel["capabilities"]["webhookProcessing"]

    # Evidence preserved...
    assert webhook["deadLetterCount"] == 1
    # ...but nothing is actionable any more.
    assert webhook["actionableDeadLetterCount"] == 0
    assert webhook["lastOutcome"] != "FAILED"
    assert channel["readiness"]["state"] == "READY"
    assert channel["reasonCode"] == "channel_ready"


def test_healthy_event_driven_channel_produces_no_false_refresh_products(db):
    """E: a working event-driven channel is READY with no action."""

    now = _now()
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_webhook_secret(db, "woocommerce:primary")
    _seed_health(db, "woocommerce:primary", now)
    _seed_webhook_receipt(db, "woocommerce:primary", now, state="processed")
    _seed_product_cache(db, "woocommerce:primary", now)
    _seed_refresh(db, "woocommerce:primary", now, status="completed")

    channel = _resource(_project(db, now), "woocommerce:primary")

    assert channel["readiness"]["state"] == "READY"
    assert channel["reasonCode"] == "channel_ready"
    assert channel["recommendedAction"]["code"] == "NO_ACTION_REQUIRED"
    assert channel["recommendedAction"]["code"] != "REFRESH_PRODUCTS"


def test_stale_event_driven_product_data_still_surfaces_needs_attention(db, monkeypatch):
    now = _now()
    monkeypatch.setenv("FLOWHUB_WOOCOMMERCE_PRODUCT_SYNC_FRESHNESS_TTL_SECONDS", "3600")
    old = now - timedelta(days=2)
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_webhook_secret(db, "woocommerce:primary")
    _seed_health(db, "woocommerce:primary", now)
    _seed_webhook_receipt(db, "woocommerce:primary", old, state="processed")
    _seed_product_cache(db, "woocommerce:primary", old)
    _seed_refresh(db, "woocommerce:primary", old, status="completed")

    channel = _resource(_project(db, now), "woocommerce:primary")

    assert channel["capabilities"]["productSynchronization"]["schedule"]["mode"] == "EVENT_DRIVEN"
    assert channel["capabilities"]["productSynchronization"]["freshness"] == "STALE"
    assert channel["readiness"]["state"] == "NEEDS_ATTENTION"
    assert channel["reasonCode"] == "product_sync_stale"


def test_queue_depth_above_zero_forbids_idle_runner_state(db):
    """F: a live runner with executable work is PENDING, never IDLE."""

    now = _now()
    _seed_heartbeat(db, now - timedelta(seconds=15), state="idle")
    for _ in range(3):
        _seed_queued_refresh_job(db, now)

    runner = _project(db, now)["backgroundJobs"][0]

    assert runner["queueDepth"] == 3
    assert runner["state"] == "PENDING"
    assert runner["state"] != "IDLE"
    assert runner["health"] == "HEALTHY"


def test_live_runner_with_no_queued_work_is_still_idle(db):
    now = _now()
    _seed_heartbeat(db, now - timedelta(seconds=15), state="idle")

    runner = _project(db, now)["backgroundJobs"][0]

    assert runner["queueDepth"] == 0
    assert runner["state"] == "IDLE"
    assert runner["health"] == "HEALTHY"


def test_abandoned_records_do_not_inflate_queue_depth_but_stay_visible(db):
    """G: expired-lease jobs and expired receipts are evidence, not backlog."""

    now = _now()
    _seed_heartbeat(db, now - timedelta(seconds=15), state="idle")
    _seed_queued_refresh_job(db, now)
    _seed_abandoned_refresh_job(db, now - timedelta(days=2))
    _seed_webhook_receipt(
        db,
        "woocommerce:primary",
        now - timedelta(days=200),
        state="queued",
        retention_until=now - timedelta(days=110),
    )

    runner = _project(db, now)["backgroundJobs"][0]

    assert runner["queueDepth"] == 1
    assert runner["staleQueueDepth"] == 2
    evidence = {item["key"]: item["value"] for item in runner["advancedEvidence"]}
    assert evidence["runner_stale_queue_depth"] == 2


def test_webhook_partial_comes_from_queued_receipts_not_ping_noise(db):
    """H: PARTIAL is derived from durable receipts; pings persist nothing."""

    now = _now()
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_webhook_secret(db, "woocommerce:primary")
    _seed_health(db, "woocommerce:primary", now)
    _seed_webhook_receipt(db, "woocommerce:primary", now, state="processed")
    _seed_webhook_receipt(db, "woocommerce:primary", now, state="queued")

    webhook = _resource(_project(db, now), "woocommerce:primary")["capabilities"][
        "webhookProcessing"
    ]

    assert webhook["lastOutcome"] == "PARTIAL"
    assert webhook["queuedCount"] == 1
    assert webhook["receivedCount"] == 2
    assert webhook["acceptedCount"] == 2


def test_woocommerce_activation_ping_is_not_persisted_as_webhook_evidence(db):
    # The ping is acknowledged by the route without a receipt, so a channel
    # that has only ever been pinged shows no delivery evidence at all and
    # cannot be inflated to PARTIAL.
    now = _now()
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_webhook_secret(db, "woocommerce:primary")
    _seed_health(db, "woocommerce:primary", now)

    webhook = _resource(_project(db, now), "woocommerce:primary")["capabilities"][
        "webhookProcessing"
    ]

    assert webhook["receivedCount"] == 0
    assert webhook["acceptedCount"] == 0
    assert webhook["lastOutcome"] == "NEVER_RUN"
    assert webhook["lastOutcome"] != "PARTIAL"


def test_dead_lettered_receipts_are_not_accepted_delivery_evidence(db):
    now = _now()
    _seed_channel(db, "woocommerce:primary", "woocommerce")
    _seed_webhook_secret(db, "woocommerce:primary")
    _seed_health(db, "woocommerce:primary", now)
    _seed_webhook_receipt(db, "woocommerce:primary", now, state="dead_letter")

    channel = _resource(_project(db, now), "woocommerce:primary")
    webhook = channel["capabilities"]["webhookProcessing"]

    assert webhook["acceptedCount"] == 0
    assert channel["capabilities"]["productSynchronization"]["schedule"]["mode"] == "NOT_SCHEDULED"


def _project(db, now: datetime) -> dict:
    return CanonicalDiagnosticsProjector(db, now=now).project()


def _resource(model: dict, resource_id: str) -> dict:
    return next(item for item in model["resources"] if item["id"] == resource_id)


def _recent_check(model: dict, resource_id: str) -> dict:
    return next(item for item in model["recentChecks"] if item["id"] == resource_id)


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


def _seed_webhook_secret(db, channel_id: str, *, key: str = "webhook_secret") -> None:
    db.add(
        IntegrationConnectorSetting(
            connector_id=channel_id,
            key=key,
            value_json=None,
            secret=True,
            configured=True,
            updated_at=_now(),
        )
    )
    db.commit()


def _seed_dead_letter(
    db,
    channel_id: str,
    at: datetime,
    *,
    receipt_state: str = "dead_letter",
    provider: str = "woocommerce",
) -> None:
    """Write a dead-letter row plus the receipt it points at.

    `receipt_state` is what decides whether the dead letter is still
    actionable: "dead_letter" means it is still parked, anything else means an
    admin replay or a later success has already resolved it.
    """

    index = next(_RECEIPT_SEQUENCE)
    receipt = WebhookReceipt(
        channel_id=channel_id,
        provider=provider,
        provider_event_id=f"dl-evt-{index}",
        payload_hash=f"dl-hash-{index}",
        payload_summary_json={},
        normalized_event_json={},
        received_at=at,
        acknowledged_at=at,
        processing_state=receipt_state,
        attempt_count=5,
        processed_at=at if receipt_state == "processed" else None,
    )
    db.add(receipt)
    db.flush()
    db.add(
        WebhookDeadLetter(
            receipt_id=receipt.id,
            channel_id=channel_id,
            provider=provider,
            provider_event_id=receipt.provider_event_id,
            reason="product cache refresh failed",
            error_category="upstream_unavailable",
            created_at=at,
        )
    )
    db.commit()


_RECEIPT_SEQUENCE = itertools.count(1)


def _seed_webhook_receipt(
    db,
    channel_id: str,
    at: datetime,
    *,
    state: str = "processed",
    provider: str = "woocommerce",
    retention_until: datetime | None = None,
) -> None:
    index = next(_RECEIPT_SEQUENCE)
    db.add(
        WebhookReceipt(
            channel_id=channel_id,
            provider=provider,
            provider_event_id=f"evt-{index}",
            payload_hash=f"hash-{index}",
            payload_summary_json={},
            normalized_event_json={},
            received_at=at,
            acknowledged_at=at,
            processing_state=state,
            attempt_count=1,
            processed_at=at if state == "processed" else None,
            retention_until=retention_until,
        )
    )
    db.commit()


def _seed_heartbeat(db, at: datetime, *, state: str = "idle") -> None:
    db.add(
        IntegrationConnectorEvent(
            connector_id="flowhub:order-sync-runner",
            event_name="order_sync_runner_heartbeat",
            severity="info",
            message=f"Runner is {state}.",
            metadata_json={"state": state, "runner_id": "runner-1"},
            created_at=at,
        )
    )
    db.commit()


def _seed_queued_refresh_job(db, at: datetime) -> None:
    """A pending job a live runner will genuinely pick up."""

    db.add(
        DlRefreshJob(
            job_type="scheduled",
            entity_type="products",
            connector_id="woocommerce:primary",
            status="pending",
            created_at=at,
            meta={},
        )
    )
    db.commit()


def _seed_abandoned_refresh_job(db, at: datetime) -> None:
    """A running job whose execution lease expired long ago."""

    db.add(
        DlRefreshJob(
            job_type="scheduled",
            entity_type="products",
            connector_id="woocommerce:primary",
            status="running",
            started_at=at,
            heartbeat_at=at,
            lease_expires_at=at + timedelta(minutes=15),
            created_at=at,
            meta={},
        )
    )
    db.commit()
