"""Observation Confidence: distinguishes Observed State from confidence that
the Observed State still represents external reality. Deliberately distinct
from cache freshness (a single fresh|stale|error flag) -- see
ADR_CHANNEL_READ_ARCHITECTURE.md. Never conflate with shadow_validation's
unrelated verified/partial/unavailable provenance vocabulary, which is
scoped to the Pricing Formula Migration, a different domain.

compute() is a pure function: no I/O, no side effects. Two call sites use
it with different evidence completeness:

- Write time (read_engine/service.py._shape_product): a row that was just
  successfully written always evaluates to CONFIRMED or LIKELY_FRESH --
  there is no entity-work failure history to consult at that instant, and
  none is needed (the write just succeeded).
- Diagnostics projection time (diagnostics/state_model.py): the fuller
  picture, including entity-work status, so a row can decay to STALE as
  its evidence ages, or escalate to RECOVERY_REQUIRED once entity-work has
  exhausted its retry budget for that entity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class ObservationConfidence(StrEnum):
    CONFIRMED = "CONFIRMED"
    LIKELY_FRESH = "LIKELY_FRESH"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


# Zero-staleness read mechanisms: the observation was fetched at the moment
# of evaluation, so it is CONFIRMED regardless of how old prior evidence was.
_ZERO_STALENESS_MECHANISMS = frozenset({"entity_read", "post_apply_verification"})


@dataclass(frozen=True)
class ConfidenceEvidence:
    last_fetched_at: datetime | None
    read_mechanism: str | None = None
    entity_work_status: str | None = None
    entity_work_attempt_count: int = 0
    entity_work_max_attempts: int = 0
    channel_ttl_seconds: int = 86_400


def compute(evidence: ConfidenceEvidence, *, now: datetime) -> tuple[ObservationConfidence, str]:
    """Returns (confidence, reason). reason is a stable, machine-readable
    code -- not user-facing prose."""
    if (
        evidence.entity_work_status == "failed"
        and evidence.entity_work_max_attempts > 0
        and evidence.entity_work_attempt_count >= evidence.entity_work_max_attempts
    ):
        return ObservationConfidence.RECOVERY_REQUIRED, "entity_work_exhausted_retries"

    if evidence.last_fetched_at is None:
        return ObservationConfidence.UNKNOWN, "never_observed"

    if evidence.read_mechanism in _ZERO_STALENESS_MECHANISMS:
        return ObservationConfidence.CONFIRMED, "zero_staleness_read"

    if evidence.entity_work_status in ("pending", "running"):
        return ObservationConfidence.STALE, "entity_work_in_flight"

    age_seconds = (now - evidence.last_fetched_at).total_seconds()
    if age_seconds <= evidence.channel_ttl_seconds:
        return ObservationConfidence.LIKELY_FRESH, "within_channel_ttl"
    return ObservationConfidence.STALE, "beyond_channel_ttl"
