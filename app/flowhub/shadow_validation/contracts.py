"""Closed identities and reason codes for Shadow Validation persistence."""

from __future__ import annotations

from enum import StrEnum


class ShadowValidationWindowState(StrEnum):
    COLLECTING = "collecting"
    ACCEPTED = "accepted"
    INVALIDATED = "invalidated"
    CLOSED = "closed"


class ValidationWindowEventKind(StrEnum):
    OPENED = "opened"
    ACCEPTED = "accepted"
    INVALIDATED = "invalidated"
    CLOSED = "closed"
    CAS_CONFLICT = "cas_conflict"


class ComparisonConfidence(StrEnum):
    VERIFIED = "verified"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class ComparisonPrimaryClassification(StrEnum):
    NOT_POSSIBLE = "comparison_not_possible"
    EXACT_MATCH = "exact_match"
    ACCEPTED_EXPECTED_ROUNDING = "accepted_expected_rounding"
    ACCEPTED_DOCUMENTED_SEMANTIC_DIFFERENCE = "accepted_documented_semantic_difference"
    REVIEW_REQUIRED = "review_required"
    CRITICAL_DIVERGENCE = "critical_divergence"
    CONTRACT_UNAVAILABLE = "comparison_contract_unavailable"
    OUTPUT_UNAVAILABLE = "comparison_output_unavailable"
    CONTEXT_MISMATCH = "comparison_context_mismatch"


class ShadowValidationReasonCode(StrEnum):
    NOT_POSSIBLE = ComparisonPrimaryClassification.NOT_POSSIBLE.value
    CONTRACT_UNAVAILABLE = ComparisonPrimaryClassification.CONTRACT_UNAVAILABLE.value
    PROVENANCE_PARTIAL = "comparison_provenance_partial"
    PROVENANCE_UNAVAILABLE = "comparison_provenance_unavailable"
    OUTPUT_UNAVAILABLE = "comparison_output_unavailable"
    CONTEXT_MISMATCH = ComparisonPrimaryClassification.CONTEXT_MISMATCH.value
    VALUE_DIVERGENCE = "comparison_value_divergence"
    CRITICAL = "critical_divergence"
    REVIEW_REQUIRED = ComparisonPrimaryClassification.REVIEW_REQUIRED.value
    ACCEPTED_EXPECTED_ROUNDING = ComparisonPrimaryClassification.ACCEPTED_EXPECTED_ROUNDING.value
    ACCEPTED_DOCUMENTED_SEMANTIC_DIFFERENCE = (
        ComparisonPrimaryClassification.ACCEPTED_DOCUMENTED_SEMANTIC_DIFFERENCE.value
    )
    COVERAGE_INCOMPLETE = "comparison_coverage_incomplete"
    EVIDENCE_EXPIRED = "comparison_evidence_expired"
    SCOPE_INVALIDATED = "comparison_scope_invalidated"
    CAS_CONFLICT = "comparison_cas_conflict"


class ShapeTargetKind(StrEnum):
    PRICE_TARGET = "price_target"
    NON_PRICE = "non_price"
    QUARANTINED = "quarantined"
    BROKEN = "broken"


class ShapeAcceptanceEffect(StrEnum):
    MAY_COUNT = "may_count"
    DIAGNOSTIC_ONLY = "diagnostic_only"
    BLOCKS_READINESS = "blocks_readiness"


class OutputLane(StrEnum):
    CANDIDATE = "candidate"
    EFFECTIVE = "effective"
    BOTH = "both"


class WindowReadinessState(StrEnum):
    READY = "ready"
    NOT_READY = "not_ready"


class WindowReadinessReason(StrEnum):
    COVERAGE_INCOMPLETE = ShadowValidationReasonCode.COVERAGE_INCOMPLETE.value
    EVIDENCE_EXPIRED = ShadowValidationReasonCode.EVIDENCE_EXPIRED.value
    SCOPE_INVALIDATED = ShadowValidationReasonCode.SCOPE_INVALIDATED.value
    CONTRACT_UNAVAILABLE = ShadowValidationReasonCode.CONTRACT_UNAVAILABLE.value
    NOT_POSSIBLE = ShadowValidationReasonCode.NOT_POSSIBLE.value
    CAS_CONFLICT = ShadowValidationReasonCode.CAS_CONFLICT.value
