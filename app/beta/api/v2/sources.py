"""FlowHub Beta — /api/v2/sources router (BU5).

Read-only view of configured data sources.  In BU5 the only source is the
Nextcloud XLSX spreadsheet set up during the Setup Wizard.

Routes:
  GET /api/v2/sources  — list configured sources (0 or 1 in BU5)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.beta.auth.dependencies import get_current_user
from app.beta.auth.models import BetaUser
from app.beta.database import get_db
from app.beta.integrations.errors import IntegrationError
from app.beta.integrations.nextcloud import NextcloudClient
from app.beta.setup.service import AppConfigService

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("")
async def list_sources(
    _: BetaUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return configured sources.

    BU5 produces at most one entry: the Nextcloud XLSX spreadsheet.
    If Nextcloud is not configured, returns an empty list.
    """
    cfg = AppConfigService(db)
    nc_url = cfg.get("nextcloud.url")
    nc_username = cfg.get("nextcloud.username")
    nc_path = cfg.get("nextcloud.spreadsheet_path")

    if not nc_url or not nc_username:
        return {"items": []}

    # Build display URL (path only — don't expose credentials)
    display_url = f"{nc_url}{nc_path or ''}"

    # Lightweight connectivity check to report status
    nc = NextcloudClient.from_config(cfg)
    status = "unconfigured"
    if nc:
        try:
            meta = await nc.get_file_meta(nc_path or "/")
            status = "active" if any(v for v in meta.values()) else "error"
        except (IntegrationError, Exception):
            status = "error"

    source = {
        "id": "nextcloud",
        "name": "Nextcloud Spreadsheet",
        "type": "nextcloud_excel",
        "displayUrl": display_url,
        "status": status,
        "lastSynced": None,
        "productCount": 0,  # populated lazily on preview
    }

    return {"items": [source]}
