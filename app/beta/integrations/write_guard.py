"""FlowHub Beta — permanent write guard (BU5).

Any code path that would attempt a write operation must call raise_write_blocked()
instead of proceeding.  This is intentional and permanent for the Beta phase.
"""

from __future__ import annotations

from fastapi import HTTPException

BETA_WRITE_BLOCKED = "Write operations are disabled in FlowHub Beta."


def raise_write_blocked() -> None:
    """Raise HTTP 403 immediately.  Call this from any endpoint that would write."""
    raise HTTPException(status_code=403, detail=BETA_WRITE_BLOCKED)
