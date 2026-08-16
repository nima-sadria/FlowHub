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
from app.flowhub.data_layer.models import DlConnectorHealth, DlRefreshJob
from app.flowhub.database import FlowHubBase
from app.flowhub.diagnostics.scheduling import ScheduledDiagnosticsEvaluator
from app.flowhub.integration_platform import models as _integration_models  # noqa: F401
from app.flowhub.integration_platform.models import (
    IntegrationConnectorInstance,
    IntegrationConnectorSetting,
)
from app.flowhub.orders import models as _order_models  # noqa: F401
from app.flowhub.source_acquisition import models as _acquisition_models  # noqa: F401
from app.flowhub.source_workspace import models as _source_models  # noqa: F401
from app.flowhub.source_workspace.models import SourceProfile
from app.flowhub.unified_workspace import models as _unified_models  # noqa: F401
from app.flowhub.webhooks import models as _webhook_models  # noqa: F401


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    FlowHubBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    try:
        yield factory
    finally:
        FlowHubBase.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture(autouse=True)
def product_policy(monkeypatch):
    for provider in ("WOOCOMMERCE", "SNAPPSHOP", "TAPSISHOP", "TECHNOLIFE"):
        monkeypatch.delenv(f"FLOWHUB_{provider}_PRODUCT_SYNC_ENABLED", raising=False)
        monkeypatch.delenv(f"FLOWHUB_{provider}_PRODUCT_SYNC_INTERVAL_SECONDS", raising=False)


@pytest.mark.asyncio
async def test_archived_disabled_and_coming_soon_never_produce_provider_io(
    session_factory, monkeypatch
):
    with session_factory() as db:
        _seed_connector(db, "nextcloud:legacy", "nextcloud", enabled=True)
        _seed_source(db, "source-legacy", "nextcloud:legacy", "archived")
        _seed_connector(db, "woocommerce:disabled", "woocommerce", enabled=False)
        _seed_connector(db, "digikala:main", "digikala", enabled=True)

    calls: list[str] = []

    async def connection(self, instance):
        calls.append(f"connection:{instance.id}")
        return {}

    async def products(self, channel_id, **kwargs):
        calls.append(f"products:{channel_id}")
        return {}

    monkeypatch.setattr(ScheduledDiagnosticsEvaluator, "_check_connection", connection)
    monkeypatch.setattr(ScheduledDiagnosticsEvaluator, "_sync_products", products)

    result = await ScheduledDiagnosticsEvaluator(session_factory).run_once()

    assert calls == []
    assert result["externalWritePerformed"] is False


@pytest.mark.asyncio
async def test_due_connection_and_explicit_product_schedule_execute_once(
    session_factory, monkeypatch
):
    now = _now()
    monkeypatch.setenv("FLOWHUB_WOOCOMMERCE_PRODUCT_SYNC_ENABLED", "true")
    monkeypatch.setenv("FLOWHUB_WOOCOMMERCE_PRODUCT_SYNC_INTERVAL_SECONDS", "3600")
    with session_factory() as db:
        _seed_connector(db, "woocommerce:primary", "woocommerce", enabled=True)
        db.add(
            DlConnectorHealth(
                connector_id="woocommerce:primary",
                connector_type="woocommerce",
                status="healthy",
                checked_at=now - timedelta(hours=2),
                last_success_at=now - timedelta(hours=2),
            )
        )
        db.add(
            DlRefreshJob(
                job_type="manual",
                entity_type="products",
                connector_id="woocommerce:primary",
                status="completed",
                created_at=now - timedelta(hours=2),
                started_at=now - timedelta(hours=2),
                completed_at=now - timedelta(hours=2),
                meta={},
            )
        )
        db.commit()

    calls: list[str] = []

    async def connection(self, instance):
        calls.append(f"connection:{instance.id}")
        return {"connectorId": instance.id, "status": "connected"}

    async def products(self, channel_id, **kwargs):
        calls.append(f"products:{channel_id}")
        return {"channelId": channel_id, "status": "completed"}

    monkeypatch.setattr(ScheduledDiagnosticsEvaluator, "_check_connection", connection)
    monkeypatch.setattr(ScheduledDiagnosticsEvaluator, "_sync_products", products)

    await ScheduledDiagnosticsEvaluator(session_factory, now=now).run_once()

    assert calls == [
        "connection:woocommerce:primary",
        "products:woocommerce:primary",
    ]


@pytest.mark.asyncio
async def test_current_evidence_and_unscheduled_products_do_not_execute(
    session_factory, monkeypatch
):
    now = _now()
    with session_factory() as db:
        _seed_connector(db, "woocommerce:primary", "woocommerce", enabled=True)
        db.add(
            DlConnectorHealth(
                connector_id="woocommerce:primary",
                connector_type="woocommerce",
                status="healthy",
                checked_at=now,
                last_success_at=now,
            )
        )
        db.commit()

    calls: list[str] = []

    async def connection(self, instance):
        calls.append(instance.id)
        return {}

    async def products(self, channel_id, **kwargs):
        calls.append(channel_id)
        return {}

    monkeypatch.setattr(ScheduledDiagnosticsEvaluator, "_check_connection", connection)
    monkeypatch.setattr(ScheduledDiagnosticsEvaluator, "_sync_products", products)

    await ScheduledDiagnosticsEvaluator(session_factory, now=now).run_once()

    assert calls == []


def _seed_connector(db, connector_id: str, connector_type: str, *, enabled: bool) -> None:
    now = _now()
    row = IntegrationConnectorInstance(
        id=connector_id,
        connector_type=connector_type,
        name=connector_type,
        version="1.0.0",
        enabled=enabled,
        read_only=True,
        status="configured" if enabled else "disabled",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    required = {
        "woocommerce": ("url", "key", "secret"),
        "nextcloud": ("url", "username", "password", "spreadsheet_path"),
        "digikala": ("access_token",),
    }.get(connector_type, ())
    for key in required:
        db.add(
            IntegrationConnectorSetting(
                connector_id=connector_id,
                key=key,
                value_json=None if key in {"key", "secret", "password", "access_token"} else "configured",
                secret=key in {"key", "secret", "password", "access_token"},
                configured=True,
                updated_at=now,
            )
        )
    db.commit()


def _seed_source(db, source_id: str, connector_id: str, status: str) -> None:
    now = _now()
    db.add(
        SourceProfile(
            id=source_id,
            name="Archived source",
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


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
