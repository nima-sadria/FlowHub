"""Persistence model for Shadow Validation C2 (immutable evidence + lifecycle fences)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Mapper, Mapped, mapped_column

from app.flowhub.database import FlowHubBase
from app.flowhub.unified_workspace.domain import ImmutableRecordError, utcnow

from .contracts import (
    ComparisonConfidence,
    ComparisonPrimaryClassification,
    OutputLane,
    ShadowValidationReasonCode,
    ShadowValidationWindowState,
    ShapeAcceptanceEffect,
    ShapeTargetKind,
    ValidationWindowEventKind,
    WindowReadinessReason,
    WindowReadinessState,
)


def _enum_check(values: tuple[str, ...]) -> str:
    return "'" + "','".join(values) + "'"


_WINDOW_STATES = _enum_check(tuple(value.value for value in ShadowValidationWindowState))
_EVENT_KINDS = _enum_check(tuple(value.value for value in ValidationWindowEventKind))
_TARGET_KINDS = _enum_check(tuple(value.value for value in ShapeTargetKind))
_ACCEPTANCE_EFFECTS = _enum_check(tuple(value.value for value in ShapeAcceptanceEffect))
_CONFIDENCE_VALUES = _enum_check(tuple(value.value for value in ComparisonConfidence))
_CLASSIFICATIONS = _enum_check(tuple(value.value for value in ComparisonPrimaryClassification))
_OUTPUT_LANES = _enum_check(tuple(value.value for value in OutputLane))
_REASON_CODES = _enum_check(tuple(value.value for value in ShadowValidationReasonCode))
_STABLE_REASON_CODES = _enum_check(tuple(value.value for value in WindowReadinessReason))
_READINESS_STATE = _enum_check(tuple(value.value for value in WindowReadinessState))


class ShadowValidationWindow(FlowHubBase):
    """Configuration snapshot for one validation cycle."""

    __tablename__ = "sv_validation_windows"
    __table_args__ = (
        CheckConstraint("required_distinct_matches >= 1", name="ck_sv_window_min_matches"),
        CheckConstraint("pricing_authority_head_version >= 0", name="ck_sv_window_authority_head_version"),
        CheckConstraint("head_version_snapshot >= 0", name="ck_sv_window_head_version_snapshot"),
        CheckConstraint(
            "evidence_freshness_seconds IS NULL OR evidence_freshness_seconds > 0",
            name="ck_sv_window_freshness_seconds",
        ),
        Index("ix_sv_window_scope", "scope_manifest_checksum"),
        Index("ix_sv_validation_windows_channel_id", "channel_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    channel_id: Mapped[str] = mapped_column(
        ForeignKey("uw_channels.id", ondelete="RESTRICT"), nullable=False
    )
    scope_manifest_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    formula_inventory_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    acceptance_policy_revision: Mapped[str] = mapped_column(String(120), nullable=False)
    pricing_policy_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("pm_policy_revisions.id", ondelete="RESTRICT"), nullable=True
    )
    pricing_policy_activation_id: Mapped[str | None] = mapped_column(
        ForeignKey("pm_policy_lifecycle_events.id", ondelete="RESTRICT"), nullable=True
    )
    pricing_authority_event_id: Mapped[str] = mapped_column(
        ForeignKey("pm_channel_pricing_authority_events.id", ondelete="RESTRICT"),
        nullable=False,
    )
    pricing_authority_head_version: Mapped[int] = mapped_column(Integer, nullable=False)
    head_version_snapshot: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    opened_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    closes_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    evidence_freshness_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    required_distinct_matches: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    configuration_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    predecessor_window_id: Mapped[str | None] = mapped_column(
        ForeignKey("sv_validation_windows.id", ondelete="RESTRICT"), nullable=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class ShadowValidationWindowHead(FlowHubBase):
    """CAS head for a channel's current validation window."""

    __tablename__ = "sv_validation_window_heads"
    __table_args__ = (
        CheckConstraint("head_version >= 0", name="ck_sv_window_head_version"),
        CheckConstraint(f"current_state IN ({_WINDOW_STATES})", name="ck_sv_window_head_state"),
    )

    channel_id: Mapped[str] = mapped_column(
        ForeignKey("uw_channels.id", ondelete="RESTRICT"), primary_key=True
    )
    current_window_id: Mapped[str | None] = mapped_column(
        ForeignKey("sv_validation_windows.id", ondelete="RESTRICT"), nullable=True
    )
    current_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ShadowValidationWindowState.COLLECTING.value
    )
    head_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class ShadowValidationWindowEvent(FlowHubBase):
    """Append-only window lifecycle event."""

    __tablename__ = "sv_validation_window_events"
    __table_args__ = (
        CheckConstraint(f"event_kind IN ({_EVENT_KINDS})", name="ck_sv_window_event_kind"),
        CheckConstraint(f"reason_code IN ({_REASON_CODES})", name="ck_sv_window_event_reason"),
        CheckConstraint("expected_head_version >= 0", name="ck_sv_window_event_head"),
        CheckConstraint("head_version_snapshot >= 0", name="ck_sv_window_event_snapshot"),
        Index("ix_sv_window_event_channel", "channel_id"),
        Index("ix_sv_window_event_validation_window_id", "validation_window_id"),
        Index("ix_sv_window_event_predecessor", "predecessor_event_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    channel_id: Mapped[str] = mapped_column(
        ForeignKey("uw_channels.id", ondelete="RESTRICT"), nullable=False
    )
    validation_window_id: Mapped[str] = mapped_column(
        ForeignKey("sv_validation_windows.id", ondelete="RESTRICT"), nullable=False
    )
    predecessor_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("sv_validation_window_events.id", ondelete="RESTRICT"), nullable=True
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=True
    )
    actor_reference: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    event_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    reason_payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    expected_head_version: Mapped[int] = mapped_column(Integer, nullable=False)
    head_version_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    configuration_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class ShapeComparisonContract(FlowHubBase):
    """Per-shape closed comparison contract definition."""

    __tablename__ = "sv_shape_comparison_contracts"
    __table_args__ = (
        CheckConstraint(f"target_kind IN ({_TARGET_KINDS})", name="ck_sv_contract_target_kind"),
        CheckConstraint(
            f"acceptance_effect IN ({_ACCEPTANCE_EFFECTS})", name="ck_sv_contract_acceptance_effect"
        ),
        UniqueConstraint("shape_id", "contract_revision", name="uq_sv_contract_shape_revision"),
        UniqueConstraint("contract_checksum", name="uq_sv_contract_checksum"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    shape_id: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    contract_revision: Mapped[str] = mapped_column(String(120), nullable=False)
    contract_version: Mapped[str] = mapped_column(String(40), nullable=False)
    formula_inventory_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    contract_checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    stable_rule_identity_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    required_input_identity_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    required_output_lanes_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    canonical_context_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    equality_rule_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    required_trace_components_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    acceptance_effect: Mapped[str] = mapped_column(String(20), nullable=False)
    classification_mapping_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    is_current: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class LegacyFormulaCapture(FlowHubBase):
    """Immutable legacy evaluation capture evidence snapshot."""

    __tablename__ = "sv_legacy_formula_captures"
    __table_args__ = (
        CheckConstraint("candidate_denominator > 0", name="ck_sv_legacy_candidate_denom"),
        CheckConstraint("effective_denominator > 0", name="ck_sv_legacy_effective_denom"),
        UniqueConstraint(
            "frozen_evaluation_package_id",
            "formula_rule_identity",
            name="uq_sv_legacy_capture_package_rule",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    channel_id: Mapped[str] = mapped_column(
        ForeignKey("uw_channels.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    frozen_evaluation_package_id: Mapped[str] = mapped_column(
        ForeignKey("pev_frozen_evaluation_packages.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    legacy_formula_engine: Mapped[str] = mapped_column(String(120), nullable=False)
    legacy_formula_engine_version: Mapped[str] = mapped_column(String(80), nullable=False)
    formula_shape_id: Mapped[str] = mapped_column(String(8), nullable=False)
    formula_rule_identity: Mapped[str] = mapped_column(String(160), nullable=False)
    workbook_identity: Mapped[str | None] = mapped_column(String(160), nullable=True)
    workbook_revision: Mapped[str | None] = mapped_column(String(80), nullable=True)
    input_manifest_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    pricing_authority_event_id: Mapped[str] = mapped_column(
        ForeignKey("pm_channel_pricing_authority_events.id", ondelete="RESTRICT"), nullable=False
    )
    pricing_authority_head_version: Mapped[int] = mapped_column(Integer, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    candidate_numerator: Mapped[int] = mapped_column(BigInteger, nullable=False)
    candidate_denominator: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    effective_numerator: Mapped[int] = mapped_column(BigInteger, nullable=False)
    effective_denominator: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    candidate_currency: Mapped[str | None] = mapped_column(String(12), nullable=True)
    candidate_unit: Mapped[str | None] = mapped_column(String(24), nullable=True)
    effective_currency: Mapped[str | None] = mapped_column(String(12), nullable=True)
    effective_unit: Mapped[str | None] = mapped_column(String(24), nullable=True)
    output_context_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    capture_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class ShadowValidationComparison(FlowHubBase):
    """Immutable comparison evidence between Legacy and FEP for one stable rule."""

    __tablename__ = "sv_shadow_comparisons"
    __table_args__ = (
        CheckConstraint(f"confidence IN ({_CONFIDENCE_VALUES})", name="ck_sv_comparison_confidence"),
        CheckConstraint(f"primary_classification IN ({_CLASSIFICATIONS})", name="ck_sv_comparison_classification"),
        CheckConstraint(
            f"reason_code IS NULL OR reason_code IN ({_REASON_CODES})",
            name="ck_sv_comparison_reason_code",
        ),
        CheckConstraint(f"required_output_lanes IN ({_OUTPUT_LANES})", name="ck_sv_comparison_output_lanes"),
        Index("ix_sv_comparison_window", "validation_window_id"),
        Index("ix_sv_shadow_comparisons_channel", "channel_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    channel_id: Mapped[str] = mapped_column(
        ForeignKey("uw_channels.id", ondelete="RESTRICT"), nullable=False
    )
    validation_window_id: Mapped[str] = mapped_column(
        ForeignKey("sv_validation_windows.id", ondelete="RESTRICT"), nullable=False
    )
    frozen_evaluation_package_id: Mapped[str] = mapped_column(
        ForeignKey("pev_frozen_evaluation_packages.id", ondelete="RESTRICT"),
        nullable=False,
    )
    legacy_formula_capture_id: Mapped[str] = mapped_column(
        ForeignKey("sv_legacy_formula_captures.id", ondelete="RESTRICT"), nullable=False
    )
    shape_id: Mapped[str] = mapped_column(String(8), nullable=False)
    comparison_contract_id: Mapped[str] = mapped_column(
        ForeignKey("sv_shape_comparison_contracts.id", ondelete="RESTRICT"), nullable=False
    )
    stable_rule_identity: Mapped[str] = mapped_column(String(160), nullable=False)
    comparison_contract_revision: Mapped[str] = mapped_column(String(120), nullable=False)
    comparison_contract_revision_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    comparison_algorithm_version: Mapped[str] = mapped_column(String(40), nullable=False)
    comparison_identity_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    frozen_evaluation_package_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    legacy_capture_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    translator_version: Mapped[str] = mapped_column(String(80), nullable=False)
    required_output_lanes: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)
    primary_classification: Mapped[str] = mapped_column(String(80), nullable=False)
    secondary_classifications_json: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    legacy_vs_package_context_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    legacy_output_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    package_output_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    findings_json: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=True
    )
    reason_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class ShadowReadinessDecision(FlowHubBase):
    """Immutable readiness decision snapshots for one window."""

    __tablename__ = "sv_validation_readiness_decisions"
    __table_args__ = (
        CheckConstraint(f"decision IN ({_READINESS_STATE})", name="ck_sv_readiness_state"),
        CheckConstraint(
            f"reason_code IS NULL OR reason_code IN ({_STABLE_REASON_CODES})",
            name="ck_sv_readiness_reason_code",
        ),
        Index("ix_sv_readiness_window", "validation_window_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    validation_window_id: Mapped[str] = mapped_column(
        ForeignKey("sv_validation_windows.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    channel_id: Mapped[str] = mapped_column(
        ForeignKey("uw_channels.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    compared_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    aggregate_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    required_comparison_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comparison_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    authority_event_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )
    authority_head_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scope_manifest_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    readiness_payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


_IMMUTABLE_MODELS = (
    ShadowValidationWindow,
    ShadowValidationWindowEvent,
    ShapeComparisonContract,
    LegacyFormulaCapture,
    ShadowValidationComparison,
    ShadowReadinessDecision,
)


def _reject_immutable_change(_mapper: Mapper[Any], _connection: Connection, target: Any) -> None:
    raise ImmutableRecordError(f"{target.__class__.__name__} records are immutable.")


for _model in _IMMUTABLE_MODELS:
    event.listen(_model, "before_update", _reject_immutable_change)
    event.listen(_model, "before_delete", _reject_immutable_change)
