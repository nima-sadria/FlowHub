"""Immutability guards for Business Observability persistence."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.flowhub.business_observability.models import BusinessEvent, BusinessEventLifecycleTransition
from app.flowhub.database import FlowHubBase
from app.flowhub.unified_workspace.domain import ImmutableRecordError


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    FlowHubBase.metadata.create_all(engine)
    return Session(engine)


def _event(**overrides: object) -> BusinessEvent:
    defaults: dict[str, object] = dict(
        id="event-1",
        domain="write_pipeline",
        event_type="write_batch_applied",
        severity="info",
        business_impact="none",
        reason_code="ok",
        reason_message="",
        primary_scope_type="batch",
        primary_scope_id="batch-1",
        primary_scope_label=None,
        secondary_scopes_json=[],
        recommended_action="",
        retryable=False,
        action_route_key=None,
        action_route_params_json={},
        correlation_id="corr-1",
        producer="write_pipeline.service",
        occurred_at=datetime.now(timezone.utc).replace(tzinfo=None),
        metadata_json={},
    )
    defaults.update(overrides)
    return BusinessEvent(**defaults)


def test_business_event_row_cannot_be_updated() -> None:
    db = _session()
    row = _event()
    db.add(row)
    db.commit()

    row.severity = "critical"
    with pytest.raises(ImmutableRecordError):
        db.commit()


def test_business_event_row_cannot_be_deleted() -> None:
    db = _session()
    row = _event()
    db.add(row)
    db.commit()

    db.delete(row)
    with pytest.raises(ImmutableRecordError):
        db.commit()


def test_lifecycle_transition_cannot_be_updated() -> None:
    db = _session()
    event = _event()
    db.add(event)
    db.commit()
    transition = BusinessEventLifecycleTransition(
        business_event_id=event.id,
        from_status=None,
        to_status="acknowledged",
        actor="alice",
        occurred_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(transition)
    db.commit()

    transition.to_status = "resolved"
    with pytest.raises(ImmutableRecordError):
        db.commit()


def test_lifecycle_transition_cannot_be_deleted() -> None:
    db = _session()
    event = _event()
    db.add(event)
    db.commit()
    transition = BusinessEventLifecycleTransition(
        business_event_id=event.id,
        from_status=None,
        to_status="acknowledged",
        actor="alice",
        occurred_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(transition)
    db.commit()

    db.delete(transition)
    with pytest.raises(ImmutableRecordError):
        db.commit()
