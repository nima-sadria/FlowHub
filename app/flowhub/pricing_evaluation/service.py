"""Orchestrates immutable Frozen Evaluation Package construction.

This service is the only place that assembles a
``FrozenEvaluationPackage`` and its pinned evidence into one atomic,
immutable unit. It never writes a Channel price and never calls
``WritePipelineService``; Phase B is evidence-only.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from fractions import Fraction
from typing import Any

from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.pricing_evaluation.contracts import (
    PRICING_EVALUATION_ARITHMETIC_VERSION,
    DependencyRefKind,
    EffectiveOutputSource,
    ManualInputDecisionKind,
    ObservationSelectionMode,
    SkewResult,
)
from app.flowhub.pricing_evaluation.derived import (
    DefinitionDraft,
    evaluate_operator,
    topological_order,
    validate_dag,
)
from app.flowhub.pricing_evaluation.errors import (
    REASON_CHANNEL_NOT_FOUND,
    REASON_CROSS_SOURCE_SKEW_VIOLATION,
    REASON_DERIVED_DEPENDENCY_MISSING,
    REASON_MANUAL_INPUT_MISSING,
    REASON_MANUAL_INPUT_SCOPE_MISMATCH,
    DependencyResolutionError,
    DerivedValueError,
)
from app.flowhub.pricing_evaluation.fingerprint import (
    compute_dependency_fingerprint,
    compute_package_checksum,
)
from app.flowhub.pricing_evaluation.manual_inputs import DecisionRecord, resolve_current_decision
from app.flowhub.pricing_evaluation.models import (
    DerivedValueDefinition,
    DerivedValueEvaluation,
    FrozenEvaluationPackage,
    ManualInputDecision,
    ManualInputRevision,
    PackageManualInputPin,
    PackagePriceOverride,
    PackageSourceObservationPin,
)
from app.flowhub.pricing_evaluation.selection import (
    ObservationCandidate,
    SelectionResult,
    evaluate_cross_source_skew,
    select_observation,
)
from app.flowhub.unified_workspace.domain import checksum, utcnow
from app.flowhub.unified_workspace.models import WorkspaceChannel


def _id() -> str:
    return str(uuid.uuid4())


@dataclass(frozen=True, slots=True)
class SourceRequirement:
    """One required Source for a package, with its selection policy inputs."""

    source_role: str
    source_id: str
    mode: ObservationSelectionMode
    candidates: tuple[ObservationCandidate, ...]
    value: Fraction
    """The resolved numeric leaf value for this Observation. Extracting a
    value from raw acquired content is a Formula Translator concern (out of
    Phase B scope); this service only pins and evaluates already-resolved
    values."""
    resource_binding_revision_id: str | None = None
    as_of: datetime | None = None
    business_cycle_identity: str | None = None
    business_effective_date: datetime | None = None
    explicit_observation_id: str | None = None
    freshness_max_age: timedelta | None = None
    require_fresh: bool = True
    selection_policy_version: str | None = None
    schema_unit_context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ManualInputRequirement:
    """Pins one already-decided ``ManualInputRevision`` into the package."""

    manual_input_revision_id: str
    key: str
    """Dependency-graph key usable by derived-value definitions via
    ``DependencyRef(kind=MANUAL_INPUT, key=...)``."""
    value: Fraction


@dataclass(frozen=True, slots=True)
class OverrideRequest:
    override_value: Fraction
    manual_input_decision_id: str


@dataclass(frozen=True, slots=True)
class PackageResult:
    package: FrozenEvaluationPackage
    source_pins: tuple[PackageSourceObservationPin, ...]
    manual_input_pins: tuple[PackageManualInputPin, ...]
    derived_evaluations: tuple[DerivedValueEvaluation, ...]
    override: PackagePriceOverride | None


class FrozenEvaluationPackageService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # -- Manual input decisions ------------------------------------------------

    def resolve_manual_input(
        self, manual_input_revision_id: str, *, now: datetime
    ) -> ManualInputDecision:
        revision = self.db.get(ManualInputRevision, manual_input_revision_id)
        if revision is None:
            raise DependencyResolutionError(REASON_MANUAL_INPUT_MISSING)
        rows = (
            self.db.query(ManualInputDecision)
            .filter(ManualInputDecision.manual_input_revision_id == manual_input_revision_id)
            .all()
        )
        records = tuple(
            DecisionRecord(id=row.id, decision=ManualInputDecisionKind(row.decision), created_at=row.created_at)
            for row in rows
        )
        current = resolve_current_decision(records, now=now, expires_at=revision.expires_at)
        return self.db.get(ManualInputDecision, current.id)  # type: ignore[return-value]

    # -- Package construction ---------------------------------------------------

    def create_package(
        self,
        *,
        channel_id: str,
        product_ref: str,
        workspace_id: str | None,
        workspace_pricing_evaluated_at: datetime,
        formula_shape_id: str,
        translator_version: str,
        pricing_policy_revision_id: str | None,
        currency_unit_registry_version: str,
        fx_snapshot_id: str | None,
        channel_config_revision_id: str | None,
        mapping_revision_id: str | None,
        product_metadata_fingerprint: str | None,
        source_requirements: tuple[SourceRequirement, ...],
        manual_input_requirements: tuple[ManualInputRequirement, ...] = (),
        cross_source_skew_tolerance: timedelta | None = None,
        derived_definitions: tuple[DefinitionDraft, ...] = (),
        calculated_candidate: Fraction | None = None,
        override: OverrideRequest | None = None,
        created_by_user: FlowHubUser | None = None,
        now: datetime | None = None,
    ) -> PackageResult:
        now = now or utcnow()

        if self.db.get(WorkspaceChannel, channel_id) is None:
            raise DependencyResolutionError(REASON_CHANNEL_NOT_FOUND)

        # -- B. Multi-source Observation selection -----------------------------
        selected_by_role: dict[str, tuple[SourceRequirement, SelectionResult]] = {}
        observed_at_by_role: dict[str, datetime] = {}
        for requirement in source_requirements:
            result = select_observation(
                mode=requirement.mode,
                candidates=requirement.candidates,
                now=now,
                as_of=requirement.as_of,
                business_cycle_identity=requirement.business_cycle_identity,
                business_effective_date=requirement.business_effective_date,
                explicit_observation_id=requirement.explicit_observation_id,
                freshness_max_age=requirement.freshness_max_age,
                require_fresh=requirement.require_fresh,
            )
            selected_by_role[requirement.source_role] = (requirement, result)
            observed_at_by_role[requirement.source_role] = result.candidate.observed_at

        skew_result = evaluate_cross_source_skew(
            observed_at_by_role, tolerance=cross_source_skew_tolerance
        )
        if skew_result is SkewResult.VIOLATION:
            raise DependencyResolutionError(REASON_CROSS_SOURCE_SKEW_VIOLATION)

        # -- C. Manual inputs ----------------------------------------------------
        manual_decisions: dict[str, ManualInputDecision] = {}
        manual_values: dict[str, Fraction] = {}
        for req in manual_input_requirements:
            revision = self.db.get(ManualInputRevision, req.manual_input_revision_id)
            if revision is None:
                raise DependencyResolutionError(REASON_MANUAL_INPUT_MISSING)
            if revision.channel_id is not None and revision.channel_id != channel_id:
                raise DependencyResolutionError(REASON_MANUAL_INPUT_SCOPE_MISMATCH)
            if revision.product_ref is not None and revision.product_ref != product_ref:
                raise DependencyResolutionError(REASON_MANUAL_INPUT_SCOPE_MISMATCH)
            decision = self.resolve_manual_input(req.manual_input_revision_id, now=now)
            manual_decisions[req.manual_input_revision_id] = decision
            manual_values[req.key] = req.value

        try:
            with self.db.begin_nested():
                package_id = _id()

                source_pin_rows: list[PackageSourceObservationPin] = []
                source_pin_tuples: list[tuple[str, str, str]] = []
                for role, (requirement, result) in sorted(selected_by_role.items()):
                    pin = PackageSourceObservationPin(
                        id=_id(),
                        frozen_evaluation_package_id=package_id,
                        source_role=role,
                        source_id=requirement.source_id,
                        resource_binding_revision_id=requirement.resource_binding_revision_id,
                        observation_id=result.candidate.observation_id,
                        observation_checksum=result.candidate.checksum,
                        observed_at=result.candidate.observed_at,
                        selection_mode=requirement.mode.value,
                        selection_policy_version=requirement.selection_policy_version,
                        as_of=requirement.as_of,
                        business_effective_date=requirement.business_effective_date,
                        business_cycle_identity=result.candidate.business_cycle_identity,
                        freshness_result=result.freshness_result.value,
                        cross_source_skew_result=skew_result.value,
                        schema_unit_context_json=dict(requirement.schema_unit_context),
                    )
                    source_pin_rows.append(pin)
                    source_pin_tuples.append(
                        (role, result.candidate.observation_id, result.candidate.checksum)
                    )
                self.db.add_all(source_pin_rows)

                manual_pin_rows: list[PackageManualInputPin] = []
                manual_pin_tuples: list[tuple[str, str]] = []
                for req in manual_input_requirements:
                    decision = manual_decisions[req.manual_input_revision_id]
                    manual_pin_rows.append(
                        PackageManualInputPin(
                            id=_id(),
                            frozen_evaluation_package_id=package_id,
                            manual_input_revision_id=req.manual_input_revision_id,
                            manual_input_decision_id=decision.id,
                        )
                    )
                    manual_pin_tuples.append((req.manual_input_revision_id, decision.id))
                self.db.add_all(manual_pin_rows)

                # -- E. Derived values --------------------------------------------
                draft_by_key = {d.definition_key: d for d in derived_definitions}
                validate_dag(draft_by_key)
                order = topological_order(draft_by_key)

                leaf_values: dict[str, Fraction] = {}
                for role, (_requirement, _result) in selected_by_role.items():
                    leaf_values[role] = selected_by_role[role][0].value
                leaf_values.update(manual_values)

                key_to_definition_id: dict[str, str] = {}
                key_to_result: dict[str, Fraction] = dict(leaf_values)
                evaluation_rows: list[DerivedValueEvaluation] = []
                for index, key in enumerate(order):
                    draft = draft_by_key[key]
                    resolved_refs: list[dict[str, Any]] = []
                    input_values: list[Fraction] = []
                    for ref in draft.dependencies:
                        if ref.kind is DependencyRefKind.DERIVED:
                            resolved_key = key_to_definition_id[ref.key]
                            input_values.append(key_to_result[ref.key])
                        else:
                            resolved_key = ref.key
                            if ref.key not in key_to_result:
                                raise DerivedValueError(REASON_DERIVED_DEPENDENCY_MISSING)
                            input_values.append(key_to_result[ref.key])
                        resolved_refs.append({"kind": ref.kind.value, "key": resolved_key})

                    definition_checksum = checksum(
                        {
                            "operator": draft.operator.value,
                            "parameters": draft.parameters,
                            "dependency_refs": resolved_refs,
                        }
                    )
                    existing = (
                        self.db.query(DerivedValueDefinition)
                        .filter(DerivedValueDefinition.checksum == definition_checksum)
                        .one_or_none()
                    )
                    if existing is None:
                        definition = DerivedValueDefinition(
                            id=_id(),
                            operator=draft.operator.value,
                            parameters_json=dict(draft.parameters),
                            dependency_refs_json=resolved_refs,
                            checksum=definition_checksum,
                        )
                        self.db.add(definition)
                        self.db.flush()
                    else:
                        definition = existing
                    key_to_definition_id[key] = definition.id

                    result_value = evaluate_operator(draft.operator, draft.parameters, tuple(input_values))
                    key_to_result[key] = result_value

                    eval_checksum = checksum(
                        {
                            "package_id": package_id,
                            "definition_id": definition.id,
                            "inputs": [str(v) for v in input_values],
                            "result": str(result_value),
                        }
                    )
                    evaluation_rows.append(
                        DerivedValueEvaluation(
                            id=_id(),
                            frozen_evaluation_package_id=package_id,
                            derived_value_definition_id=definition.id,
                            evaluation_order=index,
                            result_numerator=result_value.numerator,
                            result_denominator=result_value.denominator,
                            inputs_snapshot_json={
                                "refs": resolved_refs,
                                "values": [str(v) for v in input_values],
                            },
                            checksum=eval_checksum,
                        )
                    )
                self.db.add_all(evaluation_rows)

                # -- D. Override -----------------------------------------------------
                override_row: PackagePriceOverride | None = None
                if calculated_candidate is not None:
                    if override is not None:
                        override_row = PackagePriceOverride(
                            id=_id(),
                            frozen_evaluation_package_id=package_id,
                            calculated_candidate_numerator=calculated_candidate.numerator,
                            calculated_candidate_denominator=calculated_candidate.denominator,
                            override_value_numerator=override.override_value.numerator,
                            override_value_denominator=override.override_value.denominator,
                            override_manual_input_decision_id=override.manual_input_decision_id,
                            effective_output_numerator=override.override_value.numerator,
                            effective_output_denominator=override.override_value.denominator,
                            effective_output_source=EffectiveOutputSource.OVERRIDE_VALUE.value,
                        )
                    else:
                        override_row = PackagePriceOverride(
                            id=_id(),
                            frozen_evaluation_package_id=package_id,
                            calculated_candidate_numerator=calculated_candidate.numerator,
                            calculated_candidate_denominator=calculated_candidate.denominator,
                            override_value_numerator=None,
                            override_value_denominator=None,
                            override_manual_input_decision_id=None,
                            effective_output_numerator=calculated_candidate.numerator,
                            effective_output_denominator=calculated_candidate.denominator,
                            effective_output_source=EffectiveOutputSource.CALCULATED_CANDIDATE.value,
                        )
                    self.db.add(override_row)

                # -- G. Fingerprint and checksum --------------------------------------
                dependency_fingerprint = compute_dependency_fingerprint(
                    channel_id=channel_id,
                    product_ref=product_ref,
                    formula_shape_id=formula_shape_id,
                    translator_version=translator_version,
                    fx_snapshot_id=fx_snapshot_id,
                    currency_unit_registry_version=currency_unit_registry_version,
                    channel_config_revision_id=channel_config_revision_id,
                    mapping_revision_id=mapping_revision_id,
                    product_metadata_fingerprint=product_metadata_fingerprint,
                    arithmetic_version=PRICING_EVALUATION_ARITHMETIC_VERSION,
                    pricing_policy_revision_id=pricing_policy_revision_id,
                    source_pins=source_pin_tuples,
                    manual_input_pins=manual_pin_tuples,
                    derived_definition_ids=sorted(key_to_definition_id.values()),
                )
                package_checksum = compute_package_checksum(
                    channel_id=channel_id,
                    product_ref=product_ref,
                    workspace_id=workspace_id,
                    workspace_pricing_evaluated_at=workspace_pricing_evaluated_at.isoformat(),
                    dependency_fingerprint=dependency_fingerprint,
                )

                package = FrozenEvaluationPackage(
                    id=package_id,
                    workspace_id=workspace_id,
                    channel_id=channel_id,
                    product_ref=product_ref,
                    workspace_pricing_evaluated_at=workspace_pricing_evaluated_at,
                    pricing_policy_revision_id=pricing_policy_revision_id,
                    formula_shape_id=formula_shape_id,
                    translator_version=translator_version,
                    fx_snapshot_id=fx_snapshot_id,
                    currency_unit_registry_version=currency_unit_registry_version,
                    channel_config_revision_id=channel_config_revision_id,
                    mapping_revision_id=mapping_revision_id,
                    product_metadata_fingerprint=product_metadata_fingerprint,
                    arithmetic_version=PRICING_EVALUATION_ARITHMETIC_VERSION,
                    dependency_fingerprint=dependency_fingerprint,
                    checksum=package_checksum,
                    created_by_user_id=created_by_user.id if created_by_user is not None else None,
                )
                self.db.add(package)
                self.db.flush()
        except Exception:
            self.db.rollback()
            raise
        self.db.commit()

        return PackageResult(
            package=package,
            source_pins=tuple(source_pin_rows),
            manual_input_pins=tuple(manual_pin_rows),
            derived_evaluations=tuple(evaluation_rows),
            override=override_row,
        )
