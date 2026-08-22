"""Closed identities shared by Frozen Evaluation Package callers.

Every enum here is a closed, persisted set (mirrored by a CheckConstraint in
``models.py``). Nothing here is free text and nothing is inferred.
"""

from __future__ import annotations

from enum import StrEnum


class ObservationSelectionMode(StrEnum):
    """Deterministic policy for pinning one Observation per required Source.

    See Authoritative Architecture rule 3: selection is deterministic and
    policy-driven. There is no silent fallback to another Observation.
    """

    LATEST_ELIGIBLE_AS_OF = "latest_eligible_as_of"
    ALIGNED_BUSINESS_CYCLE = "aligned_business_cycle"
    BUSINESS_EFFECTIVE_DATE = "business_effective_date"
    LAST_APPROVED = "last_approved"
    EXPLICIT_OBSERVATION = "explicit_observation"
    LEGACY_CONSUMED_OBSERVATION = "legacy_consumed_observation"


class FreshnessResult(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


class SkewResult(StrEnum):
    WITHIN_TOLERANCE = "within_tolerance"
    VIOLATION = "violation"
    NOT_APPLICABLE = "not_applicable"


class ManualInputKind(StrEnum):
    REFERENCE_PRICE = "reference_price"
    PRICING_FACTOR = "pricing_factor"
    PRICE_OVERRIDE = "price_override"
    PRICING_ADJUSTMENT = "pricing_adjustment"
    MANUAL_METADATA = "manual_metadata"


class ManualInputDecisionKind(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    REVOKED = "revoked"


class EffectiveOutputSource(StrEnum):
    """Which of the two preserved values is authoritative for this package."""

    CALCULATED_CANDIDATE = "calculated_candidate"
    OVERRIDE_VALUE = "override_value"


class DerivedOperator(StrEnum):
    """Closed set of typed derived operators.

    Every member is directly evidenced by
    ``docs/evidence/architecture/APPENDIX_A_FORMULA_CLASSIFICATION.md`` (the
    authoritative production-workbook formula-shape inventory). No operator
    exists here that is not required by that evidence:

    - ``ADD_CONSTANT``: fixed addend, evidenced by shapes A1/A3/A4/A5/A10/A11
      ("optional fixed addend" / "500,000 added").
    - ``MULTIPLY_PERCENT``: basis plus a percentage rate, evidenced by shapes
      A1/A3/A5/A10/A11 ("Basis plus percentage").
    - ``FLOOR_TO_STEP``: floor to the nearest step, evidenced by shapes
      A1/A3/A4/A10/A11 ("floor to 50,000" / "floor to 100,000").
    - ``ROUND_UP_TO_STEP``: round up to the nearest step, evidenced by shape
      A5 (``ROUNDUP(...,-2)``).
    - ``MIN_NONZERO_SELECTION``: minimum non-zero value across pinned
      dependencies, evidenced by shape A2 ("Basis selection: Minimum
      non-zero value across a same-row vendor range").
    - ``MULTIPLY_CONSTANT`` / ``DIVIDE_CONSTANT``: evidenced by shape A6,
      whose arithmetic is proven even though the shape's business meaning
      remains quarantined (Appendix A explicitly separates "arithmetic is
      proven" from "business meaning is not" — only the arithmetic primitive
      is adopted here, not the shape itself).

    Shapes A7 (display metric, not a Channel price target), A8 (metadata
    text copy, not numeric derivation), and the broken/anomalous shapes
    A9/A12/A13 do not evidence any additional operator and are intentionally
    excluded. No new operator may be added without equivalent Appendix A
    evidence — do not speculate.
    """

    ADD_CONSTANT = "add_constant"
    MULTIPLY_PERCENT = "multiply_percent"
    FLOOR_TO_STEP = "floor_to_step"
    ROUND_UP_TO_STEP = "round_up_to_step"
    MIN_NONZERO_SELECTION = "min_nonzero_selection"
    MULTIPLY_CONSTANT = "multiply_constant"
    DIVIDE_CONSTANT = "divide_constant"


class DependencyRefKind(StrEnum):
    """Closed set of dependency reference kinds usable inside a derived DAG."""

    OBSERVATION = "observation"
    MANUAL_INPUT = "manual_input"
    DERIVED = "derived"


DERIVED_MAX_DEPTH = 8
"""Bounded depth for a derived-value DAG (Authoritative Architecture rule: bounded depth)."""

PRICING_EVALUATION_ARITHMETIC_VERSION = "pricing-evaluation-arithmetic-v1"
"""Version pin for the exact-rational derived-value evaluator in ``derived.py``."""

FORMULA_SHAPES = (
    "A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "A10", "A11", "A12", "A13",
)
"""Closed set from Appendix A. A package always pins the shape it freezes evidence for."""
