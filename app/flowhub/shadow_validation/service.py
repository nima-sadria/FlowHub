"""Comparison assembly for shadow validation (Phase C3)."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.pricing_evaluation.models import FrozenEvaluationPackage, PackagePriceOverride
from app.flowhub.shadow_validation.contracts import (
    ComparisonConfidence,
    ComparisonPrimaryClassification,
    OutputLane,
    ShadowValidationReasonCode,
    ShapeTargetKind,
)
from app.flowhub.shadow_validation.errors import (
    REASON_AUTHORITY_MISMATCH,
    REASON_CAPTURE_NOT_FOUND,
    REASON_CAPTURE_CHANNEL_MISMATCH,
    REASON_CONTRACT_NOT_FOUND,
    REASON_CONTRACT_UNAPPROVED,
    REASON_FEP_CAPTURE_MISMATCH,
    REASON_FEP_NOT_FOUND,
    REASON_OUTPUT_LANES_UNSUPPORTED,
    REASON_POLICY_MISMATCH,
    REASON_UNSUPPORTED_SHAPE,
    REASON_WINDOW_CHANNEL_MISMATCH,
    REASON_WINDOW_NOT_FOUND,
    ShadowValidationError,
)
from app.flowhub.shadow_validation.fingerprint import compute_comparison_identity_checksum
from app.flowhub.shadow_validation.models import (
    LegacyFormulaCapture,
    ShadowValidationComparison,
    ShadowValidationWindow,
    ShapeComparisonContract,
)
from app.flowhub.unified_workspace.domain import checksum, utcnow


COMPARISON_ALGORITHM_VERSION = "shadow-validation-comparison-v1"
_VERSION = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")


class _Finding:
    OUTPUT_CONTEXT_DIVERGENCE = "output_context_divergence"
    EFFECTIVE_VALUE_DIVERGENCE = "effective_value_divergence"
    CANDIDATE_VALUE_DIVERGENCE = "candidate_value_divergence"
    TRACE_DIVERGENCE = "trace_divergence"
    CRITICAL = "critical_divergence"
    EXACT_MATCH = "exact_match"


_FINDING_TO_CLASSIFICATION = {
    _Finding.OUTPUT_CONTEXT_DIVERGENCE: ComparisonPrimaryClassification.REVIEW_REQUIRED.value,
    _Finding.EFFECTIVE_VALUE_DIVERGENCE: ComparisonPrimaryClassification.ACCEPTED_EXPECTED_ROUNDING.value,
    _Finding.CANDIDATE_VALUE_DIVERGENCE: ComparisonPrimaryClassification.REVIEW_REQUIRED.value,
    _Finding.TRACE_DIVERGENCE: ComparisonPrimaryClassification.ACCEPTED_DOCUMENTED_SEMANTIC_DIFFERENCE.value,
    _Finding.CRITICAL: ComparisonPrimaryClassification.CRITICAL_DIVERGENCE.value,
    _Finding.EXACT_MATCH: ComparisonPrimaryClassification.EXACT_MATCH.value,
}

_PRIMARY_CLASSIFICATIONS = {item.value for item in ComparisonPrimaryClassification}
_CLASSIFICATION_PRECEDENCE = (
    ComparisonPrimaryClassification.CRITICAL_DIVERGENCE.value,
    ComparisonPrimaryClassification.ACCEPTED_DOCUMENTED_SEMANTIC_DIFFERENCE.value,
    ComparisonPrimaryClassification.REVIEW_REQUIRED.value,
    ComparisonPrimaryClassification.ACCEPTED_EXPECTED_ROUNDING.value,
    ComparisonPrimaryClassification.EXACT_MATCH.value,
)


def _id() -> str:
    return str(uuid.uuid4())


def _fraction(numerator: int, denominator: int) -> Fraction:
    return Fraction(int(numerator), int(denominator))


def _dedupe(items: list[str]) -> list[str]:
    output: list[str] = []
    for item in items:
        if item not in output:
            output.append(item)
    return output


def _classify_findings(findings: tuple[str, ...], contract: ShapeComparisonContract) -> str:
    contract_mapping = dict(contract.classification_mapping_json or {})
    mapped = []
    for finding in findings:
        classification = contract_mapping.get(finding, _FINDING_TO_CLASSIFICATION.get(finding))
        if classification in _PRIMARY_CLASSIFICATIONS:
            # Contract mappings may include legacy or invalid labels; ignore unknowns.
            mapped.append(classification)

    normalized = _dedupe(mapped)
    if not normalized:
        return ComparisonPrimaryClassification.EXACT_MATCH.value
    for preferred in _CLASSIFICATION_PRECEDENCE:
        if preferred in normalized:
            return preferred
    return normalized[0]


@dataclass(frozen=True, slots=True)
class ShadowValidationComparisonResult:
    comparison: ShadowValidationComparison
    primary_classification: str
    secondary_classifications: tuple[str, ...]
    confidence: str
    reason_code: str | None


class ShadowValidationComparisonAssemblyService:
    """Assemble immutable C3 comparison rows over pre-built evidence."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def assemble(
        self,
        *,
        validation_window_id: str,
        frozen_evaluation_package_id: str,
        legacy_formula_capture_id: str,
        comparison_contract_id: str | None = None,
        actor_user: FlowHubUser | None = None,
        comparison_algorithm_version: str = COMPARISON_ALGORITHM_VERSION,
        correlation_id: str = "",
        created_at: Any | None = None,
    ) -> ShadowValidationComparisonResult:
        algorithm = self._version(comparison_algorithm_version, "comparison_algorithm_version")
        now = created_at or utcnow()

        window = self._window(validation_window_id)
        fep = self._fep(frozen_evaluation_package_id)
        capture = self._capture(legacy_formula_capture_id)

        if window.channel_id != fep.channel_id:
            raise ShadowValidationError(REASON_WINDOW_CHANNEL_MISMATCH)
        if window.channel_id != capture.channel_id:
            raise ShadowValidationError(REASON_CAPTURE_CHANNEL_MISMATCH)
        if fep.id != capture.frozen_evaluation_package_id:
            raise ShadowValidationError(REASON_FEP_CAPTURE_MISMATCH)

        contract = self._contract(comparison_contract_id, shape_id=capture.formula_shape_id)
        if contract.shape_id != fep.formula_shape_id or contract.shape_id != capture.formula_shape_id:
            raise ShadowValidationError(REASON_FEP_CAPTURE_MISMATCH)
        if contract.target_kind != ShapeTargetKind.PRICE_TARGET.value:
            raise ShadowValidationError(REASON_UNSUPPORTED_SHAPE)
        if not contract.is_current:
            raise ShadowValidationError(REASON_CONTRACT_UNAPPROVED)

        output_lanes = self._normalize_output_lanes(contract.required_output_lanes_json)
        self._validate_authority_and_policy(window, fep, capture)

        confidence, provenance_reason_code = self._assess_provenance(window, fep, capture, contract)
        findings = []

        legacy_output = self._extract_legacy_output(capture, output_lanes)
        package_output = self._extract_package_output(fep, output_lanes)

        if confidence == ComparisonConfidence.VERIFIED.value:
            context_finding = self._compare_context(window, contract, capture, fep)
            if context_finding:
                findings.append(context_finding)

            value_findings, missing_output = self._compare_values(legacy_output, package_output, output_lanes)
            findings.extend(value_findings)
            if missing_output:
                confidence = ComparisonConfidence.UNAVAILABLE.value
                provenance_reason_code = ShadowValidationReasonCode.OUTPUT_UNAVAILABLE

            trace_finding = self._compare_traces(capture, contract)
            if trace_finding:
                findings.append(trace_finding)
            if len(
                {finding for finding in value_findings if finding in {_Finding.EFFECTIVE_VALUE_DIVERGENCE, _Finding.CANDIDATE_VALUE_DIVERGENCE}}
            ) == 2:
                findings.append(_Finding.CRITICAL)

            if not findings:
                primary = ComparisonPrimaryClassification.EXACT_MATCH.value
            else:
                primary = _classify_findings(tuple(findings), contract)
        else:
            primary = ComparisonPrimaryClassification.NOT_POSSIBLE.value

        if primary == ComparisonPrimaryClassification.EXACT_MATCH.value:
            secondary: tuple[str, ...] = ()
            reason_code = None
        else:
            secondary = tuple(_dedupe([primary, *_dedupe([_FINDING_TO_CLASSIFICATION.get(finding, primary) for finding in findings])]))
            reason_code = provenance_reason_code

        if confidence != ComparisonConfidence.VERIFIED.value and primary != ComparisonPrimaryClassification.NOT_POSSIBLE.value:
            primary = ComparisonPrimaryClassification.NOT_POSSIBLE.value
            reason_code = provenance_reason_code
            secondary = (primary,)

        stable_rule_identity = checksum({"value": contract.stable_rule_identity_json})
        comparison_identity_checksum = compute_comparison_identity_checksum(
            channel_id=window.channel_id,
            stable_rule_identity=stable_rule_identity,
            frozen_evaluation_package_id=fep.id,
            frozen_evaluation_package_checksum=fep.checksum,
            legacy_formula_capture_id=capture.id,
            legacy_formula_capture_checksum=capture.capture_checksum,
            comparison_contract_id=contract.id,
            comparison_contract_checksum=contract.contract_checksum,
            comparison_algorithm_version=algorithm,
        )

        comparison = ShadowValidationComparison(
            id=_id(),
            channel_id=window.channel_id,
            validation_window_id=window.id,
            frozen_evaluation_package_id=fep.id,
            legacy_formula_capture_id=capture.id,
            shape_id=contract.shape_id,
            comparison_contract_id=contract.id,
            stable_rule_identity=stable_rule_identity,
            comparison_contract_revision=contract.contract_revision,
            comparison_contract_revision_checksum=contract.contract_checksum,
            comparison_algorithm_version=algorithm,
            comparison_identity_checksum=comparison_identity_checksum,
            frozen_evaluation_package_checksum=fep.checksum,
            legacy_capture_checksum=capture.capture_checksum,
            translator_version=fep.translator_version,
            required_output_lanes=output_lanes.value,
            confidence=confidence,
            primary_classification=primary,
            secondary_classifications_json=list(secondary),
            legacy_vs_package_context_json=self._build_context_payload(window, contract, fep, capture),
            legacy_output_json=legacy_output,
            package_output_json=package_output,
            findings_json=findings,
            actor_user_id=actor_user.id if actor_user is not None else None,
            reason_code=reason_code,
            correlation_id=correlation_id,
            created_at=now,
        )

        self.db.add(comparison)
        self.db.commit()

        if confidence == ComparisonConfidence.VERIFIED.value and primary == ComparisonPrimaryClassification.EXACT_MATCH.value:
            secondary = ()
        return ShadowValidationComparisonResult(
            comparison=comparison,
            primary_classification=primary,
            secondary_classifications=tuple(secondary),
            confidence=confidence,
            reason_code=reason_code,
        )

    # -- read helpers --------------------------------------------------

    def _window(self, window_id: str) -> ShadowValidationWindow:
        window = self.db.get(ShadowValidationWindow, window_id)
        if window is None:
            raise ShadowValidationError(REASON_WINDOW_NOT_FOUND)
        return window

    def _fep(self, package_id: str) -> FrozenEvaluationPackage:
        package = self.db.get(FrozenEvaluationPackage, package_id)
        if package is None:
            raise ShadowValidationError(REASON_FEP_NOT_FOUND)
        return package

    def _capture(self, capture_id: str) -> LegacyFormulaCapture:
        capture = self.db.get(LegacyFormulaCapture, capture_id)
        if capture is None:
            raise ShadowValidationError(REASON_CAPTURE_NOT_FOUND)
        return capture

    def _contract(
        self, contract_id: str | None, *, shape_id: str
    ) -> ShapeComparisonContract:
        query = self.db.query(ShapeComparisonContract)
        if contract_id is None:
            contract = query.filter_by(shape_id=shape_id, is_current=True).one_or_none()
        else:
            contract = query.filter_by(id=contract_id).one_or_none()

        if contract is None:
            raise ShadowValidationError(REASON_CONTRACT_NOT_FOUND)
        return contract

    # -- validation ---------------------------------------------------

    def _validate_authority_and_policy(
        self,
        window: ShadowValidationWindow,
        fep: FrozenEvaluationPackage,
        capture: LegacyFormulaCapture,
    ) -> None:
        if (
            capture.pricing_authority_event_id != window.pricing_authority_event_id
            or capture.pricing_authority_head_version != window.pricing_authority_head_version
        ):
            raise ShadowValidationError(REASON_AUTHORITY_MISMATCH)
        if (fep.pricing_policy_revision_id or None) != (window.pricing_policy_revision_id or None):
            raise ShadowValidationError(REASON_POLICY_MISMATCH)

    def _normalize_output_lanes(self, lanes_json: object) -> OutputLane:
        if not isinstance(lanes_json, list):
            raise ShadowValidationError(REASON_OUTPUT_LANES_UNSUPPORTED)
        normalized = sorted(set(str(item) for item in lanes_json))
        if normalized == ["candidate"]:
            return OutputLane.CANDIDATE
        if normalized == ["effective"]:
            return OutputLane.EFFECTIVE
        if normalized == ["candidate", "effective"]:
            return OutputLane.BOTH
        raise ShadowValidationError(REASON_OUTPUT_LANES_UNSUPPORTED)

    def _assess_provenance(
        self,
        _window: ShadowValidationWindow,
        fep: FrozenEvaluationPackage,
        capture: LegacyFormulaCapture,
        contract: ShapeComparisonContract,
    ) -> tuple[str, str | None]:
        del _window
        required_input_identity = contract.required_input_identity_json
        if not isinstance(required_input_identity, dict):
            return (
                ComparisonConfidence.PARTIAL.value,
                ShadowValidationReasonCode.PROVENANCE_PARTIAL,
            )

        actual_input_identity: dict[str, str] = {
            "shape_id": capture.formula_shape_id,
            "formula_shape_id": capture.formula_shape_id,
            "formula_rule_identity": capture.formula_rule_identity,
            "input_manifest_checksum": capture.input_manifest_checksum,
            "fep_dependency_fingerprint": fep.dependency_fingerprint,
            "pricing_policy_revision_id": (fep.pricing_policy_revision_id or ""),
            "translator_version": fep.translator_version,
        }

        stable_rule_identity = contract.stable_rule_identity_json
        actual_stable_rule_identity = {
            "formula_shape_id": capture.formula_shape_id,
            "formula_rule_identity": capture.formula_rule_identity,
            "fep_formula_shape_id": fep.formula_shape_id,
        }
        if isinstance(stable_rule_identity, dict):
            for key, expected in stable_rule_identity.items():
                actual = actual_stable_rule_identity.get(key)
                if actual is None or str(actual) != str(expected):
                    return (
                        ComparisonConfidence.PARTIAL.value,
                        ShadowValidationReasonCode.PROVENANCE_PARTIAL,
                    )

        for key, expected in required_input_identity.items():
            if key not in actual_input_identity:
                return (
                    ComparisonConfidence.PARTIAL.value,
                    ShadowValidationReasonCode.PROVENANCE_PARTIAL,
                )
            if str(actual_input_identity[key]) != str(expected):
                return (
                    ComparisonConfidence.PARTIAL.value,
                    ShadowValidationReasonCode.PROVENANCE_PARTIAL,
                )

        if not fep.translator_version or not fep.checksum or not capture.capture_checksum:
            return (
                ComparisonConfidence.UNAVAILABLE.value,
                ShadowValidationReasonCode.PROVENANCE_UNAVAILABLE,
            )

        return (ComparisonConfidence.VERIFIED.value, None)

    def _extract_legacy_output(self, capture: LegacyFormulaCapture, output_lanes: OutputLane) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "shape_id": capture.formula_shape_id,
            "formula_rule_identity": capture.formula_rule_identity,
            "context": {
                "candidate_currency": capture.candidate_currency,
                "candidate_unit": capture.candidate_unit,
                "effective_currency": capture.effective_currency,
                "effective_unit": capture.effective_unit,
                "output_context": capture.output_context_json,
            },
        }
        if output_lanes in {OutputLane.CANDIDATE, OutputLane.BOTH}:
            payload["candidate"] = {
                "numerator": capture.candidate_numerator,
                "denominator": capture.candidate_denominator,
            }
        if output_lanes in {OutputLane.EFFECTIVE, OutputLane.BOTH}:
            payload["effective"] = {
                "numerator": capture.effective_numerator,
                "denominator": capture.effective_denominator,
            }
        return payload

    def _extract_package_output(self, fep: FrozenEvaluationPackage, output_lanes: OutputLane) -> dict[str, Any]:
        override = (
            self.db.query(PackagePriceOverride)
            .filter_by(frozen_evaluation_package_id=fep.id)
            .one_or_none()
        )
        if override is None:
            return {}

        payload: dict[str, Any] = {
            "shape_id": fep.formula_shape_id,
            "formula_shape_id": fep.formula_shape_id,
            "translator_version": fep.translator_version,
            "context": {
                "candidate_currency": None,
                "candidate_unit": None,
                "effective_currency": None,
                "effective_unit": None,
            },
            "metadata": {
                "arithmetic_version": fep.arithmetic_version,
                "currency_unit_registry_version": fep.currency_unit_registry_version,
            },
        }
        if output_lanes in {OutputLane.CANDIDATE, OutputLane.BOTH}:
            payload["candidate"] = {
                "numerator": override.calculated_candidate_numerator,
                "denominator": override.calculated_candidate_denominator,
            }
        if output_lanes in {OutputLane.EFFECTIVE, OutputLane.BOTH}:
            payload["effective"] = {
                "numerator": override.effective_output_numerator,
                "denominator": override.effective_output_denominator,
            }

        return payload

    def _compare_context(
        self,
        window: ShadowValidationWindow,
        contract: ShapeComparisonContract,
        capture: LegacyFormulaCapture,
        fep: FrozenEvaluationPackage,
    ) -> str | None:
        canonical_context = contract.canonical_context_json
        if not isinstance(canonical_context, dict):
            return None

        observed_context = {
            "candidate_currency": capture.candidate_currency,
            "candidate_unit": capture.candidate_unit,
            "effective_currency": capture.effective_currency,
            "effective_unit": capture.effective_unit,
            "formula_shape_id": capture.formula_shape_id,
            "fep_formula_shape_id": fep.formula_shape_id,
            "window_policy_revision": window.pricing_policy_revision_id,
            "translator_version": fep.translator_version,
            "pricing_policy_revision_id": fep.pricing_policy_revision_id,
            "currency_unit_registry_version": fep.currency_unit_registry_version,
            "arithmetic_version": fep.arithmetic_version,
        }
        for key, expected in canonical_context.items():
            if str(observed_context.get(key, "")) != str(expected):
                return _Finding.OUTPUT_CONTEXT_DIVERGENCE
        return None

    def _compare_values(
        self,
        legacy_output: dict[str, Any],
        package_output: dict[str, Any],
        output_lanes: OutputLane,
    ) -> tuple[list[str], bool]:
        findings: list[str] = []
        missing_output = False

        if output_lanes in {OutputLane.CANDIDATE, OutputLane.BOTH}:
            if "candidate" not in package_output:
                missing_output = True
            elif _fraction(
                int(legacy_output["candidate"]["numerator"]), int(legacy_output["candidate"]["denominator"])
            ) != _fraction(
                int(package_output["candidate"]["numerator"]), int(package_output["candidate"]["denominator"])
            ):
                findings.append(_Finding.CANDIDATE_VALUE_DIVERGENCE)

        if output_lanes in {OutputLane.EFFECTIVE, OutputLane.BOTH}:
            if "effective" not in package_output:
                missing_output = True
            elif _fraction(
                int(legacy_output["effective"]["numerator"]), int(legacy_output["effective"]["denominator"])
            ) != _fraction(
                int(package_output["effective"]["numerator"]), int(package_output["effective"]["denominator"])
            ):
                findings.append(_Finding.EFFECTIVE_VALUE_DIVERGENCE)

        return findings, missing_output

    def _compare_traces(
        self,
        capture: LegacyFormulaCapture,
        contract: ShapeComparisonContract,
    ) -> str | None:
        required_trace = contract.required_trace_components_json
        if not required_trace:
            return None
        if not isinstance(required_trace, list):
            return _Finding.TRACE_DIVERGENCE

        observed = capture.output_context_json.get("trace_components") or []
        if sorted(map(str, required_trace)) != sorted(map(str, observed)):
            return _Finding.TRACE_DIVERGENCE
        return None

    def _build_context_payload(
        self,
        window: ShadowValidationWindow,
        contract: ShapeComparisonContract,
        fep: FrozenEvaluationPackage,
        capture: LegacyFormulaCapture,
    ) -> dict[str, Any]:
        return {
            "channel_id": window.channel_id,
            "window_id": window.id,
            "window_authority_event_id": window.pricing_authority_event_id,
            "window_authority_head_version": window.pricing_authority_head_version,
            "window_pricing_policy_revision_id": window.pricing_policy_revision_id,
            "contract_id": contract.id,
            "contract_revision": contract.contract_revision,
            "contract_revision_checksum": contract.contract_checksum,
            "contract_output_lanes": contract.required_output_lanes_json,
            "fep_id": fep.id,
            "fep_translator_version": fep.translator_version,
            "fep_formula_shape_id": fep.formula_shape_id,
            "capture_id": capture.id,
            "capture_shape_id": capture.formula_shape_id,
            "capture_formula_rule_identity": capture.formula_rule_identity,
            "package_dependency_fingerprint": fep.dependency_fingerprint,
            "policy_revision_id": fep.pricing_policy_revision_id,
        }

    @staticmethod
    def _version(value: str, field: str) -> str:
        normalized = str(value).strip()
        if not _VERSION.fullmatch(normalized):
            raise ShadowValidationError(f"{field}_invalid")
        return normalized
