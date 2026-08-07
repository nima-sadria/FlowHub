"""Persistence models for offline formula migration preview outputs and review lineage."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    JSON,
)
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapper, Mapped, mapped_column

from app.flowhub.database import FlowHubBase
from app.flowhub.formula_migration_preview.contracts import (
    FormulaMigrationReviewAction,
    PreviewBatchState,
)
from app.flowhub.formula_translator.contracts import (
    FormulaTranslationReason,
    FormulaTranslationStatus,
    FORMULA_SHAPE_REGISTRY_VERSION,
)
from app.flowhub.unified_workspace.domain import ImmutableRecordError, utcnow


def _enum_check(values: tuple[str, ...]) -> str:
    return "'" + "','".join(values) + "'"


_BATCH_STATES = _enum_check(tuple(value.value for value in PreviewBatchState))
_TRANSLATION_STATUSES = _enum_check(tuple(value.value for value in FormulaTranslationStatus))
_REASONS = _enum_check(tuple(value.value for value in FormulaTranslationReason))
_REVIEW_ACTIONS = _enum_check(tuple(value.value for value in FormulaMigrationReviewAction))


class FormulaMigrationPreviewBatch(FlowHubBase):
    """Immutable preview batch artifact for one offline migration assembly run."""

    __tablename__ = "fmp_preview_batches"
    __table_args__ = (
        CheckConstraint(f"state IN ({_BATCH_STATES})", name="ck_fmp_batch_state"),
        CheckConstraint("registry_version != ''", name="ck_fmp_batch_registry_version_nonempty"),
        CheckConstraint("registry_checksum != ''", name="ck_fmp_batch_registry_checksum_nonempty"),
        CheckConstraint("translator_version != ''", name="ck_fmp_batch_translator_version_nonempty"),
        CheckConstraint("inventory_checksum != ''", name="ck_fmp_batch_inventory_checksum_nonempty"),
        CheckConstraint("input_checksum != ''", name="ck_fmp_batch_input_checksum_nonempty"),
        CheckConstraint("report_checksum != ''", name="ck_fmp_batch_report_checksum_nonempty"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    translator_version: Mapped[str] = mapped_column(String(80), nullable=False)
    registry_version: Mapped[str] = mapped_column(String(80), nullable=False, default=FORMULA_SHAPE_REGISTRY_VERSION)
    registry_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    inventory_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    input_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    report_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    translated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    review_required_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unsupported_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quarantined_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocking_operationally_active_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class FormulaMigrationPreviewCell(FlowHubBase):
    """Immutable per-cell evidence row for a preview batch."""

    __tablename__ = "fmp_preview_cells"
    __table_args__ = (
        CheckConstraint(f"translation_status IN ({_TRANSLATION_STATUSES})", name="ck_fmp_cell_status"),
        CheckConstraint(f"reason_code IN ({_REASONS})", name="ck_fmp_cell_reason"),
        CheckConstraint("formula_rule_identity != ''", name="ck_fmp_cell_rule_identity_nonempty"),
        CheckConstraint("translation_fingerprint != ''", name="ck_fmp_cell_fingerprint_nonempty"),
        CheckConstraint("binding_manifest_checksum != ''", name="ck_fmp_cell_binding_manifest_checksum_nonempty"),
        CheckConstraint("translator_version != ''", name="ck_fmp_cell_translator_version_nonempty"),
        CheckConstraint("registry_version != ''", name="ck_fmp_cell_registry_version_nonempty"),
        CheckConstraint("registry_checksum != ''", name="ck_fmp_cell_registry_checksum_nonempty"),
        CheckConstraint("report_row_checksum != ''", name="ck_fmp_cell_report_row_checksum_nonempty"),
        UniqueConstraint("preview_batch_id", "inventory_cell_id", name="uq_fmp_cell_batch_inventory"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    preview_batch_id: Mapped[str] = mapped_column(
        ForeignKey("fmp_preview_batches.id", ondelete="RESTRICT"),
        nullable=False,
    )
    formula_rule_identity: Mapped[str] = mapped_column(String(160), nullable=False)
    inventory_cell_id: Mapped[str] = mapped_column(String(120), nullable=False)
    formula_shape_id: Mapped[str | None] = mapped_column(String(8), nullable=True)
    translation_status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(40), nullable=False)
    translation_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    target_fragment_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    binding_manifest_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    fixture_registry_evidence_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    formula_inventory_evidence_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    translator_version: Mapped[str] = mapped_column(String(80), nullable=False)
    translator_version_diff_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    registry_version: Mapped[str] = mapped_column(String(80), nullable=False)
    registry_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    blocking_operationally_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    report_row_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class FormulaMigrationReviewDecision(FlowHubBase):
    """Append-only reviewer decisions on preview cells."""

    __tablename__ = "fmp_review_decisions"
    __table_args__ = (
        CheckConstraint(f"action IN ({_REVIEW_ACTIONS})", name="ck_fmp_review_action"),
        CheckConstraint("actor_user_id IS NOT NULL OR actor_name != ''", name="ck_fmp_review_actor_required"),
        CheckConstraint("reason != ''", name="ck_fmp_review_reason_nonempty"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    preview_cell_id: Mapped[str] = mapped_column(
        ForeignKey("fmp_preview_cells.id", ondelete="RESTRICT"),
        nullable=False,
    )
    actor_name: Mapped[str] = mapped_column(String(120), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


_IMMUTABLE_MODELS = (
    FormulaMigrationPreviewBatch,
    FormulaMigrationPreviewCell,
)
_APPEND_ONLY_MODELS = (FormulaMigrationReviewDecision,)


def _reject_immutable_change(_mapper: Mapper, _connection: Connection, target: object) -> None:
    raise ImmutableRecordError(f"{target.__class__.__name__} records are immutable.")


def _reject_append_only_mutation(_mapper: Mapper, _connection: Connection, target: object) -> None:
    raise ImmutableRecordError(f"{target.__class__.__name__} records are append-only.")


for _model in _IMMUTABLE_MODELS:
    event.listen(_model, "before_update", _reject_immutable_change)
    event.listen(_model, "before_delete", _reject_immutable_change)

for _model in _APPEND_ONLY_MODELS:
    event.listen(_model, "before_update", _reject_append_only_mutation)
    event.listen(_model, "before_delete", _reject_append_only_mutation)


__all__ = [
    "FormulaMigrationPreviewBatch",
    "FormulaMigrationPreviewCell",
    "FormulaMigrationReviewDecision",
]
