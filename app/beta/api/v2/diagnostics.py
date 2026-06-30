"""FlowHub Beta — /api/v2/diagnostics router (BU5).

Adds a real GET /status endpoint (BU5) alongside the existing CP1.3 stubs.

Routes:
  GET  /api/v2/diagnostics/status  — live system + integration status  (BU5)
  POST /api/v2/diagnostics/run     — stub (B6)
  GET  /api/v2/diagnostics/history — stub (B6)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session
from typing import Optional

from app.beta.auth.dependencies import get_current_user
from app.beta.auth.models import BetaUser
from app.beta.database import get_db
from app.beta.integrations.errors import IntegrationError
from app.beta.integrations.nextcloud import NextcloudClient
from app.beta.integrations.woocommerce import WooCommerceClient
from app.beta.setup.service import AppConfigService

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


class DiagnosticRunRequest(BaseModel):
    target: str = "all"


class DiagnosticCheckShape(BaseModel):
    check_name: str
    category: str
    target: str
    status: str
    failure_class: str
    severity: str
    message: str
    repair_hint: str
    duration_ms: float
    checked_at: str
    details: dict
    skipped_because: Optional[str]


class RepairStepShape(BaseModel):
    step_number: int
    description: str
    command: Optional[str]
    detail: Optional[str]


class DiagnosticRunResponse(BaseModel):
    target: str
    started_at: str
    completed_at: str
    duration_ms: float
    overall_status: str
    overall_failure_class: str
    overall_severity: str
    summary: str
    checks: list[DiagnosticCheckShape]
    repair_steps: list[RepairStepShape]


@router.get("/status")
async def diagnostics_status(
    _: BetaUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return live diagnostics for all system components."""
    cfg = AppConfigService(db)

    # ── Database ─────────────────────────────────────────────────────────────
    db_status = "error"
    db_detail = None
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:
        db_detail = str(exc)[:200]

    # ── WooCommerce ───────────────────────────────────────────────────────────
    wc = WooCommerceClient.from_config(cfg)
    if wc is None:
        wc_status = "unconfigured"
        wc_latency: float | None = None
        wc_count: int | None = None
        wc_detail: str | None = "WooCommerce credentials not set"
    else:
        wc_ok, wc_msg, wc_latency = await wc.test_connection()
        wc_status = "ok" if wc_ok else "error"
        wc_detail = None if wc_ok else wc_msg
        if wc_ok:
            try:
                wc_count = await wc.count_products()
            except (IntegrationError, Exception):
                wc_count = None
        else:
            wc_count = None

    # ── Nextcloud ─────────────────────────────────────────────────────────────
    nc = NextcloudClient.from_config(cfg)
    nc_path = cfg.get("nextcloud.spreadsheet_path")
    if nc is None:
        nc_status = "unconfigured"
        nc_latency: float | None = None
        nc_last_modified: str | None = None
        nc_detail: str | None = "Nextcloud credentials not set"
    else:
        nc_ok, nc_msg, nc_latency = await nc.test_connection()
        nc_status = "ok" if nc_ok else "error"
        nc_detail = None if nc_ok else nc_msg
        nc_last_modified = None
        if nc_ok and nc_path:
            try:
                meta = await nc.get_file_meta(nc_path)
                nc_last_modified = meta.get("last_modified")
            except (IntegrationError, Exception):
                pass

    from datetime import datetime, timezone
    checked_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"

    return {
        "database": {"status": db_status, "detail": db_detail},
        "woocommerce": {
            "status": wc_status,
            "latencyMs": round(wc_latency, 1) if wc_latency is not None else None,
            "productCount": wc_count,
            "detail": wc_detail,
        },
        "nextcloud": {
            "status": nc_status,
            "latencyMs": round(nc_latency, 1) if nc_latency is not None else None,
            "lastModified": nc_last_modified,
            "detail": nc_detail,
        },
        "checkedAt": checked_at,
    }


@router.post("/run", response_model=DiagnosticRunResponse)
async def run_diagnostics(body: DiagnosticRunRequest) -> DiagnosticRunResponse:
    """Trigger an on-demand diagnostic run.

    Admin permission required (enforced in B7).
    Live implementation in B6.
    """
    raise NotImplementedError("Diagnostic run endpoint implemented in B6.")


@router.get("/history")
async def diagnostic_history(limit: int = 10) -> dict:
    """Return recent diagnostic run history.

    Persistence layer implemented in B6.
    """
    return {"runs": [], "note": "Diagnostic history available in B6."}
