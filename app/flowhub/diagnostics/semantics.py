"""Stable, evidence-based diagnostic presentation semantics.

The legacy Diagnostics API exposed human status strings directly.  Keep those
strings for compatibility while publishing a machine-stable state and the
evidence needed by every UI to present the same meaning.
"""

from __future__ import annotations

from enum import StrEnum
from typing import NotRequired, TypedDict, cast


class DiagnosticState(StrEnum):
    HEALTHY = "HEALTHY"
    INFO = "INFO"
    NOT_CHECKED = "NOT_CHECKED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    DISABLED = "DISABLED"
    WARNING = "WARNING"
    ERROR = "ERROR"


class DiagnosticPresentation(TypedDict):
    status: str
    message: str
    state: str
    reason_code: str
    checked_at: str | None
    evidence_source: str
    is_actionable: bool
    recommended_action: str
    freshness_threshold_hours: NotRequired[int]


_LEGACY_STATUS = {
    DiagnosticState.HEALTHY: "Operational",
    DiagnosticState.INFO: "Information",
    DiagnosticState.NOT_CHECKED: "Not checked",
    DiagnosticState.NOT_APPLICABLE: "Not applicable",
    DiagnosticState.DISABLED: "Disabled",
    DiagnosticState.WARNING: "Warning",
    DiagnosticState.ERROR: "Error",
}


def diagnostic_presentation(
    state: DiagnosticState,
    message: str,
    *,
    reason_code: str,
    checked_at: str | None,
    evidence_source: str,
    is_actionable: bool = False,
    recommended_action: str = "",
    legacy_status: str | None = None,
    freshness_threshold_hours: int | None = None,
) -> DiagnosticPresentation:
    """Return one additive contract shared by all channel diagnostic checks."""

    result: dict[str, object] = {
        "status": legacy_status or _LEGACY_STATUS[state],
        "message": message,
        "state": state.value,
        "reason_code": reason_code,
        "checked_at": checked_at,
        "evidence_source": evidence_source,
        "is_actionable": is_actionable,
        "recommended_action": recommended_action,
    }
    if freshness_threshold_hours is not None:
        result["freshness_threshold_hours"] = freshness_threshold_hours
    return cast(DiagnosticPresentation, result)
