"""FlowHub Beta — /api/v2/settings router (BU5).

Runtime settings management.  Credentials are NEVER returned to the frontend.
The frontend sees only 'Configured' / 'Not configured' indicators.

Routes:
  GET  /api/v2/settings                  — read non-secret settings + configured flags
  POST /api/v2/settings                  — update non-credential settings (tz, currency, etc.)
  POST /api/v2/settings/woocommerce      — replace WooCommerce credentials
  POST /api/v2/settings/nextcloud        — replace Nextcloud credentials

WRITE GUARD: any route that would mutate WooCommerce or Nextcloud product data
is permanently forbidden.  These routes only update local configuration; they
do not write to WooCommerce or Nextcloud.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.beta.auth.dependencies import get_current_user
from app.beta.auth.models import BetaUser
from app.beta.auth.repository import create_audit_event
from app.beta.database import get_db
from app.beta.setup.service import AppConfigService
from app.connectors.common.auth import AuthConfig
from app.connectors.destinations.woocommerce.connector import WooCommerceConnector
from app.connectors.sources.nextcloud.connector import NextcloudConnector

router = APIRouter(prefix="/settings", tags=["settings"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_wc_configured(cfg: AppConfigService) -> bool:
    return bool(
        cfg.get("woocommerce.url") and
        cfg.get("woocommerce.key") and
        cfg.get("woocommerce.secret")
    )


def _is_nc_configured(cfg: AppConfigService) -> bool:
    return bool(
        cfg.get("nextcloud.url") and
        cfg.get("nextcloud.username") and
        cfg.get("nextcloud.password")
    )


# ── Request models ────────────────────────────────────────────────────────────

class SettingsPatch(BaseModel):
    syncIntervalMinutes: int | None = None
    timezone: str | None = None
    currency: str | None = None

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        import zoneinfo
        try:
            zoneinfo.ZoneInfo(v)
        except Exception:
            raise ValueError(f"Invalid timezone '{v}'")
        return v

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not re.match(r"^[A-Z]{3}$", v):
            raise ValueError(f"Invalid currency code '{v}'")
        return v

    @field_validator("syncIntervalMinutes")
    @classmethod
    def _validate_interval(cls, v: int | None) -> int | None:
        if v is None:
            return v
        if not (5 <= v <= 1440):
            raise ValueError("Sync interval must be between 5 and 1440 minutes")
        return v


class WooCommerceCredentials(BaseModel):
    url: str
    key: str
    secret: str

    @field_validator("url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not re.match(r"^https?://", v, re.IGNORECASE):
            raise ValueError("URL must start with http:// or https://")
        return v


class NextcloudCredentials(BaseModel):
    url: str
    username: str
    password: str
    spreadsheet_path: str

    @field_validator("url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not re.match(r"^https?://", v, re.IGNORECASE):
            raise ValueError("URL must start with http:// or https://")
        return v

    @field_validator("spreadsheet_path")
    @classmethod
    def _validate_path(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("/"):
            v = "/" + v
        return v


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def get_settings(
    current_user: BetaUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return current application settings.  Credentials are never returned."""
    cfg = AppConfigService(db)
    return {
        "woocommerceUrl": cfg.get("woocommerce.url") or "",
        "nextcloudUrl": cfg.get("nextcloud.url") or "",
        "syncIntervalMinutes": int(cfg.get("server.sync_interval_minutes") or "60"),
        "timezone": cfg.get("server.timezone") or "UTC",
        "currency": cfg.get("server.currency") or "EUR",
        "environment": cfg.get("server.environment") or "beta",
        "wcConfigured": _is_wc_configured(cfg),
        "ncConfigured": _is_nc_configured(cfg),
    }


@router.post("")
async def update_settings(
    body: SettingsPatch,
    current_user: BetaUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Update non-credential settings (timezone, currency, sync interval)."""
    cfg = AppConfigService(db)
    pairs: dict[str, str] = {}

    if body.timezone is not None:
        pairs["server.timezone"] = body.timezone
    if body.currency is not None:
        pairs["server.currency"] = body.currency
    if body.syncIntervalMinutes is not None:
        pairs["server.sync_interval_minutes"] = str(body.syncIntervalMinutes)

    if not pairs:
        raise HTTPException(status_code=400, detail="No settings provided to update.")

    cfg.set_many(pairs, updated_by=current_user.username)
    create_audit_event(
        db,
        username=current_user.username,
        event="settings_changed",
        ip_address="api",
    )
    return {"ok": True, "updated": list(pairs.keys())}


@router.post("/woocommerce")
async def update_woocommerce(
    body: WooCommerceCredentials,
    current_user: BetaUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Replace WooCommerce credentials and test the connection."""
    result = await _test_woocommerce_connection(body.url, body.key, body.secret)
    if not result["ok"]:
        return result

    cfg = AppConfigService(db)
    cfg.set_many(
        {
            "woocommerce.url": body.url,
            "woocommerce.key": body.key,
            "woocommerce.secret": body.secret,
        },
        updated_by=current_user.username,
    )
    create_audit_event(
        db,
        username=current_user.username,
        event="woocommerce_connected",
        ip_address=body.url,
    )
    return result


@router.post("/nextcloud")
async def update_nextcloud(
    body: NextcloudCredentials,
    current_user: BetaUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Replace Nextcloud credentials and test the connection."""
    result = await _test_nextcloud_connection(body.url, body.username, body.password)
    if not result["ok"]:
        return result

    cfg = AppConfigService(db)
    cfg.set_many(
        {
            "nextcloud.url": body.url,
            "nextcloud.username": body.username,
            "nextcloud.password": body.password,
            "nextcloud.spreadsheet_path": body.spreadsheet_path,
        },
        updated_by=current_user.username,
    )
    create_audit_event(
        db,
        username=current_user.username,
        event="nextcloud_connected",
        ip_address=body.url,
    )
    return result


# ── Connection test helpers ───────────────────────────────────────────────────

async def _test_woocommerce_connection(url: str, key: str, secret: str) -> dict:
    auth = AuthConfig(
        auth_type="api_key",
        credentials={"url": url, "key": key, "secret": secret},
    )
    connector = WooCommerceConnector()
    result = await connector.test_connection(auth)
    return {"ok": result.ok, "message": result.message}


async def _test_nextcloud_connection(url: str, username: str, password: str) -> dict:
    auth = AuthConfig(
        auth_type="basic",
        credentials={"url": url, "username": username, "password": password},
    )
    connector = NextcloudConnector()
    result = await connector.test_connection(auth)
    return {"ok": result.ok, "message": result.message}
