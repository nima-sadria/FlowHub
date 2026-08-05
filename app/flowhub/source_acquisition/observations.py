"""Transactional persistence for immutable Source Observations and evidence."""

from __future__ import annotations

import json
import re
import unicodedata
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.flowhub.source_acquisition.errors import SourceAcquisitionError
from app.flowhub.source_acquisition.models import (
    AcquisitionRun,
    SourceObservation,
    SourceObservationEvidence,
    SourceObservationSnapshotReference,
    SourceObservationVersionHead,
)
from app.flowhub.unified_workspace.domain import checksum, utcnow


_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,79}$")
_SENSITIVE_KEY = re.compile(r"password|secret|token|authorization|cookie", re.IGNORECASE)
_MAX_METADATA_BYTES = 16 * 1024


class SourceObservationService:
    """Stores source facts without invoking or knowing any provider transport."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def record_observation(
        self,
        *,
        acquisition_run_id: str,
        resource_identity: str,
        provenance: dict[str, Any],
        evidence: list[dict[str, Any]],
        snapshot_references: list[dict[str, Any]] | None = None,
        observed_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Create exactly one immutable Observation for a successful Run.

        A repeated command may only replay an identical record; divergent
        evidence or provenance for the same Run is a durable conflict.
        """

        run = self._run_or_error(acquisition_run_id)
        if run.status != "succeeded":
            raise SourceAcquisitionError("observation_run_not_succeeded")
        resource_identity = self._text(resource_identity, "resource_identity", 240)
        provenance = self._metadata(provenance, "provenance")
        prepared_evidence = [self._prepare_evidence(item) for item in evidence]
        if not prepared_evidence:
            raise SourceAcquisitionError("observation_evidence_required")
        prepared_snapshots = [
            self._prepare_snapshot_reference(item) for item in (snapshot_references or [])
        ]
        observed_at = observed_at or run.terminal_at or utcnow()
        resource_identity_hash = checksum({"resource_identity": resource_identity})

        existing = (
            self.db.query(SourceObservation)
            .filter(SourceObservation.acquisition_run_id == run.id)
            .one_or_none()
        )
        if existing is not None:
            self._assert_exact_replay(
                existing,
                resource_identity_hash=resource_identity_hash,
                provenance=provenance,
                evidence=prepared_evidence,
                snapshots=prepared_snapshots,
            )
            return self.observation(existing.id)

        version = self._next_version(run.source_id, run.resource_scope, observed_at)
        core = {
            "acquisition_run_id": run.id,
            "source_id": run.source_id,
            "resource_scope": run.resource_scope,
            "resource_identity_hash": resource_identity_hash,
            "observation_version": version,
            "observed_at": observed_at.isoformat(),
            "provenance": provenance,
        }
        row = SourceObservation(
            id=str(uuid.uuid4()),
            acquisition_run_id=run.id,
            source_id=run.source_id,
            resource_scope=run.resource_scope,
            resource_identity=resource_identity,
            resource_identity_hash=resource_identity_hash,
            observation_version=version,
            observed_at=observed_at,
            provenance_json=provenance,
            checksum=checksum(core),
            created_at=observed_at,
        )
        try:
            self.db.add(row)
            previous_checksum: str | None = None
            for position, item in enumerate(prepared_evidence, start=1):
                evidence_checksum = checksum(
                    {
                        "observation_checksum": row.checksum,
                        "sequence_number": position,
                        "kind": item["kind"],
                        "reference": item["reference"],
                        "metadata": item["metadata"],
                        "previous_evidence_checksum": previous_checksum,
                    }
                )
                self.db.add(
                    SourceObservationEvidence(
                        id=str(uuid.uuid4()),
                        observation_id=row.id,
                        sequence_number=position,
                        evidence_kind=item["kind"],
                        evidence_reference=item["reference"],
                        previous_evidence_checksum=previous_checksum,
                        evidence_checksum=evidence_checksum,
                        metadata_json=item["metadata"],
                        recorded_at=observed_at,
                    )
                )
                previous_checksum = evidence_checksum
            for item in prepared_snapshots:
                self._add_snapshot_reference(row.id, item, linked_at=observed_at)
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = (
                self.db.query(SourceObservation)
                .filter(SourceObservation.acquisition_run_id == run.id)
                .one_or_none()
            )
            if existing is not None:
                self._assert_exact_replay(
                    existing,
                    resource_identity_hash=resource_identity_hash,
                    provenance=provenance,
                    evidence=prepared_evidence,
                    snapshots=prepared_snapshots,
                )
                return self.observation(existing.id)
            raise SourceAcquisitionError("observation_create_conflict")
        return self.observation(row.id)

    def append_evidence(
        self, observation_id: str, *, evidence: dict[str, Any], recorded_at: datetime | None = None
    ) -> dict[str, Any]:
        observation = self._observation_or_error(observation_id)
        item = self._prepare_evidence(evidence)
        recorded_at = recorded_at or utcnow()
        latest = (
            self.db.query(SourceObservationEvidence)
            .filter(SourceObservationEvidence.observation_id == observation.id)
            .order_by(SourceObservationEvidence.sequence_number.desc())
            .with_for_update()
            .first()
        )
        sequence_number = 1 if latest is None else latest.sequence_number + 1
        previous_checksum = latest.evidence_checksum if latest else None
        row = SourceObservationEvidence(
            id=str(uuid.uuid4()),
            observation_id=observation.id,
            sequence_number=sequence_number,
            evidence_kind=item["kind"],
            evidence_reference=item["reference"],
            previous_evidence_checksum=previous_checksum,
            evidence_checksum=checksum(
                {
                    "observation_checksum": observation.checksum,
                    "sequence_number": sequence_number,
                    "kind": item["kind"],
                    "reference": item["reference"],
                    "metadata": item["metadata"],
                    "previous_evidence_checksum": previous_checksum,
                }
            ),
            metadata_json=item["metadata"],
            recorded_at=recorded_at,
        )
        try:
            self.db.add(row)
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise SourceAcquisitionError("evidence_append_conflict")
        return self._evidence_shape(row)

    def link_snapshot(
        self,
        observation_id: str,
        *,
        snapshot_kind: str,
        snapshot_reference: str,
        snapshot_checksum: str,
        metadata: dict[str, Any] | None = None,
        linked_at: datetime | None = None,
    ) -> dict[str, Any]:
        observation = self._observation_or_error(observation_id)
        item = self._prepare_snapshot_reference(
            {
                "kind": snapshot_kind,
                "reference": snapshot_reference,
                "checksum": snapshot_checksum,
                "metadata": metadata or {},
            }
        )
        existing = (
            self.db.query(SourceObservationSnapshotReference)
            .filter(
                SourceObservationSnapshotReference.observation_id == observation.id,
                SourceObservationSnapshotReference.snapshot_kind == item["kind"],
                SourceObservationSnapshotReference.snapshot_reference == item["reference"],
            )
            .one_or_none()
        )
        if existing is not None:
            if existing.snapshot_checksum != item["checksum"] or existing.metadata_json != item["metadata"]:
                raise SourceAcquisitionError("snapshot_reference_conflict")
            return self._snapshot_shape(existing)
        try:
            row = self._add_snapshot_reference(
                observation.id, item, linked_at=linked_at or utcnow()
            )
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise SourceAcquisitionError("snapshot_reference_conflict")
        return self._snapshot_shape(row)

    def observation(self, observation_id: str) -> dict[str, Any]:
        observation = self._observation_or_error(observation_id)
        evidence = (
            self.db.query(SourceObservationEvidence)
            .filter(SourceObservationEvidence.observation_id == observation.id)
            .order_by(SourceObservationEvidence.sequence_number)
            .all()
        )
        snapshots = (
            self.db.query(SourceObservationSnapshotReference)
            .filter(SourceObservationSnapshotReference.observation_id == observation.id)
            .order_by(SourceObservationSnapshotReference.linked_at, SourceObservationSnapshotReference.id)
            .all()
        )
        return {
            "id": observation.id,
            "acquisitionRunId": observation.acquisition_run_id,
            "sourceId": observation.source_id,
            "resourceScope": observation.resource_scope,
            "resourceIdentity": observation.resource_identity,
            "resourceIdentityHash": observation.resource_identity_hash,
            "observationVersion": observation.observation_version,
            "observedAt": observation.observed_at,
            "provenance": observation.provenance_json,
            "checksum": observation.checksum,
            "createdAt": observation.created_at,
            "evidence": [self._evidence_shape(item) for item in evidence],
            "snapshotReferences": [self._snapshot_shape(item) for item in snapshots],
        }

    def _next_version(self, source_id: str, resource_scope: str, observed_at: datetime) -> int:
        head = (
            self.db.query(SourceObservationVersionHead)
            .filter(
                SourceObservationVersionHead.source_id == source_id,
                SourceObservationVersionHead.resource_scope == resource_scope,
            )
            .with_for_update()
            .one_or_none()
        )
        if head is None:
            head = SourceObservationVersionHead(
                source_id=source_id,
                resource_scope=resource_scope,
                next_version=2,
                updated_at=observed_at,
            )
            self.db.add(head)
            return 1
        version = head.next_version
        head.next_version += 1
        head.updated_at = observed_at
        return version

    def _add_snapshot_reference(
        self, observation_id: str, item: dict[str, Any], *, linked_at: datetime
    ) -> SourceObservationSnapshotReference:
        row = SourceObservationSnapshotReference(
            id=str(uuid.uuid4()),
            observation_id=observation_id,
            snapshot_kind=item["kind"],
            snapshot_reference=item["reference"],
            snapshot_checksum=item["checksum"],
            metadata_json=item["metadata"],
            linked_at=linked_at,
        )
        self.db.add(row)
        return row

    def _assert_exact_replay(
        self,
        observation: SourceObservation,
        *,
        resource_identity_hash: str,
        provenance: dict[str, Any],
        evidence: list[dict[str, Any]],
        snapshots: list[dict[str, Any]],
    ) -> None:
        persisted_evidence = (
            self.db.query(SourceObservationEvidence)
            .filter(SourceObservationEvidence.observation_id == observation.id)
            .order_by(SourceObservationEvidence.sequence_number)
            .all()
        )
        persisted_snapshots = (
            self.db.query(SourceObservationSnapshotReference)
            .filter(SourceObservationSnapshotReference.observation_id == observation.id)
            .order_by(SourceObservationSnapshotReference.snapshot_kind, SourceObservationSnapshotReference.snapshot_reference)
            .all()
        )
        expected_evidence = [(item["kind"], item["reference"], item["metadata"]) for item in evidence]
        actual_evidence = [
            (item.evidence_kind, item.evidence_reference, item.metadata_json) for item in persisted_evidence
        ]
        expected_snapshots = sorted(
            (item["kind"], item["reference"], item["checksum"], item["metadata"])
            for item in snapshots
        )
        actual_snapshots = [
            (item.snapshot_kind, item.snapshot_reference, item.snapshot_checksum, item.metadata_json)
            for item in persisted_snapshots
        ]
        if (
            observation.resource_identity_hash != resource_identity_hash
            or observation.provenance_json != provenance
            or actual_evidence != expected_evidence
            or actual_snapshots != expected_snapshots
        ):
            raise SourceAcquisitionError("observation_replay_conflict")

    def _run_or_error(self, run_id: str) -> AcquisitionRun:
        row = self.db.get(AcquisitionRun, run_id)
        if row is None:
            raise SourceAcquisitionError("run_not_found")
        return row

    def _observation_or_error(self, observation_id: str) -> SourceObservation:
        row = self.db.get(SourceObservation, observation_id)
        if row is None:
            raise SourceAcquisitionError("observation_not_found")
        return row

    @staticmethod
    def _text(value: object, field: str, limit: int) -> str:
        normalized = unicodedata.normalize("NFKC", str(value)).strip()
        if not normalized or len(normalized) > limit:
            raise SourceAcquisitionError(f"{field}_invalid")
        return normalized

    @classmethod
    def _kind(cls, value: object, field: str) -> str:
        normalized = cls._text(value, field, 80).lower()
        if not _IDENTIFIER.fullmatch(normalized):
            raise SourceAcquisitionError(f"{field}_invalid")
        return normalized

    @classmethod
    def _metadata(cls, value: object, field: str) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise SourceAcquisitionError(f"{field}_invalid")
        cls._assert_safe_metadata(value)
        try:
            encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise SourceAcquisitionError(f"{field}_invalid") from exc
        if len(encoded.encode("utf-8")) > _MAX_METADATA_BYTES:
            raise SourceAcquisitionError(f"{field}_too_large")
        return value

    @classmethod
    def _assert_safe_metadata(cls, value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if _SENSITIVE_KEY.search(str(key)):
                    raise SourceAcquisitionError("provenance_sensitive_field")
                cls._assert_safe_metadata(child)
        elif isinstance(value, list):
            for child in value:
                cls._assert_safe_metadata(child)

    @classmethod
    def _prepare_evidence(cls, value: object) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise SourceAcquisitionError("evidence_invalid")
        return {
            "kind": cls._kind(value.get("kind"), "evidence_kind"),
            "reference": cls._text(value.get("reference"), "evidence_reference", 500),
            "metadata": cls._metadata(value.get("metadata") or {}, "evidence_metadata"),
        }

    @classmethod
    def _prepare_snapshot_reference(cls, value: object) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise SourceAcquisitionError("snapshot_reference_invalid")
        checksum_value = cls._text(value.get("checksum"), "snapshot_checksum", 64)
        if not re.fullmatch(r"[0-9a-f]{64}", checksum_value):
            raise SourceAcquisitionError("snapshot_checksum_invalid")
        return {
            "kind": cls._kind(value.get("kind"), "snapshot_kind"),
            "reference": cls._text(value.get("reference"), "snapshot_reference", 240),
            "checksum": checksum_value,
            "metadata": cls._metadata(value.get("metadata") or {}, "snapshot_metadata"),
        }

    @staticmethod
    def _evidence_shape(row: SourceObservationEvidence) -> dict[str, Any]:
        return {
            "id": row.id,
            "sequenceNumber": row.sequence_number,
            "kind": row.evidence_kind,
            "reference": row.evidence_reference,
            "previousEvidenceChecksum": row.previous_evidence_checksum,
            "checksum": row.evidence_checksum,
            "metadata": row.metadata_json,
            "recordedAt": row.recorded_at,
        }

    @staticmethod
    def _snapshot_shape(row: SourceObservationSnapshotReference) -> dict[str, Any]:
        return {
            "id": row.id,
            "kind": row.snapshot_kind,
            "reference": row.snapshot_reference,
            "checksum": row.snapshot_checksum,
            "metadata": row.metadata_json,
            "linkedAt": row.linked_at,
        }
