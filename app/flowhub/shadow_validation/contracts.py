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
    CONTRACT_UNAVAILABLE = "comparison_contract_unavailable"
    LEGACY_OUTPUT_UNAVAILABLE = "comparison_legacy_output_unavailable"
    MATRIX_OUTPUT_UNAVAILABLE = "comparison_matrix_output_unavailable"
    CONTEXT_MISMATCH = "comparison_context_mismatch"
    EFFECTIVE_VALUE_DIVERGENCE = "comparison_effective_value_divergence"
    CANDIDATE_VALUE_DIVERGENCE = "comparison_candidate_value_divergence"
    DERIVATION_DIVERGENCE = "comparison_derivation_divergence"
    MATCH = "comparison_match"


class ShadowValidationReasonCode(StrEnum):
    NOT_POSSIBLE = ComparisonPrimaryClassification.NOT_POSSIBLE.value
    CONTRACT_UNAVAILABLE = ComparisonPrimaryClassification.CONTRACT_UNAVAILABLE.value
    PROVENANCE_PARTIAL = "comparison_provenance_partial"
    PROVENANCE_UNAVAILABLE = "comparison_provenance_unavailable"
    OUTPUT_UNAVAILABLE = "comparison_output_unavailable"
    CONTEXT_MISMATCH = ComparisonPrimaryClassification.CONTEXT_MISMATCH.value
    VALUE_DIVERGENCE = "comparison_value_divergence"
    DERIVATION_DIVERGENCE = ComparisonPrimaryClassification.DERIVATION_DIVERGENCE.value
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
