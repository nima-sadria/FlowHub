"""Shadow validation comparison assembly (Phase C3)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import FlowHubBase
from app.flowhub.exchange_rates import models as _exchange_rates_models  # noqa: F401
from app.flowhub.pricing_authority.models import ChannelPricingAuthorityEvent
from app.flowhub.pricing_authority.models import ChannelPricingAuthorityHead
from app.flowhub.pricing_authority import models as _pricing_authority_models  # noqa: F401
from app.flowhub.pricing_evaluation.models import (
    DerivedValueEvaluation,
    FrozenEvaluationPackage,
    ManualInputDecision,
    ManualInputRevision,
    PackagePriceOverride,
    PackageManualInputPin,
)
from app.flowhub.pricing_evaluation.contracts import EffectiveOutputSource
from app.flowhub.pricing_evaluation.contracts import ManualInputDecisionKind
from app.flowhub.pricing_matrix import models as _pricing_matrix_models  # noqa: F401
from app.flowhub.shadow_validation import contracts
from app.flowhub.shadow_validation.contracts import (
    ComparisonConfidence,
    ComparisonPrimaryClassification,
    ShadowValidationWindowState,
    ValidationWindowEventKind,
    WindowReadinessReason,
    WindowReadinessState,
)
from app.flowhub.shadow_validation.errors import (
    REASON_AUTHORITY_MISMATCH,
    REASON_CONTRACT_UNAPPROVED,
    REASON_POLICY_MISMATCH,
    REASON_FEP_CAPTURE_MISMATCH,
    REASON_OUTPUT_LANES_UNSUPPORTED,
    ShadowValidationError,
)
from app.flowhub.shadow_validation.models import (
    LegacyFormulaCapture,
    ShapeComparisonContract,
    ShadowValidationWindowHead,
    ShadowValidationWindowEvent,
    ShadowValidationWindow,
    ShadowReadinessDecision,
    ShadowValidationComparison,
)
from app.flowhub.shadow_validation.service import (
    ShadowValidationComparisonAssemblyService,
    ShadowValidationReadinessService,
)
from app.flowhub.source_acquisition import models as _source_acquisition_models  # noqa: F401
from app.flowhub.source_workspace import models as _source_workspace_models  # noqa: F401
from app.flowhub.unified_workspace.domain import utcnow
from app.flowhub.unified_workspace.models import WorkspaceChannel
from app.flowhub.pricing_matrix.models import (
    ChannelPricingPolicyHead,
    PricingChannelConfigRevision,
    PricingPolicyLifecycleEvent,
    PricingPolicyRevision,
)


@dataclass
class ComparisonFixture:
    channel_id: str
    policy_revision_id: str
    window_id: str
    fep_id: str
    capture_id: str
    contract_id: str
    override_id: str
    authority_event_id: str


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    FlowHubBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    user = FlowHubUser(id=1001, username="svc", hashed_password="ignored", role="admin")
    channel = WorkspaceChannel(
        id="channel-shadow",
        connector_type="test",
        name="Shadow Channel",
        implementation_state="implemented",
        capabilities_json={},
        capability_version="v1",
        enabled=True,
    )
    authority_event = ChannelPricingAuthorityEvent(
        id="authority-event-1",
        channel_id=channel.id,
        new_authority="legacy_formula_engine",
        expected_head_version=0,
        actor_reference="seed",
        reason="seed",
        request_metadata_json={},
    )
    policy_revision = PricingPolicyRevision(
        id="policy-revision-1",
        policy_id="policy-1",
        revision_number=1,
        name="policy",
        computation_currency="USD",
        round_order="round_then_surcharge",
        max_quote_age_days=30,
        min_quote_count=1,
        evaluation_timezone="UTC",
        arithmetic_version="arith-v1",
        unit_registry_version="unit-v1",
        checksum="policy-checksum-1",
        created_by_user_id=1001,
    )

    fep = FrozenEvaluationPackage(
        id="fep-1",
        channel_id=channel.id,
        product_ref="sku-shadow",
        workspace_pricing_evaluated_at=utcnow(),
        formula_shape_id="A1",
        translator_version="translator-v1",
        currency_unit_registry_version="v1",
        arithmetic_version="arith-v1",
        dependency_fingerprint="dep-1",
        checksum="fep-checksum-1",
        pricing_policy_revision_id=policy_revision.id,
    )

    capture = LegacyFormulaCapture(
        id="capture-1",
        channel_id=channel.id,
        frozen_evaluation_package_id=fep.id,
        legacy_formula_engine="legacy-engine",
        legacy_formula_engine_version="1",
        formula_shape_id="A1",
        formula_rule_identity="rule-1",
        workbook_identity="ws-1",
        workbook_revision="r-1",
        input_manifest_checksum="input-checksum-1",
        pricing_authority_event_id=authority_event.id,
        pricing_authority_head_version=0,
        captured_at=utcnow(),
        candidate_numerator=100,
        candidate_denominator=10,
        effective_numerator=100,
        effective_denominator=10,
        candidate_currency="USD",
        candidate_unit="USD",
        effective_currency="USD",
        effective_unit="USD",
        output_context_json={"trace_components": ["component-a", "component-b"]},
        capture_checksum="capture-checksum-1",
    )

    contract = ShapeComparisonContract(
        id="contract-1",
        shape_id="A1",
        contract_revision="rev-1",
        contract_version="v1",
        contract_checksum="contract-checksum-1",
        formula_inventory_checksum="formula-inventory-1",
        target_kind=contracts.ShapeTargetKind.PRICE_TARGET.value,
        stable_rule_identity_json={
            "formula_shape_id": "A1",
            "formula_rule_identity": "rule-1",
        },
        required_input_identity_json={
            "shape_id": "A1",
            "formula_shape_id": "A1",
            "formula_rule_identity": "rule-1",
            "input_manifest_checksum": "input-checksum-1",
            "fep_dependency_fingerprint": "dep-1",
            "pricing_policy_revision_id": "policy-revision-1",
            "translator_version": "translator-v1",
        },
        required_output_lanes_json=["candidate", "effective"],
        canonical_context_json={
            "formula_shape_id": "A1",
            "translator_version": "translator-v1",
            "fep_formula_shape_id": "A1",
        },
        equality_rule_json={"method": "exact"},
        required_trace_components_json=["component-a", "component-b"],
        acceptance_effect=contracts.ShapeAcceptanceEffect.MAY_COUNT.value,
        classification_mapping_json={
            "effective_value_divergence": "accepted_expected_rounding",
            "candidate_value_divergence": "review_required",
            "output_context_divergence": "review_required",
            "trace_divergence": "accepted_documented_semantic_difference",
        },
        is_current=True,
    )

    window = ShadowValidationWindow(
        id="window-1",
        channel_id=channel.id,
        scope_manifest_checksum="scope-checksum-1",
        formula_inventory_checksum="formula-inventory-1",
        acceptance_policy_revision="policy-accept",
        pricing_policy_revision_id=policy_revision.id,
        pricing_authority_event_id=authority_event.id,
        pricing_authority_head_version=0,
        head_version_snapshot=0,
        opened_at=utcnow(),
        closes_at=None,
        required_distinct_matches=1,
        configuration_checksum="window-checksum-1",
    )
    override = PackagePriceOverride(
        id="override-1",
        frozen_evaluation_package_id=fep.id,
        calculated_candidate_numerator=100,
        calculated_candidate_denominator=10,
        effective_output_numerator=100,
        effective_output_denominator=10,
        effective_output_source=EffectiveOutputSource.CALCULATED_CANDIDATE.value,
    )
    derived_evaluation = DerivedValueEvaluation(
        id="derived-1",
        frozen_evaluation_package_id=fep.id,
        derived_value_definition_id="def-1",
        evaluation_order=1,
        result_numerator=5,
        result_denominator=1,
        inputs_snapshot_json={},
        checksum="derived-checksum-1",
    )

    session.add_all(
        (
            user,
            channel,
            policy_revision,
            authority_event,
            fep,
            capture,
            contract,
            window,
            override,
            derived_evaluation,
        )
    )
    session.commit()

    fixture = ComparisonFixture(
        channel_id=channel.id,
        policy_revision_id=policy_revision.id,
        window_id=window.id,
        fep_id=fep.id,
        capture_id=capture.id,
        contract_id=contract.id,
        override_id=override.id,
        authority_event_id=authority_event.id,
    )
    try:
        yield session, fixture
    finally:
        session.close()
        FlowHubBase.metadata.drop_all(engine)
        engine.dispose()


def _build_service(session: sa.orm.Session) -> ShadowValidationComparisonAssemblyService:
    return ShadowValidationComparisonAssemblyService(session)


def test_assemble_exact_match_persists_immutable_comparison(db: tuple[sa.orm.Session, ComparisonFixture]):
    session, fixture = db
    service = _build_service(session)

    result = service.assemble(
        validation_window_id=fixture.window_id,
        frozen_evaluation_package_id=fixture.fep_id,
        legacy_formula_capture_id=fixture.capture_id,
    )

    assert result.primary_classification == ComparisonPrimaryClassification.EXACT_MATCH.value
    assert result.confidence == ComparisonConfidence.VERIFIED.value
    assert result.reason_code is None
    assert result.secondary_classifications == ()
    assert result.comparison.required_output_lanes == "both"
    assert result.comparison.id
    assert result.comparison.actor_user_id is None
    assert result.comparison.secondary_classifications_json == []

    link_payload = result.comparison.legacy_vs_package_context_json
    assert link_payload["fep_id"] == fixture.fep_id
    assert link_payload["capture_id"] == fixture.capture_id
    assert link_payload["contract_id"] == fixture.contract_id

    same_checksum = result.comparison.comparison_identity_checksum

    again = service.assemble(
        validation_window_id=fixture.window_id,
        frozen_evaluation_package_id=fixture.fep_id,
        legacy_formula_capture_id=fixture.capture_id,
    )
    assert again.primary_classification == ComparisonPrimaryClassification.EXACT_MATCH.value
    assert again.comparison.comparison_identity_checksum == same_checksum
    assert again.comparison.id != result.comparison.id
    assert (
        session.query(ShadowValidationComparison)
        .filter_by(comparison_identity_checksum=same_checksum)
        .count()
        == 2
    )


def test_assemble_marks_review_required_on_output_context_divergence(db):
    session, fixture = db
    contract = ShapeComparisonContract(
        id="contract-context-1",
        shape_id="A1",
        contract_revision="rev-context-1",
        contract_version="v1",
        contract_checksum="contract-checksum-ctx-1",
        formula_inventory_checksum="formula-inventory-1",
        target_kind=contracts.ShapeTargetKind.PRICE_TARGET.value,
        stable_rule_identity_json={
            "formula_shape_id": "A1",
            "formula_rule_identity": "rule-1",
        },
        required_input_identity_json={
            "shape_id": "A1",
            "formula_shape_id": "A1",
            "formula_rule_identity": "rule-1",
            "input_manifest_checksum": "input-checksum-1",
            "fep_dependency_fingerprint": "dep-1",
            "pricing_policy_revision_id": "policy-revision-1",
            "translator_version": "translator-v1",
        },
        required_output_lanes_json=["candidate", "effective"],
        canonical_context_json={"formula_shape_id": "DIFFERENT"},
        equality_rule_json={"method": "exact"},
        required_trace_components_json=["component-a", "component-b"],
        acceptance_effect=contracts.ShapeAcceptanceEffect.MAY_COUNT.value,
        classification_mapping_json={
            "effective_value_divergence": "accepted_expected_rounding",
            "candidate_value_divergence": "review_required",
            "output_context_divergence": "review_required",
            "trace_divergence": "accepted_documented_semantic_difference",
        },
        is_current=True,
    )
    session.add(contract)
    session.commit()

    service = _build_service(session)
    result = service.assemble(
        validation_window_id=fixture.window_id,
        frozen_evaluation_package_id=fixture.fep_id,
        legacy_formula_capture_id=fixture.capture_id,
        comparison_contract_id=contract.id,
    )

    assert result.primary_classification == ComparisonPrimaryClassification.REVIEW_REQUIRED.value
    assert result.confidence == ComparisonConfidence.VERIFIED.value
    assert result.reason_code is None


def test_assemble_marks_accepted_expected_rounding_for_effective_divergence(db):
    session, fixture = db
    fep = FrozenEvaluationPackage(
        id="fep-2",
        channel_id=fixture.channel_id,
        product_ref="sku-shadow",
        workspace_pricing_evaluated_at=utcnow(),
        formula_shape_id="A1",
        translator_version="translator-v1",
        currency_unit_registry_version="v1",
        arithmetic_version="arith-v1",
        dependency_fingerprint="dep-1",
        checksum="fep-checksum-2",
        pricing_policy_revision_id=fixture.policy_revision_id,
    )
    capture = LegacyFormulaCapture(
        id="capture-2",
        channel_id=fixture.channel_id,
        frozen_evaluation_package_id=fep.id,
        legacy_formula_engine="legacy-engine",
        legacy_formula_engine_version="1",
        formula_shape_id="A1",
        formula_rule_identity="rule-1",
        workbook_identity="ws-1",
        workbook_revision="r-1",
        input_manifest_checksum="input-checksum-1",
        pricing_authority_event_id=fixture.authority_event_id,
        pricing_authority_head_version=0,
        captured_at=utcnow(),
        candidate_numerator=100,
        candidate_denominator=10,
        effective_numerator=100,
        effective_denominator=10,
        candidate_currency="USD",
        candidate_unit="USD",
        effective_currency="USD",
        effective_unit="USD",
        output_context_json={"trace_components": ["component-a", "component-b"]},
        capture_checksum="capture-checksum-2",
    )
    override = PackagePriceOverride(
        id="override-2",
        frozen_evaluation_package_id=fep.id,
        calculated_candidate_numerator=100,
        calculated_candidate_denominator=10,
        effective_output_numerator=101,
        effective_output_denominator=10,
        effective_output_source=EffectiveOutputSource.CALCULATED_CANDIDATE.value,
    )
    session.add_all((fep, capture, override))
    session.commit()

    result = _build_service(session).assemble(
        validation_window_id=fixture.window_id,
        frozen_evaluation_package_id=fep.id,
        legacy_formula_capture_id=capture.id,
    )

    assert result.primary_classification == ComparisonPrimaryClassification.ACCEPTED_EXPECTED_ROUNDING.value
    assert result.secondary_classifications == (
        ComparisonPrimaryClassification.ACCEPTED_EXPECTED_ROUNDING.value,
    )


def test_assemble_partial_provenance_becomes_not_possible(db):
    session, fixture = db
    contract = ShapeComparisonContract(
        id="contract-partial-1",
        shape_id="A1",
        contract_revision="rev-partial-1",
        contract_version="v1",
        contract_checksum="contract-checksum-partial-1",
        formula_inventory_checksum="formula-inventory-1",
        target_kind=contracts.ShapeTargetKind.PRICE_TARGET.value,
        stable_rule_identity_json={
            "formula_shape_id": "A1",
            "formula_rule_identity": "rule-1",
        },
        required_input_identity_json={
            "shape_id": "A1",
            "formula_shape_id": "A1",
            "formula_rule_identity": "different-rule",
            "input_manifest_checksum": "input-checksum-1",
            "fep_dependency_fingerprint": "dep-1",
            "pricing_policy_revision_id": "policy-revision-1",
            "translator_version": "translator-v1",
        },
        required_output_lanes_json=["candidate", "effective"],
        canonical_context_json={
            "formula_shape_id": "A1",
            "translator_version": "translator-v1",
            "fep_formula_shape_id": "A1",
        },
        equality_rule_json={"method": "exact"},
        required_trace_components_json=["component-a", "component-b"],
        acceptance_effect=contracts.ShapeAcceptanceEffect.MAY_COUNT.value,
        classification_mapping_json={
            "effective_value_divergence": "accepted_expected_rounding",
            "candidate_value_divergence": "review_required",
            "output_context_divergence": "review_required",
            "trace_divergence": "accepted_documented_semantic_difference",
        },
        is_current=True,
    )
    session.add(contract)
    session.commit()

    result = _build_service(session).assemble(
        validation_window_id=fixture.window_id,
        frozen_evaluation_package_id=fixture.fep_id,
        legacy_formula_capture_id=fixture.capture_id,
        comparison_contract_id=contract.id,
    )

    assert result.primary_classification == ComparisonPrimaryClassification.NOT_POSSIBLE.value
    assert result.confidence == ComparisonConfidence.PARTIAL.value
    assert result.reason_code == contracts.ShadowValidationReasonCode.PROVENANCE_PARTIAL


def test_assemble_rejects_authority_mismatch(db):
    session, fixture = db
    mismatched_event = ChannelPricingAuthorityEvent(
        id="authority-event-2",
        channel_id=fixture.channel_id,
        new_authority="legacy_formula_engine",
        expected_head_version=1,
        actor_reference="seed",
        reason="seed",
        request_metadata_json={},
    )
    authority_event_2 = ShadowValidationWindow(
        id="window-2",
        channel_id=fixture.channel_id,
        scope_manifest_checksum="scope-checksum-1",
        formula_inventory_checksum="formula-inventory-1",
        acceptance_policy_revision="policy-accept",
        pricing_policy_revision_id=fixture.policy_revision_id,
        pricing_authority_event_id=mismatched_event.id,
        pricing_authority_head_version=1,
        head_version_snapshot=0,
        opened_at=utcnow(),
        closes_at=None,
        required_distinct_matches=1,
        configuration_checksum="window-checksum-2",
    )
    session.add(mismatched_event)
    session.commit()
    session.add(authority_event_2)
    session.commit()

    with pytest.raises(ShadowValidationError) as exc:
        _build_service(session).assemble(
            validation_window_id=authority_event_2.id,
            frozen_evaluation_package_id=fixture.fep_id,
            legacy_formula_capture_id=fixture.capture_id,
        )
    assert str(exc.value) == REASON_AUTHORITY_MISMATCH


def test_assemble_rejects_policy_mismatch(db):
    session, fixture = db
    second_revision = PricingPolicyRevision(
        id="policy-revision-2",
        policy_id="policy-2",
        revision_number=1,
        name="policy-2",
        computation_currency="USD",
        round_order="round_then_surcharge",
        max_quote_age_days=30,
        min_quote_count=1,
        evaluation_timezone="UTC",
        arithmetic_version="arith-v1",
        unit_registry_version="unit-v1",
        checksum="policy-checksum-2",
        created_by_user_id=1001,
    )
    mismatch_window = ShadowValidationWindow(
        id="window-3",
        channel_id=fixture.channel_id,
        scope_manifest_checksum="scope-checksum-1",
        formula_inventory_checksum="formula-inventory-1",
        acceptance_policy_revision="policy-accept",
        pricing_policy_revision_id=second_revision.id,
        pricing_authority_event_id=fixture.authority_event_id,
        pricing_authority_head_version=0,
        head_version_snapshot=0,
        opened_at=utcnow(),
        closes_at=None,
        required_distinct_matches=1,
        configuration_checksum="window-checksum-3",
    )
    session.add_all((second_revision, mismatch_window))
    session.commit()

    with pytest.raises(ShadowValidationError) as exc:
        _build_service(session).assemble(
            validation_window_id=mismatch_window.id,
            frozen_evaluation_package_id=fixture.fep_id,
            legacy_formula_capture_id=fixture.capture_id,
        )
    assert str(exc.value) == REASON_POLICY_MISMATCH


def test_assemble_rejects_unapproved_contract(db):
    session, fixture = db
    contract = ShapeComparisonContract(
        id="contract-unapproved-1",
        shape_id="A1",
        contract_revision="rev-unapproved-1",
        contract_version="v1",
        contract_checksum="contract-checksum-unapproved-1",
        formula_inventory_checksum="formula-inventory-1",
        target_kind=contracts.ShapeTargetKind.PRICE_TARGET.value,
        stable_rule_identity_json={"formula_shape_id": "A1", "formula_rule_identity": "rule-1"},
        required_input_identity_json={
            "shape_id": "A1",
            "formula_shape_id": "A1",
            "formula_rule_identity": "rule-1",
            "input_manifest_checksum": "input-checksum-1",
            "fep_dependency_fingerprint": "dep-1",
            "pricing_policy_revision_id": "policy-revision-1",
            "translator_version": "translator-v1",
        },
        required_output_lanes_json=["candidate", "effective"],
        canonical_context_json={"formula_shape_id": "A1", "translator_version": "translator-v1", "fep_formula_shape_id": "A1"},
        equality_rule_json={"method": "exact"},
        required_trace_components_json=["component-a", "component-b"],
        acceptance_effect=contracts.ShapeAcceptanceEffect.MAY_COUNT.value,
        classification_mapping_json={
            "effective_value_divergence": "accepted_expected_rounding",
            "candidate_value_divergence": "review_required",
            "output_context_divergence": "review_required",
            "trace_divergence": "accepted_documented_semantic_difference",
        },
        is_current=False,
    )
    session.add(contract)
    session.commit()

    service = _build_service(session)
    with pytest.raises(ShadowValidationError) as exc:
        service.assemble(
            validation_window_id=fixture.window_id,
            frozen_evaluation_package_id=fixture.fep_id,
            legacy_formula_capture_id=fixture.capture_id,
            comparison_contract_id=contract.id,
        )
    assert str(exc.value) == REASON_CONTRACT_UNAPPROVED


def test_assemble_rejects_unsupported_shape_contract(db):
    session, fixture = db
    contract = ShapeComparisonContract(
        id="contract-unsupported-1",
        shape_id="A1",
        contract_revision="rev-unsupported-1",
        contract_version="v1",
        contract_checksum="contract-checksum-unsupported-1",
        formula_inventory_checksum="formula-inventory-1",
        target_kind=contracts.ShapeTargetKind.QUARANTINED.value,
        stable_rule_identity_json={"formula_shape_id": "A1", "formula_rule_identity": "rule-1"},
        required_input_identity_json={
            "shape_id": "A1",
            "formula_shape_id": "A1",
            "formula_rule_identity": "rule-1",
            "input_manifest_checksum": "input-checksum-1",
            "fep_dependency_fingerprint": "dep-1",
            "pricing_policy_revision_id": "policy-revision-1",
            "translator_version": "translator-v1",
        },
        required_output_lanes_json=["candidate", "effective"],
        canonical_context_json={"formula_shape_id": "A1", "translator_version": "translator-v1", "fep_formula_shape_id": "A1"},
        equality_rule_json={"method": "exact"},
        required_trace_components_json=["component-a", "component-b"],
        acceptance_effect=contracts.ShapeAcceptanceEffect.MAY_COUNT.value,
        classification_mapping_json={
            "effective_value_divergence": "accepted_expected_rounding",
            "candidate_value_divergence": "review_required",
            "output_context_divergence": "review_required",
            "trace_divergence": "accepted_documented_semantic_difference",
        },
        is_current=True,
    )
    session.add(contract)
    session.commit()

    with pytest.raises(ShadowValidationError, match="shadow_validation_unsupported_shape"):
        _build_service(session).assemble(
            validation_window_id=fixture.window_id,
            frozen_evaluation_package_id=fixture.fep_id,
            legacy_formula_capture_id=fixture.capture_id,
            comparison_contract_id=contract.id,
        )


def test_assemble_rejects_fep_capture_linkage_mismatch(db):
    session, fixture = db
    rogue = FrozenEvaluationPackage(
        id="rogue-fep",
        channel_id=fixture.channel_id,
        product_ref="sku-shadow",
        workspace_pricing_evaluated_at=utcnow(),
        formula_shape_id="A1",
        translator_version="translator-v1",
        currency_unit_registry_version="v1",
        arithmetic_version="arith-v1",
        dependency_fingerprint="dep-1",
        checksum="fep-checksum-2",
    )
    session.add(rogue)
    session.commit()

    with pytest.raises(ShadowValidationError) as exc:
        _build_service(session).assemble(
            validation_window_id=fixture.window_id,
            frozen_evaluation_package_id=rogue.id,
            legacy_formula_capture_id=fixture.capture_id,
        )
    assert str(exc.value) == REASON_FEP_CAPTURE_MISMATCH


def test_assemble_rejects_invalid_output_lanes(db):
    session, fixture = db
    contract = ShapeComparisonContract(
        id="contract-invalid-lanes-1",
        shape_id="A1",
        contract_revision="rev-lanes-1",
        contract_version="v1",
        contract_checksum="contract-checksum-lanes-1",
        formula_inventory_checksum="formula-inventory-1",
        target_kind=contracts.ShapeTargetKind.PRICE_TARGET.value,
        stable_rule_identity_json={"formula_shape_id": "A1", "formula_rule_identity": "rule-1"},
        required_input_identity_json={
            "shape_id": "A1",
            "formula_shape_id": "A1",
            "formula_rule_identity": "rule-1",
            "input_manifest_checksum": "input-checksum-1",
            "fep_dependency_fingerprint": "dep-1",
            "pricing_policy_revision_id": "policy-revision-1",
            "translator_version": "translator-v1",
        },
        required_output_lanes_json=[],
        canonical_context_json={"formula_shape_id": "A1", "translator_version": "translator-v1", "fep_formula_shape_id": "A1"},
        equality_rule_json={"method": "exact"},
        required_trace_components_json=["component-a", "component-b"],
        acceptance_effect=contracts.ShapeAcceptanceEffect.MAY_COUNT.value,
        classification_mapping_json={
            "effective_value_divergence": "accepted_expected_rounding",
            "candidate_value_divergence": "review_required",
            "output_context_divergence": "review_required",
            "trace_divergence": "accepted_documented_semantic_difference",
        },
        is_current=True,
    )
    session.add(contract)
    session.commit()

    with pytest.raises(ShadowValidationError) as exc:
        _build_service(session).assemble(
            validation_window_id=fixture.window_id,
            frozen_evaluation_package_id=fixture.fep_id,
            legacy_formula_capture_id=fixture.capture_id,
            comparison_contract_id=contract.id,
        )
    assert str(exc.value) == REASON_OUTPUT_LANES_UNSUPPORTED
