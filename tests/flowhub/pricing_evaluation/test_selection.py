"""Deterministic multi-source Observation selection: fail closed, no silent fallback."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.flowhub.pricing_evaluation.contracts import FreshnessResult, ObservationSelectionMode, SkewResult
from app.flowhub.pricing_evaluation.errors import DependencyResolutionError
from app.flowhub.pricing_evaluation.selection import (
    ObservationCandidate,
    evaluate_cross_source_skew,
    select_observation,
)

NOW = datetime(2026, 8, 7, 12, 0, 0)


def _candidate(observation_id: str, observed_at: datetime, **kwargs) -> ObservationCandidate:
    return ObservationCandidate(
        observation_id=observation_id, checksum=f"cs-{observation_id}", observed_at=observed_at, **kwargs
    )


def test_latest_eligible_as_of_picks_the_newest_candidate_not_after_the_boundary():
    candidates = (
        _candidate("obs-1", NOW - timedelta(days=3)),
        _candidate("obs-2", NOW - timedelta(days=1)),
        _candidate("obs-3", NOW + timedelta(days=1)),  # after as_of, excluded
    )
    result = select_observation(
        mode=ObservationSelectionMode.LATEST_ELIGIBLE_AS_OF,
        candidates=candidates,
        now=NOW,
        as_of=NOW,
    )
    assert result.candidate.observation_id == "obs-2"


def test_latest_eligible_as_of_requires_the_as_of_parameter():
    with pytest.raises(DependencyResolutionError, match="as_of_required"):
        select_observation(
            mode=ObservationSelectionMode.LATEST_ELIGIBLE_AS_OF,
            candidates=(_candidate("obs-1", NOW),),
            now=NOW,
        )


def test_missing_source_fails_closed_with_no_candidates():
    with pytest.raises(DependencyResolutionError, match="observation_missing"):
        select_observation(
            mode=ObservationSelectionMode.LAST_APPROVED, candidates=(), now=NOW
        )


def test_stale_observation_fails_closed_when_freshness_is_required():
    candidates = (_candidate("obs-1", NOW - timedelta(days=30)),)
    with pytest.raises(DependencyResolutionError, match="observation_stale"):
        select_observation(
            mode=ObservationSelectionMode.LAST_APPROVED,
            candidates=candidates,
            now=NOW,
            freshness_max_age=timedelta(days=7),
            require_fresh=True,
        )


def test_stale_observation_is_reported_but_not_fatal_when_freshness_not_required():
    candidates = (_candidate("obs-1", NOW - timedelta(days=30)),)
    result = select_observation(
        mode=ObservationSelectionMode.LAST_APPROVED,
        candidates=candidates,
        now=NOW,
        freshness_max_age=timedelta(days=7),
        require_fresh=False,
    )
    assert result.freshness_result is FreshnessResult.STALE


def test_ambiguous_tie_fails_closed_rather_than_silently_picking_one():
    candidates = (
        _candidate("obs-1", NOW - timedelta(hours=1)),
        _candidate("obs-2", NOW - timedelta(hours=1)),
    )
    with pytest.raises(DependencyResolutionError, match="observation_ambiguous"):
        select_observation(mode=ObservationSelectionMode.LAST_APPROVED, candidates=candidates, now=NOW)


def test_aligned_business_cycle_selects_the_matching_cycle_identity():
    candidates = (
        _candidate("obs-1", NOW - timedelta(days=2), business_cycle_identity="2026-W31"),
        _candidate("obs-2", NOW - timedelta(days=1), business_cycle_identity="2026-W32"),
    )
    result = select_observation(
        mode=ObservationSelectionMode.ALIGNED_BUSINESS_CYCLE,
        candidates=candidates,
        now=NOW,
        business_cycle_identity="2026-W32",
    )
    assert result.candidate.observation_id == "obs-2"


def test_aligned_business_cycle_requires_the_cycle_identity_parameter():
    with pytest.raises(DependencyResolutionError, match="business_cycle_required"):
        select_observation(
            mode=ObservationSelectionMode.ALIGNED_BUSINESS_CYCLE,
            candidates=(_candidate("obs-1", NOW),),
            now=NOW,
        )


def test_business_effective_date_picks_the_latest_observation_not_after_the_date():
    candidates = (
        _candidate("obs-1", NOW - timedelta(days=10)),
        _candidate("obs-2", NOW - timedelta(days=5)),
    )
    result = select_observation(
        mode=ObservationSelectionMode.BUSINESS_EFFECTIVE_DATE,
        candidates=candidates,
        now=NOW,
        business_effective_date=NOW - timedelta(days=4),
    )
    assert result.candidate.observation_id == "obs-2"


def test_explicit_observation_selects_exactly_the_requested_id():
    candidates = (_candidate("obs-1", NOW), _candidate("obs-2", NOW))
    result = select_observation(
        mode=ObservationSelectionMode.EXPLICIT_OBSERVATION,
        candidates=candidates,
        now=NOW,
        explicit_observation_id="obs-2",
    )
    assert result.candidate.observation_id == "obs-2"


def test_explicit_observation_not_in_candidate_set_is_unprovable():
    with pytest.raises(DependencyResolutionError, match="observation_missing"):
        select_observation(
            mode=ObservationSelectionMode.EXPLICIT_OBSERVATION,
            candidates=(_candidate("obs-1", NOW),),
            now=NOW,
            explicit_observation_id="obs-does-not-exist",
        )


def test_legacy_consumed_observation_selects_the_marked_candidate():
    candidates = (
        _candidate("obs-1", NOW - timedelta(days=1)),
        _candidate("obs-2", NOW, is_legacy_consumed=True),
    )
    result = select_observation(
        mode=ObservationSelectionMode.LEGACY_CONSUMED_OBSERVATION, candidates=candidates, now=NOW
    )
    assert result.candidate.observation_id == "obs-2"


def test_cross_source_skew_within_tolerance():
    observed = {"vendor_a": NOW, "vendor_b": NOW - timedelta(hours=2)}
    assert (
        evaluate_cross_source_skew(observed, tolerance=timedelta(hours=6))
        is SkewResult.WITHIN_TOLERANCE
    )


def test_cross_source_skew_violation():
    observed = {"vendor_a": NOW, "vendor_b": NOW - timedelta(days=3)}
    assert evaluate_cross_source_skew(observed, tolerance=timedelta(hours=6)) is SkewResult.VIOLATION


def test_cross_source_skew_not_applicable_for_a_single_source():
    assert evaluate_cross_source_skew({"vendor_a": NOW}, tolerance=timedelta(hours=1)) is SkewResult.NOT_APPLICABLE
