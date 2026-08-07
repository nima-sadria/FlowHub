"""D7 translation evidence projection tests."""

from __future__ import annotations

from datetime import datetime
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import FlowHubBase
from app.flowhub.formula_migration_preview import (
    FormulaMigrationPreviewProjectionService,
    FormulaMigrationProjectionReason,
    FormulaMigrationReviewAction,
    PreviewBatchState,
)
from app.flowhub.formula_migration_preview.contracts import FormulaMigrationPreviewProjection
from app.flowhub.formula_migration_preview.fingerprint import compute_preview_batch_checksum
from app.flowhub.formula_migration_preview.models import (
    FormulaMigrationPreviewBatch as PreviewBatchModel,
    FormulaMigrationPreviewCell as PreviewCellModel,
    FormulaMigrationReviewDecision,
)
from app.flowhub.formula_translator.contracts import (
    FORMULA_SHAPE_REGISTRY_VERSION,
    FORMULA_TRANSLATOR_VERSION,
    FormulaTranslationReason,
    FormulaTranslationStatus,
)
from app.flowhub.formula_translator.registry import (
    FORMULA_SHAPE_REGISTRY_CHECKSUM,
)
from app.flowhub.formula_translator.fingerprint import compute_translation_result_checksum
from app.flowhub.formula_translator.models import (
    FormulaTranslationQuarantine,
    FormulaTranslationResult,
)
from app.flowhub.formula_translator.registry import get_registry_entry
from app.flowhub.formula_translator.translator import translate_formula
from app.flowhub.exchange_rates import models as _exchange_rate_models  # noqa: F401
from app.flowhub.pricing_authority.models import (
    ChannelPricingAuthorityEvent,
    ChannelPricingAuthorityHead,
    PricingAuthorityWriteRejection,
)
from app.flowhub.pricing_authority import models as _pricing_authority_models  # noqa: F401
from app.flowhub.pricing_matrix import models as _pricing_matrix_models  # noqa: F401
from app.flowhub.pricing_evaluation.models import FrozenEvaluationPackage
from app.flowhub.source_acquisition import models as _source_acquisition_models  # noqa: F401
from app.flowhub.source_workspace import models as _source_workspace_models  # noqa: F401
from app.flowhub.unified_workspace.models import WorkspaceChannel
from app.flowhub.shadow_validation.models import (
    ShapeComparisonContract,
    ShadowValidationComparison,
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
    user = FlowHubUser(username="proj-user", hashed_password="unused", role="admin")
    session.add(user)
    session.commit()

    try:
        yield session, user
    finally:
        session.close()
        FlowHubBase.metadata.drop_all(engine)
        engine.dispose()


def _manifest() -> tuple[str, ...]:
    return ("basis", "rate", "fixed_addend")


def _manifest_checksum() -> str:
    return checksum(
        {
            "source_roles": _manifest(),
            "manual_roles": (),
            "derived_keys": (),
        }
    )


def _compute_batch_inventory_checksum(*, batch_id: str) -> str:
    return checksum({"batch_id": batch_id})


def _compute_batch_input_checksum(*, rows: tuple[dict[str, object], ...]) -> str:
    return checksum({"rows": rows})


def _translation_payload(
    *,
    formula: str,
    rule_identity: str,
    status: FormulaTranslationStatus,
    reason: FormulaTranslationReason,
    formula_shape_id: str | None,
    translator_version: str,
    registry_version: str,
    registry_checksum: str,
    translation_fingerprint: str,
    translation_input_payload: dict[str, object],
    translation_output_payload: dict[str, object],
    formula_text: str,
) -> dict[str, object]:
    return {
        "inventory_cell_id": rule_identity,
        "formula_rule_identity": rule_identity,
        "formula_shape_id": formula_shape_id,
        "translation_status": status.value,
        "reason_code": reason.value,
        "translation_fingerprint": translation_fingerprint,
        "binding_manifest_checksum": _manifest_checksum(),
        "target_fragment": translation_output_payload,
        "review_required": (
            {"required": True, "reason": reason.value, "evidence": {"formula": formula}}
            if status is FormulaTranslationStatus.REVIEW_REQUIRED
            else None
        ),
        "quarantine_reason": (
            {"required": True, "reason": reason.value, "evidence": {"formula": formula}}
            if status is FormulaTranslationStatus.QUARANTINED
            else None
        ),
        "fixture_registry_evidence": {
            "registry_version": registry_version,
            "registry_checksum": registry_checksum,
            "registry_entry": {
                "shape_id": formula_shape_id,
                "is_price_target": get_registry_entry(formula_shape_id).is_price_target if formula_shape_id else None,
            },
            "formula_translation_result_id": "TODO",
            "fixture_evidence": {
                "formula": formula_text,
            },
        },
        "translator_version": translator_version,
        "translator_version_diff": None,
        "blocking_operationally_active": False,
        "formula_inventory_evidence": {
            "formula_rule_identity": rule_identity,
            "inventory_cell_id": rule_identity,
            "formula_text": formula_text,
        },
        "binding_manifest": {
            "source_roles": _manifest(),
            "manual_roles": (),
            "derived_keys": (),
        },
        "registry_version": registry_version,
        "registry_checksum": registry_checksum,
    }


def _create_translation_result(
    *,
    session,
    rule_identity: str,
    status: FormulaTranslationStatus,
    reason: FormulaTranslationReason,
    formula_shape_id: str | None,
    translator_version: str,
    registry_version: str,
    registry_checksum: str,
    translation_fingerprint: str,
    translation_output_payload: dict[str, object],
    translation_input_payload: dict[str, object],
    result_id: str | None = None,
) -> str:
    result_id = result_id or f"result-{rule_identity}"
    session.add(
        FormulaTranslationResult(
            id=result_id,
            formula_rule_identity=rule_identity,
            formula_shape_id=formula_shape_id,
            translation_status=status.value,
            reason_code=reason.value,
            translator_version=translator_version,
            registry_version=registry_version,
            registry_checksum=registry_checksum,
            translation_payload_json=translation_output_payload,
            translation_fingerprint=translation_fingerprint,
            translation_input_payload_json=translation_input_payload,
        )
    )
    return result_id


def _add_cell(
    session,
    *,
    batch_id: str,
    inventory_cell_id: str,
    rule_identity: str,
    formula: str,
    status: FormulaTranslationStatus,
    translator_version: str = FORMULA_TRANSLATOR_VERSION,
    registry_version: str = FORMULA_SHAPE_REGISTRY_VERSION,
    registry_checksum: str = FORMULA_SHAPE_REGISTRY_CHECKSUM,
    result_id: str | None = None,
    blocking_operationally_active: bool = False,
    row_result_override: str | None = None,
) -> PreviewCellModel:
    outcome = translate_formula(formula=formula, formula_rule_identity=rule_identity)
    if result_id is None:
        result_id = f"result-{rule_identity}"
    existing_result = session.get(FormulaTranslationResult, result_id)

    formula_shape_id = outcome.formula_shape_id if status is None else outcome.formula_shape_id
    if existing_result is not None:
        formula_shape_id = existing_result.formula_shape_id
    elif status is FormulaTranslationStatus.REVIEW_REQUIRED and outcome.formula_shape_id is None:
        formula_shape_id = "A1"

    if result_id is None:
        result_id = f"result-{rule_identity}"

    translation_fingerprint = row_result_override
    if translation_fingerprint is None:
        if existing_result is None:
            translation_fingerprint = compute_translation_result_checksum(
                formula_rule_identity=rule_identity,
                translator_version=translator_version,
                formula_shape_id=formula_shape_id,
                translation_status=status.value,
                reason_code=outcome.reason_code.value
                if status == outcome.translation_status
                else FormulaTranslationReason.REVIEW_REQUIRED.value,
                registry_version=registry_version,
                registry_checksum=registry_checksum,
                translation_input_payload={"formula": formula},
                translation_output_payload=outcome.output_payload,
                package_fingerprint=None,
                reviewed_by=None,
            )
        else:
            translation_fingerprint = existing_result.translation_fingerprint
    if existing_result is not None and status == FormulaTranslationStatus(existing_result.translation_status):
        reason = FormulaTranslationReason(existing_result.reason_code)
    else:
        reason = (
            FormulaTranslationReason.MATCHED_SUPPORTED
            if status == FormulaTranslationStatus.TRANSLATED
            else FormulaTranslationReason.REVIEW_REQUIRED
            if status == FormulaTranslationStatus.REVIEW_REQUIRED
            else FormulaTranslationReason.SHAPE_UNSUPPORTED
            if status == FormulaTranslationStatus.UNSUPPORTED
            else FormulaTranslationReason.BROKEN_REFERENCE
            if status == FormulaTranslationStatus.QUARANTINED
            else outcome.reason_code
        )

    payload = _translation_payload(
        formula=formula,
        rule_identity=rule_identity,
        status=status,
        reason=reason,
        formula_shape_id=formula_shape_id,
        translator_version=translator_version,
        registry_version=registry_version,
        registry_checksum=registry_checksum,
        translation_fingerprint=translation_fingerprint,
        translation_input_payload={"formula": formula},
        translation_output_payload=outcome.output_payload,
        formula_text=formula,
    )

    payload["fixture_registry_evidence"]["formula_translation_result_id"] = result_id
    cell_id = f"cell-{rule_identity}"
    payload["formula_shape_id"] = formula_shape_id

    row_checksum = compute_preview_batch_checksum(
        batch_payload={"dummy": "payload"},
        cell_payloads=(payload,),
    )[:64]
    # force a deterministic checksum-like 64-hex value for the row. We only use
    # it for projection readback in this module.
    row_checksum = checksum(
        {
            "row_checksum": payload,
            "cell_id": cell_id,
        }
    )

    cell = PreviewCellModel(
        id=cell_id,
        preview_batch_id=batch_id,
        formula_rule_identity=rule_identity,
        inventory_cell_id=inventory_cell_id,
        formula_shape_id=formula_shape_id,
        translation_status=status.value,
        reason_code=reason.value,
        translation_fingerprint=translation_fingerprint,
        target_fragment_json=dict(outcome.output_payload),
        binding_manifest_checksum=_manifest_checksum(),
        fixture_registry_evidence_json={
            "formula_translation_result_id": result_id,
            "registry_version": registry_version,
            "registry_checksum": registry_checksum,
            "registry_entry": payload["fixture_registry_evidence"]["registry_entry"],
            "fixture_evidence": {"formula": formula},
        },
        formula_inventory_evidence_json={"formula_text": formula},
        translator_version=translator_version,
        translator_version_diff_json=None,
        registry_version=registry_version,
        registry_checksum=registry_checksum,
        blocking_operationally_active=blocking_operationally_active,
        report_row_checksum=row_checksum,
    )
    if status is FormulaTranslationStatus.REVIEW_REQUIRED:
        cell.review_required_json = {
            "required": True,
            "reason": reason.value,
            "evidence": {"formula": formula},
        }
    if status is FormulaTranslationStatus.QUARANTINED:
        cell.quarantine_reason_json = {
            "required": True,
            "reason": reason.value,
            "evidence": {"formula": formula},
        }
    session.add(cell)
    return cell


def _create_batch(
    session,
    *,
    batch_id: str,
    cells: tuple[PreviewCellModel, ...],
    translator_version: str = FORMULA_TRANSLATOR_VERSION,
    registry_version: str = FORMULA_SHAPE_REGISTRY_VERSION,
    registry_checksum: str = FORMULA_SHAPE_REGISTRY_CHECKSUM,
    report_checksum: str | None = None,
) -> PreviewBatchModel:
    translated = sum(1 for cell in cells if cell.translation_status == FormulaTranslationStatus.TRANSLATED.value)
    review_required_count = sum(
        1 for cell in cells if cell.translation_status == FormulaTranslationStatus.REVIEW_REQUIRED.value
    )
    unsupported = sum(1 for cell in cells if cell.translation_status == FormulaTranslationStatus.UNSUPPORTED.value)
    quarantined = sum(
        1 for cell in cells if cell.translation_status == FormulaTranslationStatus.QUARANTINED.value
    )
    block_count = sum(1 for cell in cells if cell.blocking_operationally_active)
    batch_payload = {
        "counts": {
            "translated": translated,
            "review_required": review_required_count,
            "unsupported": unsupported,
            "quarantined": quarantined,
        },
        "blocking_operationally_active": block_count,
        "inventory_checksum": _compute_batch_inventory_checksum(batch_id=batch_id),
        "input_checksum": _compute_batch_input_checksum(
            rows=tuple(cell.inventory_cell_id for cell in cells),
        ),
    }
    if report_checksum is None:
        row_payloads = []
        for cell in cells:
            row_payloads.append(
                {
                    "inventory_cell_id": cell.inventory_cell_id,
                    "formula_rule_identity": cell.formula_rule_identity,
                    "formula_shape_id": cell.formula_shape_id,
                    "translation_status": cell.translation_status,
                    "reason_code": cell.reason_code,
                    "translation_fingerprint": cell.translation_fingerprint,
                    "binding_manifest_checksum": cell.binding_manifest_checksum,
                    "target_fragment": cell.target_fragment_json,
                    "review_required": getattr(cell, "review_required_json", None),
                    "quarantine_reason": getattr(cell, "quarantine_reason_json", None),
                    "fixture_registry_evidence": cell.fixture_registry_evidence_json,
                    "translator_version": cell.translator_version,
                    "translator_version_diff": cell.translator_version_diff_json,
                    "blocking_operationally_active": cell.blocking_operationally_active,
                    "formula_inventory_evidence": cell.formula_inventory_evidence_json,
                    "binding_manifest": {
                        "source_roles": _manifest(),
                        "manual_roles": (),
                        "derived_keys": (),
                    },
                    "registry_version": cell.registry_version,
                    "registry_checksum": cell.registry_checksum,
                }
            )
        report_checksum = compute_preview_batch_checksum(
            batch_payload={
                "translator_version": translator_version,
                "registry_version": registry_version,
                "registry_checksum": registry_checksum,
                "counts": batch_payload["counts"],
                "blocking_operationally_active": block_count,
                "inventory_checksum": batch_payload["inventory_checksum"],
                "input_checksum": batch_payload["input_checksum"],
            },
            cell_payloads=tuple(row_payloads),
        )

    batch = PreviewBatchModel(
        id=batch_id,
        state=PreviewBatchState.COMPLETED.value,
        translator_version=translator_version,
        registry_version=registry_version,
        registry_checksum=registry_checksum,
        inventory_checksum=batch_payload["inventory_checksum"],
        input_checksum=batch_payload["input_checksum"],
        report_checksum=report_checksum,
        translated_count=translated,
        review_required_count=review_required_count,
        unsupported_count=unsupported,
        quarantined_count=quarantined,
        blocking_operationally_active_count=block_count,
    )
    session.add(batch)
    return batch


def _make_contract(session, shape_id: str = "A1") -> ShapeComparisonContract:
    contract_id = f"contract-{shape_id}"
    registry = get_registry_entry(shape_id)
    contract = ShapeComparisonContract(
        id=contract_id,
        shape_id=shape_id,
        contract_revision="rev-1",
        contract_version="v1",
        contract_checksum=f"{shape_id}-contract-checksum",
        formula_inventory_checksum="inventory-checksum",
        target_kind="price_target" if registry.is_price_target else "non_price",
        stable_rule_identity_json={"shape_id": shape_id},
        required_input_identity_json={},
        required_output_lanes_json=[],
        canonical_context_json={"translator_version": FORMULA_TRANSLATOR_VERSION},
        equality_rule_json={},
        required_trace_components_json=[],
        acceptance_effect="may_count",
        classification_mapping_json={},
        is_current=True,
    )
    session.add(contract)
    session.flush()
    return contract


def test_projection_marks_eligible_translated_row_as_countable_and_pins_all_evidence(db):
    session, user = db
    _make_contract(session, shape_id="A1")
    _create_translation_result(
        session=session,
        rule_identity="rule:A1",
        status=FormulaTranslationStatus.TRANSLATED,
        reason=FormulaTranslationReason.MATCHED_SUPPORTED,
        formula_shape_id="A1",
        translator_version=FORMULA_TRANSLATOR_VERSION,
        registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
        registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
        translation_fingerprint=compute_translation_result_checksum(
            formula_rule_identity="rule:A1",
            translator_version=FORMULA_TRANSLATOR_VERSION,
            formula_shape_id="A1",
            translation_status=FormulaTranslationStatus.TRANSLATED.value,
            reason_code=FormulaTranslationReason.MATCHED_SUPPORTED.value,
            registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
            registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
            translation_input_payload={"formula": "=A1"},
            translation_output_payload={"x": 1},
            package_fingerprint=None,
            reviewed_by=None,
        ),
        translation_output_payload={"x": 1},
        translation_input_payload={"formula": "=A1"},
    )
    cell = _add_cell(
        session,
        batch_id="batch-eligible",
        inventory_cell_id="i1",
        rule_identity="rule:A1",
        formula="=IF(RC[-2]=\"\",\"\",IFERROR(FLOOR((RC[-2]*(1+R2C6/100),1000),\"\"))",
        status=FormulaTranslationStatus.TRANSLATED,
    )
    _create_batch(session, batch_id="batch-eligible", cells=(cell,))
    session.commit()

    projection = FormulaMigrationPreviewProjectionService(session).project(batch_id="batch-eligible")
    assert len(projection.rows) == 1
    row = projection.rows[0]
    assert row.may_count is True
    assert row.blocked is False
    assert row.review_required is False
    assert row.non_price_evidence_only is False
    assert row.fail_reasons == ()
    assert row.formula_translation_result_id == "result-rule:A1"
    assert row.translator_version == FORMULA_TRANSLATOR_VERSION
    assert row.registry_version == FORMULA_SHAPE_REGISTRY_VERSION
    assert row.registry_checksum == FORMULA_SHAPE_REGISTRY_CHECKSUM
    assert row.shape_comparison_contract_id == "contract-A1"
    assert row.shape_comparison_contract_revision == "rev-1"
    assert row.shape_comparison_contract_revision_checksum == "A1-contract-checksum"


def test_review_required_without_approval_does_not_count(db):
    session, _user = db
    _make_contract(session, shape_id="A1")
    _create_translation_result(
        session=session,
        rule_identity="rule:review",
        status=FormulaTranslationStatus.REVIEW_REQUIRED,
        reason=FormulaTranslationReason.REVIEW_REQUIRED,
        formula_shape_id="A1",
        translator_version=FORMULA_TRANSLATOR_VERSION,
        registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
        registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
        translation_fingerprint=compute_translation_result_checksum(
            formula_rule_identity="rule:review",
            translator_version=FORMULA_TRANSLATOR_VERSION,
            formula_shape_id="A1",
            translation_status=FormulaTranslationStatus.REVIEW_REQUIRED.value,
            reason_code=FormulaTranslationReason.REVIEW_REQUIRED.value,
            registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
            registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
            translation_input_payload={"formula": "=RC[1]"},
            translation_output_payload={},
            package_fingerprint=None,
            reviewed_by=None,
        ),
        translation_output_payload={},
        translation_input_payload={"formula": "=RC[1]"},
    )
    cell = _add_cell(
        session,
        batch_id="batch-review-missing",
        inventory_cell_id="i-review",
        rule_identity="rule:review",
        formula="=RC[1]",
        status=FormulaTranslationStatus.REVIEW_REQUIRED,
    )
    _create_batch(session, batch_id="batch-review-missing", cells=(cell,))
    session.commit()
    projection = FormulaMigrationPreviewProjectionService(session).project(batch_id="batch-review-missing")
    row = projection.rows[0]
    assert row.may_count is False
    assert row.review_required is True
    assert row.blocked is True
    assert FormulaMigrationProjectionReason.REVIEW_REQUIRED_APPROVAL_MISSING.value in row.fail_reasons


def test_review_required_with_approved_decision_remains_traceable_and_countable(db):
    session, user = db
    _make_contract(session, shape_id="A1")
    _create_translation_result(
        session=session,
        rule_identity="rule:review-approve",
        status=FormulaTranslationStatus.REVIEW_REQUIRED,
        reason=FormulaTranslationReason.REVIEW_REQUIRED,
        formula_shape_id="A1",
        translator_version=FORMULA_TRANSLATOR_VERSION,
        registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
        registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
        translation_fingerprint=compute_translation_result_checksum(
            formula_rule_identity="rule:review-approve",
            translator_version=FORMULA_TRANSLATOR_VERSION,
            formula_shape_id="A1",
            translation_status=FormulaTranslationStatus.REVIEW_REQUIRED.value,
            reason_code=FormulaTranslationReason.REVIEW_REQUIRED.value,
            registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
            registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
            translation_input_payload={"formula": "=RC[1]"},
            translation_output_payload={},
            package_fingerprint=None,
            reviewed_by=None,
        ),
        translation_output_payload={},
        translation_input_payload={"formula": "=RC[1]"},
    )
    cell = _add_cell(
        session,
        batch_id="batch-review-approved",
        inventory_cell_id="i-review-approved",
        rule_identity="rule:review-approve",
        formula="=RC[1]",
        status=FormulaTranslationStatus.REVIEW_REQUIRED,
    )
    session.add(
        FormulaMigrationReviewDecision(
            id=str(uuid.uuid4()),
            preview_cell_id=cell.id,
            actor_name="reviewer",
            actor_user_id=user.id,
            action=FormulaMigrationReviewAction.APPROVED.value,
            reason="ok",
            evidence_json={},
        )
    )
    _create_batch(session, batch_id="batch-review-approved", cells=(cell,))
    session.commit()

    row = FormulaMigrationPreviewProjectionService(session).project(batch_id="batch-review-approved").rows[0]
    assert row.review_required is True
    assert row.blocked is False
    assert row.may_count is True
    assert row.review_decision_id is not None
    assert row.fail_reasons == ()


def test_quarantined_operationally_active_block_is_visible_not_counted(db):
    session, _user = db
    _make_contract(session, shape_id="A1")
    _create_translation_result(
        session=session,
        rule_identity="rule:quarantine",
        status=FormulaTranslationStatus.QUARANTINED,
        reason=FormulaTranslationReason.BROKEN_REFERENCE,
        formula_shape_id="A1",
        translator_version=FORMULA_TRANSLATOR_VERSION,
        registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
        registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
        translation_fingerprint=compute_translation_result_checksum(
            formula_rule_identity="rule:quarantine",
            translator_version=FORMULA_TRANSLATOR_VERSION,
            formula_shape_id="A1",
            translation_status=FormulaTranslationStatus.QUARANTINED.value,
            reason_code=FormulaTranslationReason.BROKEN_REFERENCE.value,
            registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
            registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
            translation_input_payload={"formula": "=NOW()"},
            translation_output_payload={},
            package_fingerprint=None,
            reviewed_by=None,
        ),
        translation_output_payload={},
        translation_input_payload={"formula": "=NOW()"},
    )
    cell = _add_cell(
        session,
        batch_id="batch-ops",
        inventory_cell_id="i-quarantine",
        rule_identity="rule:quarantine",
        formula="=NOW()",
        status=FormulaTranslationStatus.QUARANTINED,
        blocking_operationally_active=True,
    )
    _create_batch(session, batch_id="batch-ops", cells=(cell,))
    session.commit()
    row = FormulaMigrationPreviewProjectionService(session).project(batch_id="batch-ops").rows[0]
    assert row.blocked is True
    assert row.may_count is False


def test_inactive_historical_quarantine_result_does_not_shadow_new_translation(db):
    session, _user = db
    _make_contract(session, shape_id="A1")
    _create_translation_result(
        session=session,
        rule_identity="rule:historical",
        status=FormulaTranslationStatus.QUARANTINED,
        reason=FormulaTranslationReason.BROKEN_REFERENCE,
        formula_shape_id="A13",
        translator_version="old-translator",
        result_id="result-rule:historical:old",
        registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
        registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
        translation_fingerprint="old-hist-fp",
        translation_output_payload={},
        translation_input_payload={"formula": "=BAD"},
    )
    _create_translation_result(
        session=session,
        rule_identity="rule:historical",
        status=FormulaTranslationStatus.TRANSLATED,
        reason=FormulaTranslationReason.MATCHED_SUPPORTED,
        formula_shape_id="A1",
        translator_version=FORMULA_TRANSLATOR_VERSION,
        registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
        registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
        translation_fingerprint=compute_translation_result_checksum(
            formula_rule_identity="rule:historical",
            translator_version=FORMULA_TRANSLATOR_VERSION,
            formula_shape_id="A1",
            translation_status=FormulaTranslationStatus.TRANSLATED.value,
            reason_code=FormulaTranslationReason.MATCHED_SUPPORTED.value,
            registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
            registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
            translation_input_payload={"formula": "=A1"},
            translation_output_payload={},
            package_fingerprint=None,
            reviewed_by=None,
        ),
        translation_output_payload={},
        translation_input_payload={"formula": "=A1"},
    )
    cell = _add_cell(
        session,
        batch_id="batch-history",
        inventory_cell_id="i-history",
        rule_identity="rule:historical",
        formula="=A1",
        status=FormulaTranslationStatus.TRANSLATED,
    )
    _create_batch(session, batch_id="batch-history", cells=(cell,))
    session.commit()
    row = FormulaMigrationPreviewProjectionService(session).project(batch_id="batch-history").rows[0]
    assert row.may_count is True
    assert row.formula_translation_result_id == "result-rule:historical"


def test_unsupported_non_price_evidence_remains_evidence_only(db):
    session, _user = db
    _create_translation_result(
        session=session,
        rule_identity="rule:unsupported",
        status=FormulaTranslationStatus.UNSUPPORTED,
        reason=FormulaTranslationReason.SHAPE_UNSUPPORTED,
        formula_shape_id="A7",
        translator_version=FORMULA_TRANSLATOR_VERSION,
        registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
        registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
        translation_fingerprint=compute_translation_result_checksum(
            formula_rule_identity="rule:unsupported",
            translator_version=FORMULA_TRANSLATOR_VERSION,
            formula_shape_id="A7",
            translation_status=FormulaTranslationStatus.UNSUPPORTED.value,
            reason_code=FormulaTranslationReason.SHAPE_UNSUPPORTED.value,
            registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
            registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
            translation_input_payload={"formula": "=IF(RC[-1]/RC[-2],\"x\")"},
            translation_output_payload={},
            package_fingerprint=None,
            reviewed_by=None,
        ),
        translation_output_payload={},
        translation_input_payload={"formula": "=IF(RC[-1]/RC[-2],\"x\")"},
    )
    cell = _add_cell(
        session,
        batch_id="batch-unsupported",
        inventory_cell_id="i-unsupported",
        rule_identity="rule:unsupported",
        formula="=IF(RC[-1]/RC[-2],\"x\")",
        status=FormulaTranslationStatus.UNSUPPORTED,
    )
    _create_batch(session, batch_id="batch-unsupported", cells=(cell,))
    session.commit()
    row = FormulaMigrationPreviewProjectionService(session).project(batch_id="batch-unsupported").rows[0]
    assert row.shape_is_price_target is False
    assert row.non_price_evidence_only is True
    assert row.may_count is False
    assert row.blocked is False


def test_projection_fingerprint_mismatch_fails_closed(db):
    session, _user = db
    _create_translation_result(
        session=session,
        rule_identity="rule:fpmismatch",
        status=FormulaTranslationStatus.TRANSLATED,
        reason=FormulaTranslationReason.MATCHED_SUPPORTED,
        formula_shape_id="A1",
        translator_version=FORMULA_TRANSLATOR_VERSION,
        registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
        registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
        translation_fingerprint="good-fingerprint",
        translation_output_payload={},
        translation_input_payload={"formula": "=A1"},
    )
    cell = _add_cell(
        session,
        batch_id="batch-fpmismatch",
        inventory_cell_id="i-fp",
        rule_identity="rule:fpmismatch",
        formula="=A1",
        status=FormulaTranslationStatus.TRANSLATED,
    )
    # intentionally diverge translated fingerprint from stable row evidence
    cell.translation_fingerprint = "f" * 64
    _create_batch(session, batch_id="batch-fpmismatch", cells=(cell,))
    session.commit()
    row = FormulaMigrationPreviewProjectionService(session).project(batch_id="batch-fpmismatch").rows[0]
    assert FormulaMigrationProjectionReason.FINGERPRINT_MISMATCH.value in row.fail_reasons
    assert row.may_count is False


def test_projection_registry_version_mismatch_fails_closed(db):
    session, _user = db
    _make_contract(session, shape_id="A1")
    _create_translation_result(
        session=session,
        rule_identity="rule:regver",
        status=FormulaTranslationStatus.TRANSLATED,
        reason=FormulaTranslationReason.MATCHED_SUPPORTED,
        formula_shape_id="A1",
        translator_version=FORMULA_TRANSLATOR_VERSION,
        registry_version="other-registry",
        registry_checksum="0" * 64,
        translation_fingerprint=compute_translation_result_checksum(
            formula_rule_identity="rule:regver",
            translator_version=FORMULA_TRANSLATOR_VERSION,
            formula_shape_id="A1",
            translation_status=FormulaTranslationStatus.TRANSLATED.value,
            reason_code=FormulaTranslationReason.MATCHED_SUPPORTED.value,
            registry_version="other-registry",
            registry_checksum="0" * 64,
            translation_input_payload={"formula": "=A1"},
            translation_output_payload={},
            package_fingerprint=None,
            reviewed_by=None,
        ),
        translation_output_payload={},
        translation_input_payload={"formula": "=A1"},
    )
    cell = _add_cell(
        session,
        batch_id="batch-regver",
        inventory_cell_id="i-regver",
        rule_identity="rule:regver",
        formula="=A1",
        status=FormulaTranslationStatus.TRANSLATED,
        registry_version="new-registry",
        registry_checksum="f" * 64,
    )
    _create_batch(session, batch_id="batch-regver", cells=(cell,), registry_version="new-registry", registry_checksum="f" * 64)
    session.commit()
    row = FormulaMigrationPreviewProjectionService(session).project(batch_id="batch-regver").rows[0]
    assert FormulaMigrationProjectionReason.REGISTRY_VERSION_MISMATCH.value in row.fail_reasons
    assert FormulaMigrationProjectionReason.REGISTRY_CHECKSUM_MISMATCH.value in row.fail_reasons


def test_projection_batch_checksum_mismatch_fails_closed(db):
    session, _user = db
    _create_translation_result(
        session=session,
        rule_identity="rule:report",
        status=FormulaTranslationStatus.TRANSLATED,
        reason=FormulaTranslationReason.MATCHED_SUPPORTED,
        formula_shape_id="A1",
        translator_version=FORMULA_TRANSLATOR_VERSION,
        registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
        registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
        translation_fingerprint=compute_translation_result_checksum(
            formula_rule_identity="rule:report",
            translator_version=FORMULA_TRANSLATOR_VERSION,
            formula_shape_id="A1",
            translation_status=FormulaTranslationStatus.TRANSLATED.value,
            reason_code=FormulaTranslationReason.MATCHED_SUPPORTED.value,
            registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
            registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
            translation_input_payload={"formula": "=A1"},
            translation_output_payload={},
            package_fingerprint=None,
            reviewed_by=None,
        ),
        translation_output_payload={},
        translation_input_payload={"formula": "=A1"},
    )
    cell = _add_cell(
        session,
        batch_id="batch-report",
        inventory_cell_id="i-report",
        rule_identity="rule:report",
        formula="=A1",
        status=FormulaTranslationStatus.TRANSLATED,
    )
    _create_batch(
        session,
        batch_id="batch-report",
        cells=(cell,),
        report_checksum="not-a-checksum",
    )
    session.commit()
    row = FormulaMigrationPreviewProjectionService(session).project(batch_id="batch-report").rows[0]
    assert FormulaMigrationProjectionReason.PREVIEW_REPORT_CHECKSUM_MISMATCH.value in row.fail_reasons
    assert row.may_count is False


def test_projection_binding_manifest_checksum_mismatch_fails_closed(db):
    session, _user = db
    _create_translation_result(
        session=session,
        rule_identity="rule:manifest",
        status=FormulaTranslationStatus.TRANSLATED,
        reason=FormulaTranslationReason.MATCHED_SUPPORTED,
        formula_shape_id="A1",
        translator_version=FORMULA_TRANSLATOR_VERSION,
        registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
        registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
        translation_fingerprint=compute_translation_result_checksum(
            formula_rule_identity="rule:manifest",
            translator_version=FORMULA_TRANSLATOR_VERSION,
            formula_shape_id="A1",
            translation_status=FormulaTranslationStatus.TRANSLATED.value,
            reason_code=FormulaTranslationReason.MATCHED_SUPPORTED.value,
            registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
            registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
            translation_input_payload={"formula": "=A1"},
            translation_output_payload={},
            package_fingerprint=None,
            reviewed_by=None,
        ),
        translation_output_payload={},
        translation_input_payload={"formula": "=A1"},
    )
    cell = _add_cell(
        session,
        batch_id="batch-manifest",
        inventory_cell_id="i-manifest",
        rule_identity="rule:manifest",
        formula="=A1",
        status=FormulaTranslationStatus.TRANSLATED,
    )
    cell.binding_manifest_checksum = "not-a-checksum"
    _create_batch(session, batch_id="batch-manifest", cells=(cell,))
    session.commit()
    row = FormulaMigrationPreviewProjectionService(session).project(batch_id="batch-manifest").rows[0]
    assert FormulaMigrationProjectionReason.BINDING_MANIFEST_CHECKSUM_MISSING.value in row.fail_reasons


def test_projection_missing_comparison_contract_fails_closed(db):
    session, _user = db
    _create_translation_result(
        session=session,
        rule_identity="rule:nocontract",
        status=FormulaTranslationStatus.TRANSLATED,
        reason=FormulaTranslationReason.MATCHED_SUPPORTED,
        formula_shape_id="A1",
        translator_version=FORMULA_TRANSLATOR_VERSION,
        registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
        registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
        translation_fingerprint=compute_translation_result_checksum(
            formula_rule_identity="rule:nocontract",
            translator_version=FORMULA_TRANSLATOR_VERSION,
            formula_shape_id="A1",
            translation_status=FormulaTranslationStatus.TRANSLATED.value,
            reason_code=FormulaTranslationReason.MATCHED_SUPPORTED.value,
            registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
            registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
            translation_input_payload={"formula": "=A1"},
            translation_output_payload={},
            package_fingerprint=None,
            reviewed_by=None,
        ),
        translation_output_payload={},
        translation_input_payload={"formula": "=A1"},
    )
    cell = _add_cell(
        session,
        batch_id="batch-nocontract",
        inventory_cell_id="i-nocontract",
        rule_identity="rule:nocontract",
        formula="=A1",
        status=FormulaTranslationStatus.TRANSLATED,
    )
    _create_batch(session, batch_id="batch-nocontract", cells=(cell,))
    session.commit()
    row = FormulaMigrationPreviewProjectionService(session).project(batch_id="batch-nocontract").rows[0]
    assert FormulaMigrationProjectionReason.COMPARISON_CONTRACT_MISSING.value in row.fail_reasons
    assert row.may_count is False


def test_projection_translator_version_mismatch_fails_closed(db):
    session, _user = db
    _create_translation_result(
        session=session,
        rule_identity="rule:traversion",
        status=FormulaTranslationStatus.TRANSLATED,
        reason=FormulaTranslationReason.MATCHED_SUPPORTED,
        formula_shape_id="A1",
        translator_version="old-translator",
        registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
        registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
        translation_fingerprint=compute_translation_result_checksum(
            formula_rule_identity="rule:traversion",
            translator_version="old-translator",
            formula_shape_id="A1",
            translation_status=FormulaTranslationStatus.TRANSLATED.value,
            reason_code=FormulaTranslationReason.MATCHED_SUPPORTED.value,
            registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
            registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
            translation_input_payload={"formula": "=A1"},
            translation_output_payload={},
            package_fingerprint=None,
            reviewed_by=None,
        ),
        translation_output_payload={},
        translation_input_payload={"formula": "=A1"},
    )
    cell = _add_cell(
        session,
        batch_id="batch-trvers",
        inventory_cell_id="i-traversion",
        rule_identity="rule:traversion",
        formula="=A1",
        status=FormulaTranslationStatus.TRANSLATED,
        translator_version="new-translator",
    )
    _create_batch(session, batch_id="batch-trvers", cells=(cell,), translator_version="new-translator")
    session.commit()
    row = FormulaMigrationPreviewProjectionService(session).project(batch_id="batch-trvers").rows[0]
    assert FormulaMigrationProjectionReason.TRANSLATOR_VERSION_MISMATCH.value in row.fail_reasons
    assert row.may_count is False


def test_projection_missing_translation_result_fails_closed(db):
    session, _user = db
    cell = _add_cell(
        session,
        batch_id="batch-missing-result",
        inventory_cell_id="i-miss",
        rule_identity="rule:miss-result",
        formula="=A1",
        status=FormulaTranslationStatus.TRANSLATED,
    )
    cell.fixture_registry_evidence_json["formula_translation_result_id"] = None
    _create_batch(session, batch_id="batch-missing-result", cells=(cell,))
    session.commit()
    row = FormulaMigrationPreviewProjectionService(session).project(batch_id="batch-missing-result").rows[0]
    assert FormulaMigrationProjectionReason.TRANSLATION_RESULT_MISSING.value in row.fail_reasons
    assert row.may_count is False


def test_projection_deterministic_checksum_is_stable(db):
    session, _user = db
    _make_contract(session, shape_id="A1")
    _create_translation_result(
        session=session,
        rule_identity="rule:d1",
        status=FormulaTranslationStatus.TRANSLATED,
        reason=FormulaTranslationReason.MATCHED_SUPPORTED,
        formula_shape_id="A1",
        translator_version=FORMULA_TRANSLATOR_VERSION,
        registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
        registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
        translation_fingerprint=compute_translation_result_checksum(
            formula_rule_identity="rule:d1",
            translator_version=FORMULA_TRANSLATOR_VERSION,
            formula_shape_id="A1",
            translation_status=FormulaTranslationStatus.TRANSLATED.value,
            reason_code=FormulaTranslationReason.MATCHED_SUPPORTED.value,
            registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
            registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
            translation_input_payload={"formula": "=A1"},
            translation_output_payload={},
            package_fingerprint=None,
            reviewed_by=None,
        ),
        translation_output_payload={},
        translation_input_payload={"formula": "=A1"},
    )
    first = _add_cell(
        session,
        batch_id="batch-deterministic",
        inventory_cell_id="i2",
        rule_identity="rule:d2",
        formula="=A1",
        status=FormulaTranslationStatus.TRANSLATED,
    )
    second = _add_cell(
        session,
        batch_id="batch-deterministic",
        inventory_cell_id="i1",
        rule_identity="rule:d1",
        formula="=A1",
        status=FormulaTranslationStatus.TRANSLATED,
    )
    _create_batch(session, batch_id="batch-deterministic", cells=(first, second))
    session.commit()

    service = FormulaMigrationPreviewProjectionService(session)
    one = service.project(batch_id="batch-deterministic")
    two = service.project(batch_id="batch-deterministic")
    assert one.projection_checksum == two.projection_checksum


def test_projection_no_evidence_mutation_in_preview_translation_fep_and_shadow_tables(db):
    session, user = db
    _create_translation_result(
        session=session,
        rule_identity="rule:nomutate",
        status=FormulaTranslationStatus.TRANSLATED,
        reason=FormulaTranslationReason.MATCHED_SUPPORTED,
        formula_shape_id="A1",
        translator_version=FORMULA_TRANSLATOR_VERSION,
        registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
        registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
        translation_fingerprint=compute_translation_result_checksum(
            formula_rule_identity="rule:nomutate",
            translator_version=FORMULA_TRANSLATOR_VERSION,
            formula_shape_id="A1",
            translation_status=FormulaTranslationStatus.TRANSLATED.value,
            reason_code=FormulaTranslationReason.MATCHED_SUPPORTED.value,
            registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
            registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
            translation_input_payload={"formula": "=A1"},
            translation_output_payload={},
            package_fingerprint=None,
            reviewed_by=None,
        ),
        translation_output_payload={},
        translation_input_payload={"formula": "=A1"},
    )
    _make_contract(session, shape_id="A1")
    session.add(
        ShapeComparisonContract(
            id="contract-existing",
            shape_id="A1",
            contract_revision="rev-keep",
            contract_version="v1",
            contract_checksum="existing",
            formula_inventory_checksum="x",
            target_kind="price_target",
            stable_rule_identity_json={},
            required_input_identity_json={},
            required_output_lanes_json=[],
            canonical_context_json={},
            equality_rule_json={},
            required_trace_components_json=[],
            acceptance_effect="may_count",
            classification_mapping_json={},
            is_current=True,
        )
    )
    frozen = FrozenEvaluationPackage(
        id="fep-no-mut",
        channel_id="channel-no-mut",
        product_ref="sku",
        workspace_pricing_evaluated_at=datetime(2026, 1, 1),
        formula_shape_id="A1",
        translator_version=FORMULA_TRANSLATOR_VERSION,
        currency_unit_registry_version="unit-v1",
        arithmetic_version="arith-v1",
        dependency_fingerprint="dep",
        checksum="fepchecksum",
    )
    session.add(frozen)
    comparison = ShadowValidationComparison(
        id="shadow-no-mut",
        channel_id="ch-no-mut",
        validation_window_id="window-no-mut",
        frozen_evaluation_package_id="fep-no-mut",
        legacy_formula_capture_id="capture-no-mut",
        shape_id="A1",
        comparison_contract_id="contract-existing",
        stable_rule_identity="rule:A1",
        comparison_contract_revision="rev-keep",
        comparison_contract_revision_checksum="existing",
        comparison_algorithm_version="alg-v1",
        comparison_identity_checksum="cmp-id",
        frozen_evaluation_package_checksum="fepchecksum",
        legacy_capture_checksum="legacychecksum",
        translator_version=FORMULA_TRANSLATOR_VERSION,
        required_output_lanes="candidate",
        confidence="verified",
        primary_classification="accepted_expected_rounding",
        reason_code=None,
        secondary_classifications_json=[],
        legacy_vs_package_context_json={},
        legacy_output_json={},
        package_output_json={},
        findings_json=[],
    )
    session.add_all((frozen, comparison))

    tx_before = session.query(FormulaTranslationResult).count()
    preview_batch_before = session.query(PreviewBatchModel).count()
    preview_cell_before = session.query(PreviewCellModel).count()
    review_before = session.query(FormulaMigrationReviewDecision).count()
    fep_before = session.query(FrozenEvaluationPackage).count()
    contract_before = session.query(ShapeComparisonContract).count()
    comp_before = session.query(ShadowValidationComparison).count()
    authority_before = session.query(ChannelPricingAuthorityEvent).count()
    head_before = session.query(ChannelPricingAuthorityHead).count()
    write_reject_before = session.query(PricingAuthorityWriteRejection).count()
    quarantine_before = session.query(FormulaTranslationQuarantine).count()

    cell = _add_cell(
        session,
        batch_id="batch-nomutate",
        inventory_cell_id="i-nomutate",
        rule_identity="rule:nomutate",
        formula="=A1",
        status=FormulaTranslationStatus.TRANSLATED,
    )
    _create_batch(session, batch_id="batch-nomutate", cells=(cell,))
    session.commit()
    FormulaMigrationPreviewProjectionService(session).project(batch_id="batch-nomutate")

    assert session.query(FormulaTranslationResult).count() == tx_before
    assert session.query(PreviewBatchModel).count() == preview_batch_before + 1
    assert session.query(PreviewCellModel).count() == preview_cell_before + 1
    assert session.query(FormulaMigrationReviewDecision).count() == review_before
    assert session.query(ShapeComparisonContract).count() == contract_before
    assert session.query(ShadowValidationComparison).count() == comp_before
    assert session.query(FrozenEvaluationPackage).count() == fep_before
    assert session.query(ChannelPricingAuthorityEvent).count() == authority_before
    assert session.query(ChannelPricingAuthorityHead).count() == head_before
    assert session.query(PricingAuthorityWriteRejection).count() == write_reject_before
    assert session.query(FormulaTranslationQuarantine).count() == quarantine_before
