"""Immutable persistence for the Frozen Evaluation Package foundation.

Every table here is either fully immutable (no update, no delete) or
append-only evidence. Nothing here is a pricing-authority write boundary —
that remains ``app/flowhub/write_pipeline/service.py`` and
``app/flowhub/pricing_authority/service.py``, both untouched by this phase.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
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
from app.flowhub.pricing_evaluation.contracts import (
    DependencyRefKind,
    DerivedOperator,
    EffectiveOutputSource,
    FreshnessResult,
    ManualInputDecisionKind,
    ManualInputKind,
    ObservationSelectionMode,
    SkewResult,
)
from app.flowhub.unified_workspace.domain import ImmutableRecordError, utcnow


def _enum_check(values: tuple[str, ...]) -> str:
    return "'" + "','".join(values) + "'"


_SELECTION_MODES = _enum_check(tuple(m.value for m in ObservationSelectionMode))
_FRESHNESS_RESULTS = _enum_check(tuple(f.value for f in FreshnessResult))
_SKEW_RESULTS = _enum_check(tuple(s.value for s in SkewResult))
_MANUAL_INPUT_KINDS = _enum_check(tuple(k.value for k in ManualInputKind))
_MANUAL_DECISION_KINDS = _enum_check(tuple(k.value for k in ManualInputDecisionKind))
_EFFECTIVE_OUTPUT_SOURCES = _enum_check(tuple(s.value for s in EffectiveOutputSource))
_DERIVED_OPERATORS = _enum_check(tuple(o.value for o in DerivedOperator))
_DEPENDENCY_REF_KINDS = _enum_check(tuple(k.value for k in DependencyRefKind))


# ---------------------------------------------------------------------------
# A. Frozen Evaluation Package
# ---------------------------------------------------------------------------


class FrozenEvaluationPackage(FlowHubBase):
    """One immutable evidence snapshot for one Channel/product business state.

    Authoritative Architecture rule 12: a new business state creates a new
    package; existing packages never mutate.
    """

    __tablename__ = "pev_frozen_evaluation_packages"
    __table_args__ = (
        CheckConstraint("workspace_pricing_evaluated_at IS NOT NULL", name="ck_pev_package_evaluated_at"),
        # checksum is per-row tamper-evidence, not a dedup key: rule 12 allows a
        # new business state to create a new package even if it is byte-identical
        # to a prior evaluation (e.g. an explicit replay for evidence purposes).
        Index("ix_pev_package_channel_product", "channel_id", "product_ref"),
        Index("ix_pev_package_workspace", "workspace_id"),
        Index("ix_pev_package_formula_shape", "formula_shape_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Scope (Authoritative Architecture: workspace/channel/product scope).
    workspace_id: Mapped[str | None] = mapped_column(
        ForeignKey("uw_workspaces.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    channel_id: Mapped[str] = mapped_column(
        ForeignKey("uw_channels.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    product_ref: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    workspace_pricing_evaluated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    pricing_policy_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("pm_policy_revisions.id", ondelete="RESTRICT"), nullable=True
    )

    # Formula-migration identity pins (Authoritative Architecture rule 10).
    formula_shape_id: Mapped[str] = mapped_column(String(8), nullable=False)
    translator_version: Mapped[str] = mapped_column(String(80), nullable=False)

    # Package pins (Section F).
    fx_snapshot_id: Mapped[str | None] = mapped_column(
        ForeignKey("fh_exchange_rate_snapshots.id", ondelete="RESTRICT"), nullable=True
    )
    currency_unit_registry_version: Mapped[str] = mapped_column(String(40), nullable=False)
    channel_config_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("pm_channel_config_revisions.id", ondelete="RESTRICT"), nullable=True
    )
    mapping_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("sc_source_mapping_revisions.id", ondelete="RESTRICT"), nullable=True
    )
    product_metadata_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """No product-metadata revision table exists yet; this is a checksum of the
    pinned product fields at freeze time, not a foreign key to a revision."""
    arithmetic_version: Mapped[str] = mapped_column(String(40), nullable=False)

    dependency_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)

    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


# ---------------------------------------------------------------------------
# B. Multi-source Observation selection evidence
# ---------------------------------------------------------------------------


class PackageSourceObservationPin(FlowHubBase):
    """Exactly one pinned Observation per required Source role in a package."""

    __tablename__ = "pev_package_source_observation_pins"
    __table_args__ = (
        CheckConstraint(f"selection_mode IN ({_SELECTION_MODES})", name="ck_pev_pin_selection_mode"),
        CheckConstraint(f"freshness_result IN ({_FRESHNESS_RESULTS})", name="ck_pev_pin_freshness"),
        CheckConstraint(
            f"cross_source_skew_result IS NULL OR cross_source_skew_result IN ({_SKEW_RESULTS})",
            name="ck_pev_pin_skew",
        ),
        UniqueConstraint(
            "frozen_evaluation_package_id", "source_role", name="uq_pev_pin_package_role"
        ),
        Index("ix_pev_pin_observation", "observation_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    frozen_evaluation_package_id: Mapped[str] = mapped_column(
        ForeignKey("pev_frozen_evaluation_packages.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_role: Mapped[str] = mapped_column(String(80), nullable=False)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("sc_sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    resource_binding_revision_id: Mapped[str | None] = mapped_column(String(120), nullable=True)

    observation_id: Mapped[str] = mapped_column(
        ForeignKey("saq_observations.id", ondelete="RESTRICT"), nullable=False
    )
    observation_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    selection_mode: Mapped[str] = mapped_column(String(40), nullable=False)
    selection_policy_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    as_of: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    business_effective_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    business_cycle_identity: Mapped[str | None] = mapped_column(String(120), nullable=True)

    freshness_result: Mapped[str] = mapped_column(String(20), nullable=False)
    cross_source_skew_result: Mapped[str | None] = mapped_column(String(30), nullable=True)
    schema_unit_context_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


# ---------------------------------------------------------------------------
# C. Manual inputs
# ---------------------------------------------------------------------------


class ManualInputRevision(FlowHubBase):
    """Immutable versioned manual pricing input.

    No mutable current-value field exists on this model or any related model:
    the *current* decision is always resolved by deterministic query over
    ``ManualInputDecision`` (see ``service.resolve_manual_input``), never by a
    mutable pointer column.
    """

    __tablename__ = "pev_manual_input_revisions"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_MANUAL_INPUT_KINDS})", name="ck_pev_manual_input_kind"),
        UniqueConstraint(
            "kind", "channel_id", "product_ref", "revision_number",
            name="uq_pev_manual_input_revision_number",
        ),
        UniqueConstraint("checksum", name="uq_pev_manual_input_checksum"),
        Index("ix_pev_manual_input_scope", "kind", "channel_id", "product_ref"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    channel_id: Mapped[str | None] = mapped_column(
        ForeignKey("uw_channels.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    product_ref: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)

    value_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    currency: Mapped[str | None] = mapped_column(String(12), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(24), nullable=True)

    effective_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class ManualInputDecision(FlowHubBase):
    """Append-only decision lineage for one ``ManualInputRevision``."""

    __tablename__ = "pev_manual_input_decisions"
    __table_args__ = (
        CheckConstraint(f"decision IN ({_MANUAL_DECISION_KINDS})", name="ck_pev_manual_decision_kind"),
        Index("ix_pev_manual_decision_revision", "manual_input_revision_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    manual_input_revision_id: Mapped[str] = mapped_column(
        ForeignKey("pev_manual_input_revisions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    predecessor_decision_id: Mapped[str | None] = mapped_column(
        ForeignKey("pev_manual_input_decisions.id", ondelete="RESTRICT"), nullable=True
    )
    actor_user_id: Mapped[int] = mapped_column(
        ForeignKey("flowhub_users.id", ondelete="RESTRICT"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class PackageManualInputPin(FlowHubBase):
    """Pins one approved ``ManualInputRevision``/``ManualInputDecision`` pair into a package."""

    __tablename__ = "pev_package_manual_input_pins"
    __table_args__ = (
        UniqueConstraint(
            "frozen_evaluation_package_id", "manual_input_revision_id",
            name="uq_pev_manual_pin_package_revision",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    frozen_evaluation_package_id: Mapped[str] = mapped_column(
        ForeignKey("pev_frozen_evaluation_packages.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    manual_input_revision_id: Mapped[str] = mapped_column(
        ForeignKey("pev_manual_input_revisions.id", ondelete="RESTRICT"), nullable=False
    )
    manual_input_decision_id: Mapped[str] = mapped_column(
        ForeignKey("pev_manual_input_decisions.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


# ---------------------------------------------------------------------------
# D. Override evidence
# ---------------------------------------------------------------------------


class PackagePriceOverride(FlowHubBase):
    """Preserves candidate, override, and effective output as distinct evidence.

    Authoritative Architecture / Section D: an active override does not
    suppress normal candidate calculation. ``calculated_candidate_*`` is
    always populated; ``override_value_*`` is populated only when an
    approved override decision applies.
    """

    __tablename__ = "pev_package_price_overrides"
    __table_args__ = (
        CheckConstraint(
            f"effective_output_source IN ({_EFFECTIVE_OUTPUT_SOURCES})",
            name="ck_pev_override_effective_source",
        ),
        CheckConstraint("calculated_candidate_denominator > 0", name="ck_pev_override_candidate_denom"),
        CheckConstraint(
            "override_value_denominator IS NULL OR override_value_denominator > 0",
            name="ck_pev_override_value_denom",
        ),
        UniqueConstraint("frozen_evaluation_package_id", name="uq_pev_override_package"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    frozen_evaluation_package_id: Mapped[str] = mapped_column(
        ForeignKey("pev_frozen_evaluation_packages.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    calculated_candidate_numerator: Mapped[int] = mapped_column(BigInteger, nullable=False)
    calculated_candidate_denominator: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)

    override_value_numerator: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    override_value_denominator: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    override_manual_input_decision_id: Mapped[str | None] = mapped_column(
        ForeignKey("pev_manual_input_decisions.id", ondelete="RESTRICT"), nullable=True
    )

    effective_output_numerator: Mapped[int] = mapped_column(BigInteger, nullable=False)
    effective_output_denominator: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    effective_output_source: Mapped[str] = mapped_column(String(24), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


# ---------------------------------------------------------------------------
# E. Derived values
# ---------------------------------------------------------------------------


class DerivedValueDefinition(FlowHubBase):
    """Immutable closed-typed derivation definition. No expression strings."""

    __tablename__ = "pev_derived_value_definitions"
    __table_args__ = (
        CheckConstraint(f"operator IN ({_DERIVED_OPERATORS})", name="ck_pev_derived_operator"),
        UniqueConstraint("checksum", name="uq_pev_derived_definition_checksum"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    operator: Mapped[str] = mapped_column(String(30), nullable=False)
    parameters_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    dependency_refs_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    """Ordered list of ``{"kind": DependencyRefKind, ...}`` references. See
    ``derived.py`` for the exact per-kind shape."""
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class DerivedValueEvaluation(FlowHubBase):
    """Immutable evidence of one derived-value evaluation inside one package.

    Authoritative Architecture rule 7: derived results are evidence, not
    authoritative reusable inputs. This table is never read as an upstream
    dependency source across a different package (see ``derived.py``:
    ``REASON_DERIVED_CROSS_PACKAGE_DEPENDENCY``).
    """

    __tablename__ = "pev_derived_value_evaluations"
    __table_args__ = (
        CheckConstraint("result_denominator > 0", name="ck_pev_derived_eval_denom"),
        CheckConstraint("evaluation_order >= 0", name="ck_pev_derived_eval_order"),
        UniqueConstraint(
            "frozen_evaluation_package_id", "derived_value_definition_id",
            name="uq_pev_derived_eval_package_definition",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    frozen_evaluation_package_id: Mapped[str] = mapped_column(
        ForeignKey("pev_frozen_evaluation_packages.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    derived_value_definition_id: Mapped[str] = mapped_column(
        ForeignKey("pev_derived_value_definitions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    evaluation_order: Mapped[int] = mapped_column(Integer, nullable=False)
    result_numerator: Mapped[int] = mapped_column(BigInteger, nullable=False)
    result_denominator: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    inputs_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


_IMMUTABLE_MODELS = (
    FrozenEvaluationPackage,
    PackageSourceObservationPin,
    ManualInputRevision,
    PackageManualInputPin,
    PackagePriceOverride,
    DerivedValueDefinition,
    DerivedValueEvaluation,
)

_APPEND_ONLY_MODELS = (ManualInputDecision,)


def _reject_immutable_change(_mapper: Mapper[Any], _connection: Connection, target: Any) -> None:
    raise ImmutableRecordError(f"{target.__class__.__name__} records are immutable.")


def _reject_append_only_mutation(_mapper: Mapper[Any], _connection: Connection, target: Any) -> None:
    raise ImmutableRecordError(f"{target.__class__.__name__} records are append-only.")


for _model in _IMMUTABLE_MODELS:
    event.listen(_model, "before_update", _reject_immutable_change)
    event.listen(_model, "before_delete", _reject_immutable_change)

for _model in _APPEND_ONLY_MODELS:
    event.listen(_model, "before_update", _reject_append_only_mutation)
    event.listen(_model, "before_delete", _reject_append_only_mutation)
