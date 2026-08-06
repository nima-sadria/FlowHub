"""Persistence models for formula translator outcomes and quarantine evidence."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapped, Mapper, mapped_column

from app.flowhub.database import FlowHubBase
from app.flowhub.formula_translator.contracts import (
    FormulaTranslationReason,
    FormulaTranslationStatus,
)
from app.flowhub.unified_workspace.domain import ImmutableRecordError, utcnow


def _enum_check(values: tuple[str, ...]) -> str:
    return "'" + "','".join(values) + "'"


_STATUS_VALUES = _enum_check(tuple(status.value for status in FormulaTranslationStatus))
_REASON_VALUES = _enum_check(tuple(reason.value for reason in FormulaTranslationReason))


class FormulaShapeRegistryEntry(FlowHubBase):
    """Closed, checked-in Appendix A registry row."""

    __tablename__ = "ft_formula_shape_registry"
    __table_args__ = (
        CheckConstraint(
            f"translation_status IN ({_STATUS_VALUES})",
            name="ck_ft_shape_registry_translation_status",
        ),
        CheckConstraint(
            f"default_reason_code IN ({_REASON_VALUES})",
            name="ck_ft_shape_registry_reason_code",
        ),
        CheckConstraint("formula_cell_count >= 0", name="ck_ft_shape_cell_count"),
        CheckConstraint("registry_version != ''", name="ck_ft_shape_registry_version_nonempty"),
        CheckConstraint("registry_checksum != ''", name="ck_ft_shape_registry_checksum_nonempty"),
    )

    shape_id: Mapped[str] = mapped_column(String(8), primary_key=True)
    translation_status: Mapped[str] = mapped_column(String(20), nullable=False)
    default_reason_code: Mapped[str] = mapped_column(String(40), nullable=False)
    is_price_target: Mapped[bool] = mapped_column(Boolean, nullable=False)
    formula_cell_count: Mapped[int] = mapped_column(Integer, nullable=False)
    topology_hint: Mapped[str] = mapped_column(String(80), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    record_payload_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    registry_version: Mapped[str] = mapped_column(String(80), nullable=False)
    registry_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class FormulaTranslationResult(FlowHubBase):
    """Immutable translation outcome for one formula rule identity."""

    __tablename__ = "ft_formula_translation_results"
    __table_args__ = (
        CheckConstraint(
            f"translation_status IN ({_STATUS_VALUES})",
            name="ck_ft_translation_status",
        ),
        CheckConstraint(
            f"reason_code IN ({_REASON_VALUES})",
            name="ck_ft_translation_reason_code",
        ),
        CheckConstraint(
            "formula_rule_identity != ''",
            name="ck_ft_translation_rule_identity_nonempty",
        ),
        CheckConstraint(
            "formula_shape_id IS NULL OR LENGTH(formula_shape_id) >= 1",
            name="ck_ft_translation_shape_id",
        ),
        CheckConstraint("translator_version != ''", name="ck_ft_translation_translator_version"),
        CheckConstraint("registry_version != ''", name="ck_ft_translation_registry_version_nonempty"),
        CheckConstraint("registry_checksum != ''", name="ck_ft_translation_registry_checksum_nonempty"),
        CheckConstraint("translation_fingerprint != ''", name="ck_ft_translation_fingerprint_nonempty"),
        UniqueConstraint(
            "formula_rule_identity",
            "translator_version",
            name="uq_ft_translation_rule_and_version",
        ),
        Index("ix_ft_translation_status", "translation_status"),
        Index("ix_ft_translation_shape", "formula_shape_id"),
        Index("ix_ft_translation_rule", "formula_rule_identity"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    formula_rule_identity: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    formula_shape_id: Mapped[str | None] = mapped_column(String(8), nullable=True)
    translation_status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(40), nullable=False)
    translator_version: Mapped[str] = mapped_column(String(80), nullable=False)
    registry_version: Mapped[str] = mapped_column(String(80), nullable=False)
    registry_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    translation_payload_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    translation_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    translation_input_payload_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class FormulaTranslationQuarantine(FlowHubBase):
    """Append-only quarantine evidence for non-translated or quarantined rules."""

    __tablename__ = "ft_formula_translation_quarantine"
    __table_args__ = (
        CheckConstraint(
            f"quarantine_reason IN ({_REASON_VALUES})",
            name="ck_ft_quarantine_reason_code",
        ),
        CheckConstraint(
            "quarantine_reason != ''",
            name="ck_ft_quarantine_reason_nonempty",
        ),
        Index("ix_ft_quarantine_result", "formula_translation_result_id"),
        UniqueConstraint(
            "formula_translation_result_id",
            name="uq_ft_quarantine_result",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    formula_translation_result_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ft_formula_translation_results.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quarantine_reason: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


_IMMUTABLE_MODELS = (
    FormulaShapeRegistryEntry,
    FormulaTranslationResult,
)

_APPEND_ONLY_MODELS = (FormulaTranslationQuarantine,)


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
