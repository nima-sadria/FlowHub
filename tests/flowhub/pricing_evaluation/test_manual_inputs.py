"""Deterministic current-decision resolution over an append-only lineage."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.flowhub.pricing_evaluation.contracts import ManualInputDecisionKind
from app.flowhub.pricing_evaluation.errors import DependencyResolutionError
from app.flowhub.pricing_evaluation.manual_inputs import DecisionRecord, resolve_current_decision

NOW = datetime(2026, 8, 7, 12, 0, 0)


def _decision(id_: str, kind: ManualInputDecisionKind, at: datetime) -> DecisionRecord:
    return DecisionRecord(id=id_, decision=kind, created_at=at)


def test_no_decisions_fails_closed_as_missing():
    with pytest.raises(DependencyResolutionError, match="manual_input_missing"):
        resolve_current_decision((), now=NOW, expires_at=None)


def test_single_approved_decision_resolves():
    decisions = (_decision("d1", ManualInputDecisionKind.APPROVED, NOW - timedelta(hours=1)),)
    current = resolve_current_decision(decisions, now=NOW, expires_at=None)
    assert current.id == "d1"


def test_ambiguous_same_timestamp_decisions_fail_closed():
    decisions = (
        _decision("d1", ManualInputDecisionKind.APPROVED, NOW - timedelta(hours=1)),
        _decision("d2", ManualInputDecisionKind.APPROVED, NOW - timedelta(hours=1)),
    )
    with pytest.raises(DependencyResolutionError, match="manual_input_decision_ambiguous"):
        resolve_current_decision(decisions, now=NOW, expires_at=None)


def test_a_later_revocation_supersedes_an_earlier_approval():
    decisions = (
        _decision("d1", ManualInputDecisionKind.APPROVED, NOW - timedelta(hours=2)),
        _decision("d2", ManualInputDecisionKind.REVOKED, NOW - timedelta(hours=1)),
    )
    with pytest.raises(DependencyResolutionError, match="manual_input_revoked"):
        resolve_current_decision(decisions, now=NOW, expires_at=None)


def test_a_later_rejection_supersedes_an_earlier_approval():
    decisions = (
        _decision("d1", ManualInputDecisionKind.APPROVED, NOW - timedelta(hours=2)),
        _decision("d2", ManualInputDecisionKind.REJECTED, NOW - timedelta(hours=1)),
    )
    with pytest.raises(DependencyResolutionError, match="manual_input_not_approved"):
        resolve_current_decision(decisions, now=NOW, expires_at=None)


def test_an_expired_approved_revision_fails_closed():
    decisions = (_decision("d1", ManualInputDecisionKind.APPROVED, NOW - timedelta(days=10)),)
    with pytest.raises(DependencyResolutionError, match="manual_input_expired"):
        resolve_current_decision(decisions, now=NOW, expires_at=NOW - timedelta(days=1))


def test_an_approval_after_a_revocation_is_current_again():
    decisions = (
        _decision("d1", ManualInputDecisionKind.APPROVED, NOW - timedelta(hours=3)),
        _decision("d2", ManualInputDecisionKind.REVOKED, NOW - timedelta(hours=2)),
        _decision("d3", ManualInputDecisionKind.APPROVED, NOW - timedelta(hours=1)),
    )
    current = resolve_current_decision(decisions, now=NOW, expires_at=None)
    assert current.id == "d3"
