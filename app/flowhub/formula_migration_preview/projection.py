"""Projection bridge from immutable D6 preview artifacts to D7 evidence contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.flowhub.formula_migration_preview.contracts import (
    FormulaMigrationPreviewEvidenceProjection,
    FormulaMigrationPreviewProjection,
    FormulaMigrationProjectionReason,
)
from app.flowhub.formula_migration_preview.models import (
    FormulaMigrationPreviewBatch as PreviewBatchModel,
    FormulaMigrationPreviewCell as PreviewCellModel,
    FormulaMigrationReviewDecision,
)
from app.flowhub.formula_translator.contracts import (
    FormulaTranslationReason,
    FormulaTranslationStatus,
)
from app.flowhub.formula_translator.models import FormulaTranslationResult
from app.flowhub.formula_translator.registry import get_registry_entry
from app.flowhub.shadow_validation.models import ShapeComparisonContract
from app.flowhub.unified_workspace.domain import checksum, stable_json


def _looks_like_checksum(value: object) -> bool:
    if not isinstance(value, str):
        return False
    if len(value) != 64:
        return False
    return all(char in "0123456789abcdefABCDEF" for char in value)


def compute_projection_row_checksum(*, payload: Mapping[str, object]) -> str:
    return checksum(
        {
            "projection_row": stable_json(dict(sorted(payload.items()))),
        }
    )


def _lookup_shape_contract(
    session: Session, *, shape_id: str
) -> ShapeComparisonContract | None:
    statement = (
        select(ShapeComparisonContract)
        .where(ShapeComparisonContract.shape_id == shape_id)
        .where(ShapeComparisonContract.is_current.is_(True))
        .order_by(ShapeComparisonContract.contract_revision.asc(), ShapeComparisonContract.id.asc())
        .limit(1)
    )
    return session.execute(statement).scalar_one_or_none()


@dataclass(frozen=True, slots=True)
class _CellProjectionDraft:
    preview_batch_id: str
    preview_cell_id: str
    inventory_cell_id: str
    formula_rule_identity: str
    formula_shape_id: str | None
    formula_translation_result_id: str
    translation_status: str
    reason_code: str
    translation_fingerprint: str
    translator_version: str
    registry_version: str
    registry_checksum: str
    binding_manifest_checksum: str
    preview_batch_report_checksum: str
    preview_row_checksum: str
    shape_is_price_target: bool
    shape_comparison_contract_id: str | None
    shape_comparison_contract_revision: str | None
    shape_comparison_contract_revision_checksum: str | None
    review_decision_id: str | None
    may_count: bool
    review_required: bool
    blocked: bool
    non_price_evidence_only: bool
    fail_reasons: tuple[str, ...]


class FormulaMigrationPreviewProjectionService:
    """Build read-only D7 projection for Phase B/C integration."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def project(self, *, batch_id: str) -> FormulaMigrationPreviewProjection:
        batch = self.db.get(PreviewBatchModel, batch_id)
        if batch is None:
            raise ValueError(FormulaMigrationProjectionReason.PREVIEW_BATCH_MISSING.value)

        cells = (
            self.db.query(PreviewCellModel)
            .where(PreviewCellModel.preview_batch_id == batch_id)
            .order_by(
                PreviewCellModel.inventory_cell_id.asc(),
                PreviewCellModel.id.asc(),
            )
            .all()
        )

        rows = [
            self._project_cell(batch=batch, cell=cell)
            for cell in cells
        ]
        ordered_rows = sorted(rows, key=lambda row: (row.inventory_cell_id, row.preview_cell_id))

        projected_rows = tuple(
            FormulaMigrationPreviewEvidenceProjection(
                preview_batch_id=row.preview_batch_id,
                preview_cell_id=row.preview_cell_id,
                inventory_cell_id=row.inventory_cell_id,
                formula_rule_identity=row.formula_rule_identity,
                formula_shape_id=row.formula_shape_id,
                formula_translation_result_id=row.formula_translation_result_id,
                translation_status=row.translation_status,
                reason_code=row.reason_code,
                translation_fingerprint=row.translation_fingerprint,
                translator_version=row.translator_version,
                registry_version=row.registry_version,
                registry_checksum=row.registry_checksum,
                binding_manifest_checksum=row.binding_manifest_checksum,
                preview_batch_report_checksum=row.preview_batch_report_checksum,
                preview_row_checksum=row.preview_row_checksum,
                shape_is_price_target=row.shape_is_price_target,
                shape_comparison_contract_id=row.shape_comparison_contract_id,
                shape_comparison_contract_revision=row.shape_comparison_contract_revision,
                shape_comparison_contract_revision_checksum=row.shape_comparison_contract_revision_checksum,
                review_decision_id=row.review_decision_id,
                may_count=row.may_count,
                review_required=row.review_required,
                blocked=row.blocked,
                non_price_evidence_only=row.non_price_evidence_only,
                fail_reasons=row.fail_reasons,
                projection_row_checksum=compute_projection_row_checksum(
                    payload={
                        "cell_id": row.preview_cell_id,
                        "batch_id": row.preview_batch_id,
                        "inventory_cell_id": row.inventory_cell_id,
                        "formula_rule_identity": row.formula_rule_identity,
                        "formula_shape_id": row.formula_shape_id,
                        "translation_status": row.translation_status,
                        "reason_code": row.reason_code,
                        "translation_fingerprint": row.translation_fingerprint,
                        "translator_version": row.translator_version,
                        "registry_version": row.registry_version,
                        "registry_checksum": row.registry_checksum,
                        "binding_manifest_checksum": row.binding_manifest_checksum,
                        "preview_row_checksum": row.preview_row_checksum,
                        "preview_batch_report_checksum": row.preview_batch_report_checksum,
                        "shape_is_price_target": row.shape_is_price_target,
                        "comparison_contract_id": row.shape_comparison_contract_id,
                        "comparison_contract_revision": row.shape_comparison_contract_revision,
                        "comparison_contract_revision_checksum": row.shape_comparison_contract_revision_checksum,
                        "review_decision_id": row.review_decision_id,
                        "may_count": row.may_count,
                        "review_required": row.review_required,
                        "blocked": row.blocked,
                        "non_price_evidence_only": row.non_price_evidence_only,
                        "fail_reasons": row.fail_reasons,
                    }
                ),
            )
            for row in ordered_rows
        )

        projection_checksum = checksum(
            {
                "batch_id": batch.id,
                "batch_report_checksum": batch.report_checksum,
                "rows": tuple(row.projection_row_checksum for row in projected_rows),
            }
        )
        return FormulaMigrationPreviewProjection(
            batch_id=batch.id,
            batch_report_checksum=batch.report_checksum,
            rows=tuple(projected_rows),
            projection_checksum=projection_checksum,
        )

    def _project_cell(self, *, batch: PreviewBatchModel, cell: PreviewCellModel) -> _CellProjectionDraft:
        reasons: set[str] = set()
        if not _looks_like_checksum(batch.report_checksum):
            reasons.add(FormulaMigrationProjectionReason.PREVIEW_REPORT_CHECKSUM_MISMATCH.value)
        fixture_evidence = (
            cell.fixture_registry_evidence_json
            if isinstance(cell.fixture_registry_evidence_json, Mapping)
            else {}
        )
        if (
            isinstance(fixture_evidence.get("registry_version"), str)
            and fixture_evidence.get("registry_version") != cell.registry_version
        ):
            reasons.add(FormulaMigrationProjectionReason.STALE_OR_INCONSISTENT_RESULT.value)
        if (
            isinstance(fixture_evidence.get("registry_checksum"), str)
            and fixture_evidence.get("registry_checksum") != cell.registry_checksum
        ):
            reasons.add(FormulaMigrationProjectionReason.STALE_OR_INCONSISTENT_RESULT.value)
        if not _looks_like_checksum(cell.binding_manifest_checksum):
            reasons.add(FormulaMigrationProjectionReason.BINDING_MANIFEST_CHECKSUM_MISSING.value)
        if not _looks_like_checksum(cell.translation_fingerprint):
            reasons.add(FormulaMigrationProjectionReason.FINGERPRINT_MISMATCH.value)
        if not _looks_like_checksum(cell.registry_checksum):
            reasons.add(FormulaMigrationProjectionReason.REGISTRY_CHECKSUM_MISMATCH.value)
        if not _looks_like_checksum(cell.report_row_checksum):
            reasons.add(FormulaMigrationProjectionReason.PREVIEW_ROW_CHECKSUM_MISMATCH.value)

        if cell.registry_version != batch.registry_version:
            reasons.add(FormulaMigrationProjectionReason.REGISTRY_VERSION_MISMATCH.value)
        if cell.registry_checksum != batch.registry_checksum:
            reasons.add(FormulaMigrationProjectionReason.REGISTRY_CHECKSUM_MISMATCH.value)
        if cell.translator_version != batch.translator_version:
            reasons.add(FormulaMigrationProjectionReason.TRANSLATOR_VERSION_MISMATCH.value)

        translation_status: FormulaTranslationStatus
        try:
            translation_status = FormulaTranslationStatus(cell.translation_status)
        except ValueError as exc:
            reasons.add(FormulaMigrationProjectionReason.STALE_OR_INCONSISTENT_RESULT.value)
            translation_status = FormulaTranslationStatus.UNSUPPORTED

        reason_code = cell.reason_code
        try:
            FormulaTranslationReason(reason_code)
        except ValueError:
            reasons.add(FormulaMigrationProjectionReason.STALE_OR_INCONSISTENT_RESULT.value)

        formula_shape_id = cell.formula_shape_id
        shape_is_price_target = False
        if formula_shape_id is None:
            reasons.add(FormulaMigrationProjectionReason.SHAPE_TARGET_MISMATCH.value)
        else:
            try:
                shape_entry = get_registry_entry(formula_shape_id)
                shape_is_price_target = bool(shape_entry.is_price_target)
            except KeyError:
                reasons.add(FormulaMigrationProjectionReason.SHAPE_TARGET_MISMATCH.value)

        comparison_contract: ShapeComparisonContract | None = None
        if formula_shape_id is not None and shape_is_price_target:
            comparison_contract = _lookup_shape_contract(
                self.db, shape_id=formula_shape_id
            )
            if comparison_contract is None:
                reasons.add(FormulaMigrationProjectionReason.COMPARISON_CONTRACT_MISSING.value)

        fixture_evidence = cell.fixture_registry_evidence_json or {}
        result_id = fixture_evidence.get("formula_translation_result_id")
        if not isinstance(result_id, str) or not result_id:
            reasons.add(FormulaMigrationProjectionReason.TRANSLATION_RESULT_MISSING.value)
            result = None
            result_id = ""
        else:
            result = self.db.get(FormulaTranslationResult, result_id)
            if result is None:
                reasons.add(FormulaMigrationProjectionReason.TRANSLATION_RESULT_MISSING.value)

        if result is not None:
            if result.formula_rule_identity != cell.formula_rule_identity:
                reasons.add(FormulaMigrationProjectionReason.STALE_OR_INCONSISTENT_RESULT.value)
            if result.formula_shape_id != formula_shape_id:
                reasons.add(FormulaMigrationProjectionReason.SHAPE_TARGET_MISMATCH.value)
            if result.translation_status != cell.translation_status:
                reasons.add(FormulaMigrationProjectionReason.STALE_OR_INCONSISTENT_RESULT.value)
            if result.reason_code != cell.reason_code:
                reasons.add(FormulaMigrationProjectionReason.STALE_OR_INCONSISTENT_RESULT.value)
            if result.translation_fingerprint != cell.translation_fingerprint:
                reasons.add(FormulaMigrationProjectionReason.FINGERPRINT_MISMATCH.value)
            if result.translator_version != cell.translator_version:
                reasons.add(FormulaMigrationProjectionReason.TRANSLATOR_VERSION_MISMATCH.value)
            if result.registry_version != cell.registry_version:
                reasons.add(FormulaMigrationProjectionReason.REGISTRY_VERSION_MISMATCH.value)
            if result.registry_checksum != cell.registry_checksum:
                reasons.add(FormulaMigrationProjectionReason.REGISTRY_CHECKSUM_MISMATCH.value)

        review_required = translation_status is FormulaTranslationStatus.REVIEW_REQUIRED
        review_decision_id: str | None = None
        if review_required:
            latest = (
                self.db.query(FormulaMigrationReviewDecision)
                .where(FormulaMigrationReviewDecision.preview_cell_id == cell.id)
                .order_by(
                    FormulaMigrationReviewDecision.created_at.asc(),
                    FormulaMigrationReviewDecision.id.asc(),
                )
                .all()
            )
            latest_decision = latest[-1] if latest else None
            if latest_decision is None or latest_decision.action != "approved":
                reasons.add(FormulaMigrationProjectionReason.REVIEW_REQUIRED_APPROVAL_MISSING.value)
            else:
                review_decision_id = latest_decision.id

        may_count = (
            shape_is_price_target
            and (translation_status is FormulaTranslationStatus.TRANSLATED or review_required)
            and not cell.blocking_operationally_active
            and not reasons
        )

        blocked = bool(reasons)
        if translation_status is FormulaTranslationStatus.QUARANTINED and cell.blocking_operationally_active:
            blocked = True

        if reasons:
            may_count = False

        if not shape_is_price_target:
            non_price_evidence_only = True
        else:
            non_price_evidence_only = False

        return _CellProjectionDraft(
            preview_batch_id=batch.id,
            preview_cell_id=cell.id,
            inventory_cell_id=cell.inventory_cell_id,
            formula_rule_identity=cell.formula_rule_identity,
            formula_shape_id=formula_shape_id,
            formula_translation_result_id=result_id,
            translation_status=cell.translation_status,
            reason_code=cell.reason_code,
            translation_fingerprint=cell.translation_fingerprint,
            translator_version=cell.translator_version,
            registry_version=cell.registry_version,
            registry_checksum=cell.registry_checksum,
            binding_manifest_checksum=cell.binding_manifest_checksum,
            preview_batch_report_checksum=batch.report_checksum,
            preview_row_checksum=cell.report_row_checksum,
            shape_is_price_target=shape_is_price_target,
            shape_comparison_contract_id=(
                comparison_contract.id if comparison_contract else None
            ),
            shape_comparison_contract_revision=(
                comparison_contract.contract_revision if comparison_contract else None
            ),
            shape_comparison_contract_revision_checksum=(
                comparison_contract.contract_checksum if comparison_contract else None
            ),
            review_decision_id=review_decision_id,
            may_count=may_count,
            review_required=review_required,
            blocked=blocked,
            non_price_evidence_only=non_price_evidence_only,
            fail_reasons=tuple(sorted(reasons)),
        )
