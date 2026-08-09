"""Behavioral tests for BusinessObservabilityService."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.flowhub.business_observability.errors import BusinessObservabilityError
from app.flowhub.business_observability.service import BusinessObservabilityService
from app.flowhub.database import FlowHubBase


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    FlowHubBase.metadata.create_all(engine)
    return Session(engine)


def _emit(service: BusinessObservabilityService, **overrides: object):
    defaults: dict[str, object] = dict(
        domain="write_pipeline",
        event_type="write_batch_applied",
        severity="info",
        business_impact="none",
        reason_code="ok",
        primary_scope_type="batch",
        primary_scope_id="batch-1",
        producer="write_pipeline.service",
        correlation_id="corr-1",
    )
    defaults.update(overrides)
    return service.emit_event(**defaults)


def test_emit_event_rejects_unknown_domain() -> None:
    service = BusinessObservabilityService(_session())
    with pytest.raises(BusinessObservabilityError):
        _emit(service, domain="not_a_real_domain")


def test_emit_event_rejects_unknown_severity() -> None:
    service = BusinessObservabilityService(_session())
    with pytest.raises(BusinessObservabilityError):
        _emit(service, severity="not_a_real_severity")


def test_emit_event_rejects_missing_reason_code() -> None:
    service = BusinessObservabilityService(_session())
    with pytest.raises(BusinessObservabilityError):
        _emit(service, reason_code="")


def test_emit_event_generates_correlation_id_when_absent() -> None:
    service = BusinessObservabilityService(_session())
    event = _emit(service, correlation_id="")
    assert event.correlation_id.startswith("corr_")


def test_new_event_starts_open_with_no_lifecycle_history() -> None:
    service = BusinessObservabilityService(_session())
    event = _emit(service)
    shape = service.get_event(event.id)
    assert shape.status == "open"
    assert shape.acknowledgedAt is None
    assert shape.resolvedAt is None
    assert service.lifecycle_history(event.id) == []


def test_acknowledge_then_resolve_records_full_lifecycle_history() -> None:
    service = BusinessObservabilityService(_session())
    event = _emit(service)

    service.acknowledge(event.id, actor="alice", note="looking into it")
    acknowledged = service.get_event(event.id)
    assert acknowledged.status == "acknowledged"
    assert acknowledged.acknowledgedBy == "alice"
    assert acknowledged.resolvedAt is None

    service.resolve(event.id, actor="bob")
    resolved = service.get_event(event.id)
    assert resolved.status == "resolved"
    assert resolved.resolvedBy == "bob"
    assert resolved.acknowledgedBy == "alice"  # earlier transition is preserved, not overwritten

    history = service.lifecycle_history(event.id)
    assert [item.toStatus for item in history] == ["acknowledged", "resolved"]


def test_open_can_resolve_directly_without_acknowledge() -> None:
    service = BusinessObservabilityService(_session())
    event = _emit(service)
    service.resolve(event.id, actor="bob")
    assert service.get_event(event.id).status == "resolved"


def test_resolved_event_cannot_be_reopened() -> None:
    service = BusinessObservabilityService(_session())
    event = _emit(service)
    service.resolve(event.id, actor="bob")
    with pytest.raises(BusinessObservabilityError):
        service.acknowledge(event.id, actor="carol")
    with pytest.raises(BusinessObservabilityError):
        service.resolve(event.id, actor="carol")


def test_acknowledge_twice_is_rejected() -> None:
    service = BusinessObservabilityService(_session())
    event = _emit(service)
    service.acknowledge(event.id, actor="alice")
    with pytest.raises(BusinessObservabilityError):
        service.acknowledge(event.id, actor="alice")


def test_list_events_filters_by_domain_and_severity() -> None:
    service = BusinessObservabilityService(_session())
    _emit(service, domain="write_pipeline", severity="info")
    _emit(service, domain="pricing", severity="error", reason_code="pricing_origin_not_authorized")

    pricing_only = service.list_events(domain="pricing")
    assert len(pricing_only) == 1
    assert pricing_only[0].domain == "pricing"

    errors_only = service.list_events(severity="error")
    assert len(errors_only) == 1
    assert errors_only[0].severity == "error"


def test_list_events_filters_by_status() -> None:
    service = BusinessObservabilityService(_session())
    open_event = _emit(service)
    resolved_event = _emit(service, primary_scope_id="batch-2")
    service.resolve(resolved_event.id, actor="bob")

    open_only = service.list_events(status="open")
    assert {item.id for item in open_only} == {open_event.id}

    resolved_only = service.list_events(status="resolved")
    assert {item.id for item in resolved_only} == {resolved_event.id}


def test_kpi_blocking_by_domain_excludes_resolved_and_low_impact() -> None:
    service = BusinessObservabilityService(_session())
    _emit(service, domain="pricing", business_impact="blocking", primary_scope_id="p1")
    informational = _emit(service, domain="pricing", business_impact="none", primary_scope_id="p2")
    resolved = _emit(
        service, domain="channels", business_impact="critical_business_failure", primary_scope_id="p3"
    )
    service.resolve(resolved.id, actor="bob")

    kpis = service.kpis()
    assert kpis.openBlockingByDomain["pricing"] == 1
    assert kpis.openBlockingByDomain["channels"] == 0
    assert informational.id  # informational event exists but never counted as blocking


def test_kpi_write_pipeline_partial_failure_rate_30d() -> None:
    service = BusinessObservabilityService(_session())
    _emit(service, event_type="write_batch_applied", business_impact="none", primary_scope_id="b1")
    _emit(
        service,
        event_type="write_batch_partially_failed",
        business_impact="partial_failure",
        primary_scope_id="b2",
    )

    kpis = service.kpis()
    assert kpis.writePipelinePartialFailureRate30d == pytest.approx(0.5)


def test_kpi_partial_failure_rate_excludes_events_older_than_30_days() -> None:
    service = BusinessObservabilityService(_session())
    old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=45)
    _emit(
        service,
        event_type="write_batch_partially_failed",
        business_impact="partial_failure",
        primary_scope_id="old-batch",
        occurred_at=old,
    )
    _emit(service, event_type="write_batch_applied", business_impact="none", primary_scope_id="new-batch")

    kpis = service.kpis()
    assert kpis.writePipelinePartialFailureRate30d == pytest.approx(0.0)


def test_kpi_oldest_unresolved_blocking_age_ignores_resolved_events() -> None:
    service = BusinessObservabilityService(_session())
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    older = _emit(
        service,
        domain="channels",
        business_impact="blocking",
        primary_scope_id="c1",
        occurred_at=now - timedelta(hours=5),
    )
    _emit(
        service,
        domain="channels",
        business_impact="blocking",
        primary_scope_id="c2",
        occurred_at=now - timedelta(hours=1),
    )

    kpis = service.kpis(now=now)
    assert kpis.oldestUnresolvedBlockingEventAgeSeconds == pytest.approx(5 * 3600, rel=0.01)

    service.resolve(older.id, actor="bob")
    kpis_after_resolve = service.kpis(now=now)
    assert kpis_after_resolve.oldestUnresolvedBlockingEventAgeSeconds == pytest.approx(3600, rel=0.01)
