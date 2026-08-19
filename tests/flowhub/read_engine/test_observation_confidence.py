"""Observation Confidence: pure compute() truth table.

Deliberately distinct from cache freshness -- see
ADR_CHANNEL_READ_ARCHITECTURE.md. Covers, among other things, the
"dead-letter history does not poison current health after recovery"
invariant: confidence is recomputed from current evidence every time, never
carried forward as a sticky flag.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.flowhub.read_engine.observation_confidence import (
    ConfidenceEvidence,
    ObservationConfidence,
    compute,
)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def test_never_observed_is_unknown():
    confidence, reason = compute(ConfidenceEvidence(last_fetched_at=None), now=_now())
    assert confidence is ObservationConfidence.UNKNOWN
    assert reason == "never_observed"


def test_entity_read_is_confirmed_regardless_of_age():
    # A targeted read is zero-staleness by construction: even if the
    # timestamp is somehow old (clock skew, replayed evidence), the
    # mechanism itself is the evidence of currentness.
    now = _now()
    old = now - timedelta(days=30)
    confidence, reason = compute(
        ConfidenceEvidence(last_fetched_at=old, read_mechanism="entity_read"), now=now
    )
    assert confidence is ObservationConfidence.CONFIRMED
    assert reason == "zero_staleness_read"


def test_post_apply_verification_is_confirmed():
    now = _now()
    confidence, _ = compute(
        ConfidenceEvidence(last_fetched_at=now, read_mechanism="post_apply_verification"), now=now
    )
    assert confidence is ObservationConfidence.CONFIRMED


def test_within_ttl_channel_scope_read_is_likely_fresh():
    now = _now()
    confidence, reason = compute(
        ConfidenceEvidence(last_fetched_at=now, read_mechanism="initial_full_read", channel_ttl_seconds=3600),
        now=now,
    )
    assert confidence is ObservationConfidence.LIKELY_FRESH
    assert reason == "within_channel_ttl"


def test_beyond_ttl_channel_scope_read_decays_to_stale():
    now = _now()
    old = now - timedelta(hours=2)
    confidence, reason = compute(
        ConfidenceEvidence(last_fetched_at=old, read_mechanism="modified_since", channel_ttl_seconds=3600),
        now=now,
    )
    assert confidence is ObservationConfidence.STALE
    assert reason == "beyond_channel_ttl"


def test_in_flight_entity_work_is_stale_not_unknown():
    now = _now()
    confidence, reason = compute(
        ConfidenceEvidence(last_fetched_at=now - timedelta(hours=2), entity_work_status="running", channel_ttl_seconds=3600),
        now=now,
    )
    assert confidence is ObservationConfidence.STALE
    assert reason == "entity_work_in_flight"


def test_entity_work_exhausted_retries_is_recovery_required():
    now = _now()
    confidence, reason = compute(
        ConfidenceEvidence(
            last_fetched_at=now,
            entity_work_status="failed",
            entity_work_attempt_count=5,
            entity_work_max_attempts=5,
        ),
        now=now,
    )
    assert confidence is ObservationConfidence.RECOVERY_REQUIRED
    assert reason == "entity_work_exhausted_retries"


def test_recovery_required_takes_precedence_over_a_fresh_timestamp():
    """Even a just-now last_fetched_at cannot mask exhausted entity-work
    retries -- the evidence that FlowHub tried and failed to observe a
    real change must not be silently dropped."""
    now = _now()
    confidence, _ = compute(
        ConfidenceEvidence(
            last_fetched_at=now,
            read_mechanism="initial_full_read",
            entity_work_status="failed",
            entity_work_attempt_count=5,
            entity_work_max_attempts=5,
        ),
        now=now,
    )
    assert confidence is ObservationConfidence.RECOVERY_REQUIRED


def test_recovery_required_does_not_persist_after_a_subsequent_successful_read():
    """The core 'dead-letter history does not poison health after
    recovery' invariant: compute() has no memory of the prior failed
    entity-work row once fresher evidence (no active failure, a recent
    read) is presented -- confidence is evidence-driven, never sticky."""
    now = _now()
    failed_confidence, _ = compute(
        ConfidenceEvidence(
            last_fetched_at=now - timedelta(hours=1),
            entity_work_status="failed",
            entity_work_attempt_count=5,
            entity_work_max_attempts=5,
        ),
        now=now,
    )
    assert failed_confidence is ObservationConfidence.RECOVERY_REQUIRED

    # A subsequent successful targeted read starts a *new* entity-work
    # row (status=None from this row's perspective, or "completed" -- either
    # way, not "failed" at max attempts) with fresh evidence.
    recovered_confidence, reason = compute(
        ConfidenceEvidence(last_fetched_at=now, read_mechanism="entity_read", entity_work_status="completed"),
        now=now,
    )
    assert recovered_confidence is ObservationConfidence.CONFIRMED
    assert reason == "zero_staleness_read"


def test_failed_with_attempts_remaining_is_not_recovery_required():
    """attempt_count < max_attempts means the work item will still retry
    -- premature to declare recovery required."""
    now = _now()
    confidence, _ = compute(
        ConfidenceEvidence(
            last_fetched_at=now - timedelta(hours=1),
            entity_work_status="failed",
            entity_work_attempt_count=2,
            entity_work_max_attempts=5,
            channel_ttl_seconds=3600,
        ),
        now=now,
    )
    assert confidence is not ObservationConfidence.RECOVERY_REQUIRED
