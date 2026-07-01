"""FlowHub /api/health router.

Public health probe used by load balancers, Nginx Proxy Manager, and the CLI.
No authentication required.  Returns minimal status — no internal details exposed.
"""

import os

from fastapi import APIRouter

router = APIRouter()

_VERSION = os.getenv("FLOWHUB_VERSION", "1.0.0")
_ENVIRONMENT = os.getenv("FLOWHUB_ENV", "production")


@router.get("/health")
async def health() -> dict:
    """Minimal liveness probe.  Always returns 200 OK when the app is running."""
    return {"status": "ok", "env": _ENVIRONMENT, "version": _VERSION}
