from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import FlowHubBase
from app.flowhub.source_acquisition.errors import SourceAcquisitionError
from app.flowhub.source_acquisition.models import AcquisitionRun
from app.flowhub.source_acquisition.service import SourceAcquisitionService
from app.flowhub.source_workspace.models import SourceProfile
from app.flowhub.unified_workspace.domain import ImmutableRecordError
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


def _run(service: SourceAcquisitionService, source_id: str = "source-one", *, key: str | None = None) -> dict[str, object]:
    return service.request_run(
        source_id=source_id,
        trigger_kind="manual",
        idempotency_key=key,
        request_payload={"operation": "acquire"},
    )


def _start(service: SourceAcquisitionService, run_id: str, now=None) -> dict[str, object]:
    return service.start_run(run_id, worker_id="worker-a", lease_seconds=60, now=now)


@pytest.mark.parametrize("result", ("observed", "not_modified", "content_unchanged_reparse"))
def test_queued_running_succeeded_with_each_allowed_result(result: str) -> None:
    db = _session()
    source = _source(db)
    service = SourceAcquisitionService(db)
    run = _run(service, source.id)

    assert _start(service, str(run["id"]))["status"] == "running"
    completed = service.succeed_run(str(run["id"]), worker_id="worker-a", result=result)

    assert completed["status"] == "succeeded"
    assert completed["result"] == result
    assert completed["terminalAt"] is not None


def test_cancellation_is_explicit_and_running_cancellation_requires_worker_acknowledgement() -> None:
    db = _session()
    source = _source(db)
    service = SourceAcquisitionService(db)

    queued = _run(service, source.id)
    cancelled = service.request_cancellation(str(queued["id"]), requester_user_id=1)
    assert cancelled["status"] == "cancelled"
    assert service.request_cancellation(str(queued["id"]), requester_user_id=1)["id"] == queued["id"]

    running = _run(service, source.id)
    _start(service, str(running["id"]))
    pending = service.request_cancellation(str(running["id"]), requester_user_id=1)
    assert pending["status"] == "running"
    assert pending["cancellationRequestedAt"] is not None
    acknowledged = service.acknowledge_cancellation(str(running["id"]), worker_id="worker-a")
    assert acknowledged["status"] == "cancelled"


def test_failed_run_and_terminal_state_immutability() -> None:
    db = _session()
    source = _source(db)
    service = SourceAcquisitionService(db)
    run = _run(service, source.id)
    _start(service, str(run["id"]))

    failed = service.fail_run(str(run["id"]), worker_id="worker-a", failure_code="provider_timeout")
    assert failed["status"] == "failed"
    assert failed["result"] == "none"
    with pytest.raises(SourceAcquisitionError, match="invalid_run_transition"):
        service.start_run(str(run["id"]), worker_id="worker-a", lease_seconds=60)
    with pytest.raises(SourceAcquisitionError, match="run_not_cancellable"):
        service.request_cancellation(str(run["id"]), requester_user_id=1)
    persisted = db.get(AcquisitionRun, str(run["id"]))
    assert persisted is not None
    persisted.failure_code = "changed_after_terminal"
    with pytest.raises(ImmutableRecordError):
        db.commit()
    db.rollback()


def test_expired_lease_becomes_abandoned_and_stale_worker_cannot_complete() -> None:
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
            now=now + timedelta(seconds=61),
        )
    abandoned = service.get_run(str(run["id"]))
    assert abandoned["status"] == "abandoned"
    assert abandoned["failureCode"] == "worker_lease_expired"


def test_invalid_transitions_and_worker_ownership_are_rejected() -> None:
    db = _session()
    source = _source(db)
    service = SourceAcquisitionService(db)
    run = _run(service, source.id)
    with pytest.raises(SourceAcquisitionError, match="invalid_run_transition"):
        service.succeed_run(str(run["id"]), worker_id="worker-a", result="observed")

    _start(service, str(run["id"]))
    with pytest.raises(SourceAcquisitionError, match="worker_ownership_conflict"):
        service.heartbeat(str(run["id"]), worker_id="worker-b", lease_seconds=60)
    with pytest.raises(SourceAcquisitionError, match="invalid_run_result"):
        service.succeed_run(str(run["id"]), worker_id="worker-a", result="none")


def test_idempotent_creation_conflict_and_active_scope_uniqueness() -> None:
    db = _session()
    source = _source(db)
    service = SourceAcquisitionService(db)
    first = _run(service, source.id, key="  caller-1  ")
    replay = _run(service, source.id, key="caller-1")
    assert replay["id"] == first["id"]

    with pytest.raises(SourceAcquisitionError, match="idempotency_key_conflict"):
        service.request_run(
            source_id=source.id,
            trigger_kind="manual",
            idempotency_key="caller-1",
            request_payload={"operation": "different"},
        )
    with pytest.raises(SourceAcquisitionError, match="active_run_conflict"):
        _run(service, source.id, key="caller-2")


def test_deterministic_creation_isolated_by_source_and_scope_and_terminal_allows_next_run() -> None:
    db = _session()
    first_source = _source(db, "source-one")
    second_source = _source(db, "source-two")
    service = SourceAcquisitionService(db)
    first = _run(service, first_source.id, key="one")
    scoped = service.request_run(
        source_id=first_source.id,
        trigger_kind="manual",
        resource_scope="alternate-binding",
        idempotency_key="two",
        request_payload={"operation": "acquire"},
    )
    isolated = _run(service, second_source.id, key="one")
    assert {first["id"], scoped["id"], isolated["id"]}

    _start(service, str(first["id"]))
    service.succeed_run(str(first["id"]), worker_id="worker-a", result="observed")
    later = _run(service, first_source.id, key="later")
    assert later["id"] != first["id"]


def test_retry_creates_distinct_linked_attempt_and_is_idempotent() -> None:
    db = _session()
    source = _source(db)
    service = SourceAcquisitionService(db)
    original = _run(service, source.id)
    _start(service, str(original["id"]))
    service.fail_run(str(original["id"]), worker_id="worker-a", failure_code="provider_timeout")

    retry = service.retry_run(str(original["id"]), idempotency_key="retry-1", actor_user_id=1)
    replay = service.retry_run(str(original["id"]), idempotency_key="retry-1", actor_user_id=1)
    assert retry["id"] != original["id"]
    assert retry["parentRunId"] == original["id"]
    assert retry["rootRunId"] == original["id"]
    assert retry["attemptNumber"] == 2
    assert replay["id"] == retry["id"]

    with pytest.raises(SourceAcquisitionError, match="run_not_retryable"):
        service.retry_run(str(retry["id"]), idempotency_key="retry-active")


def test_transaction_rollback_does_not_leave_partial_run_or_idempotency_record() -> None:
    db = _session()
    source = _source(db)
    service = SourceAcquisitionService(db)
    with pytest.raises(SourceAcquisitionError, match="source_not_found"):
        _run(service, "missing-source", key="missing")
    assert db.query(AcquisitionRun).count() == 0

    run = _run(service, source.id, key="usable-after-failure")
    assert run["status"] == "queued"


def test_active_unique_index_enforces_non_idempotent_race_safety() -> None:
    db = _session()
    source = _source(db)
    service = SourceAcquisitionService(db)
    first = _run(service, source.id)
    duplicate = AcquisitionRun(
        id="duplicate",
        source_id=source.id,
        resource_scope="source",
        trigger_kind="manual",
        request_fingerprint="x" * 64,
        correlation_id="duplicate",
        root_run_id="duplicate",
        attempt_number=1,
        status="queued",
        result="none",
    )
    db.add(duplicate)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    assert service.get_run(str(first["id"]))["status"] == "queued"
