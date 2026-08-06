"""Stable, machine-readable failures for Frozen Evaluation Package construction.

Every failure carries a closed ``code`` only. Callers must never format a raw
lower-layer exception (DB driver text, connector text, secret-bearing values)
into these errors; only the fixed reason codes below are permitted.
"""

from __future__ import annotations


class PricingEvaluationError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class DependencyResolutionError(PricingEvaluationError):
    """Fail-closed: a required dependency was missing, stale, ambiguous, or unprovable."""


class DerivedValueError(PricingEvaluationError):
    """Fail-closed: a derived-value definition or evaluation could not proceed safely."""


# -- Stable reason codes -------------------------------------------------------
# Observation selection (Authoritative Architecture rules 2, 3, 4, 11)
REASON_OBSERVATION_MISSING = "observation_missing"
REASON_OBSERVATION_STALE = "observation_stale"
REASON_OBSERVATION_AMBIGUOUS = "observation_ambiguous"
REASON_OBSERVATION_UNPROVABLE = "observation_unprovable"
REASON_OBSERVATION_SOURCE_MISMATCH = "observation_source_mismatch"
REASON_CROSS_SOURCE_SKEW_VIOLATION = "cross_source_skew_violation"
REASON_SELECTION_MODE_UNSUPPORTED = "selection_mode_unsupported"
REASON_EXPLICIT_OBSERVATION_REQUIRED = "explicit_observation_required"
REASON_BUSINESS_CYCLE_REQUIRED = "business_cycle_required"
REASON_BUSINESS_EFFECTIVE_DATE_REQUIRED = "business_effective_date_required"
REASON_AS_OF_REQUIRED = "as_of_required"

# Manual inputs (Authoritative Architecture rule 5)
REASON_MANUAL_INPUT_MISSING = "manual_input_missing"
REASON_MANUAL_INPUT_DECISION_AMBIGUOUS = "manual_input_decision_ambiguous"
REASON_MANUAL_INPUT_NOT_APPROVED = "manual_input_not_approved"
REASON_MANUAL_INPUT_REVOKED = "manual_input_revoked"
REASON_MANUAL_INPUT_EXPIRED = "manual_input_expired"
REASON_MANUAL_INPUT_SCOPE_MISMATCH = "manual_input_scope_mismatch"

# Derived values (Authoritative Architecture rules 6, 7, 8, 9)
REASON_DERIVED_CYCLE_DETECTED = "derived_cycle_detected"
REASON_DERIVED_DEPTH_EXCEEDED = "derived_depth_exceeded"
REASON_DERIVED_DEPENDENCY_MISSING = "derived_dependency_missing"
REASON_DERIVED_CROSS_PACKAGE_DEPENDENCY = "derived_cross_package_dependency"
REASON_DERIVED_OPERATOR_UNSUPPORTED = "derived_operator_unsupported"
REASON_DERIVED_PARAMETERS_INVALID = "derived_parameters_invalid"
REASON_DERIVED_NO_ELIGIBLE_INPUT = "derived_no_eligible_input"

# Package pins (Authoritative Architecture rule 10)
REASON_FX_SNAPSHOT_MISSING = "fx_snapshot_missing"
REASON_CHANNEL_CONFIG_REVISION_MISSING = "channel_config_revision_missing"
REASON_CHANNEL_NOT_FOUND = "pricing_evaluation_channel_not_found"

# Generic fallback (never wraps raw lower-layer text)
REASON_DEPENDENCY_UNRESOLVABLE = "package_dependency_unresolvable"
