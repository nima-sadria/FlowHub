"""Source Acquisition -> Business Observability producer wiring (Business Observability v1, Phase 2)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.business_observability.models import BusinessEvent
from app.flowhub.database import FlowHubBase
from app.flowhub.source_acquisition.errors import SourceAcquisitionError
from app.flowhub.source_acquisition.service import SourceAcquisitionService
from app.flowhub.source_workspace.models import SourceProfile
from app.flowhub.unified_workspace import models as _unified_workspace_models  # noqa: F401
from app.flowhub.unified_workspace.domain import utcnow


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    FlowHubBase.metadata.create_all(engine)
    return Session(engine)


def _source(db: Session, source_id: str = "source-one") -> SourceProfile:
    user = db.get(FlowHubUser, 1)
    if user is None:
        user = FlowHubUser(id=1, username="owner", hashed_password="x", role="admin", is_active=True)
        db.add(user)
        db.flush()
    source = SourceProfile(
        id=source_id,
        name=source_id,
        source_kind="external",
        external_source_id=f"external-{source_id}",
        worksheet_mode="selected",
        worksheet_name="Products",
        data_start_row=2,
        status="active",
        version=1,
        owner_user_id=user.id,
    )
    db.add(source)
    db.commit()
    return source


def _run(service: SourceAcquisitionService, source_id: str = "source-one") -> dict[str, object]:
    return service.request_run(
        source_id=source_id,
        trigger_kind="manual",
        idempotency_key=None,
        request_payload={"operation": "acquire"},
    )


def _start(service: SourceAcquisitionService, run_id: str, now=None) -> dict[str, object]:
    return service.start_run(run_id, worker_id="worker-a", lease_seconds=60, now=now)


def _business_events(db: Session) -> list[BusinessEvent]:
    return db.query(BusinessEvent).filter(BusinessEvent.domain == "source_acquisition").all()


def test_fail_run_emits_source_read_failed_business_event() -> None:
    db = _session()
    source = _source(db)
    service = SourceAcquisitionService(db)
    run = _run(service, source.id)
    _start(service, str(run["id"]))

    service.fail_run(str(run["id"]), worker_id="worker-a", failure_code="provider_timeout")

    events = _business_events(db)
    assert len(events) == 1
    event = events[0]
    assert event.event_type == "source_read_failed"
    assert event.severity == "error"
    assert event.business_impact == "degraded"
    assert event.reason_code == "provider_timeout"
    assert event.primary_scope_type == "source"
    assert event.primary_scope_id == source.id
    assert event.secondary_scopes_json == [
        {"scope_type": "batch", "scope_id": str(run["id"]), "scope_label": None}
    ]
    assert event.action_route_key == "source.detail"
    assert event.action_route_params_json == {"source_id": source.id}
    assert event.retryable is True
    # The run's own correlation_id is reused as the business event's
    # correlation_id (Owner decision: standardize, don't invent a second id).
    assert event.correlation_id == run["correlationId"]


def test_expired_lease_emits_source_run_abandoned_business_event() -> None:
    db = _session()
    source = _source(db)
    service = SourceAcquisitionService(db)
    now = utcnow()
    run = _run(service, source.id)
    _start(service, str(run["id"]), now=now)

    with pytest.raises(SourceAcquisitionError, match="lease_expired"):
        service.succeed_run(
            str(run["id"]),
            worker_id="worker-a",
            result="observed",
            now=now + timedelta(seconds=120),
        )

    events = _business_events(db)
    assert len(events) == 1
    event = events[0]
    assert event.event_type == "source_run_abandoned"
    assert event.severity == "error"
    assert event.business_impact == "degraded"
    assert event.reason_code == "worker_lease_expired"
    assert event.primary_scope_type == "source"
    assert event.primary_scope_id == source.id
    assert event.retryable is True


def test_successful_run_does_not_emit_a_business_event() -> None:
    db = _session()
    source = _source(db)
    service = SourceAcquisitionService(db)
    run = _run(service, source.id)
    _start(service, str(run["id"]))

    service.succeed_run(str(run["id"]), worker_id="worker-a", result="observed")

    assert _business_events(db) == []


def test_cancelled_run_does_not_emit_a_business_event() -> None:
    db = _session()
    source = _source(db)
    service = SourceAcquisitionService(db)
    run = _run(service, source.id)

    service.request_cancellation(str(run["id"]), requester_user_id=1)

    assert _business_events(db) == []
