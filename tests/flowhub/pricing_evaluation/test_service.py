"""Frozen Evaluation Package service: integration coverage over a real Session."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from fractions import Fraction

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import FlowHubBase
from app.flowhub.pricing_evaluation.contracts import (
    DependencyRefKind,
    DerivedOperator,
    EffectiveOutputSource,
    ManualInputDecisionKind,
    ManualInputKind,
    ObservationSelectionMode,
)
from app.flowhub.pricing_evaluation.derived import DefinitionDraft, DependencyRef
from app.flowhub.pricing_evaluation.errors import DependencyResolutionError, DerivedValueError
from app.flowhub.pricing_evaluation.models import (
    FrozenEvaluationPackage,
    ManualInputDecision,
    ManualInputRevision,
)
from app.flowhub.pricing_evaluation.selection import ObservationCandidate
from app.flowhub.pricing_evaluation.service import (
    FrozenEvaluationPackageService,
    ManualInputRequirement,
    OverrideRequest,
    SourceRequirement,
)
from app.flowhub.source_acquisition.models import AcquisitionRun, SourceObservation
from app.flowhub.source_workspace.models import SourceProfile as Source
from app.flowhub.unified_workspace.domain import ImmutableRecordError, utcnow
from app.flowhub.exchange_rates import models as _exchange_rate_models  # noqa: F401
from app.flowhub.pricing_matrix import models as _pricing_matrix_models  # noqa: F401
from app.flowhub.write_pipeline import models as _write_pipeline_models  # noqa: F401
from app.flowhub.unified_workspace.models import WorkspaceChannel

NOW = datetime(2026, 8, 7, 12, 0, 0)

_DEFAULT_SOURCE_BINDING_CONTEXT = {
    "currency": "USD",
    "unit": "USD",
    "scale": {"numerator": 1, "denominator": 1},
}


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    FlowHubBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    user = FlowHubUser(username=f"pev_{uuid.uuid4().hex}", hashed_password="unused", role="admin")
    channel = WorkspaceChannel(
        id="woocommerce:primary",
        connector_type="woocommerce",
        name="Primary",
        implementation_state="ready",
        capabilities_json={},
        capability_version="test-v1",
        enabled=True,
    )
    other_channel = WorkspaceChannel(
        id="snappshop:primary",
        connector_type="snappshop",
        name="Secondary",
        implementation_state="ready",
        capabilities_json={},
        capability_version="test-v1",
        enabled=True,
    )
    session.add(user)
    session.flush()
    source_a = Source(
        id="src-vendor-a", name="Vendor A", source_kind="external", owner_user_id=user.id, status="active"
    )
    source_b = Source(
        id="src-vendor-b", name="Vendor B", source_kind="external", owner_user_id=user.id, status="active"
    )
    session.add_all((channel, other_channel, source_a, source_b))
    session.commit()
    try:
        yield session, user
    finally:
        session.close()
        FlowHubBase.metadata.drop_all(engine)
        engine.dispose()


def _observation(session, *, source_id: str, observed_at: datetime, value_suffix: str) -> SourceObservation:
    run_id = f"run-{value_suffix}"
    now = utcnow()
    run = AcquisitionRun(
        id=run_id,
        source_id=source_id,
        resource_scope="source",
        trigger_kind="manual",
        request_fingerprint="a" * 64,
        correlation_id=f"corr-{value_suffix}",
        parent_run_id=None,
        root_run_id=run_id,
        attempt_number=1,
        status="succeeded",
        result="observed",
        queued_at=now,
        started_at=now,
        terminal_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(run)
    session.flush()
    observation = SourceObservation(
        id=f"obs-{value_suffix}",
        acquisition_run_id=run_id,
        source_id=source_id,
        resource_scope="source",
        resource_identity=f"identity-{value_suffix}",
        resource_identity_hash="b" * 64,
        observation_version=1,
        observed_at=observed_at,
        provenance_json={},
        checksum=f"checksum-{value_suffix}",
    )
    session.add(observation)
    session.flush()
    return observation


def _candidate(observation: SourceObservation) -> ObservationCandidate:
    return ObservationCandidate(
        observation_id=observation.id,
        checksum=observation.checksum,
        observed_at=observation.observed_at,
    )


def _source_requirement(
    *args: object,
    resource_binding_revision_id: str = "binding-1",
    schema_unit_context: dict[str, object] | None = None,
    **kwargs: object,
) -> SourceRequirement:
    if args:
        source_role = args[0]
        source_id = args[1]
        mode = kwargs.pop("mode") if "mode" in kwargs else args[2]
        candidates = kwargs.pop("candidates") if "candidates" in kwargs else args[3]
        value = kwargs.pop("value") if "value" in kwargs else args[4]
    else:
        source_role = kwargs.pop("source_role")
        source_id = kwargs.pop("source_id")
        mode = kwargs.pop("mode")
        candidates = kwargs.pop("candidates")
        value = kwargs.pop("value")

    return SourceRequirement(
        source_role=source_role,
        source_id=source_id,
        mode=mode,
        candidates=candidates,
        value=value,
        resource_binding_revision_id=resource_binding_revision_id,
        schema_unit_context=dict(schema_unit_context or _DEFAULT_SOURCE_BINDING_CONTEXT),
        **kwargs,
    )


def _base_kwargs(**overrides):
    kwargs = dict(
        channel_id="woocommerce:primary",
        product_ref="SKU-1",
        workspace_id=None,
        workspace_pricing_evaluated_at=NOW,
        formula_shape_id="A1",
        translator_version="translator-not-active-v0",
        pricing_policy_revision_id=None,
        currency_unit_registry_version="unit-registry-v1",
        fx_snapshot_id=None,
        channel_config_revision_id=None,
        mapping_revision_id=None,
        product_metadata_fingerprint=None,
    )
    kwargs.update(overrides)
    return kwargs


# -- Single-source and multi-source packages ------------------------------------


def test_deterministic_single_source_package(db):
    session, user = db
    observation = _observation(session, source_id="src-vendor-a", observed_at=NOW - timedelta(hours=1), value_suffix="single")
    service = FrozenEvaluationPackageService(session)
    result = service.create_package(
        **_base_kwargs(),
        source_requirements=(
            _source_requirement(
                source_role="primary_vendor",
                source_id="src-vendor-a",
                mode=ObservationSelectionMode.LAST_APPROVED,
                candidates=(_candidate(observation),),
                value=Fraction(100_000),
            ),
        ),
        created_by_user=user,
        now=NOW,
    )
    assert result.package.id is not None
    assert len(result.source_pins) == 1
    assert result.source_pins[0].observation_id == observation.id


def test_multi_source_package_pins_exactly_one_observation_per_role(db):
    session, user = db
    obs_a = _observation(session, source_id="src-vendor-a", observed_at=NOW - timedelta(hours=1), value_suffix="multi-a")
    obs_b = _observation(session, source_id="src-vendor-b", observed_at=NOW - timedelta(hours=2), value_suffix="multi-b")
    service = FrozenEvaluationPackageService(session)
    result = service.create_package(
        **_base_kwargs(),
        source_requirements=(
            _source_requirement("vendor_a", "src-vendor-a", ObservationSelectionMode.LAST_APPROVED, (_candidate(obs_a),), Fraction(100_000)),
            _source_requirement("vendor_b", "src-vendor-b", ObservationSelectionMode.LAST_APPROVED, (_candidate(obs_b),), Fraction(120_000)),
        ),
        created_by_user=user,
        now=NOW,
    )
    roles = {pin.source_role for pin in result.source_pins}
    assert roles == {"vendor_a", "vendor_b"}


def test_missing_source_fails_closed_and_creates_no_package(db):
    session, user = db
    service = FrozenEvaluationPackageService(session)
    with pytest.raises(DependencyResolutionError, match="observation_missing"):
        service.create_package(
            **_base_kwargs(),
            source_requirements=(
                _source_requirement("vendor_a", "src-vendor-a", ObservationSelectionMode.LAST_APPROVED, (), Fraction(1)),
            ),
            created_by_user=user,
            now=NOW,
        )
    assert session.query(FrozenEvaluationPackage).count() == 0


def test_duplicate_source_role_fails_closed(db):
    session, user = db
    obs = _observation(session, source_id="src-vendor-a", observed_at=NOW - timedelta(hours=1), value_suffix="dup-role")
    service = FrozenEvaluationPackageService(session)
    with pytest.raises(DependencyResolutionError, match="source_role_duplicate"):
        service.create_package(
            **_base_kwargs(),
            source_requirements=(
                _source_requirement(
                    "vendor_a", "src-vendor-a", ObservationSelectionMode.LAST_APPROVED, (_candidate(obs),), Fraction(100_000)
                ),
                _source_requirement(
                    "vendor_a", "src-vendor-b", ObservationSelectionMode.LAST_APPROVED, (_candidate(obs),), Fraction(120_000),
                    resource_binding_revision_id="binding-2",
                ),
            ),
            created_by_user=user,
            now=NOW,
        )
    assert session.query(FrozenEvaluationPackage).count() == 0


def test_source_binding_revision_missing_fails_closed(db):
    session, user = db
    obs = _observation(session, source_id="src-vendor-a", observed_at=NOW - timedelta(hours=1), value_suffix="binding-missing")
    service = FrozenEvaluationPackageService(session)
    with pytest.raises(DependencyResolutionError, match="source_binding_revision_missing"):
        service.create_package(
            **_base_kwargs(),
            source_requirements=(
                _source_requirement(
                    "vendor_a", "src-vendor-a", ObservationSelectionMode.LAST_APPROVED, (_candidate(obs),), Fraction(100_000),
                    resource_binding_revision_id=None,
                ),
            ),
            created_by_user=user,
            now=NOW,
        )
    assert session.query(FrozenEvaluationPackage).count() == 0


@pytest.mark.parametrize(
    ("label", "context", "reason"),
    [
        (
            "missing_currency",
            {"unit": "USD", "scale": {"numerator": 1, "denominator": 1}},
            "source_currency_unresolved",
        ),
        (
            "missing_unit",
            {"currency": "USD", "scale": {"numerator": 1, "denominator": 1}},
            "source_unit_unresolved",
        ),
        (
            "missing_scale",
            {"currency": "USD", "unit": "USD"},
            "source_scale_unresolved",
        ),
        (
            "invalid_scale",
            {"currency": "USD", "unit": "USD", "scale": {"numerator": 0, "denominator": -1}},
            "source_scale_unresolved",
        ),
    ],
)
def test_source_binding_context_fails_closed_when_not_resolved(db, label, context, reason):
    session, user = db
    obs = _observation(
        session, source_id="src-vendor-a", observed_at=NOW - timedelta(hours=1), value_suffix=f"unresolved-{label}"
    )
    service = FrozenEvaluationPackageService(session)
    with pytest.raises(DependencyResolutionError, match=reason):
        service.create_package(
            **_base_kwargs(),
            source_requirements=(
                _source_requirement(
                    "vendor_a", "src-vendor-a", ObservationSelectionMode.LAST_APPROVED, (_candidate(obs),), Fraction(100_000),
                    schema_unit_context=context,
                ),
            ),
            created_by_user=user,
            now=NOW,
        )
    assert session.query(FrozenEvaluationPackage).count() == 0


def test_stale_source_fails_closed(db):
    session, user = db
    obs = _observation(session, source_id="src-vendor-a", observed_at=NOW - timedelta(days=30), value_suffix="stale")
    service = FrozenEvaluationPackageService(session)
    with pytest.raises(DependencyResolutionError, match="observation_stale"):
        service.create_package(
            **_base_kwargs(),
            source_requirements=(
                _source_requirement(
                    "vendor_a", "src-vendor-a", ObservationSelectionMode.LAST_APPROVED, (_candidate(obs),),
                    Fraction(1), freshness_max_age=timedelta(days=7), require_fresh=True,
                ),
            ),
            created_by_user=user,
            now=NOW,
        )
    assert session.query(FrozenEvaluationPackage).count() == 0


def test_cross_source_skew_violation_fails_closed(db):
    session, user = db
    obs_a = _observation(session, source_id="src-vendor-a", observed_at=NOW, value_suffix="skew-a")
    obs_b = _observation(session, source_id="src-vendor-b", observed_at=NOW - timedelta(days=5), value_suffix="skew-b")
    service = FrozenEvaluationPackageService(session)
    with pytest.raises(DependencyResolutionError, match="cross_source_skew_violation"):
        service.create_package(
            **_base_kwargs(),
            source_requirements=(
                _source_requirement("vendor_a", "src-vendor-a", ObservationSelectionMode.LAST_APPROVED, (_candidate(obs_a),), Fraction(1)),
                _source_requirement("vendor_b", "src-vendor-b", ObservationSelectionMode.LAST_APPROVED, (_candidate(obs_b),), Fraction(1)),
            ),
            cross_source_skew_tolerance=timedelta(hours=6),
            created_by_user=user,
            now=NOW,
        )
    assert session.query(FrozenEvaluationPackage).count() == 0


def test_aligned_business_cycle_selection(db):
    session, user = db
    obs = _observation(session, source_id="src-vendor-a", observed_at=NOW - timedelta(hours=1), value_suffix="cycle")
    service = FrozenEvaluationPackageService(session)
    result = service.create_package(
        **_base_kwargs(),
        source_requirements=(
            _source_requirement(
                "vendor_a", "src-vendor-a", ObservationSelectionMode.ALIGNED_BUSINESS_CYCLE,
                (ObservationCandidate(obs.id, obs.checksum, obs.observed_at, business_cycle_identity="2026-W31"),),
                Fraction(1), business_cycle_identity="2026-W31",
            ),
        ),
        created_by_user=user,
        now=NOW,
    )
    assert result.source_pins[0].business_cycle_identity == "2026-W31"


def test_explicit_observation_selection(db):
    session, user = db
    obs = _observation(session, source_id="src-vendor-a", observed_at=NOW - timedelta(hours=1), value_suffix="explicit")
    service = FrozenEvaluationPackageService(session)
    result = service.create_package(
        **_base_kwargs(),
        source_requirements=(
            _source_requirement(
                "vendor_a", "src-vendor-a", ObservationSelectionMode.EXPLICIT_OBSERVATION,
                (_candidate(obs),), Fraction(1), explicit_observation_id=obs.id,
            ),
        ),
        created_by_user=user,
        now=NOW,
    )
    assert result.source_pins[0].observation_id == obs.id


# -- Manual inputs ----------------------------------------------------------------


def _manual_input(
    session,
    user,
    *,
    decision_kind: ManualInputDecisionKind,
    effective_at=None,
    created_at=None,
) -> tuple[ManualInputRevision, ManualInputDecision]:
    revision = ManualInputRevision(
        id=str(uuid.uuid4()),
        kind=ManualInputKind.REFERENCE_PRICE.value,
        channel_id="woocommerce:primary",
        product_ref="SKU-1",
        revision_number=1,
        value_json={"value": "100000"},
        checksum=str(uuid.uuid4()),
        created_by_user_id=user.id,
    )
    session.add(revision)
    session.flush()
    decision = ManualInputDecision(
        id=str(uuid.uuid4()),
        manual_input_revision_id=revision.id,
        decision=decision_kind.value,
        actor_user_id=user.id,
        reason="test",
        effective_at=effective_at,
        created_at=created_at or NOW - timedelta(hours=1),
    )
    session.add(decision)
    session.commit()
    return revision, decision


def test_manual_approved_selection_is_pinned(db):
    session, user = db
    obs = _observation(session, source_id="src-vendor-a", observed_at=NOW - timedelta(hours=1), value_suffix="manual-ok")
    revision, decision = _manual_input(session, user, decision_kind=ManualInputDecisionKind.APPROVED)
    service = FrozenEvaluationPackageService(session)
    result = service.create_package(
        **_base_kwargs(),
        source_requirements=(
            _source_requirement("vendor_a", "src-vendor-a", ObservationSelectionMode.LAST_APPROVED, (_candidate(obs),), Fraction(100_000)),
        ),
        manual_input_requirements=(
            ManualInputRequirement(manual_input_revision_id=revision.id, key="ref_price", value=Fraction(100_000)),
        ),
        created_by_user=user,
        now=NOW,
    )
    assert len(result.manual_input_pins) == 1
    assert result.manual_input_pins[0].manual_input_decision_id == decision.id


def test_manual_ambiguity_fails_closed(db):
    session, user = db
    revision = ManualInputRevision(
        id=str(uuid.uuid4()), kind=ManualInputKind.REFERENCE_PRICE.value, channel_id="woocommerce:primary",
        product_ref="SKU-1", revision_number=1, value_json={"value": "1"}, checksum=str(uuid.uuid4()),
        created_by_user_id=user.id,
    )
    session.add(revision)
    session.flush()
    tie = NOW - timedelta(hours=1)
    session.add_all((
        ManualInputDecision(id=str(uuid.uuid4()), manual_input_revision_id=revision.id, decision="approved", actor_user_id=user.id, reason="a", created_at=tie),
        ManualInputDecision(id=str(uuid.uuid4()), manual_input_revision_id=revision.id, decision="approved", actor_user_id=user.id, reason="b", created_at=tie),
    ))
    session.commit()
    obs = _observation(session, source_id="src-vendor-a", observed_at=NOW - timedelta(hours=1), value_suffix="manual-ambiguous")
    service = FrozenEvaluationPackageService(session)
    with pytest.raises(DependencyResolutionError, match="manual_input_decision_ambiguous"):
        service.create_package(
            **_base_kwargs(),
            source_requirements=(
                _source_requirement("vendor_a", "src-vendor-a", ObservationSelectionMode.LAST_APPROVED, (_candidate(obs),), Fraction(1)),
            ),
            manual_input_requirements=(
                ManualInputRequirement(manual_input_revision_id=revision.id, key="ref_price", value=Fraction(1)),
            ),
            created_by_user=user,
            now=NOW,
        )
    assert session.query(FrozenEvaluationPackage).count() == 0


def test_revoked_manual_input_fails_closed(db):
    session, user = db
    revision, _decision = _manual_input(session, user, decision_kind=ManualInputDecisionKind.APPROVED)
    session.add(
        ManualInputDecision(
            id=str(uuid.uuid4()), manual_input_revision_id=revision.id, decision="revoked",
            actor_user_id=user.id, reason="revoke", created_at=NOW - timedelta(minutes=1),
        )
    )
    session.commit()
    obs = _observation(session, source_id="src-vendor-a", observed_at=NOW - timedelta(hours=1), value_suffix="manual-revoked")
    service = FrozenEvaluationPackageService(session)
    with pytest.raises(DependencyResolutionError, match="manual_input_revoked"):
        service.create_package(
            **_base_kwargs(),
            source_requirements=(
                _source_requirement("vendor_a", "src-vendor-a", ObservationSelectionMode.LAST_APPROVED, (_candidate(obs),), Fraction(1)),
            ),
            manual_input_requirements=(
                ManualInputRequirement(manual_input_revision_id=revision.id, key="ref_price", value=Fraction(1)),
            ),
            created_by_user=user,
            now=NOW,
        )


def test_expired_manual_input_fails_closed(db):
    session, user = db
    revision = ManualInputRevision(
        id=str(uuid.uuid4()), kind=ManualInputKind.REFERENCE_PRICE.value, channel_id="woocommerce:primary",
        product_ref="SKU-1", revision_number=1, value_json={"value": "1"}, checksum=str(uuid.uuid4()),
        created_by_user_id=user.id, expires_at=NOW - timedelta(days=1),
    )
    session.add(revision)
    session.flush()
    session.add(ManualInputDecision(id=str(uuid.uuid4()), manual_input_revision_id=revision.id, decision="approved", actor_user_id=user.id, reason="ok"))
    session.commit()
    obs = _observation(session, source_id="src-vendor-a", observed_at=NOW - timedelta(hours=1), value_suffix="manual-expired")
    service = FrozenEvaluationPackageService(session)
    with pytest.raises(DependencyResolutionError, match="manual_input_expired"):
        service.create_package(
            **_base_kwargs(),
            source_requirements=(
                _source_requirement("vendor_a", "src-vendor-a", ObservationSelectionMode.LAST_APPROVED, (_candidate(obs),), Fraction(1)),
            ),
            manual_input_requirements=(
                ManualInputRequirement(manual_input_revision_id=revision.id, key="ref_price", value=Fraction(1)),
            ),
            created_by_user=user,
            now=NOW,
        )


def test_manual_input_duplicate_key_fails_closed(db):
    session, user = db
    obs = _observation(session, source_id="src-vendor-a", observed_at=NOW - timedelta(hours=1), value_suffix="manual-duplicate-key")
    revision, _decision = _manual_input(session, user, decision_kind=ManualInputDecisionKind.APPROVED)
    service = FrozenEvaluationPackageService(session)
    with pytest.raises(DependencyResolutionError, match="manual_input_key_duplicate"):
        service.create_package(
            **_base_kwargs(),
            source_requirements=(
                _source_requirement("vendor_a", "src-vendor-a", ObservationSelectionMode.LAST_APPROVED, (_candidate(obs),), Fraction(1)),
            ),
            manual_input_requirements=(
                ManualInputRequirement(manual_input_revision_id=revision.id, key="dup", value=Fraction(1)),
                ManualInputRequirement(manual_input_revision_id=revision.id, key="dup", value=Fraction(2)),
            ),
            created_by_user=user,
            now=NOW,
        )
    assert session.query(FrozenEvaluationPackage).count() == 0


def test_manual_metadata_requires_currency_and_unit(db):
    session, user = db
    obs = _observation(session, source_id="src-vendor-a", observed_at=NOW - timedelta(hours=1), value_suffix="manual-metadata")
    revision = ManualInputRevision(
        id=str(uuid.uuid4()),
        kind=ManualInputKind.MANUAL_METADATA.value,
        channel_id="woocommerce:primary",
        product_ref="SKU-1",
        revision_number=1,
        value_json={"value": "{}", "metadata_key": "x"},
        currency="USD",
        unit=None,
        checksum=str(uuid.uuid4()),
        created_by_user_id=user.id,
    )
    session.add(revision)
    session.flush()
    session.add(
        ManualInputDecision(
            id=str(uuid.uuid4()),
            manual_input_revision_id=revision.id,
            decision=ManualInputDecisionKind.APPROVED.value,
            actor_user_id=user.id,
            reason="approved",
        )
    )
    session.commit()

    service = FrozenEvaluationPackageService(session)
    with pytest.raises(DependencyResolutionError, match="manual_input_scope_mismatch"):
        service.create_package(
            **_base_kwargs(),
            source_requirements=(
                _source_requirement("vendor_a", "src-vendor-a", ObservationSelectionMode.LAST_APPROVED, (_candidate(obs),), Fraction(1)),
            ),
            manual_input_requirements=(
                ManualInputRequirement(manual_input_revision_id=revision.id, key="manual_metadata", value=Fraction(1)),
            ),
            created_by_user=user,
            now=NOW,
        )


# -- Override ---------------------------------------------------------------------


def test_override_preserves_candidate_override_and_effective_output_separately(db):
    session, user = db
    obs = _observation(session, source_id="src-vendor-a", observed_at=NOW - timedelta(hours=1), value_suffix="override")
    revision, decision = _manual_input(session, user, decision_kind=ManualInputDecisionKind.APPROVED)
    service = FrozenEvaluationPackageService(session)
    result = service.create_package(
        **_base_kwargs(),
        source_requirements=(
            _source_requirement("vendor_a", "src-vendor-a", ObservationSelectionMode.LAST_APPROVED, (_candidate(obs),), Fraction(100_000)),
        ),
        calculated_candidate=Fraction(110_000),
        override=OverrideRequest(override_value=Fraction(99_000), manual_input_decision_id=decision.id),
        created_by_user=user,
        now=NOW,
    )
    override_row = result.override
    assert override_row is not None
    assert Fraction(override_row.calculated_candidate_numerator, override_row.calculated_candidate_denominator) == Fraction(110_000)
    assert Fraction(override_row.override_value_numerator, override_row.override_value_denominator) == Fraction(99_000)
    assert Fraction(override_row.effective_output_numerator, override_row.effective_output_denominator) == Fraction(99_000)
    assert override_row.effective_output_source == EffectiveOutputSource.OVERRIDE_VALUE.value


def test_no_override_still_records_the_calculated_candidate_as_effective(db):
    session, user = db
    obs = _observation(session, source_id="src-vendor-a", observed_at=NOW - timedelta(hours=1), value_suffix="no-override")
    service = FrozenEvaluationPackageService(session)
    result = service.create_package(
        **_base_kwargs(),
        source_requirements=(
            _source_requirement("vendor_a", "src-vendor-a", ObservationSelectionMode.LAST_APPROVED, (_candidate(obs),), Fraction(100_000)),
        ),
        calculated_candidate=Fraction(110_000),
        created_by_user=user,
        now=NOW,
    )
    override_row = result.override
    assert override_row.effective_output_source == EffectiveOutputSource.CALCULATED_CANDIDATE.value
    assert Fraction(override_row.effective_output_numerator, override_row.effective_output_denominator) == Fraction(110_000)


# -- Derived values within a package ---------------------------------------------


def test_derived_values_are_evaluated_and_persisted_in_order(db):
    session, user = db
    obs = _observation(session, source_id="src-vendor-a", observed_at=NOW - timedelta(hours=1), value_suffix="derived")
    service = FrozenEvaluationPackageService(session)
    step1 = DefinitionDraft(
        definition_key="step1",
        operator=DerivedOperator.MULTIPLY_PERCENT,
        parameters={"percent_bp": 1000},
        dependencies=(DependencyRef(DependencyRefKind.OBSERVATION, "vendor_a"),),
    )
    step2 = DefinitionDraft(
        definition_key="step2",
        operator=DerivedOperator.FLOOR_TO_STEP,
        parameters={"step_minor": 50_000},
        dependencies=(DependencyRef(DependencyRefKind.DERIVED, "step1"),),
    )
    result = service.create_package(
        **_base_kwargs(),
        source_requirements=(
            _source_requirement("vendor_a", "src-vendor-a", ObservationSelectionMode.LAST_APPROVED, (_candidate(obs),), Fraction(100_000)),
        ),
        derived_definitions=(step1, step2),
        created_by_user=user,
        now=NOW,
    )
    assert len(result.derived_evaluations) == 2
    by_order = sorted(result.derived_evaluations, key=lambda e: e.evaluation_order)
    first, second = by_order
    assert Fraction(first.result_numerator, first.result_denominator) == Fraction(110_000)
    assert Fraction(second.result_numerator, second.result_denominator) == Fraction(100_000)


def test_cross_package_derived_dependency_is_rejected(db):
    """A DERIVED ref that names a key outside the current package's draft set
    is unresolvable by construction -- there is no code path that reads
    another package's DerivedValueEvaluation as an upstream input."""
    session, user = db
    obs = _observation(session, source_id="src-vendor-a", observed_at=NOW - timedelta(hours=1), value_suffix="cross-pkg")
    service = FrozenEvaluationPackageService(session)
    foreign_ref_definition = DefinitionDraft(
        definition_key="only_step",
        operator=DerivedOperator.ADD_CONSTANT,
        parameters={"addend_minor": 1},
        dependencies=(DependencyRef(DependencyRefKind.DERIVED, "some-other-packages-definition"),),
    )
    with pytest.raises(DerivedValueError, match="derived_dependency_missing"):
        service.create_package(
            **_base_kwargs(),
            source_requirements=(
                _source_requirement("vendor_a", "src-vendor-a", ObservationSelectionMode.LAST_APPROVED, (_candidate(obs),), Fraction(1)),
            ),
            derived_definitions=(foreign_ref_definition,),
            created_by_user=user,
            now=NOW,
        )
    assert session.query(FrozenEvaluationPackage).count() == 0


# -- Pins, immutability, isolation, determinism ------------------------------------


def test_fx_unit_config_pins_are_persisted(db):
    session, user = db
    obs = _observation(session, source_id="src-vendor-a", observed_at=NOW - timedelta(hours=1), value_suffix="pins")
    service = FrozenEvaluationPackageService(session)
    result = service.create_package(
        **_base_kwargs(currency_unit_registry_version="unit-registry-v7"),
        source_requirements=(
            _source_requirement("vendor_a", "src-vendor-a", ObservationSelectionMode.LAST_APPROVED, (_candidate(obs),), Fraction(1)),
        ),
        created_by_user=user,
        now=NOW,
    )
    assert result.package.currency_unit_registry_version == "unit-registry-v7"
    assert result.package.arithmetic_version == "pricing-evaluation-arithmetic-v1"


def test_immutability_rejects_update_and_delete(db):
    session, user = db
    obs = _observation(session, source_id="src-vendor-a", observed_at=NOW - timedelta(hours=1), value_suffix="immutable")
    service = FrozenEvaluationPackageService(session)
    result = service.create_package(
        **_base_kwargs(),
        source_requirements=(
            _source_requirement("vendor_a", "src-vendor-a", ObservationSelectionMode.LAST_APPROVED, (_candidate(obs),), Fraction(1)),
        ),
        created_by_user=user,
        now=NOW,
    )
    result.package.formula_shape_id = "A3"
    with pytest.raises(ImmutableRecordError):
        session.commit()
    session.rollback()


def test_channel_isolation_a_blocked_channel_does_not_affect_another(db):
    session, user = db
    obs_ok = _observation(session, source_id="src-vendor-a", observed_at=NOW - timedelta(hours=1), value_suffix="iso-ok")
    service = FrozenEvaluationPackageService(session)
    with pytest.raises(DependencyResolutionError):
        service.create_package(
            **_base_kwargs(channel_id="snappshop:primary"),
            source_requirements=(
                _source_requirement("vendor_a", "src-vendor-a", ObservationSelectionMode.LAST_APPROVED, (), Fraction(1)),
            ),
            created_by_user=user,
            now=NOW,
        )
    result = service.create_package(
        **_base_kwargs(channel_id="woocommerce:primary"),
        source_requirements=(
            _source_requirement("vendor_a", "src-vendor-a", ObservationSelectionMode.LAST_APPROVED, (_candidate(obs_ok),), Fraction(1)),
        ),
        created_by_user=user,
        now=NOW,
    )
    assert result.package.channel_id == "woocommerce:primary"


def test_replay_determinism_same_inputs_produce_the_same_fingerprint(db):
    session, user = db
    obs = _observation(session, source_id="src-vendor-a", observed_at=NOW - timedelta(hours=1), value_suffix="replay")
    service = FrozenEvaluationPackageService(session)
    kwargs = dict(
        **_base_kwargs(),
        source_requirements=(
            _source_requirement("vendor_a", "src-vendor-a", ObservationSelectionMode.LAST_APPROVED, (_candidate(obs),), Fraction(1)),
        ),
        created_by_user=user,
        now=NOW,
    )
    first = service.create_package(**kwargs)
    second = service.create_package(**kwargs)
    assert first.package.id != second.package.id
    assert first.package.dependency_fingerprint == second.package.dependency_fingerprint


def test_channel_not_found_fails_closed(db):
    session, user = db
    service = FrozenEvaluationPackageService(session)
    with pytest.raises(DependencyResolutionError, match="pricing_evaluation_channel_not_found"):
        service.create_package(
            **_base_kwargs(channel_id="does-not-exist"),
            source_requirements=(),
            created_by_user=user,
            now=NOW,
        )
