from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import FlowHubBase
from app.flowhub.source_acquisition.errors import SourceAcquisitionError
from app.flowhub.source_acquisition.models import (
    SourceObservation,
    SourceObservationEvidence,
    SourceObservationSnapshotReference,
)
from app.flowhub.source_acquisition.observations import SourceObservationService
from app.flowhub.source_acquisition.service import SourceAcquisitionService
from app.flowhub.source_workspace.models import SourceProfile
from app.flowhub.unified_workspace import models as _unified_workspace_models  # noqa: F401
from app.flowhub.unified_workspace.domain import ImmutableRecordError, utcnow


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    FlowHubBase.metadata.create_all(engine)
    return Session(engine)


def _source(db: Session) -> SourceProfile:
    user = FlowHubUser(id=1, username="owner", hashed_password="x", role="admin", is_active=True)
    source = SourceProfile(
        id="source-one",
        name="Source",
        source_kind="external",
        external_source_id="external-source-one",
        worksheet_mode="selected",
        worksheet_name="Products",
        data_start_row=2,
        status="active",
        version=1,
        owner_user_id=user.id,
    )
    db.add_all([user, source])
    db.commit()
    return source


def _succeeded_run(db: Session, source_id: str, *, key: str | None = None) -> dict[str, object]:
    runs = SourceAcquisitionService(db)
    run = runs.request_run(
        source_id=source_id,
        trigger_kind="manual",
        idempotency_key=key,
        request_payload={"operation": "acquire"},
    )
    runs.start_run(str(run["id"]), worker_id="worker", lease_seconds=60)
    return runs.succeed_run(str(run["id"]), worker_id="worker", result="observed")


def _payload() -> dict[str, object]:
    return {
        "resource_identity": "nextcloud:file:123",
        "provenance": {"capture_contract": "v1", "provider": "webdav"},
        "evidence": [
            {"kind": "provider_receipt", "reference": "receipt:123", "metadata": {"status": 200}},
            {"kind": "capture_manifest", "reference": "manifest:abc", "metadata": {"bytes": 1024}},
        ],
        "snapshot_references": [
            {
                "kind": "capture_manifest",
                "reference": "snapshot:abc",
                "checksum": "a" * 64,
                "metadata": {"format": "xlsx"},
            }
        ],
    }


def test_successful_run_creates_immutable_observation_with_provenance_and_evidence_chain() -> None:
    db = _session()
    source = _source(db)
    run = _succeeded_run(db, source.id)
    service = SourceObservationService(db)
    observation = service.record_observation(acquisition_run_id=str(run["id"]), **_payload())

    assert observation["sourceId"] == source.id
    assert observation["acquisitionRunId"] == run["id"]
    assert observation["observationVersion"] == 1
    assert observation["provenance"] == {"capture_contract": "v1", "provider": "webdav"}
    assert len(observation["evidence"]) == 2
    assert observation["evidence"][1]["previousEvidenceChecksum"] == observation["evidence"][0]["checksum"]
    assert observation["snapshotReferences"][0]["reference"] == "snapshot:abc"

    persisted = db.get(SourceObservation, str(observation["id"]))
    assert persisted is not None
    persisted.resource_identity = "mutated"
    with pytest.raises(ImmutableRecordError):
        db.commit()
    db.rollback()


def test_exact_observation_replay_is_idempotent_but_divergent_replay_conflicts() -> None:
    db = _session()
    source = _source(db)
    run = _succeeded_run(db, source.id)
    service = SourceObservationService(db)
    first = service.record_observation(acquisition_run_id=str(run["id"]), **_payload())
    replay = service.record_observation(acquisition_run_id=str(run["id"]), **_payload())
    assert replay["id"] == first["id"]

    changed = _payload()
    changed["provenance"] = {"capture_contract": "v2", "provider": "webdav"}
    with pytest.raises(SourceAcquisitionError, match="observation_replay_conflict"):
        service.record_observation(acquisition_run_id=str(run["id"]), **changed)


def test_observation_requires_successful_run_and_rolls_back_invalid_persistence() -> None:
    db = _session()
    source = _source(db)
    run_service = SourceAcquisitionService(db)
    pending = run_service.request_run(
        source_id=source.id,
        trigger_kind="manual",
        request_payload={"operation": "acquire"},
    )
    service = SourceObservationService(db)
    with pytest.raises(SourceAcquisitionError, match="observation_run_not_succeeded"):
        service.record_observation(acquisition_run_id=str(pending["id"]), **_payload())

    run_service.request_cancellation(str(pending["id"]), requester_user_id=1)
    succeeded = _succeeded_run(db, source.id)
    invalid = _payload()
    invalid["snapshot_references"] = [{"kind": "capture_manifest", "reference": "x", "checksum": "bad"}]
    with pytest.raises(SourceAcquisitionError, match="snapshot_checksum_invalid"):
        service.record_observation(acquisition_run_id=str(succeeded["id"]), **invalid)
    assert db.query(SourceObservation).count() == 0


def test_evidence_and_snapshot_references_append_without_mutating_observation() -> None:
    db = _session()
    source = _source(db)
    run = _succeeded_run(db, source.id)
    service = SourceObservationService(db)
    observation = service.record_observation(acquisition_run_id=str(run["id"]), **_payload())

    evidence = service.append_evidence(
        str(observation["id"]),
        evidence={"kind": "audit_receipt", "reference": "audit:1", "metadata": {"actor": "system"}},
    )
    assert evidence["sequenceNumber"] == 3
    assert evidence["previousEvidenceChecksum"] == observation["evidence"][-1]["checksum"]
    snapshot = service.link_snapshot(
        str(observation["id"]),
        snapshot_kind="workspace_snapshot",
        snapshot_reference="workspace:1",
        snapshot_checksum="b" * 64,
        metadata={"phase": "future"},
    )
    assert snapshot["reference"] == "workspace:1"
    assert service.link_snapshot(
        str(observation["id"]),
        snapshot_kind="workspace_snapshot",
        snapshot_reference="workspace:1",
        snapshot_checksum="b" * 64,
        metadata={"phase": "future"},
    )["id"] == snapshot["id"]

    persisted = db.get(SourceObservationEvidence, str(evidence["id"]))
    assert persisted is not None
    persisted.evidence_reference = "mutated"
    with pytest.raises(ImmutableRecordError):
        db.commit()
    db.rollback()
    link = db.get(SourceObservationSnapshotReference, str(snapshot["id"]))
    assert link is not None
    db.delete(link)
    with pytest.raises(ImmutableRecordError):
        db.commit()
    db.rollback()


def test_retry_lineage_produces_a_new_observation_without_mutating_prior_observation() -> None:
    db = _session()
    source = _source(db)
    runs = SourceAcquisitionService(db)
    original = runs.request_run(
        source_id=source.id,
        trigger_kind="manual",
        request_payload={"operation": "acquire"},
    )
    runs.start_run(str(original["id"]), worker_id="worker", lease_seconds=60)
    runs.fail_run(str(original["id"]), worker_id="worker", failure_code="provider_timeout")
    retry = runs.retry_run(str(original["id"]), idempotency_key="retry-1")
    runs.start_run(str(retry["id"]), worker_id="worker", lease_seconds=60)
    runs.succeed_run(str(retry["id"]), worker_id="worker", result="observed")

    observation = SourceObservationService(db).record_observation(
        acquisition_run_id=str(retry["id"]), **_payload()
    )
    assert observation["acquisitionRunId"] == retry["id"]
    assert retry["parentRunId"] == original["id"]
    assert retry["rootRunId"] == original["id"]
    assert observation["observationVersion"] == 1
    assert db.query(SourceObservation).filter_by(acquisition_run_id=original["id"]).count() == 0


def test_observation_versions_are_deterministic_per_source_scope_and_metadata_rejects_secrets() -> None:
    db = _session()
    source = _source(db)
    first = _succeeded_run(db, source.id, key="first")
    second = _succeeded_run(db, source.id, key="second")
    service = SourceObservationService(db)
    first_observation = service.record_observation(acquisition_run_id=str(first["id"]), **_payload())
    second_payload = _payload()
    second_payload["resource_identity"] = "nextcloud:file:124"
    second_observation = service.record_observation(acquisition_run_id=str(second["id"]), **second_payload)
    assert (first_observation["observationVersion"], second_observation["observationVersion"]) == (1, 2)

    third = _succeeded_run(db, source.id, key="third")
    unsafe = _payload()
    unsafe["provenance"] = {"access_token": "never-persist"}
    with pytest.raises(SourceAcquisitionError, match="provenance_sensitive_field"):
        service.record_observation(acquisition_run_id=str(third["id"]), **unsafe)
