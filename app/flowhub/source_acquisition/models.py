"""Append-safe persistence for Source Acquisition Run lifecycle state."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    event,
    inspect,
    text,
)
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from app.flowhub.database import FlowHubBase
from app.flowhub.unified_workspace.domain import ImmutableRecordError, utcnow


ACTIVE_RUN_STATUSES = ("queued", "running")
TERMINAL_RUN_STATUSES = ("succeeded", "failed", "cancelled", "abandoned")


class AcquisitionRun(FlowHubBase):
    """One requested Source read, without any provider execution implementation."""

    __tablename__ = "saq_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled','abandoned')",
            name="ck_saq_run_status",
        ),
        CheckConstraint(
            "result IN ('observed','not_modified','content_unchanged_reparse','none')",
            name="ck_saq_run_result",
        ),
        CheckConstraint(
            "(status IN ('queued','running') AND result = 'none') "
            "OR (status = 'succeeded' AND result IN "
            "('observed','not_modified','content_unchanged_reparse')) "
            "OR (status IN ('failed','cancelled','abandoned') AND result = 'none')",
            name="ck_saq_run_status_result",
        ),
        CheckConstraint("attempt_number > 0", name="ck_saq_run_attempt_number"),
        CheckConstraint(
            "(status IN ('queued','running') AND terminal_at IS NULL) "
            "OR (status IN ('succeeded','failed','cancelled','abandoned') "
            "AND terminal_at IS NOT NULL)",
            name="ck_saq_run_terminal_timestamp",
        ),
        Index("ix_saq_runs_source_scope_status", "source_id", "resource_scope", "status"),
        Index("ix_saq_runs_correlation_id", "correlation_id"),
        Index("ix_saq_runs_lease_expiry", "lease_expires_at"),
        Index(
            "uq_saq_runs_idempotency_scope",
            "source_id",
            "resource_scope",
            "idempotency_key",
            unique=True,
            sqlite_where=text("idempotency_key IS NOT NULL"),
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
        Index(
            "uq_saq_runs_active_scope",
            "source_id",
            "resource_scope",
            unique=True,
            sqlite_where=text("status IN ('queued','running')"),
            postgresql_where=text("status IN ('queued','running')"),
        ),
        Index("uq_saq_runs_root_attempt", "root_run_id", "attempt_number", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("sc_sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    resource_scope: Mapped[str] = mapped_column(String(240), nullable=False, default="source")
    trigger_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(240), nullable=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(120), nullable=False)
    parent_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("saq_runs.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    root_run_id: Mapped[str] = mapped_column(
        ForeignKey("saq_runs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued", index=True)
    result: Mapped[str] = mapped_column(String(40), nullable=False, default="none")
    queued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancellation_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancellation_requested_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=True
    )
    worker_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


def _reject_terminal_mutation(
    _mapper: Mapper[Any], _connection: Connection, target: AcquisitionRun
) -> None:
    state = inspect(target)
    status_history = state.attrs.status.history
    previous_status = status_history.deleted[0] if status_history.deleted else target.status
    if previous_status in TERMINAL_RUN_STATUSES:
        raise ImmutableRecordError("Terminal AcquisitionRun records are immutable.")


def _reject_run_delete(
    _mapper: Mapper[Any], _connection: Connection, _target: AcquisitionRun
) -> None:
    raise ImmutableRecordError("AcquisitionRun records are append-safe and cannot be deleted.")


event.listen(AcquisitionRun, "before_update", _reject_terminal_mutation)
event.listen(AcquisitionRun, "before_delete", _reject_run_delete)


class SourceObservationVersionHead(FlowHubBase):
    """Mutable allocator; immutable Observations never calculate their own version."""

    __tablename__ = "saq_observation_version_heads"

    source_id: Mapped[str] = mapped_column(
        ForeignKey("sc_sources.id", ondelete="RESTRICT"), primary_key=True
    )
    resource_scope: Mapped[str] = mapped_column(String(240), primary_key=True)
    next_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class SourceObservation(FlowHubBase):
    """Immutable provider-neutral fact recorded for one successful Acquisition Run."""

    __tablename__ = "saq_observations"
    __table_args__ = (
        CheckConstraint("observation_version > 0", name="ck_saq_observation_version"),
        UniqueConstraint("acquisition_run_id", name="uq_saq_observation_run"),
        UniqueConstraint(
            "source_id",
            "resource_scope",
            "observation_version",
            name="uq_saq_observation_scope_version",
        ),
        UniqueConstraint("checksum", name="uq_saq_observation_checksum"),
        Index("ix_saq_observations_source_scope_observed", "source_id", "resource_scope", "observed_at"),
        Index("ix_saq_observations_resource_identity_hash", "resource_identity_hash"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    acquisition_run_id: Mapped[str] = mapped_column(
        ForeignKey("saq_runs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("sc_sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    resource_scope: Mapped[str] = mapped_column(String(240), nullable=False)
    resource_identity: Mapped[str] = mapped_column(String(240), nullable=False)
    resource_identity_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    observation_version: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class SourceObservationEvidence(FlowHubBase):
    """Append-only evidence chain for one immutable Observation."""

    __tablename__ = "saq_observation_evidence"
    __table_args__ = (
        CheckConstraint("sequence_number > 0", name="ck_saq_evidence_sequence"),
        UniqueConstraint("observation_id", "sequence_number", name="uq_saq_evidence_sequence"),
        Index("ix_saq_evidence_observation_recorded", "observation_id", "recorded_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    observation_id: Mapped[str] = mapped_column(
        ForeignKey("saq_observations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_kind: Mapped[str] = mapped_column(String(80), nullable=False)
    evidence_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    previous_evidence_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    evidence_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class SourceObservationSnapshotReference(FlowHubBase):
    """Append-only reference to a snapshot without coupling this phase to Workspace creation."""

    __tablename__ = "saq_observation_snapshot_references"
    __table_args__ = (
        UniqueConstraint(
            "observation_id",
            "snapshot_kind",
            "snapshot_reference",
            name="uq_saq_observation_snapshot_reference",
        ),
        Index("ix_saq_snapshot_reference_observation", "observation_id", "linked_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    observation_id: Mapped[str] = mapped_column(
        ForeignKey("saq_observations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    snapshot_kind: Mapped[str] = mapped_column(String(80), nullable=False)
    snapshot_reference: Mapped[str] = mapped_column(String(240), nullable=False)
    snapshot_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    linked_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class SourceObservationDataset(FlowHubBase):
    """Immutable, provider-neutral worksheet data retained for local replay."""

    __tablename__ = "saq_observation_datasets"
    __table_args__ = (
        UniqueConstraint("observation_id", name="uq_saq_observation_dataset_observation"),
        CheckConstraint("source_snapshot_version > 0", name="ck_saq_dataset_snapshot_version"),
        CheckConstraint("row_count >= 0", name="ck_saq_dataset_row_count"),
        CheckConstraint("worksheet_count >= 0", name="ck_saq_dataset_worksheet_count"),
        Index(
            "ix_saq_observation_dataset_source_scope_created",
            "source_id",
            "resource_scope",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    observation_id: Mapped[str] = mapped_column(
        ForeignKey("saq_observations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("sc_sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    resource_scope: Mapped[str] = mapped_column(String(240), nullable=False)
    binding_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(40), nullable=False)
    formula_evaluation_version: Mapped[str] = mapped_column(String(40), nullable=False)
    source_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("dl_source_snapshots.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_snapshot_version: Mapped[int] = mapped_column(Integer, nullable=False)
    workbook_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    worksheet_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class SourceObservationWorksheetDataset(FlowHubBase):
    """One ordered worksheet within an immutable local Observation dataset."""

    __tablename__ = "saq_observation_worksheet_datasets"
    __table_args__ = (
        UniqueConstraint(
            "dataset_id",
            "worksheet_name",
            name="uq_saq_observation_dataset_worksheet_name",
        ),
        UniqueConstraint(
            "dataset_id",
            "worksheet_order",
            name="uq_saq_observation_dataset_worksheet_order",
        ),
        CheckConstraint("worksheet_order > 0", name="ck_saq_dataset_worksheet_order"),
        CheckConstraint("row_count >= 0", name="ck_saq_dataset_worksheet_row_count"),
        Index(
            "ix_saq_observation_worksheet_dataset_order",
            "dataset_id",
            "worksheet_order",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(
        ForeignKey("saq_observation_datasets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    worksheet_name: Mapped[str] = mapped_column(String(240), nullable=False)
    worksheet_order: Mapped[int] = mapped_column(Integer, nullable=False)
    rows_json: Mapped[list[list[Any]]] = mapped_column(JSON, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class SourceMappingSchemaExpectation(FlowHubBase):
    """Immutable expected header contract for one Source Mapping revision."""

    __tablename__ = "saq_mapping_schema_expectations"
    __table_args__ = (
        UniqueConstraint("mapping_revision_id", name="uq_saq_mapping_schema_expectation_revision"),
        UniqueConstraint("checksum", name="uq_saq_mapping_schema_expectation_checksum"),
        Index("ix_saq_mapping_schema_expectations_source_created", "source_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("sc_sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    mapping_revision_id: Mapped[str] = mapped_column(
        ForeignKey("sc_source_mapping_revisions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    canonicalization_version: Mapped[str] = mapped_column(String(40), nullable=False)
    raw_headers_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    canonical_headers_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    raw_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    required_canonical_headers_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class SourceSchemaAssessment(FlowHubBase):
    """Immutable schema comparison over one Observation and Mapping identity."""

    __tablename__ = "saq_schema_assessments"
    __table_args__ = (
        CheckConstraint(
            "execution_status IN ('not_run','pending','running','passed','failed','skipped','not_applicable')",
            name="ck_saq_assessment_execution_status",
        ),
        CheckConstraint(
            "schema_status IS NULL OR schema_status IN ('match','drift','ambiguous','no_mapping')",
            name="ck_saq_assessment_schema_status",
        ),
        CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="ck_saq_assessment_duration"),
        UniqueConstraint(
            "observation_id",
            "mapping_identity",
            "assessment_algorithm_version",
            name="uq_saq_assessment_identity",
        ),
        UniqueConstraint("checksum", name="uq_saq_assessment_checksum"),
        Index("ix_saq_assessments_source_status_created", "source_id", "schema_status", "created_at"),
        Index("ix_saq_assessments_mapping_created", "mapping_revision_id", "created_at"),
        Index("ix_saq_assessments_observation_created", "observation_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    observation_id: Mapped[str] = mapped_column(
        ForeignKey("saq_observations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("sc_sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    resource_scope: Mapped[str] = mapped_column(String(240), nullable=False)
    mapping_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("sc_source_mapping_revisions.id", ondelete="RESTRICT"), nullable=True
    )
    mapping_expectation_id: Mapped[str | None] = mapped_column(
        ForeignKey("saq_mapping_schema_expectations.id", ondelete="RESTRICT"), nullable=True
    )
    mapping_identity: Mapped[str] = mapped_column(String(80), nullable=False)
    assessment_algorithm_version: Mapped[str] = mapped_column(String(40), nullable=False)
    canonicalization_version: Mapped[str] = mapped_column(String(40), nullable=False)
    execution_status: Mapped[str] = mapped_column(String(30), nullable=False)
    schema_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    observed_raw_headers_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    observed_canonical_headers_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    expected_raw_headers_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    expected_canonical_headers_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    observed_raw_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    observed_canonical_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expected_raw_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expected_canonical_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    freshness_basis_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    assessed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class SourceSchemaDriftRecord(FlowHubBase):
    """One immutable, position-aware structural difference in an Assessment."""

    __tablename__ = "saq_schema_drift_records"
    __table_args__ = (
        UniqueConstraint("assessment_id", "sequence_number", name="uq_saq_drift_sequence"),
        CheckConstraint("sequence_number > 0", name="ck_saq_drift_sequence"),
        CheckConstraint(
            "change_kind IN ('added','removed','reordered','rename_candidate','duplicate_header',"
            "'canonical_collision','required_field_missing','unsupported_shape')",
            name="ck_saq_drift_change_kind",
        ),
        Index("ix_saq_drift_assessment_sequence", "assessment_id", "sequence_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("saq_schema_assessments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    change_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    expected_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    observed_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_raw_value: Mapped[str | None] = mapped_column(String(240), nullable=True)
    expected_canonical_value: Mapped[str | None] = mapped_column(String(240), nullable=True)
    observed_raw_value: Mapped[str | None] = mapped_column(String(240), nullable=True)
    observed_canonical_value: Mapped[str | None] = mapped_column(String(240), nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(40), nullable=True)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    algorithm_version: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class SourceSchemaDiagnostic(FlowHubBase):
    """Machine-readable, immutable assessment diagnostic without localized prose."""

    __tablename__ = "saq_schema_diagnostics"
    __table_args__ = (
        UniqueConstraint("assessment_id", "sequence_number", name="uq_saq_diagnostic_sequence"),
        CheckConstraint("sequence_number > 0", name="ck_saq_diagnostic_sequence"),
        Index("ix_saq_diagnostics_assessment_created", "assessment_id", "created_at"),
        Index("ix_saq_diagnostics_reason_created", "reason_code", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("saq_schema_assessments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    stage_id: Mapped[str] = mapped_column(String(80), nullable=False)
    execution_status: Mapped[str] = mapped_column(String(30), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(120), nullable=False)
    recommended_action_code: Mapped[str] = mapped_column(String(120), nullable=False)
    action_parameters_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


_APPEND_ONLY_OBSERVATION_MODELS = (
    SourceObservation,
    SourceObservationEvidence,
    SourceObservationSnapshotReference,
    SourceObservationDataset,
    SourceObservationWorksheetDataset,
    SourceMappingSchemaExpectation,
    SourceSchemaAssessment,
    SourceSchemaDriftRecord,
    SourceSchemaDiagnostic,
)


def _reject_append_only_mutation(
    _mapper: Mapper[Any], _connection: Connection, target: Any
) -> None:
    raise ImmutableRecordError(f"{target.__class__.__name__} records are append-only.")


for _model in _APPEND_ONLY_OBSERVATION_MODELS:
    event.listen(_model, "before_update", _reject_append_only_mutation)
    event.listen(_model, "before_delete", _reject_append_only_mutation)
