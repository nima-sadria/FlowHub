"""FlowHub /api/v2/settings router.

Settings are local configuration and Integration Platform connector settings.
Secrets are never returned. Credential writes update local records only; live
connection validation is handled by future diagnostics/refresh flows.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.flowhub.auth.dependencies import get_current_user
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.auth.repository import create_audit_event
from app.flowhub.database import get_db
from app.flowhub.integration_platform.service import IntegrationPlatformService
from app.flowhub.setup.service import AppConfigService

router = APIRouter(prefix="/settings", tags=["settings"])


def _is_wc_configured(cfg: AppConfigService) -> bool:
    return bool(cfg.get("woocommerce.url") and cfg.get("woocommerce.key") and cfg.get("woocommerce.secret"))


def _is_nc_configured(cfg: AppConfigService) -> bool:
    return bool(cfg.get("nextcloud.url") and cfg.get("nextcloud.username") and cfg.get("nextcloud.password"))


class SettingsPatch(BaseModel):
    syncIntervalMinutes: int | None = None
    timezone: str | None = None
    currency: str | None = None

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        import zoneinfo

        try:
            zoneinfo.ZoneInfo(value)
        except Exception:
            raise ValueError(f"Invalid timezone '{value}'")
        return value

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not re.match(r"^[A-Z]{3}$", value):
            raise ValueError(f"Invalid currency code '{value}'")
        return value

    @field_validator("syncIntervalMinutes")
    @classmethod
    def _validate_interval(cls, value: int | None) -> int | None:
        if value is None:
            return value
        if not (5 <= value <= 1440):
            raise ValueError("Sync interval must be between 5 and 1440 minutes")
        return value


class WooCommerceCredentials(BaseModel):
    url: str
    key: str
    secret: str

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not re.match(r"^https?://", value, re.IGNORECASE):
            raise ValueError("URL must start with http:// or https://")
        return value


class NextcloudCredentials(BaseModel):
    url: str
    username: str
    password: str
    spreadsheet_path: str

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not re.match(r"^https?://", value, re.IGNORECASE):
            raise ValueError("URL must start with http:// or https://")
        return value

    @field_validator("spreadsheet_path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        value = value.strip()
        return value if value.startswith("/") else f"/{value}"


@router.get("")
async def get_settings(
    current_user: FlowHubUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _ = current_user
    cfg = AppConfigService(db)
    connectors = IntegrationPlatformService(db).settings_summary()
    return {
        "woocommerceUrl": cfg.get("woocommerce.url") or "",
        "nextcloudUrl": cfg.get("nextcloud.url") or "",
        "syncIntervalMinutes": int(cfg.get("server.sync_interval_minutes") or "60"),
        "timezone": cfg.get("server.timezone") or "UTC",
        "currency": cfg.get("server.currency") or "EUR",
        "environment": cfg.get("server.environment") or "production",
        "wcConfigured": _is_wc_configured(cfg),
        "ncConfigured": _is_nc_configured(cfg),
        "connectors": [item.model_dump() for item in connectors],
        "runtime_write_blocked": True,
    }


@router.post("")
async def update_settings(
    body: SettingsPatch,
    current_user: FlowHubUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
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
    create_audit_event(db, username=current_user.username, event="settings_changed", ip_address="api")
    return {"ok": True, "updated": list(pairs.keys()), "runtime_write_blocked": True}


@router.post("/woocommerce")
async def update_woocommerce(
    body: WooCommerceCredentials,
    current_user: FlowHubUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    cfg = AppConfigService(db)
    cfg.set_many(
        {
            "woocommerce.url": body.url,
            "woocommerce.key": body.key,
            "woocommerce.secret": body.secret,
        },
        updated_by=current_user.username,
    )
    IntegrationPlatformService(db).ensure_connector_from_settings(
        connector_type="woocommerce",
        connector_id="woocommerce:primary",
        name="WooCommerce",
        values={"url": body.url, "key": body.key, "secret": body.secret},
    )
    create_audit_event(db, username=current_user.username, event="woocommerce_configured", ip_address=body.url)
    return {
        "ok": True,
        "message": "WooCommerce settings saved locally. Live validation is handled by diagnostics.",
        "runtime_write_blocked": True,
    }


@router.post("/nextcloud")
async def update_nextcloud(
    body: NextcloudCredentials,
    current_user: FlowHubUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
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
    IntegrationPlatformService(db).ensure_connector_from_settings(
        connector_type="nextcloud",
        connector_id="nextcloud:primary",
        name="Nextcloud Spreadsheet",
        values={
            "url": body.url,
            "username": body.username,
            "password": body.password,
            "spreadsheet_path": body.spreadsheet_path,
        },
    )
    create_audit_event(db, username=current_user.username, event="nextcloud_configured", ip_address=body.url)
    return {
        "ok": True,
        "message": "Nextcloud settings saved locally. Live validation is handled by diagnostics.",
        "runtime_write_blocked": True,
    }
