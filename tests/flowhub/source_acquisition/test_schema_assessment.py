from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import FlowHubBase
from app.flowhub.source_acquisition.errors import SourceAcquisitionError
from app.flowhub.source_acquisition.models import (
    SourceMappingSchemaExpectation,
    SourceSchemaAssessment,
    SourceSchemaDiagnostic,
    SourceSchemaDriftRecord,
)
from app.flowhub.source_acquisition.observations import SourceObservationService
from app.flowhub.source_acquisition.schema_assessment import (
    ASSESSMENT_ALGORITHM_VERSION,
    CANONICALIZATION_VERSION,
    SourceSchemaAssessmentService,
)
from app.flowhub.source_acquisition.service import SourceAcquisitionService
from app.flowhub.source_workspace.models import SourceFieldMapping, SourceMappingRevision, SourceProfile
from app.flowhub.unified_workspace import models as _unified_workspace_models  # noqa: F401
from app.flowhub.unified_workspace.domain import ImmutableRecordError, checksum, utcnow


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    FlowHubBase.metadata.create_all(engine)
    return Session(engine)


def _source(db: Session) -> SourceProfile:
    user = FlowHubUser(id=1, username="owner", hashed_password="x", role="admin", is_active=True)
    source = SourceProfile(
        id="source-one", name="Source", source_kind="external", external_source_id="external-one",
        worksheet_mode="selected", worksheet_name="Products", data_start_row=2,
        status="active", version=1, owner_user_id=1,
    )
    db.add_all([user, source])
    db.commit()
    return source


def _observation(db: Session, source: SourceProfile, headers: list[str], *, key: str) -> dict[str, object]:
    runs = SourceAcquisitionService(db)
    run = runs.request_run(
        source_id=source.id, trigger_kind="manual", idempotency_key=key,
        request_payload={"operation": "acquire"},
    )
    runs.start_run(str(run["id"]), worker_id="worker", lease_seconds=60)
    runs.succeed_run(str(run["id"]), worker_id="worker", result="observed")
    return SourceObservationService(db).record_observation(
        acquisition_run_id=str(run["id"]),
        resource_identity="upload:binding-one",
        provenance={"capture_contract": "v1"},
        evidence=[{"kind": "schema_headers", "reference": f"headers:{key}", "metadata": {"headers": headers}}],
    )


def _mapping(db: Session, source: SourceProfile, *, version: int = 1, required: str | None = "Name") -> SourceMappingRevision:
    mapping = SourceMappingRevision(
        id=f"mapping-{version}", source_id=source.id, version=version,
        checksum=checksum({"mapping": version}), worksheet_mode="selected", worksheet_name="Products",
        data_start_row=2, value_policy_json={}, created_by_user_id=1, created_at=utcnow(),
    )
    db.add(mapping)
    if required:
        db.add(SourceFieldMapping(
            id=f"field-{version}", mapping_revision_id=mapping.id, field="name",
            reference_type="header_name", reference_value=required, required=True,
        ))
    db.commit()
    return mapping


def _assessed(db: Session, headers: list[str], expected: list[str], *, required: str | None = "Name") -> tuple[SourceSchemaAssessmentService, dict[str, object], SourceMappingRevision]:
    source = _source(db)
    observation = _observation(db, source, headers, key="one")
    mapping = _mapping(db, source, required=required)
    service = SourceSchemaAssessmentService(db)
    service.create_mapping_expectation(mapping_revision_id=mapping.id, raw_headers=expected)
    return service, observation, mapping


def test_exact_match_preserves_raw_and_canonical_schema() -> None:
    db = _session()
    service, observation, mapping = _assessed(db, [" Name ", "قیمت\u200cها"], ["Name", "قیمت ها"])
    result = service.assess(observation_id=str(observation["id"]), mapping_revision_id=mapping.id)
    assert result["executionStatus"] == "passed"
    assert result["schemaStatus"] == "match"
    assert result["freshness"] == "current"
    assert result["observed"]["rawHeaders"] == [" Name ", "قیمت\u200cها"]
    assert result["observed"]["canonicalHeaders"] == ["name", "قیمتها"]
    assert result["diagnostics"][0]["reasonCode"] == "schema_match"


@pytest.mark.parametrize(
    ("observed", "expected", "kind", "reason"),
    [
        (["Name", "Price", "Stock"], ["Name", "Price"], "added", "headers_added"),
        (["Name"], ["Name", "Price"], "removed", "headers_removed"),
        (["Price", "Name"], ["Name", "Price"], "reordered", "headers_reordered"),
    ],
)
def test_structural_drift_records_are_position_aware(
    observed: list[str], expected: list[str], kind: str, reason: str
) -> None:
    db = _session()
    service, observation, mapping = _assessed(db, observed, expected)
    result = service.assess(observation_id=str(observation["id"]), mapping_revision_id=mapping.id)
    assert result["schemaStatus"] == "drift"
    assert kind in {item["changeKind"] for item in result["diffs"]}
    assert reason in {item["reasonCode"] for item in result["diagnostics"]}


def test_duplicate_raw_and_canonical_collision_are_ambiguous() -> None:
    db = _session()
    service, observation, mapping = _assessed(db, ["Name", "Name"], ["Name", "Price"])
    duplicate = service.assess(observation_id=str(observation["id"]), mapping_revision_id=mapping.id)
    assert duplicate["schemaStatus"] == "ambiguous"
    assert {item["changeKind"] for item in duplicate["diffs"]} == {"duplicate_header"}

    second_db = _session()
    second_source = _source(second_db)
    second_observation = _observation(second_db, second_source, ["قيمت", "قیمت"], key="two")
    second_mapping = _mapping(second_db, second_source, required=None)
    second_service = SourceSchemaAssessmentService(second_db)
    second_service.create_mapping_expectation(mapping_revision_id=second_mapping.id, raw_headers=["قیمت", "Name"])
    collision = second_service.assess(observation_id=str(second_observation["id"]), mapping_revision_id=second_mapping.id)
    assert collision["schemaStatus"] == "ambiguous"
    assert "canonical_collision" in {item["changeKind"] for item in collision["diffs"]}


def test_no_mapping_and_ambiguous_rename_are_not_success() -> None:
    db = _session()
    source = _source(db)
    observation = _observation(db, source, ["Name", "Price"], key="one")
    service = SourceSchemaAssessmentService(db)
    no_mapping = service.assess(observation_id=str(observation["id"]), mapping_revision_id=None)
    assert no_mapping["schemaStatus"] == "no_mapping"
    assert no_mapping["diagnostics"][0]["recommendedActionCode"] == "configure_mapping"

    mapping = _mapping(db, source)
    service.create_mapping_expectation(
        mapping_revision_id=mapping.id,
        raw_headers=["Name", "Price", "Sku"],
    )
    other = _observation(db, source, ["Name", "Sku", "Amount"], key="two")
    ambiguous = service.assess(observation_id=str(other["id"]), mapping_revision_id=mapping.id)
    assert ambiguous["schemaStatus"] == "ambiguous"
    assert ambiguous["diagnostics"][0]["reasonCode"] == "ambiguous_mapping"


def test_rename_candidate_requires_unique_same_position_evidence() -> None:
    db = _session()
    service, observation, mapping = _assessed(db, ["Name", "Amount"], ["Name", "Price"])
    result = service.assess(observation_id=str(observation["id"]), mapping_revision_id=mapping.id)
    assert result["schemaStatus"] == "drift"
    candidate = result["diffs"][0]
    assert candidate["changeKind"] == "rename_candidate"
    assert candidate["confidence"] == "exact_position"


def test_required_field_missing_and_fingerprints_are_deterministic() -> None:
    db = _session()
    service, observation, mapping = _assessed(db, ["Price"], ["Name", "Price"])
    result = service.assess(observation_id=str(observation["id"]), mapping_revision_id=mapping.id)
    assert "required_field_missing" in {item["changeKind"] for item in result["diffs"]}
    assert "required_field_missing" in {item["reasonCode"] for item in result["diagnostics"]}
    assert SourceSchemaAssessmentService.fingerprint(["Name"], canonical=False) == SourceSchemaAssessmentService.fingerprint(["Name"], canonical=False)
    assert SourceSchemaAssessmentService.fingerprint([" Name "], canonical=True) == SourceSchemaAssessmentService.fingerprint(["Name"], canonical=True)
    assert SourceSchemaAssessmentService.fingerprint(["Name"], canonical=False) != SourceSchemaAssessmentService.fingerprint(["Price"], canonical=False)


def test_idempotency_retry_lineage_and_new_mapping_revision_are_independent() -> None:
    db = _session()
    service, observation, mapping = _assessed(db, ["Name", "Price"], ["Name", "Price"])
    first = service.assess(observation_id=str(observation["id"]), mapping_revision_id=mapping.id)
    assert service.assess(observation_id=str(observation["id"]), mapping_revision_id=mapping.id)["id"] == first["id"]
    source = db.get(SourceProfile, "source-one")
    assert source is not None
    newer_mapping = _mapping(db, source, version=2)
    service.create_mapping_expectation(mapping_revision_id=newer_mapping.id, raw_headers=["Name", "Price"])
    second = service.assess(observation_id=str(observation["id"]), mapping_revision_id=newer_mapping.id)
    assert second["id"] != first["id"]
    assert service.assessment(str(first["id"]))["freshness"] == "stale"
    newer_observation = _observation(db, source, ["Name", "Price"], key="two")
    retry_assessment = service.assess(observation_id=str(newer_observation["id"]), mapping_revision_id=newer_mapping.id)
    assert retry_assessment["id"] != second["id"]
    assert service.assessment(str(second["id"]))["freshness"] == "stale"


def test_execution_states_and_diagnostic_metadata_are_separate_and_safe() -> None:
    db = _session()
    source = _source(db)
    observation = _observation(db, source, ["Name"], key="one")
    service = SourceSchemaAssessmentService(db)
    not_run = service.record_execution_state(
        observation_id=str(observation["id"]), mapping_revision_id=None,
        execution_status="not_run", reason_code="assessment_not_run", recommended_action_code="run_assessment",
    )
    assert not_run["executionStatus"] == "not_run"
    assert not_run["freshness"] == "unknown"
    other = _observation(db, source, ["Name"], key="two")
    skipped = service.record_execution_state(
        observation_id=str(other["id"]), mapping_revision_id=None,
        execution_status="skipped", reason_code="assessment_not_run", recommended_action_code="run_assessment",
    )
    assert skipped["executionStatus"] == "skipped"
    with pytest.raises(SourceAcquisitionError, match="diagnostic_sensitive_field"):
        service.record_execution_state(
            observation_id=str(other["id"]), mapping_revision_id=None,
            execution_status="failed", reason_code="assessment_failed", recommended_action_code="repair",
            action_parameters={"token": "never"}, assessment_algorithm_version="schema-assessment-v2",
        )


def test_assessment_and_children_are_atomic_and_immutable() -> None:
    db = _session()
    service, observation, mapping = _assessed(db, ["Name"], ["Name"])
    result = service.assess(observation_id=str(observation["id"]), mapping_revision_id=mapping.id)
    row = db.get(SourceSchemaAssessment, str(result["id"]))
    assert row is not None
    row.schema_status = "drift"
    with pytest.raises(ImmutableRecordError):
        db.commit()
    db.rollback()
    assert db.query(SourceSchemaDriftRecord).count() == 0
    assert db.query(SourceSchemaDiagnostic).count() == 1
    with pytest.raises(SourceAcquisitionError, match="expected_schema_required_header_missing"):
        service.create_mapping_expectation(mapping_revision_id=mapping.id, raw_headers=["Price"])
    assert db.query(SourceMappingSchemaExpectation).count() == 1


def test_algorithm_version_change_projects_stale_without_mutating_assessment() -> None:
    db = _session()
    service, observation, mapping = _assessed(db, ["Name"], ["Name"])
    old = service.assess(
        observation_id=str(observation["id"]), mapping_revision_id=mapping.id,
        assessment_algorithm_version="schema-assessment-v0",
    )
    assert old["freshness"] == "stale"
    current = service.assess(observation_id=str(observation["id"]), mapping_revision_id=mapping.id)
    assert current["assessmentAlgorithmVersion"] == ASSESSMENT_ALGORITHM_VERSION
    assert current["freshness"] == "current"
    assert CANONICALIZATION_VERSION == "header-canonical-v1"
