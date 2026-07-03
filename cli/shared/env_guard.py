"""FlowHub - Environment safety guard."""

from __future__ import annotations

from app.flowhub.config import ConfigProfile


class ProductionResourceError(Exception):
    """Raised when a write operation is attempted in PRODUCTION profile."""


def require_FLOWHUB_env(profile: ConfigProfile) -> None:
    """Assert the active profile is not PRODUCTION; raise otherwise.

    Called before any write or mutating operation. Read-only diagnostics
    are always permitted regardless of profile.
    """
    if profile.is_production():
        raise ProductionResourceError(
            "This command is blocked in the PRODUCTION profile. "
            "Only read-only operations (status, health, diagnostics) are "
            "permitted. Write operations must be performed by the production "
            "installer outside this CLI."
        )
