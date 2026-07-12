"""FlowHub /api/v2/settings router.

Settings are local configuration and Integration Platform connector settings.
Secrets are never returned. Credential writes update local records only; live
connection validation is handled by future diagnostics/refresh flows.
"""

# ruff: noqa: B008

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator, model_validator
from sqlalchemy.orm import Session

from app.flowhub.auth.authorization import require_admin
from app.flowhub.auth.dependencies import get_current_user
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.auth.repository import create_audit_event
from app.flowhub.config.nextcloud_url import NextcloudUrlValidationError, normalize_nextcloud_url
from app.flowhub.database import get_db
from app.flowhub.integration_platform.service import IntegrationPlatformService
from app.flowhub.rate_limit.service import RateLimitService
from app.flowhub.setup.service import AppConfigService

router = APIRouter(prefix="/settings", tags=["settings"])


def _is_wc_configured(cfg: AppConfigService) -> bool:
    return bool(
        cfg.get("woocommerce.url") and cfg.get("woocommerce.key") and cfg.get("woocommerce.secret")
    )


def _is_nc_configured(cfg: AppConfigService) -> bool:
    return bool(
        cfg.get("nextcloud.url") and cfg.get("nextcloud.username") and cfg.get("nextcloud.password")
    )


def _public_nextcloud_url(cfg: AppConfigService) -> str:
    try:
        return normalize_nextcloud_url(
            cfg.get("nextcloud.url") or "",
            cfg.get("nextcloud.username") or "",
        )["server_root_url"]
    except NextcloudUrlValidationError:
        return ""


class SettingsPatch(BaseModel):
    syncIntervalMinutes: int | None = None
    timezone: str | None = None
    currency: str | None = None
    currencyUnit: str | None = None

    @model_validator(mode="after")
    def _validate_currency_unit_pair(self):
        if (
            self.currency == "IRR"
            and self.currencyUnit is not None
            and self.currencyUnit not in {"RIAL", "TOMAN"}
        ):
            raise ValueError("IRR requires an explicit RIAL or TOMAN pricing unit.")
        if self.currencyUnit is not None and not re.match(r"^[A-Z]{3,12}$", self.currencyUnit):
            raise ValueError("Currency unit must contain 3-12 uppercase letters.")
        return self

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        import zoneinfo

        try:
            zoneinfo.ZoneInfo(value)
        except Exception as exc:
            raise ValueError(f"Invalid timezone '{value}'") from exc
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


class RateLimitSettingsPatch(BaseModel):
    read_requests_per_minute: int
    write_requests_per_minute: int

    @field_validator("read_requests_per_minute", "write_requests_per_minute")
    @classmethod
    def _validate_rpm(cls, value: int) -> int:
        if not (1 <= value <= 1000):
            raise ValueError("Rate limit must be between 1 and 1000 requests per minute")
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
        "nextcloudUrl": _public_nextcloud_url(cfg),
        "syncIntervalMinutes": int(cfg.get("server.sync_interval_minutes") or "60"),
        "timezone": cfg.get("server.timezone") or "UTC",
        "currency": cfg.get("server.currency") or "EUR",
        "currencyUnit": cfg.get("server.currency_unit") or (cfg.get("server.currency") or "EUR"),
        "environment": cfg.get("server.environment") or "production",
        "wcConfigured": _is_wc_configured(cfg),
        "ncConfigured": _is_nc_configured(cfg),
        "connectors": [item.model_dump() for item in connectors],
        "runtime_write_blocked": True,
    }


@router.post("")
async def update_settings(
    body: SettingsPatch,
    current_user: FlowHubUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    cfg = AppConfigService(db)
    pairs: dict[str, str] = {}
    if body.timezone is not None:
        pairs["server.timezone"] = body.timezone
    if body.currency is not None:
        pairs["server.currency"] = body.currency
    if body.currencyUnit is not None:
        pairs["server.currency_unit"] = body.currencyUnit
    if body.syncIntervalMinutes is not None:
        pairs["server.sync_interval_minutes"] = str(body.syncIntervalMinutes)
    if not pairs:
        raise HTTPException(status_code=400, detail="No settings provided to update.")
    cfg.set_many(pairs, updated_by=current_user.username)
    create_audit_event(
        db, username=current_user.username, event="settings_changed", ip_address="api"
    )
    return {"ok": True, "updated": list(pairs.keys()), "runtime_write_blocked": True}


@router.get("/rate-limits")
async def get_rate_limits(
    current_user: FlowHubUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _ = current_user
    settings = RateLimitService(db).get_settings()
    return {
        "read_requests_per_minute": settings.read_requests_per_minute,
        "write_requests_per_minute": settings.write_requests_per_minute,
        "read_delay_ms": round((60.0 / settings.read_requests_per_minute) * 1000, 2),
        "write_delay_ms": round((60.0 / settings.write_requests_per_minute) * 1000, 2),
        "inherits_to_all_connectors": True,
        "per_connector_override_available": False,
        "scheduler_started": False,
        "automatic_sync": False,
        "runtime_write_blocked": True,
    }


@router.post("/rate-limits")
async def update_rate_limits(
    body: RateLimitSettingsPatch,
    current_user: FlowHubUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    settings = RateLimitService(db).update_settings(
        body.read_requests_per_minute,
        body.write_requests_per_minute,
        updated_by=current_user.username,
    )
    create_audit_event(
        db, username=current_user.username, event="rate_limits_changed", ip_address="api"
    )
    return {
        "ok": True,
        "read_requests_per_minute": settings.read_requests_per_minute,
        "write_requests_per_minute": settings.write_requests_per_minute,
        "read_delay_ms": round((60.0 / settings.read_requests_per_minute) * 1000, 2),
        "write_delay_ms": round((60.0 / settings.write_requests_per_minute) * 1000, 2),
        "inherits_to_all_connectors": True,
        "per_connector_override_available": False,
        "scheduler_started": False,
        "automatic_sync": False,
        "runtime_write_blocked": True,
    }


@router.post("/woocommerce")
async def update_woocommerce(
    body: WooCommerceCredentials,
    current_user: FlowHubUser = Depends(require_admin),
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
    create_audit_event(
        db, username=current_user.username, event="woocommerce_configured", ip_address=body.url
    )
    return {
        "ok": True,
        "message": "WooCommerce settings saved locally. Live validation is handled by diagnostics.",
        "runtime_write_blocked": True,
    }


@router.post("/nextcloud")
async def update_nextcloud(
    body: NextcloudCredentials,
    current_user: FlowHubUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    try:
        normalized = normalize_nextcloud_url(body.url, body.username)
    except NextcloudUrlValidationError as exc:
        raise HTTPException(
            status_code=422, detail={"code": exc.code, "message": str(exc)}
        ) from exc
    cfg = AppConfigService(db)
    cfg.set_many(
        {
            "nextcloud.url": normalized["server_root_url"],
            "nextcloud.webdav_files_root_url": normalized["webdav_files_root_url"],
            "nextcloud.username": normalized["username"],
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
            "url": normalized["server_root_url"],
            "username": normalized["username"],
            "password": body.password,
            "spreadsheet_path": body.spreadsheet_path,
        },
    )
    create_audit_event(
        db,
        username=current_user.username,
        event="nextcloud_configured",
        ip_address="local-settings",
    )
    return {
        "ok": True,
        "message": "Nextcloud settings saved locally. Live validation is handled by diagnostics.",
        "runtime_write_blocked": True,
    }
