"""Deterministic, policy-driven Observation selection. No silent fallback.

This module is framework-free: it operates on plain ``ObservationCandidate``
values supplied by the service layer (which is responsible for querying
``SourceObservation`` rows) and never touches the database itself. That keeps
selection logic exhaustively unit-testable without a Session.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.flowhub.pricing_evaluation.contracts import FreshnessResult, ObservationSelectionMode, SkewResult
from app.flowhub.pricing_evaluation.errors import (
    REASON_AS_OF_REQUIRED,
    REASON_BUSINESS_CYCLE_REQUIRED,
    REASON_BUSINESS_EFFECTIVE_DATE_REQUIRED,
    REASON_EXPLICIT_OBSERVATION_REQUIRED,
    REASON_OBSERVATION_AMBIGUOUS,
    REASON_OBSERVATION_MISSING,
    REASON_OBSERVATION_STALE,
    REASON_SELECTION_MODE_UNSUPPORTED,
    DependencyResolutionError,
)


@dataclass(frozen=True, slots=True)
class ObservationCandidate:
    observation_id: str
    checksum: str
    observed_at: datetime
    business_cycle_identity: str | None = None
    is_legacy_consumed: bool = False


@dataclass(frozen=True, slots=True)
class SelectionResult:
    candidate: ObservationCandidate
    freshness_result: FreshnessResult


def _latest_before(
    candidates: tuple[ObservationCandidate, ...], boundary: datetime
) -> ObservationCandidate:
    eligible = tuple(c for c in candidates if c.observed_at <= boundary)
    if not eligible:
        raise DependencyResolutionError(REASON_OBSERVATION_MISSING)
    newest = max(c.observed_at for c in eligible)
    tied = tuple(c for c in eligible if c.observed_at == newest)
    if len(tied) > 1:
        raise DependencyResolutionError(REASON_OBSERVATION_AMBIGUOUS)
    return tied[0]


def select_observation(
    *,
    mode: ObservationSelectionMode,
    candidates: tuple[ObservationCandidate, ...],
    now: datetime,
    as_of: datetime | None = None,
    business_cycle_identity: str | None = None,
    business_effective_date: datetime | None = None,
    explicit_observation_id: str | None = None,
    freshness_max_age: timedelta | None = None,
    require_fresh: bool = True,
) -> SelectionResult:
    """Select exactly one Observation per the documented mode, or fail closed.

    Authoritative Architecture rules 2-4, 11: every required Source resolves
    to exactly one immutable Observation; selection is deterministic and
    policy-driven; there is no silent fallback; missing/stale/ambiguous/
    unprovable dependencies fail closed.
    """

    if not candidates:
        raise DependencyResolutionError(REASON_OBSERVATION_MISSING)

    if mode is ObservationSelectionMode.LATEST_ELIGIBLE_AS_OF:
        if as_of is None:
            raise DependencyResolutionError(REASON_AS_OF_REQUIRED)
        selected = _latest_before(candidates, as_of)

    elif mode is ObservationSelectionMode.BUSINESS_EFFECTIVE_DATE:
        if business_effective_date is None:
            raise DependencyResolutionError(REASON_BUSINESS_EFFECTIVE_DATE_REQUIRED)
        selected = _latest_before(candidates, business_effective_date)

    elif mode is ObservationSelectionMode.ALIGNED_BUSINESS_CYCLE:
        if not business_cycle_identity:
            raise DependencyResolutionError(REASON_BUSINESS_CYCLE_REQUIRED)
        matching = tuple(
            c for c in candidates if c.business_cycle_identity == business_cycle_identity
        )
        if not matching:
            raise DependencyResolutionError(REASON_OBSERVATION_MISSING)
        if len(matching) > 1:
            raise DependencyResolutionError(REASON_OBSERVATION_AMBIGUOUS)
        selected = matching[0]

    elif mode is ObservationSelectionMode.LAST_APPROVED:
        # The caller is responsible for pre-filtering `candidates` down to an
        # approved set; this mode only breaks the tie deterministically.
        newest = max(c.observed_at for c in candidates)
        tied = tuple(c for c in candidates if c.observed_at == newest)
        if len(tied) > 1:
            raise DependencyResolutionError(REASON_OBSERVATION_AMBIGUOUS)
        selected = tied[0]

    elif mode is ObservationSelectionMode.EXPLICIT_OBSERVATION:
        if not explicit_observation_id:
            raise DependencyResolutionError(REASON_EXPLICIT_OBSERVATION_REQUIRED)
        matching = tuple(c for c in candidates if c.observation_id == explicit_observation_id)
        if not matching:
            raise DependencyResolutionError(REASON_OBSERVATION_MISSING)
        selected = matching[0]

    elif mode is ObservationSelectionMode.LEGACY_CONSUMED_OBSERVATION:
        matching = tuple(c for c in candidates if c.is_legacy_consumed)
        if not matching:
            raise DependencyResolutionError(REASON_OBSERVATION_MISSING)
        if len(matching) > 1:
            raise DependencyResolutionError(REASON_OBSERVATION_AMBIGUOUS)
        selected = matching[0]

    else:  # pragma: no cover - StrEnum closes the set; defensive fail-closed only.
        raise DependencyResolutionError(REASON_SELECTION_MODE_UNSUPPORTED)

    if freshness_max_age is None:
        freshness_result = FreshnessResult.UNKNOWN
    else:
        age = now - selected.observed_at
        if age < timedelta(0):
            freshness_result = FreshnessResult.UNKNOWN
        elif age <= freshness_max_age:
            freshness_result = FreshnessResult.FRESH
        else:
            freshness_result = FreshnessResult.STALE

    if require_fresh and freshness_result is FreshnessResult.STALE:
        raise DependencyResolutionError(REASON_OBSERVATION_STALE)

    return SelectionResult(candidate=selected, freshness_result=freshness_result)


def evaluate_cross_source_skew(
    observed_at_by_role: dict[str, datetime], *, tolerance: timedelta | None
) -> SkewResult:
    """Compare observation timestamps across every required Source role.

    Authoritative Architecture: fail closed on skew-invalid dependencies. This
    only computes the evidence; the caller decides whether a ``VIOLATION``
    blocks package creation.
    """

    if tolerance is None or len(observed_at_by_role) < 2:
        return SkewResult.NOT_APPLICABLE
    values = observed_at_by_role.values()
    spread = max(values) - min(values)
    return SkewResult.WITHIN_TOLERANCE if spread <= tolerance else SkewResult.VIOLATION
