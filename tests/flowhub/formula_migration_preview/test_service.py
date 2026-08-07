"""D6 offline migration preview tests."""

from __future__ import annotations

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import FlowHubBase
from app.flowhub.formula_migration_preview import (
    DependencyManifest,
    FormulaInventoryCell,
    FormulaMigrationInputCell,
    FormulaMigrationPreviewService,
    FormulaMigrationReviewAction,
    PreviewInput,
    ReviewDecisionRecord,
)
from app.flowhub.formula_migration_preview.models import (
    FormulaMigrationPreviewCell,
    FormulaMigrationReviewDecision,
)
from app.flowhub.formula_migration_preview.contracts import PreviewBatchState
from app.flowhub.formula_translator.contracts import (
    FORMULA_TRANSLATOR_VERSION,
    FormulaTranslationReason,
    FormulaTranslationStatus,
)
from app.flowhub.formula_translator.registry import (
    FORMULA_SHAPE_REGISTRY_CHECKSUM,
    FORMULA_SHAPE_REGISTRY_VERSION,
)
from app.flowhub.formula_translator.fingerprint import compute_translation_result_checksum
from app.flowhub.formula_translator.models import (
    FormulaShapeRegistryEntry,
    FormulaTranslationQuarantine,
    FormulaTranslationResult,
)
from app.flowhub.formula_translator.translator import translate_formula
from app.flowhub.pricing_authority.models import (
    ChannelPricingAuthorityEvent,
    ChannelPricingAuthorityHead,
    PricingAuthorityWriteRejection,
)
from app.flowhub.unified_workspace.domain import checksum


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    FlowHubBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    user = FlowHubUser(username="migration-user", hashed_password="unused", role="admin")
    session.add(user)
    session.commit()

    try:
        yield session, user
    finally:
        session.close()
        FlowHubBase.metadata.drop_all(engine)
        engine.dispose()


def _manifest() -> DependencyManifest:
    return DependencyManifest(
        source_roles=("basis", "rate"),
        manual_roles=(),
        derived_keys=(),
    )


def _manifest_checksum() -> str:
    manifest = _manifest()
    return checksum(
        {
            "source_roles": manifest.source_roles,
            "manual_roles": manifest.manual_roles,
            "derived_keys": manifest.derived_keys,
        }
    )


def _input_cell(
    *,
    inventory_id: str,
    formula: str,
    formula_rule_identity: str,
    translator_version: str = FORMULA_TRANSLATOR_VERSION,
    status_override: FormulaTranslationStatus | None = None,
    reason_override: FormulaTranslationReason | None = None,
    shape_override: str | None = None,
    translation_fingerprint_override: str | None = None,
) -> FormulaMigrationInputCell:
    outcome = translate_formula(formula=formula, formula_rule_identity=formula_rule_identity)
    if status_override is not None:
        outcome = outcome.__class__(
            formula_shape_id=outcome.formula_shape_id,
            translation_status=status_override,
            reason_code=reason_override or outcome.reason_code,
            input_payload=outcome.input_payload,
            output_payload=outcome.output_payload,
            translation_fingerprint=outcome.translation_fingerprint,
        )

    formula_shape_id = shape_override if shape_override is not None else outcome.formula_shape_id
    status = status_override or outcome.translation_status
    reason = reason_override or outcome.reason_code

    translation_fingerprint = translation_fingerprint_override
    if translation_fingerprint is None:
        translation_fingerprint = compute_translation_result_checksum(
            formula_rule_identity=formula_rule_identity,
            translator_version=translator_version,
            formula_shape_id=formula_shape_id,
            translation_status=status.value,
            reason_code=reason.value,
            registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
            registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
            translation_input_payload=outcome.input_payload,
            translation_output_payload=outcome.output_payload,
            package_fingerprint=None,
            reviewed_by=None,
        )

    return FormulaMigrationInputCell(
        inventory_cell=FormulaInventoryCell(
            inventory_id=inventory_id,
            formula_text=formula,
            worksheet="Sheet1",
            row=1,
            column=1,
        ),
        translation_status=status,
        reason_code=reason,
        formula_shape_id=formula_shape_id,
        translation_fingerprint=translation_fingerprint,
        translation_output_payload=outcome.output_payload,
        translation_input_payload=outcome.input_payload,
        binding_manifest=_manifest(),
        binding_manifest_checksum=_manifest_checksum(),
        translator_version=translator_version,
        registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
        registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
        formula_rule_identity=formula_rule_identity,
        translation_fingerprint_by_version={},
        fixture_and_registry_evidence={"fixture": "d5"},
    )


def _run_preview(
    db,
    user,
    batch_id: str,
    *cell_args: FormulaMigrationInputCell,
    cells: tuple[FormulaMigrationInputCell, ...] | None = None,
):
    if cells is None:
        payload_cells = cell_args
    else:
        if cell_args:
            raise TypeError("pass either positional cells or cells kwarg, not both")
        payload_cells = cells

    service = FormulaMigrationPreviewService(db)
    return service.assemble_preview(
        batch_id=batch_id,
        preview_input=PreviewInput(cells=tuple(payload_cells)),
        created_by_user=user,
    )


def _assert_counts(batch, *, translated: int, review_required: int, unsupported: int, quarantined: int, blocking: int) -> None:
    assert batch.counts["translated"] == translated
    assert batch.counts["review_required"] == review_required
    assert batch.counts["unsupported"] == unsupported
    assert batch.counts["quarantined"] == quarantined
    assert batch.blocking_operationally_active == blocking


def test_preview_assembly_mixed_batch_counts_and_state(db):
    session, user = db
    batch = _run_preview(
        session,
        user,
        batch_id="batch-mixed",
        cells=(
            _input_cell(
                inventory_id="i1",
                formula="=IF(RC[-2]=\"\",\"x\",IFERROR(FLOOR((RC[-2]*(1+R2C6/100)+IF(ISNUMBER(R3C6),R3C6,0))*1000000,50000),\"x\"))",
                formula_rule_identity="rule:A1",
            ),
            _input_cell(
                inventory_id="i2",
                formula="=RC[1]",
                formula_rule_identity="rule:A8",
                status_override=FormulaTranslationStatus.REVIEW_REQUIRED,
            ),
            _input_cell(
                inventory_id="i3",
                formula="=IFERROR(RC[-1]/RC[-2],\"x\")",
                formula_rule_identity="rule:A7",
                status_override=FormulaTranslationStatus.UNSUPPORTED,
            ),
            _input_cell(
                inventory_id="i4",
                formula="=IFERROR(RC[1]/RC[2],\"x\")",
                formula_rule_identity="rule:A9",
                status_override=FormulaTranslationStatus.QUARANTINED,
            ),
        ),
    )

    assert batch.state == PreviewBatchState.COMPLETED
    _assert_counts(batch, translated=1, review_required=1, unsupported=1, quarantined=1, blocking=1)


def test_preview_assembly_all_translated_batch(db):
    session, user = db
    batch = _run_preview(
        session,
        user,
        batch_id="batch-all-translated",
        cells=(
            _input_cell(
                inventory_id="i1",
                formula="=IF(RC[-2]=\"\",\"x\",IFERROR(FLOOR((RC[-2]*(1+R2C6/100)+IF(ISNUMBER(R3C6),R3C6,0))*1000000,50000),\"x\"))",
                formula_rule_identity="rule:A1",
            ),
            _input_cell(
                inventory_id="i2",
                formula="=IFERROR(FLOOR(RC[1]*(1+R2C3/100)*1000,100000),\"\u274c\")",
                formula_rule_identity="rule:A3",
            ),
            _input_cell(
                inventory_id="i3",
                formula="=IFERROR(FLOOR((RC[1]*(1+R10C3/100)*1000),100000),\"\u274c\")",
                formula_rule_identity="rule:A10",
            ),
        ),
    )
    assert batch.state == PreviewBatchState.COMPLETED
    _assert_counts(batch, translated=3, review_required=0, unsupported=0, quarantined=0, blocking=0)


def test_preview_assembly_quarantined_cells_remain_visible(db):
    session, user = db
    batch = _run_preview(
        session,
        user,
        batch_id="batch-quarantine",
        cells=(
            _input_cell(
                inventory_id="i1",
                formula="=IFERROR(#REF!*(1+R2C3/100),\"x\")",
                formula_rule_identity="rule:A13",
                status_override=FormulaTranslationStatus.QUARANTINED,
                shape_override="A13",
            ),
            _input_cell(
                inventory_id="i2",
                formula="=NOW()",
                formula_rule_identity="rule:unknown",
                status_override=FormulaTranslationStatus.QUARANTINED,
                shape_override=None,
            ),
        ),
    )
    _assert_counts(batch, translated=0, review_required=0, unsupported=0, quarantined=2, blocking=2)
    ids = {cell.inventory_cell_id for cell in batch.cells}
    assert ids == {"i1", "i2"}


def test_preview_assembly_review_required_batch(db):
    session, user = db
    batch = _run_preview(
        session,
        user,
        batch_id="batch-review-required",
        cells=(
            _input_cell(
                inventory_id="i1",
                formula="=RC[1]",
                formula_rule_identity="rule:A8-1",
                status_override=FormulaTranslationStatus.REVIEW_REQUIRED,
            ),
            _input_cell(
                inventory_id="i2",
                formula="=RC[1]",
                formula_rule_identity="rule:A8-2",
                status_override=FormulaTranslationStatus.REVIEW_REQUIRED,
            ),
        ),
    )
    _assert_counts(batch, translated=0, review_required=2, unsupported=0, quarantined=0, blocking=0)


def test_preview_assembly_deterministic_rerun_reuses_translation_results(db):
    session, user = db
    cell_a1 = _input_cell(
        inventory_id="i1",
        formula="=IF(RC[-2]=\"\",\"x\",IFERROR(FLOOR((RC[-2]*(1+R2C6/100)+IF(ISNUMBER(R3C6),R3C6,0))*1000000,50000),\"x\"))",
        formula_rule_identity="rule:A1",
    )
    cell_a3 = _input_cell(
        inventory_id="i2",
        formula="=IFERROR(FLOOR(RC[1]*(1+R2C3/100)*1000,100000),\"\u274c\")",
        formula_rule_identity="rule:A3",
    )

    first_batch = _run_preview(session, user, batch_id="batch-first", cells=(cell_a1, cell_a3))
    second_batch = _run_preview(
        session,
        user,
        batch_id="batch-second",
        cells=(cell_a3, cell_a1),
    )

    first_ids = {r.id for r in session.query(FormulaTranslationResult).all()}
    second_ids = {r.id for r in session.query(FormulaTranslationResult).all()}
    assert first_ids == second_ids
    assert len(first_ids) == 2
    assert first_batch.report_checksum == second_batch.report_checksum


def test_preview_assembly_translator_version_change_reports_diff(db):
    session, user = db
    old = _input_cell(
        inventory_id="i1",
        formula="=IFERROR(RC[1]/RC[2],\"x\")",
        formula_rule_identity="rule:version",
        translator_version="formula-translator-schema-v1",
        status_override=FormulaTranslationStatus.UNSUPPORTED,
        reason_override=FormulaTranslationReason.SHAPE_UNSUPPORTED,
        shape_override="A7",
    )
    legacy = _run_preview(session, user, batch_id="batch-v1", cells=(old,))
    assert legacy.cells[0].translator_version_diff is None

    new = _input_cell(
        inventory_id="i1",
        formula="=IFERROR(RC[1]/RC[2],\"x\")",
        formula_rule_identity="rule:version",
        translator_version="formula-translator-schema-v2",
        status_override=FormulaTranslationStatus.UNSUPPORTED,
        reason_override=FormulaTranslationReason.SHAPE_UNSUPPORTED,
        shape_override="A7",
    )
    upgraded = _run_preview(session, user, batch_id="batch-v2", cells=(new,))
    diff = upgraded.cells[0].translator_version_diff
    assert diff is not None
    assert diff["prior_translator_version"] == "formula-translator-schema-v1"
    assert diff["current_translator_version"] == "formula-translator-schema-v2"
    assert len(session.query(FormulaTranslationResult).all()) == 2


def test_translator_result_conflict_prevents_mutation_and_keeps_prior(db):
    session, user = db
    original = _input_cell(
        inventory_id="i1",
        formula="=IFERROR(RC[1]/RC[2],\"x\")",
        formula_rule_identity="rule:conflict",
        translator_version="formula-translator-schema-v1",
        status_override=FormulaTranslationStatus.UNSUPPORTED,
    )
    _run_preview(session, user, batch_id="batch-conflict-1", cells=(original,))
    result = session.query(FormulaTranslationResult).one()
    conflict = FormulaMigrationInputCell(
        inventory_cell=FormulaInventoryCell(
            inventory_id="i1",
            formula_text=original.translation_input_payload["formula"],
            worksheet="Sheet1",
            row=1,
            column=1,
        ),
        translation_status=original.translation_status,
        reason_code=original.reason_code,
        formula_shape_id=original.formula_shape_id,
        translation_fingerprint="bad-fingerprint",
        translation_output_payload=original.translation_output_payload,
        translation_input_payload=original.translation_input_payload,
        binding_manifest=original.binding_manifest,
        binding_manifest_checksum=original.binding_manifest_checksum,
        translator_version=original.translator_version,
        registry_version=original.registry_version,
        registry_checksum=original.registry_checksum,
        formula_rule_identity=original.formula_rule_identity,
    )
    service = FormulaMigrationPreviewService(session)
    with pytest.raises(ValueError, match="translation_result_conflict"):
        service.assemble_preview(
            batch_id="batch-conflict-2",
            preview_input=PreviewInput(cells=(conflict,)),
            created_by_user=user,
        )
    session.refresh(result)
    assert result.translation_fingerprint == original.translation_fingerprint


def test_same_semantic_inputs_reuse_immutable_translation_result(db):
    session, user = db
    cell = _input_cell(
        inventory_id="i1",
        formula="=IFERROR(FLOOR(RC[1]*(1+R2C3/100),100000),\"x\")",
        formula_rule_identity="rule:reuse",
    )
    first = _run_preview(session, user, batch_id="batch-reuse-1", cells=(cell,))
    baseline = session.query(FormulaTranslationResult).filter(
        FormulaTranslationResult.formula_rule_identity == "rule:reuse"
    ).one()
    second = _run_preview(session, user, batch_id="batch-reuse-2", cells=(cell,))
    assert first.cells[0].translation_fingerprint == second.cells[0].translation_fingerprint
    assert session.query(FormulaTranslationResult).filter(
        FormulaTranslationResult.formula_rule_identity == "rule:reuse"
    ).one().id == baseline.id
    assert session.query(FormulaTranslationResult).count() == 1


def test_unsupported_review_decision_cannot_upgrade_translation(db):
    session, user = db
    cell = _input_cell(
        inventory_id="i1",
        formula="=IFERROR(RC[1]/RC[2],\"x\")",
        formula_rule_identity="rule:unsupported",
        status_override=FormulaTranslationStatus.UNSUPPORTED,
    )
    batch = _run_preview(session, user, batch_id="batch-unsupported", cells=(cell,))
    service = FormulaMigrationPreviewService(session)
    service.add_review_decision(
        ReviewDecisionRecord(
            preview_batch_id=batch.batch_id,
            inventory_cell_id="i1",
            action=FormulaMigrationReviewAction.APPROVED,
            actor="reviewer",
            actor_user_id=user.id,
            reason="manual approval requested",
            evidence={},
        )
    )
    row = (
        session.query(FormulaMigrationPreviewCell)
        .filter(FormulaMigrationPreviewCell.inventory_cell_id == "i1")
        .one()
    )
    assert row.translation_status == FormulaTranslationStatus.UNSUPPORTED.value


def test_quarantined_review_decision_cannot_upgrade_translation(db):
    session, user = db
    cell = _input_cell(
        inventory_id="i1",
        formula="=IF(RC[-4]=\"\",\"x\",IFERROR(FLOOR((RC[-4]*(1+R2C3/100)+IF(ISNUMBER(R3C6),R3C6,0))*1000000,50000),\"x\")",
        formula_rule_identity="rule:quarantine",
        status_override=FormulaTranslationStatus.QUARANTINED,
    )
    batch = _run_preview(session, user, batch_id="batch-quarantined", cells=(cell,))
    service = FormulaMigrationPreviewService(session)
    service.add_review_decision(
        ReviewDecisionRecord(
            preview_batch_id=batch.batch_id,
            inventory_cell_id="i1",
            action=FormulaMigrationReviewAction.APPROVED,
            actor="reviewer",
            actor_user_id=user.id,
            reason="manual approval requested",
            evidence={},
        )
    )
    row = (
        session.query(FormulaMigrationPreviewCell)
        .filter(FormulaMigrationPreviewCell.inventory_cell_id == "i1")
        .one()
    )
    assert row.translation_status == FormulaTranslationStatus.QUARANTINED.value


def test_review_decisions_are_append_only(db):
    session, user = db
    cell = _input_cell(
        inventory_id="i1",
        formula="=RC[1]",
        formula_rule_identity="rule:append",
        status_override=FormulaTranslationStatus.REVIEW_REQUIRED,
    )
    batch = _run_preview(session, user, batch_id="batch-append", cells=(cell,))
    service = FormulaMigrationPreviewService(session)
    service.add_review_decision(
        ReviewDecisionRecord(
            preview_batch_id=batch.batch_id,
            inventory_cell_id="i1",
            action=FormulaMigrationReviewAction.NOTE,
            actor="reviewer",
            actor_user_id=user.id,
            reason="first",
        )
    )
    service.add_review_decision(
        ReviewDecisionRecord(
            preview_batch_id=batch.batch_id,
            inventory_cell_id="i1",
            action=FormulaMigrationReviewAction.APPROVED,
            actor="reviewer",
            actor_user_id=user.id,
            reason="second",
        )
    )
    decisions = session.query(FormulaMigrationReviewDecision).all()
    assert len(decisions) == 2
    assert decisions[0].reason == "first"
    assert decisions[1].reason == "second"


def test_blocking_operationally_active_rows_are_reported(db):
    session, user = db
    batch = _run_preview(
        session,
        user,
        batch_id="batch-blocking",
        cells=(
            _input_cell(
                inventory_id="i1",
                formula="=IF(RC[-2]=\"\",\"x\",IFERROR(FLOOR((RC[-2]*(1+R2C6/100)+IF(ISNUMBER(R3C6),R3C6,0))*1000000,50000),\"x\"))",
                formula_rule_identity="rule:A1",
            ),
            _input_cell(
                inventory_id="i2",
                formula="=IFERROR(RC[1]/#REF!,\"x\")",
                formula_rule_identity="rule:A13",
                status_override=FormulaTranslationStatus.QUARANTINED,
                shape_override="A13",
            ),
            _input_cell(
                inventory_id="i3",
                formula="=NOW()",
                formula_rule_identity="rule:unknown",
                status_override=FormulaTranslationStatus.QUARANTINED,
                shape_override=None,
            ),
        ),
    )
    assert batch.blocking_operationally_active == 2


def test_historical_quarantine_rows_do_not_disappear(db):
    session, user = db
    old_result = FormulaTranslationResult(
        id="history-quarantine-result-v1",
        formula_rule_identity="rule:history",
        formula_shape_id="A9",
        translation_status=FormulaTranslationStatus.QUARANTINED.value,
        reason_code=FormulaTranslationReason.BROKEN_REFERENCE.value,
        translator_version="formula-translator-schema-v1",
        registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
        registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
        translation_payload_json={},
        translation_fingerprint="historical-quarantine",
        translation_input_payload_json={"formula": "old"},
    )
    session.add(old_result)
    session.commit()

    service = FormulaMigrationPreviewService(session)
    batch = service.assemble_preview(
        batch_id="batch-history",
        preview_input=PreviewInput(
            cells=(
                _input_cell(
                    inventory_id="i1",
                    formula="=IFERROR(FLOOR(RC[1]*(1+R2C3/100)*1000,100000),\"\u274c\")",
                    formula_rule_identity="rule:history",
                    translator_version="formula-translator-schema-v2",
                ),
            )
        ),
        created_by_user=user,
    )
    assert batch.batch_id == "batch-history"
    results = session.query(FormulaTranslationResult).filter(
        FormulaTranslationResult.formula_rule_identity == "rule:history"
    ).order_by(FormulaTranslationResult.translator_version).all()
    assert len(results) == 2
    assert results[0].translation_status == FormulaTranslationStatus.QUARANTINED.value


def test_report_checksum_deterministic_for_reordered_input(db):
    session, user = db
    a1 = _input_cell(
        inventory_id="i1",
        formula="=IFERROR(FLOOR(RC[1]*(1+R2C3/100)*1000,100000),\"\u274c\")",
        formula_rule_identity="rule:a1",
    )
    a2 = _input_cell(
        inventory_id="i2",
        formula="=IFERROR(FLOOR((RC[1]*(1+R10C3/100)*1000),100000),\"\u274c\")",
        formula_rule_identity="rule:a10",
    )
    batch_one = _run_preview(session, user, batch_id="batch-order-one", cells=(a1, a2))
    batch_two = _run_preview(session, user, batch_id="batch-order-two", cells=(a2, a1))
    assert batch_one.report_checksum == batch_two.report_checksum


def test_no_fep_write_authority_side_effects(db):
    session, user = db
    before_authority_rows = session.query(ChannelPricingAuthorityEvent).count()
    before_authority_head = session.query(ChannelPricingAuthorityHead).count()
    before_authority_rejections = session.query(PricingAuthorityWriteRejection).count()
    before_quarantine = session.query(FormulaTranslationQuarantine).count()
    before_registry = session.query(FormulaShapeRegistryEntry).count()

    _run_preview(
        session,
        user,
        batch_id="batch-side-effect",
        cells=(
            _input_cell(
                inventory_id="i1",
                formula="=IFERROR(FLOOR(RC[1]*(1+R2C3/100)*1000,100000),\"x\")",
                formula_rule_identity="rule:safe",
            ),
        ),
    )

    assert session.query(ChannelPricingAuthorityEvent).count() == before_authority_rows
    assert session.query(ChannelPricingAuthorityHead).count() == before_authority_head
    assert session.query(PricingAuthorityWriteRejection).count() == before_authority_rejections
    assert session.query(FormulaTranslationQuarantine).count() == before_quarantine
    assert session.query(FormulaShapeRegistryEntry).count() == before_registry
