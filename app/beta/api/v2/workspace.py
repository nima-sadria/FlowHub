"""FlowHub Beta — /api/v2/workspace router (BU5).

Stateless price-preview computation.  Every request downloads the current
spreadsheet, fetches all WC products, computes the diff in-memory, and
returns the result.  Nothing is persisted.

NO APPLY.  NO SCHEDULER.  NO WRITE OPERATIONS.

Routes:
  POST /api/v2/workspace/preview  — compute and return a read-only preview
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.beta.auth.dependencies import get_current_user
from app.beta.auth.models import BetaUser
from app.beta.auth.repository import create_audit_event
from app.beta.database import get_db
from app.beta.integrations.errors import IntegrationError
from app.beta.integrations.nextcloud import NextcloudClient
from app.beta.integrations.spreadsheet import load_workbook_bytes, parse_price_list
from app.beta.integrations.woocommerce import WooCommerceClient
from app.beta.setup.service import AppConfigService

router = APIRouter(prefix="/workspace", tags=["workspace"])

_UTC = timezone.utc


def _utcnow_iso() -> str:
    return datetime.now(_UTC).replace(tzinfo=None).isoformat() + "Z"


# ── Preview computation ───────────────────────────────────────────────────────

def _compute_preview(
    wc_products: list[dict],
    sheet_entries: dict[int, dict],
    currency: str,
) -> list[dict]:
    """Match WC products against spreadsheet entries; return price-change dicts."""
    changes: list[dict] = []

    for product in wc_products:
        wc_id = product.get("wcId")
        if not wc_id:
            continue
        entry = sheet_entries.get(wc_id)
        if entry is None:
            continue  # product not in spreadsheet — skip

        sheet_price = entry["price"]
        if sheet_price is None:
            continue  # OOS or parse error — skip

        wc_price = product.get("currentPrice", 0.0)
        if abs(wc_price - sheet_price) < 0.001:
            continue  # no change

        difference = sheet_price - wc_price
        change_pct = (difference / wc_price * 100) if wc_price != 0 else 0.0

        changes.append({
            "productId": str(wc_id),
            "productName": product.get("name", ""),
            "sku": product.get("sku", ""),
            "currentPrice": wc_price,
            "proposedPrice": sheet_price,
            "difference": round(difference, 4),
            "changePct": round(change_pct, 2),
            "currency": currency,
            "warning": entry.get("warning"),
        })

    return changes


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/preview")
async def start_preview(
    current_user: BetaUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Compute a read-only price preview.

    Fetches all WooCommerce products, downloads the Nextcloud spreadsheet,
    and returns the in-memory comparison.  Nothing is written anywhere.
    """
    cfg = AppConfigService(db)

    wc = WooCommerceClient.from_config(cfg)
    nc = NextcloudClient.from_config(cfg)
    nc_path = cfg.get("nextcloud.spreadsheet_path")

    if not wc:
        raise HTTPException(
            status_code=503,
            detail="WooCommerce is not configured. Go to Settings → WooCommerce Integration.",
        )
    if not nc or not nc_path:
        raise HTTPException(
            status_code=503,
            detail="Nextcloud is not configured. Go to Settings → Nextcloud Integration.",
        )

    currency = cfg.get("server.currency") or "EUR"

    # Audit: preview started
    create_audit_event(
        db,
        username=current_user.username,
        event="preview_started",
        ip_address="api",
    )

    try:
        # Fetch WC products (all pages) and spreadsheet in parallel
        import asyncio
        wc_products_task = asyncio.create_task(wc.get_all_products_for_preview())
        xlsx_bytes_task = asyncio.create_task(nc.download_file(nc_path))

        wc_products = await wc_products_task
        xlsx_bytes, _meta = await xlsx_bytes_task

        # Parse spreadsheet
        wb = load_workbook_bytes(xlsx_bytes)
        sheet_entries, duplicates = parse_price_list(wb)

        # Compute diff
        changes = _compute_preview(wc_products, sheet_entries, currency)

        # Audit: completed
        create_audit_event(
            db,
            username=current_user.username,
            event="preview_completed",
            ip_address=f"{len(changes)} changes",
        )

        preview_id = str(uuid.uuid4())
        started_at = _utcnow_iso()

        return {
            "id": preview_id,
            "sourceId": "nextcloud",
            "sourceName": "Nextcloud Spreadsheet",
            "state": "preview_ready",
            "totalChanges": len(changes),
            "changes": changes,
            "startedAt": started_at,
            "duplicateWarnings": [
                f"Product {d['product_id']}: found in sheets "
                f"'{d['prev_sheet']}' and '{d['final_sheet']}' — using '{d['final_sheet']}'"
                for d in duplicates
            ],
        }

    except HTTPException:
        raise
    except IntegrationError as exc:
        create_audit_event(
            db,
            username=current_user.username,
            event="preview_failed",
            ip_address=str(exc.message)[:45],
        )
        raise HTTPException(status_code=502, detail=exc.detail)
    except Exception as exc:
        create_audit_event(
            db,
            username=current_user.username,
            event="preview_failed",
            ip_address=str(exc)[:45],
        )
        raise HTTPException(
            status_code=502,
            detail=f"Preview failed: {str(exc)[:300]}",
        )


@router.get("/state")
async def get_state(
    _: BetaUser = Depends(get_current_user),
) -> dict:
    """Return current workspace state.  Always 'idle' in stateless BU5."""
    return {"state": "idle"}
