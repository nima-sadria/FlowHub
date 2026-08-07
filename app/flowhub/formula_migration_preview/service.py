"""Offline formula migration preview assembly and review ledger service (D6)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.formula_migration_preview.contracts import (
    DependencyManifest,
    FormulaInventoryCell,
    FormulaMigrationCellDecision,
    FormulaMigrationInputCell,
    FormulaMigrationPreviewBatch,
    FormulaMigrationReviewAction,
    PreviewBatchState,
)
from app.flowhub.formula_migration_preview.fingerprint import (
    compute_preview_batch_checksum,
    compute_preview_row_checksum,
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
from app.flowhub.unified_workspace.domain import checksum, utcnow


@dataclass(frozen=True, slots=True)
class PreviewInput:
    cells: tuple[FormulaMigrationInputCell, ...]


@dataclass(frozen=True, slots=True)
class ReviewDecisionRecord:
    preview_batch_id: str
    inventory_cell_id: str
    action: FormulaMigrationReviewAction
    actor: str
    actor_user_id: int | None
    reason: str
    evidence: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _TranslatorDiff:
    has_prior: bool
    prior_translator_version: str | None = None
    prior_fingerprint: str | None = None
    current_translator_version: str | None = None
    current_fingerprint: str | None = None


def _coerce_manifest_checksum(manifest: DependencyManifest) -> str:
    return checksum(
        {
            "source_roles": manifest.source_roles,
            "manual_roles": manifest.manual_roles,
            "derived_keys": manifest.derived_keys,
        }
    )


def _coerce_cell(raw_cell: FormulaMigrationInputCell) -> FormulaMigrationInputCell:
    if not isinstance(raw_cell.inventory_cell, FormulaInventoryCell):
        raise TypeError("inventory_cell_type_invalid")

    status = raw_cell.translation_status
    if not isinstance(status, FormulaTranslationStatus):
        status = FormulaTranslationStatus(status)

    reason = raw_cell.reason_code
    if not isinstance(reason, FormulaTranslationReason):
        reason = FormulaTranslationReason(reason)

    if not isinstance(raw_cell.binding_manifest, DependencyManifest):
        raise TypeError("binding_manifest_type_invalid")

    manifest_checksum = raw_cell.binding_manifest_checksum
    if not manifest_checksum:
        manifest_checksum = _coerce_manifest_checksum(raw_cell.binding_manifest)
    elif manifest_checksum != _coerce_manifest_checksum(raw_cell.binding_manifest):
        raise ValueError("binding_manifest_checksum_mismatch")

    return FormulaMigrationInputCell(
        inventory_cell=raw_cell.inventory_cell,
        translation_status=status,
        reason_code=reason,
        formula_shape_id=raw_cell.formula_shape_id,
        translation_fingerprint=raw_cell.translation_fingerprint,
        translation_output_payload=dict(raw_cell.translation_output_payload),
        translation_input_payload=dict(raw_cell.translation_input_payload),
        binding_manifest=raw_cell.binding_manifest,
        binding_manifest_checksum=manifest_checksum,
        translator_version=raw_cell.translator_version,
        registry_version=raw_cell.registry_version,
        registry_checksum=raw_cell.registry_checksum,
        formula_rule_identity=raw_cell.formula_rule_identity,
        translation_fingerprint_by_version=dict(raw_cell.translation_fingerprint_by_version),
        fixture_and_registry_evidence=dict(raw_cell.fixture_and_registry_evidence),
    )


def _validate_input_cell(
    cell: FormulaMigrationInputCell, *,
    registry_version: str,
    registry_checksum: str,
    translator_version: str,
) -> None:
    if not cell.inventory_cell.inventory_id:
        raise ValueError("inventory_cell_id_missing")
    if not cell.formula_rule_identity:
        raise ValueError("formula_rule_identity_missing")
    if not cell.translation_fingerprint:
        raise ValueError("translation_fingerprint_missing")
    if not cell.formula_rule_identity:
        raise ValueError("formula_rule_identity_missing")
    if cell.translator_version != translator_version:
        raise ValueError("translator_version_mismatch")
    if cell.registry_version != registry_version:
        raise ValueError("registry_version_mismatch")
    if cell.registry_checksum != registry_checksum:
        raise ValueError("registry_checksum_mismatch")


def _payload_hash(cell: FormulaMigrationInputCell) -> dict[str, object]:
    return {
        "formula_rule_identity": cell.formula_rule_identity,
        "translation_status": cell.translation_status.value,
        "reason_code": cell.reason_code.value,
        "translator_version": cell.translator_version,
        "formula_shape_id": cell.formula_shape_id,
        "registry_version": cell.registry_version,
        "registry_checksum": cell.registry_checksum,
        "binding_manifest_checksum": cell.binding_manifest_checksum,
        "translation_input_payload": dict(cell.translation_input_payload),
        "translation_output_payload": dict(cell.translation_output_payload),
    }


def _operationally_active_blocking(shape_id: str | None, status: FormulaTranslationStatus) -> bool:
    if status is FormulaTranslationStatus.TRANSLATED:
        return False
    if status is FormulaTranslationStatus.REVIEW_REQUIRED:
        return False
    if status is FormulaTranslationStatus.UNSUPPORTED:
        return False
    if status is FormulaTranslationStatus.QUARANTINED:
        return True
    if shape_id is None:
        return True
    try:
        registry_entry = get_registry_entry(shape_id)
    except KeyError:
        return True
    return bool(registry_entry.is_price_target)


class FormulaMigrationPreviewService:
    """Assembles immutable offline preview outputs and review decisions."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def assemble_preview(
        self,
        *,
        batch_id: str,
        preview_input: PreviewInput,
        created_by_user: FlowHubUser | None = None,
        now: datetime | None = None,
    ) -> FormulaMigrationPreviewBatch:
        if not batch_id:
            raise ValueError("batch_id_required")
        if not preview_input.cells:
            raise ValueError("preview_cells_required")

        cells = tuple(_coerce_cell(raw_cell) for raw_cell in preview_input.cells)
        translator_version = cells[0].translator_version
        registry_version = cells[0].registry_version
        registry_checksum = cells[0].registry_checksum

        for cell in cells:
            _validate_input_cell(
                cell,
                registry_version=registry_version,
                registry_checksum=registry_checksum,
                translator_version=translator_version,
            )
            if registry_version != cell.registry_version or registry_checksum != cell.registry_checksum:
                raise ValueError("mixed_batch_registry_state")

        now = now or utcnow()
        ordered_cells = sorted(cells, key=lambda item: item.inventory_cell.inventory_id)
        cell_rows: dict[str, dict[str, object]] = {}
        decisions: list[FormulaMigrationCellDecision] = []
        rows_payload_for_checksum: list[dict[str, object]] = []

        for cell in ordered_cells:
            result = self._get_or_create_translation_result(cell=cell)
            translator_diff = self._compute_translator_diff(
                cell=cell,
                current_result=result,
            )

            translation_version_diff: dict[str, object] | None = None
            if translator_diff.has_prior:
                translation_version_diff = {
                    "prior_translator_version": translator_diff.prior_translator_version,
                    "prior_translation_fingerprint": translator_diff.prior_fingerprint,
                    "current_translator_version": translator_diff.current_translator_version,
                    "current_translation_fingerprint": translator_diff.current_fingerprint,
                }

            review_required = None
            if cell.translation_status is FormulaTranslationStatus.REVIEW_REQUIRED:
                review_required = {
                    "required": True,
                    "reason": cell.reason_code.value,
                    "evidence": dict(cell.fixture_and_registry_evidence),
                }

            quarantine_reason = None
            if cell.translation_status is FormulaTranslationStatus.QUARANTINED:
                quarantine_reason = {
                    "required": True,
                    "reason": cell.reason_code.value,
                    "evidence": dict(cell.fixture_and_registry_evidence),
                }

            blocking = _operationally_active_blocking(
                shape_id=cell.formula_shape_id,
                status=cell.translation_status,
            )
            target_fragment = (
                dict(cell.translation_output_payload)
                if cell.translation_status is FormulaTranslationStatus.TRANSLATED
                else {}
            )

            if cell.formula_shape_id is not None:
                try:
                    registry_entry = get_registry_entry(cell.formula_shape_id)
                    is_price_target = registry_entry.is_price_target
                    registry_entry_payload = {
                        "shape_id": registry_entry.shape_id,
                        "is_price_target": is_price_target,
                        "default_reason_code": registry_entry.default_reason_code.value,
                    }
                except KeyError:
                    registry_entry_payload = {
                        "shape_id": cell.formula_shape_id,
                        "is_price_target": True,
                    }
            else:
                registry_entry_payload = {"shape_id": None, "is_price_target": True, "unknown_shape": True}

            formula_inventory_evidence = {
                "formula_rule_identity": cell.formula_rule_identity,
                "inventory_cell_id": cell.inventory_cell.inventory_id,
                "formula_text": cell.inventory_cell.formula_text,
                "worksheet": cell.inventory_cell.worksheet,
                "row": cell.inventory_cell.row,
                "column": cell.inventory_cell.column,
            }
            binding_manifest_evidence = {
                "source_roles": tuple(cell.binding_manifest.source_roles),
                "manual_roles": tuple(cell.binding_manifest.manual_roles),
                "derived_keys": tuple(cell.binding_manifest.derived_keys),
            }
            fixture_registry_evidence = {
                "registry_version": cell.registry_version,
                "registry_checksum": cell.registry_checksum,
                "registry_entry": registry_entry_payload,
                "formula_translation_result_id": result.id,
                "fixture_evidence": dict(cell.fixture_and_registry_evidence),
            }

            row_payload: dict[str, object] = {
                "inventory_cell_id": cell.inventory_cell.inventory_id,
                "formula_rule_identity": cell.formula_rule_identity,
                "formula_shape_id": cell.formula_shape_id,
                "translation_status": cell.translation_status.value,
                "reason_code": cell.reason_code.value,
                "translation_fingerprint": result.translation_fingerprint,
                "binding_manifest_checksum": cell.binding_manifest_checksum,
                "target_fragment": target_fragment,
                "review_required": review_required,
                "quarantine_reason": quarantine_reason,
                "fixture_registry_evidence": fixture_registry_evidence,
                "translator_version": cell.translator_version,
                "translator_version_diff": translation_version_diff,
                "blocking_operationally_active": blocking,
                "formula_inventory_evidence": formula_inventory_evidence,
                "binding_manifest": binding_manifest_evidence,
                "registry_version": registry_version,
                "registry_checksum": registry_checksum,
            }
            row_payload["report_row_checksum"] = compute_preview_row_checksum(row_payload=row_payload)

            rows_payload_for_checksum.append(row_payload)
            row_decision = FormulaMigrationCellDecision(
                inventory_cell_id=cell.inventory_cell.inventory_id,
                formula_rule_identity=cell.formula_rule_identity,
                formula_shape_id=cell.formula_shape_id,
                translation_status=cell.translation_status,
                reason_code=cell.reason_code,
                translation_fingerprint=result.translation_fingerprint,
                binding_manifest_checksum=cell.binding_manifest_checksum,
                target_fragment=target_fragment,
                review_required=review_required,
                quarantine_reason=quarantine_reason,
                fixture_registry_evidence=fixture_registry_evidence,
                translator_version=cell.translator_version,
                translator_version_diff=translation_version_diff,
                blocking_operationally_active=blocking,
                formula_inventory_evidence=formula_inventory_evidence,
                report_row_checksum=row_payload["report_row_checksum"],
            )
            decisions.append(row_decision)
            cell_rows[cell.inventory_cell.inventory_id] = row_payload

        counts = {
            "translated": sum(
                1 for payload in rows_payload_for_checksum if payload["translation_status"] == FormulaTranslationStatus.TRANSLATED.value
            ),
            "review_required": sum(
                1 for payload in rows_payload_for_checksum if payload["translation_status"] == FormulaTranslationStatus.REVIEW_REQUIRED.value
            ),
            "unsupported": sum(
                1 for payload in rows_payload_for_checksum if payload["translation_status"] == FormulaTranslationStatus.UNSUPPORTED.value
            ),
            "quarantined": sum(
                1 for payload in rows_payload_for_checksum if payload["translation_status"] == FormulaTranslationStatus.QUARANTINED.value
            ),
        }
        blocking_operationally_active_count = sum(
            1 for payload in rows_payload_for_checksum if payload["blocking_operationally_active"]
        )

        inventory_checksum = checksum(
            {
                "rows": sorted(
                    (
                        payload["inventory_cell_id"],
                        payload["formula_rule_identity"],
                        payload["translation_status"],
                        payload["reason_code"],
                        payload["translation_fingerprint"],
                        payload["binding_manifest_checksum"],
                    )
                    for payload in rows_payload_for_checksum
                )
            }
        )
        input_checksum = checksum(
            {
                "inputs": tuple(
                    _payload_hash(cell)
                    for cell in sorted(cells, key=lambda item: item.inventory_cell.inventory_id)
                )
            }
        )
        batch_checksum_payload = {
            "translator_version": translator_version,
            "registry_version": registry_version,
            "registry_checksum": registry_checksum,
            "counts": counts,
            "blocking_operationally_active": blocking_operationally_active_count,
            "inventory_checksum": inventory_checksum,
            "input_checksum": input_checksum,
        }
        report_checksum = compute_preview_batch_checksum(
            batch_payload=batch_checksum_payload,
            cell_payloads=rows_payload_for_checksum,
        )

        batch_model = PreviewBatchModel(
            id=batch_id,
            state=PreviewBatchState.COMPLETED.value,
            translator_version=translator_version,
            registry_version=registry_version,
            registry_checksum=registry_checksum,
            inventory_checksum=inventory_checksum,
            input_checksum=input_checksum,
            report_checksum=report_checksum,
            translated_count=counts["translated"],
            review_required_count=counts["review_required"],
            unsupported_count=counts["unsupported"],
            quarantined_count=counts["quarantined"],
            blocking_operationally_active_count=blocking_operationally_active_count,
            created_by_user_id=created_by_user.id if created_by_user else None,
            created_at=now,
        )
        self.db.add(batch_model)
        self.db.flush()

        for decision in decisions:
            payload = cell_rows[decision.inventory_cell_id]
            cell_model = PreviewCellModel(
                id=str(uuid.uuid4()),
                preview_batch_id=batch_model.id,
                formula_rule_identity=decision.formula_rule_identity,
                inventory_cell_id=decision.inventory_cell_id,
                formula_shape_id=decision.formula_shape_id,
                translation_status=decision.translation_status.value,
                reason_code=decision.reason_code.value,
                translation_fingerprint=decision.translation_fingerprint,
                target_fragment_json=dict(decision.target_fragment),
                binding_manifest_checksum=decision.binding_manifest_checksum,
                fixture_registry_evidence_json=dict(decision.fixture_registry_evidence),
                formula_inventory_evidence_json=dict(decision.formula_inventory_evidence),
                translator_version=decision.translator_version,
                translator_version_diff_json=(
                    dict(decision.translator_version_diff) if decision.translator_version_diff is not None else None
                ),
                registry_version=payload["registry_version"],
                registry_checksum=payload["registry_checksum"],
                blocking_operationally_active=bool(decision.blocking_operationally_active),
                report_row_checksum=decision.report_row_checksum,
                created_at=now,
            )
            self.db.add(cell_model)

        self.db.commit()

        return FormulaMigrationPreviewBatch(
            batch_id=batch_model.id,
            state=PreviewBatchState.COMPLETED,
            translator_version=batch_model.translator_version,
            registry_version=batch_model.registry_version,
            registry_checksum=batch_model.registry_checksum,
            counts=counts,
            blocking_operationally_active=blocking_operationally_active_count,
            cells=tuple(decisions),
            report_checksum=report_checksum,
        )

    def add_review_decision(self, decision: ReviewDecisionRecord, now: datetime | None = None) -> str:
        if not decision.actor.strip():
            raise ValueError("actor_required")
        if not decision.reason.strip():
            raise ValueError("reason_required")

        cell = self._resolve_cell_for_batch_or_raise(
            preview_batch_id=decision.preview_batch_id,
            inventory_cell_id=decision.inventory_cell_id,
        )
        now = now or utcnow()
        decision_row = FormulaMigrationReviewDecision(
            id=str(uuid.uuid4()),
            preview_cell_id=cell.id,
            actor_name=decision.actor,
            actor_user_id=decision.actor_user_id,
            action=decision.action.value,
            reason=decision.reason,
            evidence_json=dict(decision.evidence),
            created_at=now,
        )
        self.db.add(decision_row)
        self.db.commit()
        return decision_row.id

    def current_review_state(self, *, preview_batch_id: str, inventory_cell_id: str) -> dict[str, object] | None:
        cell = self._resolve_cell_for_batch_or_raise(
            preview_batch_id=preview_batch_id,
            inventory_cell_id=inventory_cell_id,
        )
        rows = (
            self.db.query(FormulaMigrationReviewDecision)
            .filter(FormulaMigrationReviewDecision.preview_cell_id == cell.id)
            .order_by(FormulaMigrationReviewDecision.created_at.asc(), FormulaMigrationReviewDecision.id.asc())
            .all()
        )
        if not rows:
            return None
        latest = rows[-1]
        return {
            "action": latest.action,
            "actor": latest.actor_name,
            "actor_user_id": latest.actor_user_id,
            "reason": latest.reason,
            "evidence": dict(latest.evidence_json),
            "created_at": latest.created_at,
        }

    def _resolve_cell_for_batch_or_raise(
        self, preview_batch_id: str, inventory_cell_id: str
    ) -> PreviewCellModel:
        statement = (
            select(PreviewCellModel)
            .where(PreviewCellModel.preview_batch_id == preview_batch_id)
            .where(PreviewCellModel.inventory_cell_id == inventory_cell_id)
        )
        cell = self.db.execute(statement).scalar_one_or_none()
        if cell is None:
            raise ValueError("preview_cell_missing")
        return cell

    def _find_existing_translation_result(
        self, *, formula_rule_identity: str, translator_version: str
    ) -> FormulaTranslationResult | None:
        statement = (
            select(FormulaTranslationResult)
            .where(FormulaTranslationResult.formula_rule_identity == formula_rule_identity)
            .where(FormulaTranslationResult.translator_version == translator_version)
        )
        return self.db.execute(statement).scalar_one_or_none()

    def _find_prior_translation_result(
        self, *, formula_rule_identity: str, current_translator_version: str
    ) -> FormulaTranslationResult | None:
        statement = (
            select(FormulaTranslationResult)
            .where(FormulaTranslationResult.formula_rule_identity == formula_rule_identity)
            .where(FormulaTranslationResult.translator_version != current_translator_version)
            .order_by(FormulaTranslationResult.created_at.desc())
        )
        return self.db.execute(statement).scalars().first()

    def _compute_translator_diff(
        self,
        *,
        cell: FormulaMigrationInputCell,
        current_result: FormulaTranslationResult,
    ) -> _TranslatorDiff:
        prior = self._find_prior_translation_result(
            formula_rule_identity=cell.formula_rule_identity,
            current_translator_version=cell.translator_version,
        )
        if prior is None:
            return _TranslatorDiff(has_prior=False)
        return _TranslatorDiff(
            has_prior=True,
            prior_translator_version=prior.translator_version,
            prior_fingerprint=prior.translation_fingerprint,
            current_translator_version=current_result.translator_version,
            current_fingerprint=current_result.translation_fingerprint,
        )

    def _get_or_create_translation_result(
        self, *, cell: FormulaMigrationInputCell
    ) -> FormulaTranslationResult:
        existing = self._find_existing_translation_result(
            formula_rule_identity=cell.formula_rule_identity,
            translator_version=cell.translator_version,
        )
        if existing is not None:
            if existing.translation_fingerprint != cell.translation_fingerprint:
                raise ValueError("translation_result_conflict")
            return existing

        result = FormulaTranslationResult(
            id=str(uuid.uuid4()),
            formula_rule_identity=cell.formula_rule_identity,
            formula_shape_id=cell.formula_shape_id,
            translation_status=cell.translation_status.value,
            reason_code=cell.reason_code.value,
            translator_version=cell.translator_version,
            registry_version=cell.registry_version,
            registry_checksum=cell.registry_checksum,
            translation_payload_json=dict(cell.translation_output_payload),
            translation_fingerprint=cell.translation_fingerprint,
            translation_input_payload_json=dict(cell.translation_input_payload),
            created_at=utcnow(),
        )
        self.db.add(result)
        self.db.flush()
        return result
