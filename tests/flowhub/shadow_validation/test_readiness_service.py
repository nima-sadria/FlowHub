"""Shadow validation readiness aggregation and CAS behavior (Phase C4)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import json
import uuid

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
from app.flowhub.pricing_evaluation.contracts import EffectiveOutputSource
from app.flowhub.pricing_evaluation.contracts import ManualInputDecisionKind
from app.flowhub.pricing_evaluation.contracts import ManualInputKind
from app.flowhub.pricing_evaluation.models import (
    DerivedValueEvaluation,
    FrozenEvaluationPackage,
    ManualInputDecision,
    ManualInputRevision,
    PackageManualInputPin,
    PackagePriceOverride,
)
from app.flowhub.pricing_matrix.models import (
    ChannelPricingPolicyHead,
    PricingPolicyLifecycleEvent,
    PricingPolicyRevision,
)
from app.flowhub.shadow_validation import contracts
from app.flowhub.shadow_validation.contracts import (
    ComparisonConfidence,
    ComparisonPrimaryClassification,
    ValidationWindowEventKind,
    ShadowValidationWindowState,
    WindowReadinessReason,
    WindowReadinessState,
    ShapeAcceptanceEffect,
    ShapeTargetKind,
)
from app.flowhub.shadow_validation.fingerprint import compute_comparison_identity_checksum
from app.flowhub.shadow_validation.fingerprint import compute_readiness_checksum
from app.flowhub.shadow_validation.models import (
    LegacyFormulaCapture,
    ShapeComparisonContract,
    ShadowReadinessDecision,
    ShadowValidationWindow,
    ShadowValidationWindowEvent,
    ShadowValidationWindowHead,
    ShadowValidationComparison,
)
from app.flowhub.shadow_validation.service import ShadowValidationReadinessService
from app.flowhub.source_acquisition import models as _source_acquisition_models  # noqa: F401
from app.flowhub.source_workspace import models as _source_workspace_models  # noqa: F401
from app.flowhub.unified_workspace.domain import utcnow
from app.flowhub.unified_workspace.models import WorkspaceChannel


@dataclass
class ReadinessFixture:
    session: sa.orm.Session
    channel_id: str
    user_id: int
    authority_head: ChannelPricingAuthorityHead
    authority_event_id: str
    policy_activation_id: str
    policy_revision_id: str
    window_id: str
    package_id: str
    capture_id: str
    contract_id: str


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    FlowHubBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    user = FlowHubUser(id=1001, username="sv-user", hashed_password="ignored", role="admin")
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
    authority_head = ChannelPricingAuthorityHead(
        channel_id=channel.id,
        current_authority="legacy_formula_engine",
        effective_event_id=authority_event.id,
        head_version=0,
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
    policy_activation = PricingPolicyLifecycleEvent(
        id="policy-activation-1",
        channel_id=channel.id,
        event_kind="activate",
        actor_user_id=1001,
        reason="seed",
        policy_revision_id=policy_revision.id,
        channel_config_revision_id="cfg-1",
        effective_activation_id="policy-activation-1",
    )
    policy_head = ChannelPricingPolicyHead(
        channel_id=channel.id,
        current_event_id=policy_activation.id,
        effective_activation_id=policy_activation.id,
        head_version=0,
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
        channel_config_revision_id="cfg-1",
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
        canonical_context_json={"formula_shape_id": "A1", "translator_version": "translator-v1"},
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
        pricing_policy_activation_id=policy_activation.id,
        pricing_authority_event_id=authority_event.id,
        pricing_authority_head_version=0,
        head_version_snapshot=0,
        opened_at=utcnow(),
        closes_at=None,
        required_distinct_matches=1,
        configuration_checksum="window-checksum-1",
    )
    window_head = ShadowValidationWindowHead(
        channel_id=channel.id,
        current_window_id=window.id,
        current_state=ShadowValidationWindowState.COLLECTING.value,
        head_version=0,
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
            authority_event,
            authority_head,
            policy_revision,
            policy_activation,
            policy_head,
            fep,
            capture,
            contract,
            window,
            window_head,
            override,
            derived_evaluation,
        )
    )
    session.commit()

    fixture = ReadinessFixture(
        session=session,
        channel_id=channel.id,
        user_id=user.id,
        authority_head=authority_head,
        authority_event_id=authority_event.id,
        policy_activation_id=policy_activation.id,
        policy_revision_id=policy_revision.id,
        window_id=window.id,
        package_id=fep.id,
        capture_id=capture.id,
        contract_id=contract.id,
    )
    try:
        yield fixture
    finally:
        session.close()
        FlowHubBase.metadata.drop_all(engine)
        engine.dispose()


def _service(session: sa.orm.Session) -> ShadowValidationReadinessService:
    return ShadowValidationReadinessService(session)


def _get_window(session: sa.orm.Session, fixture: ReadinessFixture) -> ShadowValidationWindow:
    return session.get(ShadowValidationWindow, fixture.window_id)


def _get_head(session: sa.orm.Session, fixture: ReadinessFixture) -> ShadowValidationWindowHead:
    return session.get(ShadowValidationWindowHead, fixture.channel_id)


def _add_comparison(
    session: sa.orm.Session,
    fixture: ReadinessFixture,
    *,
    contract_id: str,
    package_id: str,
    capture_id: str,
    classification: str,
    confidence: str = ComparisonConfidence.VERIFIED.value,
    comparison_id: str,
    comparison_contract_revision_checksum: str | None = None,
    secondary: tuple[str, ...] = (),
    created_at=None,
) -> ShadowValidationComparison:
    if created_at is None:
        created_at = utcnow()
    window = _get_window(session, fixture)
    contract = session.get(ShapeComparisonContract, contract_id)
    package = session.get(FrozenEvaluationPackage, package_id)
    capture = session.get(LegacyFormulaCapture, capture_id)
    if contract is None or package is None or capture is None:
        raise AssertionError("fixture contract/package/capture missing")

    return ShadowValidationComparison(
        id=comparison_id,
        channel_id=fixture.channel_id,
        validation_window_id=window.id,
        frozen_evaluation_package_id=package_id,
        legacy_formula_capture_id=capture_id,
        shape_id=contract.shape_id,
        comparison_contract_id=contract_id,
        stable_rule_identity=json.dumps(contract.stable_rule_identity_json, sort_keys=True),
        comparison_contract_revision=contract.contract_revision,
        comparison_contract_revision_checksum=(
            comparison_contract_revision_checksum
            if comparison_contract_revision_checksum is not None
            else contract.contract_checksum
        ),
        comparison_algorithm_version="shadow-validation-comparison-v1",
        comparison_identity_checksum=compute_comparison_identity_checksum(
            channel_id=fixture.channel_id,
            stable_rule_identity=json.dumps(contract.stable_rule_identity_json, sort_keys=True),
            frozen_evaluation_package_id=package.id,
            frozen_evaluation_package_checksum=package.checksum,
            legacy_formula_capture_id=capture.id,
            legacy_formula_capture_checksum=capture.capture_checksum,
            comparison_contract_id=contract.id,
            comparison_contract_checksum=contract.contract_checksum,
            comparison_algorithm_version="shadow-validation-comparison-v1",
        ),
        frozen_evaluation_package_checksum=package.checksum,
        legacy_capture_checksum=capture.capture_checksum,
        translator_version=package.translator_version,
        required_output_lanes="both",
        confidence=confidence,
        primary_classification=classification,
        secondary_classifications_json=list(secondary),
        legacy_vs_package_context_json={},
        legacy_output_json={},
        package_output_json={},
        findings_json=[],
        actor_user_id=None,
        reason_code=None,
        correlation_id="cmp-1",
        created_at=created_at,
    )


def _replace_active_window(
    session: sa.orm.Session,
    fixture: ReadinessFixture,
    *,
    required_distinct_matches: int | None = None,
    closes_at: object | None = None,
    evidence_freshness_seconds: int | None = None,
    pricing_policy_activation_id: str | None = None,
    pricing_authority_event_id: str | None = None,
    pricing_authority_head_version: int | None = None,
) -> ShadowValidationWindow:
    base_window = _get_window(session, fixture)
    if base_window is None:
        raise AssertionError("base window missing")

    new_window = ShadowValidationWindow(
        id=f"window-{uuid.uuid4().hex}",
        channel_id=base_window.channel_id,
        scope_manifest_checksum=base_window.scope_manifest_checksum,
        formula_inventory_checksum=base_window.formula_inventory_checksum,
        acceptance_policy_revision=base_window.acceptance_policy_revision,
        pricing_policy_revision_id=base_window.pricing_policy_revision_id,
        pricing_policy_activation_id=(
            pricing_policy_activation_id
            if pricing_policy_activation_id is not None
            else base_window.pricing_policy_activation_id
        ),
        pricing_authority_event_id=(
            pricing_authority_event_id
            if pricing_authority_event_id is not None
            else base_window.pricing_authority_event_id
        ),
        pricing_authority_head_version=(
            pricing_authority_head_version
            if pricing_authority_head_version is not None
            else base_window.pricing_authority_head_version
        ),
        head_version_snapshot=base_window.head_version_snapshot,
        opened_at=utcnow(),
        closes_at=closes_at if closes_at is not None else base_window.closes_at,
        evidence_freshness_seconds=evidence_freshness_seconds
        if evidence_freshness_seconds is not None
        else base_window.evidence_freshness_seconds,
        required_distinct_matches=(
            required_distinct_matches
            if required_distinct_matches is not None
            else base_window.required_distinct_matches
        ),
        configuration_checksum=base_window.configuration_checksum,
    )
    session.add(new_window)
    session.flush()

    head = _get_head(session, fixture)
    if head is None:
        raise AssertionError("window head missing")
    head.current_window_id = new_window.id
    fixture.window_id = new_window.id
    return new_window


def _manual_input_pair(session: sa.orm.Session, *, fixture: ReadinessFixture, revision_id: str) -> tuple[
    str,
    str,
]:
    revision = ManualInputRevision(
        id=revision_id,
        kind=ManualInputKind.REFERENCE_PRICE.value,
        channel_id=fixture.channel_id,
        product_ref="sku-shadow",
        revision_number=1,
        value_json={"value": "100"},
        currency="USD",
        unit="USD",
        checksum=f"{revision_id}-checksum",
        created_by_user_id=fixture.user_id,
    )
    approved = ManualInputDecision(
        id=f"{revision_id}-decision-approved",
        manual_input_revision_id=revision_id,
        decision=ManualInputDecisionKind.APPROVED.value,
        actor_user_id=fixture.user_id,
        reason="approved",
    )
    session.add_all((revision, approved))
    session.commit()
    return revision_id, approved.id


@pytest.mark.parametrize(
    "classification,confidence,expected_ready",
    [
        (ComparisonPrimaryClassification.EXACT_MATCH.value, ComparisonConfidence.VERIFIED.value, True),
        (
            ComparisonPrimaryClassification.ACCEPTED_EXPECTED_ROUNDING.value,
            ComparisonConfidence.VERIFIED.value,
            True,
        ),
        (
            ComparisonPrimaryClassification.ACCEPTED_DOCUMENTED_SEMANTIC_DIFFERENCE.value,
            ComparisonConfidence.VERIFIED.value,
            True,
        ),
        (ComparisonPrimaryClassification.REVIEW_REQUIRED.value, ComparisonConfidence.VERIFIED.value, True),
        (ComparisonPrimaryClassification.CRITICAL_DIVERGENCE.value, ComparisonConfidence.VERIFIED.value, False),
        (ComparisonPrimaryClassification.NOT_POSSIBLE.value, ComparisonConfidence.VERIFIED.value, False),
        (ComparisonPrimaryClassification.EXACT_MATCH.value, ComparisonConfidence.PARTIAL.value, False),
    ],
)
def test_readiness_projection_counts_only_verified_eligible_classes(
    db: ReadinessFixture,
    classification: str,
    confidence: str,
    expected_ready: bool,
):
    fixture = db
    comparison = _add_comparison(
        fixture.session,
        fixture,
        contract_id=fixture.contract_id,
        package_id=fixture.package_id,
        capture_id=fixture.capture_id,
        comparison_id="comparison-1",
        classification=classification,
        confidence=confidence,
    )
    fixture.session.add(comparison)
    fixture.session.commit()

    projection = _service(fixture.session).project(channel_id=fixture.channel_id)
    if expected_ready:
        assert projection.decision == WindowReadinessState.READY.value
        assert projection.reason_code is None
        assert projection.compared_count == 1
        assert projection.comparison_ids_json == [comparison.id]
    else:
        assert projection.decision == WindowReadinessState.NOT_READY.value
        assert projection.reason_code == WindowReadinessReason.NOT_POSSIBLE.value
        assert projection.compared_count == 0


def test_ready_projection_is_deterministic_and_projection_checksum_stable(db: ReadinessFixture):
    fixture = db
    fixture.session.add(
        _add_comparison(
            fixture.session,
            fixture,
            contract_id=fixture.contract_id,
            package_id=fixture.package_id,
            capture_id=fixture.capture_id,
            comparison_id="comparison-deterministic",
            classification=ComparisonPrimaryClassification.EXACT_MATCH.value,
        )
    )
    fixture.session.commit()

    first = _service(fixture.session).project(channel_id=fixture.channel_id)
    second = _service(fixture.session).project(channel_id=fixture.channel_id)

    assert first.decision == WindowReadinessState.READY.value
    assert second.decision == WindowReadinessState.READY.value
    assert first.aggregate_checksum == second.aggregate_checksum
    assert first.aggregate_checksum == compute_readiness_checksum(
        validation_window_id=fixture.window_id,
        decision=WindowReadinessState.READY.value,
        reason_code=None,
        comparison_count=1,
        readiness_payload=first.readiness_payload,
    )
    assert first.comparison_ids_json == ["comparison-deterministic"]


def test_readiness_fails_open_when_coverage_incomplete(db: ReadinessFixture):
    fixture = db
    _replace_active_window(fixture.session, fixture, required_distinct_matches=2)

    fixture.session.add(
        _add_comparison(
            fixture.session,
            fixture,
            contract_id=fixture.contract_id,
            package_id=fixture.package_id,
            capture_id=fixture.capture_id,
            comparison_id="comparison-covered",
            classification=ComparisonPrimaryClassification.EXACT_MATCH.value,
        )
    )
    fixture.session.commit()

    projection = _service(fixture.session).project(channel_id=fixture.channel_id)

    assert projection.decision == WindowReadinessState.NOT_READY.value
    assert projection.reason_code == WindowReadinessReason.COVERAGE_INCOMPLETE.value
    assert projection.compared_count == 1


def test_readiness_fails_when_window_closed(db: ReadinessFixture):
    fixture = db
    _replace_active_window(fixture.session, fixture, closes_at=utcnow() - timedelta(minutes=1))

    fixture.session.add(
        _add_comparison(
            fixture.session,
            fixture,
            contract_id=fixture.contract_id,
            package_id=fixture.package_id,
            capture_id=fixture.capture_id,
            comparison_id="comparison-expired",
            classification=ComparisonPrimaryClassification.EXACT_MATCH.value,
        )
    )
    fixture.session.commit()

    projection = _service(fixture.session).project(channel_id=fixture.channel_id)
    assert projection.decision == WindowReadinessState.NOT_READY.value
    assert projection.reason_code == WindowReadinessReason.EVIDENCE_EXPIRED.value


def test_readiness_detects_freshness_staleness(db: ReadinessFixture):
    fixture = db
    _replace_active_window(fixture.session, fixture, evidence_freshness_seconds=1)

    fixture.session.add(
        _add_comparison(
            fixture.session,
            fixture,
            contract_id=fixture.contract_id,
            package_id=fixture.package_id,
            capture_id=fixture.capture_id,
            comparison_id="comparison-stale",
            classification=ComparisonPrimaryClassification.EXACT_MATCH.value,
            created_at=utcnow() - timedelta(seconds=120),
        )
    )
    fixture.session.commit()

    projection = _service(fixture.session).project(channel_id=fixture.channel_id, now=utcnow())
    assert projection.decision == WindowReadinessState.NOT_READY.value
    assert projection.reason_code == WindowReadinessReason.EVIDENCE_EXPIRED.value


def test_contract_unavailable_for_quarantined_rule(db: ReadinessFixture):
    fixture = db
    base_contract = fixture.session.get(ShapeComparisonContract, fixture.contract_id)
    if base_contract is None:
        raise AssertionError("base contract missing")
    quarantined_contract = ShapeComparisonContract(
        id="contract-quarantined-1",
        shape_id=base_contract.shape_id,
        contract_revision="rev-quarantine-1",
        contract_version="v1",
        contract_checksum="contract-checksum-quarantine-1",
        formula_inventory_checksum=base_contract.formula_inventory_checksum,
        target_kind=contracts.ShapeTargetKind.QUARANTINED.value,
        stable_rule_identity_json=base_contract.stable_rule_identity_json,
        required_input_identity_json=base_contract.required_input_identity_json,
        required_output_lanes_json=base_contract.required_output_lanes_json,
        canonical_context_json=base_contract.canonical_context_json,
        equality_rule_json=base_contract.equality_rule_json,
        required_trace_components_json=base_contract.required_trace_components_json,
        acceptance_effect=ShapeAcceptanceEffect.MAY_COUNT.value,
        classification_mapping_json=base_contract.classification_mapping_json,
        is_current=False,
    )
    fixture.session.add(quarantined_contract)
    fixture.session.commit()

    fixture.session.add(
        _add_comparison(
        fixture.session,
        fixture,
        contract_id=quarantined_contract.id,
        package_id=fixture.package_id,
        capture_id=fixture.capture_id,
        comparison_id="comparison-quarantine",
        classification=ComparisonPrimaryClassification.EXACT_MATCH.value,
        )
    )
    fixture.session.commit()

    projection = _service(fixture.session).project(channel_id=fixture.channel_id)
    assert projection.decision == WindowReadinessState.NOT_READY.value
    assert projection.reason_code == WindowReadinessReason.CONTRACT_UNAVAILABLE.value


def test_invalidation_on_authority_transition(db: ReadinessFixture):
    fixture = db
    fixture.session.add(
        _add_comparison(
            fixture.session,
            fixture,
            contract_id=fixture.contract_id,
            package_id=fixture.package_id,
            capture_id=fixture.capture_id,
            comparison_id="comparison-authority",
            classification=ComparisonPrimaryClassification.EXACT_MATCH.value,
        )
    )
    fixture.session.commit()

    fixture.session.add(
        ChannelPricingAuthorityEvent(
            id="authority-event-2",
            channel_id=fixture.channel_id,
            previous_authority="legacy_formula_engine",
            new_authority="migration_locked",
            expected_head_version=1,
            actor_reference="seed",
            reason="rotate",
            request_metadata_json={},
        )
    )
    fixture.authority_head.effective_event_id = "authority-event-2"
    fixture.authority_head.head_version = 1
    fixture.session.commit()

    projection = _service(fixture.session).project(channel_id=fixture.channel_id)
    assert projection.reason_code == WindowReadinessReason.SCOPE_INVALIDATED.value


def test_invalidation_on_policy_activation_change(db: ReadinessFixture):
    fixture = db
    fixture.session.add(
        _add_comparison(
            fixture.session,
            fixture,
            contract_id=fixture.contract_id,
            package_id=fixture.package_id,
            capture_id=fixture.capture_id,
            comparison_id="comparison-policy",
            classification=ComparisonPrimaryClassification.EXACT_MATCH.value,
        )
    )
    new_activation = PricingPolicyLifecycleEvent(
        id="policy-activation-2",
        channel_id=fixture.channel_id,
        event_kind="activate",
        actor_user_id=fixture.user_id,
        reason="policy switch",
        policy_revision_id=fixture.policy_revision_id,
        channel_config_revision_id="cfg-1",
    )
    fixture.session.add(new_activation)
    fixture.session.commit()

    policy_head = fixture.session.get(ChannelPricingPolicyHead, fixture.channel_id)
    if policy_head is None:
        raise AssertionError("policy head missing")
    policy_head.effective_activation_id = new_activation.id
    policy_head.current_event_id = new_activation.id
    fixture.session.commit()

    projection = _service(fixture.session).project(channel_id=fixture.channel_id)
    assert projection.reason_code == WindowReadinessReason.SCOPE_INVALIDATED.value


def test_invalidation_on_channel_config_revision_change(db: ReadinessFixture):
    fixture = db
    new_activation = PricingPolicyLifecycleEvent(
        id="policy-activation-3",
        channel_id=fixture.channel_id,
        event_kind="activate",
        actor_user_id=fixture.user_id,
        reason="config changed",
        policy_revision_id=fixture.policy_revision_id,
        channel_config_revision_id="cfg-2",
    )
    fixture.session.add(new_activation)
    fixture.session.commit()
    _replace_active_window(
        fixture.session,
        fixture,
        pricing_policy_activation_id=new_activation.id,
    )
    fixture.session.add(
        _add_comparison(
            fixture.session,
            fixture,
            contract_id=fixture.contract_id,
            package_id=fixture.package_id,
            capture_id=fixture.capture_id,
            comparison_id="comparison-config",
            classification=ComparisonPrimaryClassification.EXACT_MATCH.value,
        )
    )
    fixture.session.commit()

    projection = _service(fixture.session).project(channel_id=fixture.channel_id)
    assert projection.reason_code == WindowReadinessReason.SCOPE_INVALIDATED.value


def test_invalidation_on_manual_input_revocation(db: ReadinessFixture):
    fixture = db
    revision_id, approved_id = _manual_input_pair(
        fixture.session,
        fixture=fixture,
        revision_id="mir-1",
    )
    fixture.session.add(
        PackageManualInputPin(
            id="pin-1",
            frozen_evaluation_package_id=fixture.package_id,
            manual_input_revision_id=revision_id,
            manual_input_decision_id=approved_id,
        )
    )
    fixture.session.add(
        _add_comparison(
            fixture.session,
            fixture,
            contract_id=fixture.contract_id,
            package_id=fixture.package_id,
            capture_id=fixture.capture_id,
            comparison_id="comparison-manual",
            classification=ComparisonPrimaryClassification.EXACT_MATCH.value,
        )
    )
    fixture.session.commit()

    fixture.session.add(
        ManualInputDecision(
            id="mir-1-decision-revoked",
            manual_input_revision_id=revision_id,
            decision=ManualInputDecisionKind.REVOKED.value,
            actor_user_id=fixture.user_id,
            reason="revoked",
        )
    )
    fixture.session.commit()

    projection = _service(fixture.session).project(channel_id=fixture.channel_id)
    assert projection.reason_code == WindowReadinessReason.SCOPE_INVALIDATED.value


def test_invalidation_on_active_override_decision_revocation(db: ReadinessFixture):
    fixture = db
    revision_id, approved_id = _manual_input_pair(
        fixture.session,
        fixture=fixture,
        revision_id="mir-2",
    )
    base_package = fixture.session.get(FrozenEvaluationPackage, fixture.package_id)
    if base_package is None:
        raise AssertionError("base package missing")
    override_package = FrozenEvaluationPackage(
        id="fep-override-2",
        channel_id=fixture.channel_id,
        product_ref="sku-shadow",
        workspace_pricing_evaluated_at=utcnow(),
        formula_shape_id=base_package.formula_shape_id,
        translator_version=base_package.translator_version,
        currency_unit_registry_version=base_package.currency_unit_registry_version,
        arithmetic_version=base_package.arithmetic_version,
        dependency_fingerprint=base_package.dependency_fingerprint,
        checksum="fep-checksum-override-2",
        pricing_policy_revision_id=fixture.policy_revision_id,
        channel_config_revision_id=base_package.channel_config_revision_id,
    )
    override_capture = LegacyFormulaCapture(
        id="capture-override-2",
        channel_id=fixture.channel_id,
        frozen_evaluation_package_id=override_package.id,
        legacy_formula_engine="legacy-engine",
        legacy_formula_engine_version="1",
        formula_shape_id=base_package.formula_shape_id,
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
        capture_checksum="capture-checksum-override-2",
    )
    override = PackagePriceOverride(
        id="override-2",
        frozen_evaluation_package_id=override_package.id,
        calculated_candidate_numerator=100,
        calculated_candidate_denominator=10,
        effective_output_numerator=100,
        effective_output_denominator=10,
        effective_output_source=EffectiveOutputSource.CALCULATED_CANDIDATE.value,
        override_manual_input_decision_id=approved_id,
    )
    fixture.session.add_all((override_package, override_capture, override))
    fixture.session.commit()

    fixture.session.add(
        _add_comparison(
            fixture.session,
            fixture,
            contract_id=fixture.contract_id,
            package_id=override_package.id,
            capture_id=override_capture.id,
            comparison_id="comparison-override",
            classification=ComparisonPrimaryClassification.EXACT_MATCH.value,
        )
    )
    fixture.session.add(
        ManualInputDecision(
            id="mir-2-decision-revoked",
            manual_input_revision_id=revision_id,
            decision=ManualInputDecisionKind.REVOKED.value,
            actor_user_id=fixture.user_id,
            reason="revoked",
        )
    )
    fixture.session.commit()

    projection = _service(fixture.session).project(channel_id=fixture.channel_id)
    assert projection.reason_code == WindowReadinessReason.SCOPE_INVALIDATED.value


def test_invalidation_on_comparison_contract_revision_change(db: ReadinessFixture):
    fixture = db
    fixture.session.add(
        _add_comparison(
            fixture.session,
            fixture,
            contract_id=fixture.contract_id,
            package_id=fixture.package_id,
            capture_id=fixture.capture_id,
            comparison_id="comparison-contract-revision",
            classification=ComparisonPrimaryClassification.EXACT_MATCH.value,
            comparison_contract_revision_checksum="contract-checksum-stale",
        )
    )
    fixture.session.commit()

    projection = _service(fixture.session).project(channel_id=fixture.channel_id)
    assert projection.reason_code == WindowReadinessReason.SCOPE_INVALIDATED.value


def test_invalidation_on_fep_update_translator_change(db: ReadinessFixture):
    fixture = db
    fixture.session.add(
        _add_comparison(
            fixture.session,
            fixture,
            contract_id=fixture.contract_id,
            package_id=fixture.package_id,
            capture_id=fixture.capture_id,
            comparison_id="comparison-fep",
            classification=ComparisonPrimaryClassification.EXACT_MATCH.value,
        )
    )
    base_capture = fixture.session.get(LegacyFormulaCapture, fixture.capture_id)
    if base_capture is None:
        raise AssertionError("capture missing")
    base_package = fixture.session.get(FrozenEvaluationPackage, fixture.package_id)
    if base_package is None:
        raise AssertionError("package missing")
    new_package = FrozenEvaluationPackage(
        id="fep-2",
        channel_id=fixture.channel_id,
        product_ref="sku-shadow",
        workspace_pricing_evaluated_at=utcnow(),
        formula_shape_id=base_package.formula_shape_id,
        translator_version="translator-v2",
        currency_unit_registry_version=base_package.currency_unit_registry_version,
        arithmetic_version=base_package.arithmetic_version,
        dependency_fingerprint=base_package.dependency_fingerprint,
        checksum="fep-checksum-2",
        pricing_policy_revision_id=fixture.policy_revision_id,
        channel_config_revision_id=base_package.channel_config_revision_id,
    )
    fixture.session.add(new_package)
    fixture.session.commit()

    projection = _service(fixture.session).project(channel_id=fixture.channel_id)
    assert projection.reason_code == WindowReadinessReason.SCOPE_INVALIDATED.value


def test_seal_window_returns_cas_conflict_without_writing_side_effects(db: ReadinessFixture):
    fixture = db
    fixture.session.add(
        _add_comparison(
            fixture.session,
            fixture,
            contract_id=fixture.contract_id,
            package_id=fixture.package_id,
            capture_id=fixture.capture_id,
            comparison_id="comparison-conflict",
            classification=ComparisonPrimaryClassification.EXACT_MATCH.value,
        )
    )
    fixture.session.commit()

    result = _service(fixture.session).seal_window(
        channel_id=fixture.channel_id,
        expected_head_version=999,
        correlation_id="cas-conflict",
    )

    assert result.cas_conflict
    assert result.transition is None
    assert result.decision is None
    assert result.reason_code == WindowReadinessReason.CAS_CONFLICT.value
    assert fixture.session.query(ShadowValidationWindowEvent).count() == 0
    assert fixture.session.query(ShadowReadinessDecision).count() == 0

    accepted = _service(fixture.session).seal_window(
        channel_id=fixture.channel_id,
        expected_head_version=0,
        correlation_id="ok",
    )
    assert accepted.transition == ValidationWindowEventKind.ACCEPTED.value
    assert accepted.reason_code is None


def test_seal_window_keeps_decisions_append_only_and_links_events(db: ReadinessFixture):
    fixture = db
    fixture.session.add(
        _add_comparison(
            fixture.session,
            fixture,
            contract_id=fixture.contract_id,
            package_id=fixture.package_id,
            capture_id=fixture.capture_id,
            comparison_id="comparison-chain",
            classification=ComparisonPrimaryClassification.EXACT_MATCH.value,
        )
    )
    fixture.session.commit()

    first = _service(fixture.session).seal_window(channel_id=fixture.channel_id, expected_head_version=0)
    assert first.decision is not None
    assert first.transition == ValidationWindowEventKind.ACCEPTED.value

    fixture.authority_head.effective_event_id = "authority-event-2"
    fixture.authority_head.head_version = 1
    fixture.session.commit()

    second = _service(fixture.session).seal_window(channel_id=fixture.channel_id, expected_head_version=1)
    assert second.transition == ValidationWindowEventKind.INVALIDATED.value
    assert second.decision is not None

    events = (
        fixture.session.query(ShadowValidationWindowEvent)
        .filter_by(channel_id=fixture.channel_id)
        .order_by(ShadowValidationWindowEvent.created_at.asc())
        .all()
    )
    assert len(events) == 2
    assert events[0].event_kind == ValidationWindowEventKind.ACCEPTED.value
    assert events[1].event_kind == ValidationWindowEventKind.INVALIDATED.value
    assert events[1].predecessor_event_id == events[0].id
    assert fixture.session.query(ShadowReadinessDecision).count() == 2
