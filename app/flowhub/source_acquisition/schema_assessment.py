"""Immutable Source schema assessment over persisted Observation evidence only."""

from __future__ import annotations

import json
import re
import unicodedata
import uuid
from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.flowhub.source_acquisition.errors import SourceAcquisitionError
from app.flowhub.source_acquisition.models import (
    SourceMappingSchemaExpectation,
    SourceObservation,
    SourceObservationEvidence,
    SourceSchemaAssessment,
    SourceSchemaDiagnostic,
    SourceSchemaDriftRecord,
)
from app.flowhub.source_workspace.models import SourceFieldMapping, SourceMappingRevision
from app.flowhub.unified_workspace.domain import checksum, utcnow


CANONICALIZATION_VERSION = "header-canonical-v1"
ASSESSMENT_ALGORITHM_VERSION = "schema-assessment-v1"
SCHEMA_STAGE_ID = "source_schema_assessment"
_CODE = re.compile(r"^[a-z][a-z0-9_]{0,119}$")
_VERSION = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")
_BIDI = re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]")
_SPACE_OR_ZWNJ = re.compile(r"[\s\u200c]+")
_SENSITIVE_KEY = re.compile(r"password|secret|token|authorization|cookie", re.IGNORECASE)
_MAX_HEADERS = 500
_MAX_JSON_BYTES = 64 * 1024
_EXECUTION_STATUSES = {
    "not_run",
    "pending",
    "running",
    "passed",
    "failed",
    "skipped",
    "not_applicable",
}


class SourceSchemaAssessmentService:
    """Persists deterministic compatibility facts without parsing or provider I/O."""

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def canonicalize_header(value: object) -> str:
        """Return the v1 comparison form while callers retain the raw header."""

        raw = unicodedata.normalize("NFKC", str(value))
        raw = raw.replace("\u064a", "\u06cc").replace("\u0649", "\u06cc")
        raw = raw.replace("\u0643", "\u06a9")
        raw = _BIDI.sub("", raw)
        return _SPACE_OR_ZWNJ.sub("", raw).casefold()

    @classmethod
    def fingerprint(cls, headers: list[str], *, canonical: bool) -> str:
        values = [cls.canonicalize_header(item) for item in headers] if canonical else list(headers)
        return checksum(
            {
                "algorithm": CANONICALIZATION_VERSION,
                "representation": "canonical" if canonical else "raw",
                "headers": values,
            }
        )

    def create_mapping_expectation(
        self,
        *,
        mapping_revision_id: str,
        raw_headers: list[object],
        created_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Freeze expected schema for one immutable Mapping revision exactly once."""

        mapping = self.db.get(SourceMappingRevision, mapping_revision_id)
        if mapping is None:
            raise SourceAcquisitionError("mapping_revision_not_found")
        raw = self._headers(raw_headers, field="expected_headers", reject_blank=True)
        canonical = [self.canonicalize_header(value) for value in raw]
        if len(set(canonical)) != len(canonical):
            raise SourceAcquisitionError("expected_schema_canonical_collision")
        required = self._required_mapping_headers(mapping.id)
        missing = sorted(set(required) - set(canonical))
        if missing:
            raise SourceAcquisitionError("expected_schema_required_header_missing")
        document = {
            "mapping_revision_id": mapping.id,
            "source_id": mapping.source_id,
            "canonicalization_version": CANONICALIZATION_VERSION,
            "raw_headers": raw,
            "canonical_headers": canonical,
            "required_canonical_headers": required,
        }
        document_checksum = checksum(document)
        existing = (
            self.db.query(SourceMappingSchemaExpectation)
            .filter(SourceMappingSchemaExpectation.mapping_revision_id == mapping.id)
            .one_or_none()
        )
        if existing is not None:
            if existing.checksum != document_checksum:
                raise SourceAcquisitionError("mapping_schema_expectation_conflict")
            return self.expectation(existing.id)
        now = created_at or utcnow()
        row = SourceMappingSchemaExpectation(
            id=str(uuid.uuid4()),
            source_id=mapping.source_id,
            mapping_revision_id=mapping.id,
            canonicalization_version=CANONICALIZATION_VERSION,
            raw_headers_json=raw,
            canonical_headers_json=canonical,
            raw_fingerprint=self.fingerprint(raw, canonical=False),
            canonical_fingerprint=self.fingerprint(raw, canonical=True),
            required_canonical_headers_json=required,
            checksum=document_checksum,
            created_at=now,
        )
        try:
            self.db.add(row)
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = (
                self.db.query(SourceMappingSchemaExpectation)
                .filter(SourceMappingSchemaExpectation.mapping_revision_id == mapping.id)
                .one_or_none()
            )
            if existing is not None and existing.checksum == document_checksum:
                return self.expectation(existing.id)
            raise SourceAcquisitionError("mapping_schema_expectation_conflict")
        return self.expectation(row.id)

    def assess(
        self,
        *,
        observation_id: str,
        mapping_revision_id: str | None,
        assessment_algorithm_version: str = ASSESSMENT_ALGORITHM_VERSION,
        assessed_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Compare one persisted Observation with one persisted Mapping contract."""

        observation = self._observation(observation_id)
        algorithm = self._version(assessment_algorithm_version, "assessment_algorithm_version")
        mapping, expectation, identity = self._mapping_context(
            observation.source_id, mapping_revision_id
        )
        existing = self._existing(observation.id, identity, algorithm)
        if existing is not None:
            return self.assessment(existing.id)
        now = assessed_at or utcnow()
        try:
            observed_raw = self._observed_headers(observation.id)
        except SourceAcquisitionError as exc:
            return self._persist(
                observation=observation,
                mapping=mapping,
                expectation=expectation,
                mapping_identity=identity,
                algorithm=algorithm,
                execution_status="failed",
                schema_status=None,
                observed_raw=[],
                expected_raw=expectation.raw_headers_json if expectation else [],
                diffs=[],
                diagnostics=[
                    self._diagnostic(
                        "assessment_failed",
                        "repair_observation_evidence",
                        {"cause_code": exc.code},
                    )
                ],
                assessed_at=now,
            )
        if expectation is None:
            return self._persist(
                observation=observation,
                mapping=mapping,
                expectation=None,
                mapping_identity=identity,
                algorithm=algorithm,
                execution_status="passed",
                schema_status="no_mapping",
                observed_raw=observed_raw,
                expected_raw=[],
                diffs=[],
                diagnostics=[self._diagnostic("no_mapping", "configure_mapping")],
                assessed_at=now,
            )
        status, diffs, diagnostics = self._compare(observed_raw, expectation)
        return self._persist(
            observation=observation,
            mapping=mapping,
            expectation=expectation,
            mapping_identity=identity,
            algorithm=algorithm,
            execution_status="passed",
            schema_status=status,
            observed_raw=observed_raw,
            expected_raw=expectation.raw_headers_json,
            diffs=diffs,
            diagnostics=diagnostics,
            assessed_at=now,
        )

    def record_execution_state(
        self,
        *,
        observation_id: str,
        mapping_revision_id: str | None,
        execution_status: str,
        reason_code: str,
        recommended_action_code: str,
        action_parameters: dict[str, Any] | None = None,
        assessment_algorithm_version: str = ASSESSMENT_ALGORITHM_VERSION,
        assessed_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Persist a non-comparison terminal/state fact without fabricating health."""

        if execution_status not in _EXECUTION_STATUSES - {"passed"}:
            raise SourceAcquisitionError("assessment_execution_status_invalid")
        observation = self._observation(observation_id)
        algorithm = self._version(assessment_algorithm_version, "assessment_algorithm_version")
        mapping, expectation, identity = self._mapping_context(
            observation.source_id, mapping_revision_id
        )
        existing = self._existing(observation.id, identity, algorithm)
        if existing is not None:
            return self.assessment(existing.id)
        return self._persist(
            observation=observation,
            mapping=mapping,
            expectation=expectation,
            mapping_identity=identity,
            algorithm=algorithm,
            execution_status=execution_status,
            schema_status=None,
            observed_raw=[],
            expected_raw=expectation.raw_headers_json if expectation else [],
            diffs=[],
            diagnostics=[
                self._diagnostic(reason_code, recommended_action_code, action_parameters or {})
            ],
            assessed_at=assessed_at or utcnow(),
        )

    def expectation(self, expectation_id: str) -> dict[str, Any]:
        row = self.db.get(SourceMappingSchemaExpectation, expectation_id)
        if row is None:
            raise SourceAcquisitionError("mapping_schema_expectation_not_found")
        return {
            "id": row.id,
            "sourceId": row.source_id,
            "mappingRevisionId": row.mapping_revision_id,
            "canonicalizationVersion": row.canonicalization_version,
            "rawHeaders": row.raw_headers_json,
            "canonicalHeaders": row.canonical_headers_json,
            "rawFingerprint": row.raw_fingerprint,
            "canonicalFingerprint": row.canonical_fingerprint,
            "requiredCanonicalHeaders": row.required_canonical_headers_json,
            "checksum": row.checksum,
            "createdAt": row.created_at,
        }

    def assessment(self, assessment_id: str) -> dict[str, Any]:
        row = self.db.get(SourceSchemaAssessment, assessment_id)
        if row is None:
            raise SourceAcquisitionError("schema_assessment_not_found")
        diffs = (
            self.db.query(SourceSchemaDriftRecord)
            .filter(SourceSchemaDriftRecord.assessment_id == row.id)
            .order_by(SourceSchemaDriftRecord.sequence_number)
            .all()
        )
        diagnostics = (
            self.db.query(SourceSchemaDiagnostic)
            .filter(SourceSchemaDiagnostic.assessment_id == row.id)
            .order_by(SourceSchemaDiagnostic.sequence_number)
            .all()
        )
        freshness = self._freshness(row)
        return {
            "id": row.id,
            "observationId": row.observation_id,
            "sourceId": row.source_id,
            "resourceScope": row.resource_scope,
            "mappingRevisionId": row.mapping_revision_id,
            "mappingExpectationId": row.mapping_expectation_id,
            "assessmentAlgorithmVersion": row.assessment_algorithm_version,
            "canonicalizationVersion": row.canonicalization_version,
            "executionStatus": row.execution_status,
            "schemaStatus": row.schema_status,
            "freshness": freshness,
            "freshnessBasis": row.freshness_basis_json,
            "observed": self._schema_shape(
                row.observed_raw_headers_json,
                row.observed_canonical_headers_json,
                row.observed_raw_fingerprint,
                row.observed_canonical_fingerprint,
            ),
            "expected": self._schema_shape(
                row.expected_raw_headers_json,
                row.expected_canonical_headers_json,
                row.expected_raw_fingerprint,
                row.expected_canonical_fingerprint,
            ),
            "diffs": [self._diff_shape(item) for item in diffs],
            "diagnostics": [self._diagnostic_shape(item, freshness) for item in diagnostics],
            "checksum": row.checksum,
            "assessedAt": row.assessed_at,
            "createdAt": row.created_at,
        }

    def _mapping_context(
        self, source_id: str, mapping_revision_id: str | None
    ) -> tuple[SourceMappingRevision | None, SourceMappingSchemaExpectation | None, str]:
        if mapping_revision_id is None:
            return None, None, "no_mapping"
        mapping = self.db.get(SourceMappingRevision, mapping_revision_id)
        if mapping is None:
            raise SourceAcquisitionError("mapping_revision_not_found")
        if mapping.source_id != source_id:
            raise SourceAcquisitionError("mapping_revision_source_mismatch")
        expectation = (
            self.db.query(SourceMappingSchemaExpectation)
            .filter(SourceMappingSchemaExpectation.mapping_revision_id == mapping.id)
            .one_or_none()
        )
        return mapping, expectation, f"mapping:{mapping.id}"

    def _compare(
        self, observed_raw: list[str], expectation: SourceMappingSchemaExpectation
    ) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        observed = [self.canonicalize_header(value) for value in observed_raw]
        expected_raw = expectation.raw_headers_json
        expected = expectation.canonical_headers_json
        diffs: list[dict[str, Any]] = []
        diagnostics: list[dict[str, Any]] = []
        raw_counts = Counter(observed_raw)
        canonical_counts = Counter(observed)
        for index, raw in enumerate(observed_raw, start=1):
            canonical = observed[index - 1]
            if not canonical:
                diffs.append(self._diff("unsupported_shape", observed_position=index, observed_raw=raw, observed_canonical=canonical))
            elif raw_counts[raw] > 1:
                diffs.append(self._diff("duplicate_header", observed_position=index, observed_raw=raw, observed_canonical=canonical))
            elif canonical_counts[canonical] > 1:
                diffs.append(self._diff("canonical_collision", observed_position=index, observed_raw=raw, observed_canonical=canonical))
        if diffs:
            reasons = {item["change_kind"] for item in diffs}
            if "duplicate_header" in reasons:
                diagnostics.append(self._diagnostic("duplicate_header", "rename_duplicate_header"))
            if "canonical_collision" in reasons:
                diagnostics.append(self._diagnostic("canonical_collision", "rename_colliding_header"))
            if "unsupported_shape" in reasons:
                diagnostics.append(self._diagnostic("unsupported_field_shape", "repair_header_shape"))
            return "ambiguous", diffs, diagnostics

        observed_positions = {value: index for index, value in enumerate(observed, start=1)}
        expected_positions = {value: index for index, value in enumerate(expected, start=1)}
        added = [value for value in observed if value not in expected_positions]
        removed = [value for value in expected if value not in observed_positions]
        if len(added) == len(removed) == 1:
            added_value, removed_value = added[0], removed[0]
            if observed_positions[added_value] == expected_positions[removed_value]:
                diffs.append(
                    self._diff(
                        "rename_candidate",
                        expected_position=expected_positions[removed_value],
                        observed_position=observed_positions[added_value],
                        expected_raw=expected_raw[expected_positions[removed_value] - 1],
                        expected_canonical=removed_value,
                        observed_raw=observed_raw[observed_positions[added_value] - 1],
                        observed_canonical=added_value,
                        confidence="exact_position",
                        evidence={"basis": "one_removed_one_added_same_position"},
                    )
                )
                diagnostics.append(self._diagnostic("schema_drift", "review_rename_candidate"))
                return "drift", diffs, diagnostics
            diagnostics.append(self._diagnostic("ambiguous_mapping", "review_mapping"))
            return "ambiguous", [], diagnostics
        for value in added:
            diffs.append(
                self._diff(
                    "added",
                    observed_position=observed_positions[value],
                    observed_raw=observed_raw[observed_positions[value] - 1],
                    observed_canonical=value,
                )
            )
        for value in removed:
            diffs.append(
                self._diff(
                    "removed",
                    expected_position=expected_positions[value],
                    expected_raw=expected_raw[expected_positions[value] - 1],
                    expected_canonical=value,
                )
            )
        if added:
            diagnostics.append(self._diagnostic("headers_added", "review_observed_headers"))
        if removed:
            diagnostics.append(self._diagnostic("headers_removed", "update_mapping"))
        observed_set = set(observed)
        for required in expectation.required_canonical_headers_json:
            if required not in observed_set:
                diffs.append(
                    self._diff(
                        "required_field_missing",
                        expected_position=expected_positions.get(required),
                        expected_raw=expected_raw[expected_positions[required] - 1] if required in expected_positions else None,
                        expected_canonical=required,
                    )
                )
                diagnostics.append(self._diagnostic("required_field_missing", "restore_required_header"))
        if not added and not removed and observed != expected:
            for value in expected:
                if observed_positions[value] != expected_positions[value]:
                    diffs.append(
                        self._diff(
                            "reordered",
                            expected_position=expected_positions[value],
                            observed_position=observed_positions[value],
                            expected_raw=expected_raw[expected_positions[value] - 1],
                            expected_canonical=value,
                            observed_raw=observed_raw[observed_positions[value] - 1],
                            observed_canonical=value,
                        )
                    )
            diagnostics.append(self._diagnostic("headers_reordered", "review_column_order"))
        if diffs:
            if not diagnostics:
                diagnostics.append(self._diagnostic("schema_drift", "review_mapping"))
            return "drift", diffs, diagnostics
        return "match", [], [self._diagnostic("schema_match", "none")]

    def _persist(
        self,
        *,
        observation: SourceObservation,
        mapping: SourceMappingRevision | None,
        expectation: SourceMappingSchemaExpectation | None,
        mapping_identity: str,
        algorithm: str,
        execution_status: str,
        schema_status: str | None,
        observed_raw: list[str],
        expected_raw: list[str],
        diffs: list[dict[str, Any]],
        diagnostics: list[dict[str, Any]],
        assessed_at: datetime,
    ) -> dict[str, Any]:
        observed_canonical = [self.canonicalize_header(value) for value in observed_raw]
        expected_canonical = [self.canonicalize_header(value) for value in expected_raw]
        freshness_basis = {
            "observation_checksum": observation.checksum,
            "observation_version": observation.observation_version,
            "observation_observed_at": observation.observed_at.isoformat(),
            "mapping_revision_id": mapping.id if mapping else None,
            "mapping_checksum": mapping.checksum if mapping else None,
            "mapping_expectation_checksum": expectation.checksum if expectation else None,
            "assessment_algorithm_version": algorithm,
            "canonicalization_version": CANONICALIZATION_VERSION,
        }
        document = {
            "observation_id": observation.id,
            "mapping_identity": mapping_identity,
            "algorithm": algorithm,
            "execution_status": execution_status,
            "schema_status": schema_status,
            "observed_raw": observed_raw,
            "expected_raw": expected_raw,
            "diffs": diffs,
            "diagnostics": diagnostics,
            "freshness_basis": freshness_basis,
        }
        document_checksum = checksum(document)
        existing = self._existing(observation.id, mapping_identity, algorithm)
        if existing is not None:
            if existing.checksum != document_checksum:
                raise SourceAcquisitionError("schema_assessment_replay_conflict")
            return self.assessment(existing.id)
        row = SourceSchemaAssessment(
            id=str(uuid.uuid4()),
            observation_id=observation.id,
            source_id=observation.source_id,
            resource_scope=observation.resource_scope,
            mapping_revision_id=mapping.id if mapping else None,
            mapping_expectation_id=expectation.id if expectation else None,
            mapping_identity=mapping_identity,
            assessment_algorithm_version=algorithm,
            canonicalization_version=CANONICALIZATION_VERSION,
            execution_status=execution_status,
            schema_status=schema_status,
            observed_raw_headers_json=observed_raw,
            observed_canonical_headers_json=observed_canonical,
            expected_raw_headers_json=expected_raw,
            expected_canonical_headers_json=expected_canonical,
            observed_raw_fingerprint=self.fingerprint(observed_raw, canonical=False) if observed_raw else None,
            observed_canonical_fingerprint=self.fingerprint(observed_raw, canonical=True) if observed_raw else None,
            expected_raw_fingerprint=self.fingerprint(expected_raw, canonical=False) if expected_raw else None,
            expected_canonical_fingerprint=self.fingerprint(expected_raw, canonical=True) if expected_raw else None,
            freshness_basis_json=freshness_basis,
            duration_ms=None,
            checksum=document_checksum,
            assessed_at=assessed_at,
            created_at=assessed_at,
        )
        try:
            self.db.add(row)
            self.db.flush()
            for position, item in enumerate(diffs, start=1):
                self.db.add(
                    SourceSchemaDriftRecord(
                        id=str(uuid.uuid4()),
                        assessment_id=row.id,
                        sequence_number=position,
                        change_kind=item["change_kind"],
                        expected_position=item.get("expected_position"),
                        observed_position=item.get("observed_position"),
                        expected_raw_value=item.get("expected_raw"),
                        expected_canonical_value=item.get("expected_canonical"),
                        observed_raw_value=item.get("observed_raw"),
                        observed_canonical_value=item.get("observed_canonical"),
                        confidence=item.get("confidence"),
                        evidence_json=item.get("evidence", {}),
                        algorithm_version=algorithm,
                        created_at=assessed_at,
                    )
                )
            for position, item in enumerate(diagnostics, start=1):
                self.db.add(
                    SourceSchemaDiagnostic(
                        id=str(uuid.uuid4()),
                        assessment_id=row.id,
                        sequence_number=position,
                        stage_id=SCHEMA_STAGE_ID,
                        execution_status=execution_status,
                        reason_code=item["reason_code"],
                        recommended_action_code=item["action_code"],
                        action_parameters_json=item["parameters"],
                        duration_ms=None,
                        created_at=assessed_at,
                    )
                )
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = self._existing(observation.id, mapping_identity, algorithm)
            if existing is not None and existing.checksum == document_checksum:
                return self.assessment(existing.id)
            raise SourceAcquisitionError("schema_assessment_replay_conflict")
        return self.assessment(row.id)

    def _freshness(self, assessment: SourceSchemaAssessment) -> str:
        if assessment.execution_status in {"not_run", "pending", "running", "skipped", "not_applicable"}:
            return "unknown"
        if assessment.assessment_algorithm_version != ASSESSMENT_ALGORITHM_VERSION:
            return "stale"
        latest_observation = (
            self.db.query(func.max(SourceObservation.observation_version))
            .filter(
                SourceObservation.source_id == assessment.source_id,
                SourceObservation.resource_scope == assessment.resource_scope,
            )
            .scalar()
        )
        observed_version = assessment.freshness_basis_json.get("observation_version")
        if latest_observation is None or observed_version is None:
            return "unknown"
        if latest_observation > observed_version:
            return "stale"
        latest_mapping = (
            self.db.query(SourceMappingRevision)
            .filter(SourceMappingRevision.source_id == assessment.source_id)
            .order_by(SourceMappingRevision.version.desc())
            .first()
        )
        if assessment.mapping_revision_id is None:
            return "stale" if latest_mapping is not None else "current"
        if latest_mapping is None or latest_mapping.id != assessment.mapping_revision_id:
            return "stale"
        return "current"

    def _observed_headers(self, observation_id: str) -> list[str]:
        records = (
            self.db.query(SourceObservationEvidence)
            .filter(
                SourceObservationEvidence.observation_id == observation_id,
                SourceObservationEvidence.evidence_kind == "schema_headers",
            )
            .order_by(SourceObservationEvidence.sequence_number)
            .all()
        )
        if len(records) != 1:
            raise SourceAcquisitionError("assessment_not_run")
        return self._headers(records[0].metadata_json.get("headers"), field="observed_headers", reject_blank=False)

    def _required_mapping_headers(self, mapping_revision_id: str) -> list[str]:
        fields = (
            self.db.query(SourceFieldMapping)
            .filter(
                SourceFieldMapping.mapping_revision_id == mapping_revision_id,
                SourceFieldMapping.required.is_(True),
                SourceFieldMapping.reference_type == "header_name",
            )
            .order_by(SourceFieldMapping.field)
            .all()
        )
        return sorted({self.canonicalize_header(item.reference_value or "") for item in fields})

    def _existing(self, observation_id: str, mapping_identity: str, algorithm: str) -> SourceSchemaAssessment | None:
        return (
            self.db.query(SourceSchemaAssessment)
            .filter(
                SourceSchemaAssessment.observation_id == observation_id,
                SourceSchemaAssessment.mapping_identity == mapping_identity,
                SourceSchemaAssessment.assessment_algorithm_version == algorithm,
            )
            .one_or_none()
        )

    def _observation(self, observation_id: str) -> SourceObservation:
        row = self.db.get(SourceObservation, observation_id)
        if row is None:
            raise SourceAcquisitionError("observation_not_found")
        return row

    @classmethod
    def _headers(cls, value: object, *, field: str, reject_blank: bool) -> list[str]:
        if not isinstance(value, list) or not value or len(value) > _MAX_HEADERS:
            raise SourceAcquisitionError(f"{field}_invalid")
        headers: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise SourceAcquisitionError(f"{field}_invalid")
            # Raw headers are evidence. Canonicalization is deliberately deferred
            # to the comparison path so a diff can show the original form.
            raw = item
            if len(raw) > 240 or (reject_blank and not raw.strip()):
                raise SourceAcquisitionError(f"{field}_invalid")
            headers.append(raw)
        cls._json_bound(headers, field)
        return headers

    @classmethod
    def _diagnostic(cls, reason_code: str, action_code: str, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
        if not _CODE.fullmatch(reason_code) or not _CODE.fullmatch(action_code):
            raise SourceAcquisitionError("diagnostic_code_invalid")
        values = parameters or {}
        if not isinstance(values, dict):
            raise SourceAcquisitionError("diagnostic_parameters_invalid")
        cls._json_bound(values, "diagnostic_parameters")
        return {"reason_code": reason_code, "action_code": action_code, "parameters": values}

    @staticmethod
    def _diff(change_kind: str, **values: Any) -> dict[str, Any]:
        return {"change_kind": change_kind, **{key: value for key, value in values.items() if value is not None}}

    @staticmethod
    def _version(value: str, field: str) -> str:
        normalized = str(value).strip()
        if not _VERSION.fullmatch(normalized):
            raise SourceAcquisitionError(f"{field}_invalid")
        return normalized

    @classmethod
    def _json_bound(cls, value: object, field: str) -> None:
        cls._assert_safe_metadata(value)
        try:
            encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise SourceAcquisitionError(f"{field}_invalid") from exc
        if len(encoded.encode("utf-8")) > _MAX_JSON_BYTES:
            raise SourceAcquisitionError(f"{field}_too_large")

    @classmethod
    def _assert_safe_metadata(cls, value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if _SENSITIVE_KEY.search(str(key)):
                    raise SourceAcquisitionError("diagnostic_sensitive_field")
                cls._assert_safe_metadata(child)
        elif isinstance(value, list):
            for child in value:
                cls._assert_safe_metadata(child)

    @staticmethod
    def _schema_shape(raw: list[str], canonical: list[str], raw_fingerprint: str | None, canonical_fingerprint: str | None) -> dict[str, Any]:
        return {"rawHeaders": raw, "canonicalHeaders": canonical, "rawFingerprint": raw_fingerprint, "canonicalFingerprint": canonical_fingerprint}

    @staticmethod
    def _diff_shape(row: SourceSchemaDriftRecord) -> dict[str, Any]:
        return {
            "sequenceNumber": row.sequence_number,
            "changeKind": row.change_kind,
            "expectedPosition": row.expected_position,
            "observedPosition": row.observed_position,
            "expectedRawValue": row.expected_raw_value,
            "expectedCanonicalValue": row.expected_canonical_value,
            "observedRawValue": row.observed_raw_value,
            "observedCanonicalValue": row.observed_canonical_value,
            "confidence": row.confidence,
            "evidence": row.evidence_json,
            "algorithmVersion": row.algorithm_version,
        }

    @staticmethod
    def _diagnostic_shape(row: SourceSchemaDiagnostic, freshness: str) -> dict[str, Any]:
        return {
            "stageId": row.stage_id,
            "executionStatus": row.execution_status,
            "freshness": freshness,
            "reasonCode": row.reason_code,
            "recommendedActionCode": row.recommended_action_code,
            "recommendedActionParameters": row.action_parameters_json,
            "durationMs": row.duration_ms,
            "createdAt": row.created_at,
        }
