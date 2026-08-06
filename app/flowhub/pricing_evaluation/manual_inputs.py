"""Deterministic current-decision resolution for immutable manual inputs.

No mutable "current status" field exists anywhere in this subsystem. The
current decision is always recomputed from the append-only
``ManualInputDecision`` lineage.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.flowhub.pricing_evaluation.contracts import ManualInputDecisionKind
from app.flowhub.pricing_evaluation.errors import (
    REASON_MANUAL_INPUT_DECISION_AMBIGUOUS,
    REASON_MANUAL_INPUT_EXPIRED,
    REASON_MANUAL_INPUT_MISSING,
    REASON_MANUAL_INPUT_NOT_APPROVED,
    REASON_MANUAL_INPUT_REVOKED,
    DependencyResolutionError,
)


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    id: str
    decision: ManualInputDecisionKind
    created_at: datetime


def resolve_current_decision(
    decisions: tuple[DecisionRecord, ...],
    *,
    now: datetime,
    expires_at: datetime | None,
) -> DecisionRecord:
    """Resolve the current effective decision, or fail closed.

    The most recently created decision is authoritative (append-only
    lineage: a later ``revoked``/``rejected`` decision always supersedes an
    earlier ``approved`` one). Two decisions sharing the exact same
    timestamp is treated as unprovable precedence, not silently broken by
    insertion order.
    """

    if not decisions:
        raise DependencyResolutionError(REASON_MANUAL_INPUT_MISSING)
    latest_ts = max(d.created_at for d in decisions)
    latest = tuple(d for d in decisions if d.created_at == latest_ts)
    if len(latest) > 1:
        raise DependencyResolutionError(REASON_MANUAL_INPUT_DECISION_AMBIGUOUS)
    current = latest[0]
    if current.decision is ManualInputDecisionKind.REVOKED:
        raise DependencyResolutionError(REASON_MANUAL_INPUT_REVOKED)
    if current.decision is ManualInputDecisionKind.REJECTED:
        raise DependencyResolutionError(REASON_MANUAL_INPUT_NOT_APPROVED)
    if expires_at is not None and expires_at <= now:
        raise DependencyResolutionError(REASON_MANUAL_INPUT_EXPIRED)
    return current
