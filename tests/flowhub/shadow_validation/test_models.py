"""Persistence behavior checks for Shadow Validation immutable records and CAS state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
from app.flowhub.pricing_evaluation.models import FrozenEvaluationPackage
from app.flowhub.pricing_matrix import models as _pricing_matrix_models  # noqa: F401
from app.flowhub.shadow_validation import contracts
from app.flowhub.shadow_validation.models import (
    LegacyFormulaCapture,
    ShadowReadinessDecision,
    ShadowValidationComparison,
    ShadowValidationWindow,
    ShadowValidationWindowEvent,
    ShadowValidationWindowHead,
    ShapeComparisonContract,
)
from app.flowhub.unified_workspace.domain import ImmutableRecordError
from app.flowhub.source_acquisition import models as _source_acquisition_models  # noqa: F401
from app.flowhub.source_workspace import models as _source_workspace_models  # noqa: F401
from app.flowhub.unified_workspace.models import WorkspaceChannel
from app.flowhub.unified_workspace.domain import utcnow


@dataclass
class ShadowValidationFixture:
    channel_id: str
    authority_event_id: str
    fep_id: str
    contract_id: str
    capture_id: str


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    FlowHubBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    user = FlowHubUser(username="sv_user", hashed_password="ignored", role="admin")
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
        id="sv-event-1",
        channel_id=channel.id,
        new_authority="legacy_formula_engine",
        expected_head_version=0,
        actor_reference="seed",
        reason="seed",
        request_metadata_json={},
    )
    fep = FrozenEvaluationPackage(
        id="fep-shadow-1",
        channel_id=channel.id,
        product_ref="sku-shadow",
        workspace_pricing_evaluated_at=datetime.utcnow(),
        formula_shape_id="A1",
        translator_version="translator-v1",
        currency_unit_registry_version="v1",
        arithmetic_version="arith-v1",
        dependency_fingerprint="a" * 64,
        checksum="c" * 64,
    )
    contract = ShapeComparisonContract(
        id="sv-contract-1",
        shape_id="A1",
        contract_revision="rev-1",
        contract_version="v1",
        contract_checksum="d" * 64,
        formula_inventory_checksum="f" * 64,
        target_kind=contracts.ShapeTargetKind.PRICE_TARGET.value,
        stable_rule_identity_json={"rule": "rule-1"},
        required_input_identity_json={"shape": "A1"},
        required_output_lanes_json=["candidate"],
        canonical_context_json={"currency": "USD"},
        equality_rule_json={"method": "exact"},
        required_trace_components_json=[],
        acceptance_effect=contracts.ShapeAcceptanceEffect.MAY_COUNT.value,
        classification_mapping_json={"output_context_divergence": "review_required"},
        is_current=True,
    )
    capture = LegacyFormulaCapture(
        id="sv-capture-1",
        channel_id=channel.id,
        frozen_evaluation_package_id=fep.id,
        legacy_formula_engine="legacy-engine",
        legacy_formula_engine_version="1",
        formula_shape_id="A1",
        formula_rule_identity="rule-1",
        workbook_identity="ws-1",
        workbook_revision="r-1",
        input_manifest_checksum="i" * 64,
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
        output_context_json={},
        capture_checksum="e" * 64,
    )
    session.add_all(
        (
            user,
            channel,
            authority_event,
            fep,
            contract,
            capture,
        )
    )
    session.commit()

    fixture = ShadowValidationFixture(
        channel_id=channel.id,
        authority_event_id=authority_event.id,
        fep_id=fep.id,
        contract_id=contract.id,
        capture_id=capture.id,
    )
    try:
        yield session, fixture
    finally:
        session.close()
        FlowHubBase.metadata.drop_all(engine)
        engine.dispose()


def _window(session, fixture: ShadowValidationFixture) -> ShadowValidationWindow:
    return ShadowValidationWindow(
        id=f"window-{uuid.uuid4().hex}",
        channel_id=fixture.channel_id,
        scope_manifest_checksum="s" * 64,
        formula_inventory_checksum="f" * 64,
        acceptance_policy_revision="policy-1",
        pricing_authority_event_id=fixture.authority_event_id,
        pricing_authority_head_version=0,
        head_version_snapshot=0,
        opened_at=utcnow(),
        closes_at=None,
        required_distinct_matches=1,
        configuration_checksum="x" * 64,
    )


def _event(session, fixture: ShadowValidationFixture) -> ShadowValidationWindowEvent:
    return ShadowValidationWindowEvent(
        id=f"event-{uuid.uuid4().hex}",
        channel_id=fixture.channel_id,
        validation_window_id=_window(session, fixture).id,
        actor_reference="operator",
        event_kind=contracts.ValidationWindowEventKind.OPENED.value,
        reason_code=contracts.ShadowValidationReasonCode.NOT_POSSIBLE.value,
        reason_payload_json={},
        expected_head_version=0,
        head_version_snapshot=0,
        correlation_id="cmp-1",
        configuration_checksum="x" * 64,
    )


def _comparison(session, fixture: ShadowValidationFixture) -> ShadowValidationComparison:
    return ShadowValidationComparison(
        id=f"comparison-{uuid.uuid4().hex}",
        channel_id=fixture.channel_id,
        validation_window_id=_window(session, fixture).id,
        frozen_evaluation_package_id=fixture.fep_id,
        legacy_formula_capture_id=fixture.capture_id,
        shape_id="A1",
        comparison_contract_id=fixture.contract_id,
        stable_rule_identity="rule-1",
        comparison_contract_revision="rev-1",
        comparison_contract_revision_checksum="d" * 64,
        comparison_algorithm_version="a-1",
        comparison_identity_checksum="ci" * 32,
        frozen_evaluation_package_checksum="c" * 64,
        legacy_capture_checksum="e" * 64,
        translator_version="t-1",
        required_output_lanes=contracts.OutputLane.CANDIDATE.value,
        confidence=contracts.ComparisonConfidence.VERIFIED.value,
        primary_classification=contracts.ComparisonPrimaryClassification.EXACT_MATCH.value,
        secondary_classifications_json=[],
        legacy_vs_package_context_json={},
        legacy_output_json={},
        package_output_json={},
        findings_json=[],
        correlation_id="cmp-1",
        created_at=utcnow(),
    )


def _readiness(session, fixture: ShadowValidationFixture) -> ShadowReadinessDecision:
    return ShadowReadinessDecision(
        id=f"readiness-{uuid.uuid4().hex}",
        validation_window_id=_window(session, fixture).id,
        channel_id=fixture.channel_id,
        decision=contracts.WindowReadinessState.NOT_READY.value,
        reason_code=contracts.ShadowValidationReasonCode.SCOPE_INVALIDATED.value,
        compared_count=0,
        aggregate_checksum="a" * 64,
        required_comparison_count=1,
        comparison_ids_json=[],
        authority_event_id=fixture.authority_event_id,
        authority_head_version=0,
        scope_manifest_checksum="s" * 64,
        readiness_payload_json={},
    )


@pytest.mark.parametrize(
    ("model_factory", "mutable_field", "new_value"),
    [
        (_window, "scope_manifest_checksum", "different"),
        (
            _event,
            "actor_reference",
            "replacement",
        ),
        (_comparison, "required_output_lanes", contracts.OutputLane.EFFECTIVE.value),
        (_readiness, "compared_count", 3),
        (
            lambda session, fixture: ShapeComparisonContract(
                id=f"contract-{uuid.uuid4().hex}",
                shape_id="A1",
                contract_revision="rev-2",
                contract_version="v1",
                contract_checksum="g" * 64,
                formula_inventory_checksum="f" * 64,
                target_kind=contracts.ShapeTargetKind.PRICE_TARGET.value,
                stable_rule_identity_json={"rule": "rule-1"},
                required_input_identity_json={"shape": "A1"},
                required_output_lanes_json=["candidate"],
                canonical_context_json={},
                equality_rule_json={},
                required_trace_components_json=[],
                acceptance_effect=contracts.ShapeAcceptanceEffect.MAY_COUNT.value,
                classification_mapping_json={},
                is_current=True,
            ),
            "contract_version",
            "v2",
        ),
        (
            lambda session, fixture: LegacyFormulaCapture(
                id=f"capture-{uuid.uuid4().hex}",
                channel_id=fixture.channel_id,
                frozen_evaluation_package_id=fixture.fep_id,
                legacy_formula_engine="legacy-engine",
                legacy_formula_engine_version="2",
                formula_shape_id="A1",
                formula_rule_identity="rule-2",
                input_manifest_checksum="i" * 64,
                pricing_authority_event_id=fixture.authority_event_id,
                pricing_authority_head_version=0,
                captured_at=utcnow(),
                candidate_numerator=10,
                candidate_denominator=2,
                effective_numerator=10,
                effective_denominator=2,
                candidate_currency="USD",
                candidate_unit="USD",
                effective_currency="USD",
                effective_unit="USD",
                output_context_json={},
                capture_checksum="z" * 64,
            ),
            "effective_currency",
            "EUR",
        ),
    ],
)
def test_shadow_validation_immutable_records_reject_updates(
    db,
    model_factory,
    mutable_field,
    new_value,
):
    session, fixture = db
    if model_factory is _comparison:
        window = _window(session, fixture)
        session.add(window)
        session.commit()
        row = model_factory(session, fixture)
        row.validation_window_id = window.id
    elif model_factory in (_event,):
        window = _window(session, fixture)
        session.add(window)
        session.commit()
        row = model_factory(session, fixture)
        row.validation_window_id = window.id
    elif model_factory is _readiness:
        window = _window(session, fixture)
        session.add(window)
        session.commit()
        row = model_factory(session, fixture)
        row.validation_window_id = window.id
    else:
        row = model_factory(session, fixture)

    session.add(row)
    session.commit()

    setattr(row, mutable_field, new_value)
    with pytest.raises(ImmutableRecordError):
        session.commit()
    session.rollback()

    session.delete(row)
    with pytest.raises(ImmutableRecordError):
        session.commit()
    session.rollback()


def test_shadow_validation_window_head_can_be_mutated_for_cas(db):
    session, fixture = db
    head = ShadowValidationWindowHead(
        channel_id=fixture.channel_id,
        current_state=contracts.ShadowValidationWindowState.COLLECTING.value,
        head_version=0,
        updated_at=utcnow(),
    )
    session.add(head)
    session.commit()

    head.head_version = 1
    head.current_state = contracts.ShadowValidationWindowState.ACCEPTED.value
    head.current_window_id = None
    session.commit()

    assert session.get(ShadowValidationWindowHead, fixture.channel_id).head_version == 1


def test_constraints_reject_invalid_reason_codes(db):
    session, fixture = db
    window = _window(session, fixture)
    session.add(window)
    session.commit()

    bad_event = ShadowValidationWindowEvent(
        id="event-bad",
        channel_id=fixture.channel_id,
        validation_window_id=window.id,
        actor_reference="bad",
        event_kind=contracts.ValidationWindowEventKind.OPENED.value,
        reason_code="not_a_reason",
        reason_payload_json={},
        expected_head_version=0,
        head_version_snapshot=0,
        correlation_id="cmp-bad",
        configuration_checksum="x" * 64,
    )
    with pytest.raises(sa.exc.IntegrityError):
        session.add(bad_event)
        session.commit()
    session.rollback()

    invalid_contract = ShapeComparisonContract(
        id="bad-contract",
        shape_id="A1",
        contract_revision="bad",
        contract_version="v1",
        contract_checksum="g" * 64,
        formula_inventory_checksum="f" * 64,
        target_kind="invalid_kind",
        stable_rule_identity_json={},
        required_input_identity_json={},
        required_output_lanes_json=["candidate"],
        canonical_context_json={},
        equality_rule_json={},
        required_trace_components_json=[],
        acceptance_effect=contracts.ShapeAcceptanceEffect.MAY_COUNT.value,
        classification_mapping_json={},
        is_current=True,
    )
    with pytest.raises(sa.exc.IntegrityError):
        session.add(invalid_contract)
        session.commit()
    session.rollback()


def test_ready_rejection_reason_must_be_closed_when_present(db):
    session, fixture = db
    window = _window(session, fixture)
    session.add(window)
    session.commit()

    bad_readiness = ShadowReadinessDecision(
        id="readiness-bad",
        validation_window_id=window.id,
        channel_id=fixture.channel_id,
        decision=contracts.WindowReadinessState.NOT_READY.value,
        reason_code="not_a_reason",
        compared_count=0,
        aggregate_checksum="a" * 64,
        required_comparison_count=1,
        comparison_ids_json=[],
        scope_manifest_checksum="s" * 64,
        readiness_payload_json={},
        created_at=utcnow(),
    )
    with pytest.raises(sa.exc.IntegrityError):
        session.add(bad_readiness)
        session.commit()
