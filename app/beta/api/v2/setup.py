"""FlowHub Beta — /api/v2/setup router (BU4).

Web Setup Wizard API. All endpoints are unauthenticated while setup is
incomplete. Once setup is marked complete every endpoint returns 409 so
that the wizard cannot be re-run through the API without a DB reset.

Routes:
  GET  /api/v2/setup/status                      — public, always available
  POST /api/v2/setup/server-profile              — save server profile
  POST /api/v2/setup/database                    — verify DB + migration status
  POST /api/v2/setup/admin                       — create first administrator
  POST /api/v2/setup/integrations/woocommerce    — save + test WC credentials
  POST /api/v2/setup/integrations/nextcloud      — save + test NC credentials
  POST /api/v2/setup/complete                    — finalize and lock wizard

Security: after POST /setup/complete all setup endpoints return 409.
          POST /setup/admin additionally checks that no admin user exists yet.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.beta.auth.jwt_service import create_access_token
from app.beta.auth.models import BetaUser
from app.beta.auth.password import hash_password
from app.beta.auth.refresh_token import generate_refresh_token, hash_refresh_token
from app.beta.auth.repository import create_audit_event, store_refresh_token
from app.beta.database import get_db
from app.beta.setup.service import AppConfigService

router = APIRouter(prefix="/setup", tags=["setup"])

_REFRESH_EXPIRE_DAYS = 30

_UTC = timezone.utc


def _utcnow() -> datetime:
    return datetime.now(_UTC).replace(tzinfo=None)


# ── Guard helpers ─────────────────────────────────────────────────────────────

def _require_setup_not_complete(db: Session) -> AppConfigService:
    """Raise 409 if setup has already been completed."""
    svc = AppConfigService(db)
    if svc.is_setup_completed():
        raise HTTPException(
            status_code=409,
            detail="Setup has already been completed. Use Settings to change configuration.",
        )
    return svc


def _get_config_service(db: Session) -> AppConfigService:
    return AppConfigService(db)


# ── Request / Response models ─────────────────────────────────────────────────

class ServerProfilePayload(BaseModel):
    domain: str
    port: int = 8085
    environment: str = "beta"
    timezone: str = "UTC"
    currency: str = "USD"

    @field_validator("domain")
    @classmethod
    def _validate_domain(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Domain is required")
        return v

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, v: str) -> str:
        import zoneinfo
        try:
            zoneinfo.ZoneInfo(v)
        except Exception:
            raise ValueError(f"Invalid timezone '{v}'. Use IANA format, e.g. UTC or Europe/Amsterdam")
        return v

    @field_validator("currency")
    @classmethod
    def _validate_currency(cls, v: str) -> str:
        if not re.match(r"^[A-Z]{3}$", v):
            raise ValueError(f"Invalid currency '{v}'. Use 3-letter ISO 4217 code, e.g. USD, EUR, IRR")
        return v

    @field_validator("port")
    @classmethod
    def _validate_port(cls, v: int) -> int:
        if not (1 <= v <= 65535):
            raise ValueError("Port must be between 1 and 65535")
        return v

    @field_validator("environment")
    @classmethod
    def _validate_env(cls, v: str) -> str:
        allowed = {"beta", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"Environment must be one of: {', '.join(sorted(allowed))}")
        return v


class AdminPayload(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def _validate_username(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Username must be at least 3 characters")
        if not re.match(r"^[a-zA-Z0-9_\-\.]+$", v):
            raise ValueError("Username may only contain letters, numbers, underscores, hyphens, and dots")
        return v

    @field_validator("password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class WooCommercePayload(BaseModel):
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


class NextcloudPayload(BaseModel):
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

@router.get("/status")
async def setup_status(db: Session = Depends(get_db)) -> dict:
    """Public endpoint: returns whether setup has been completed."""
    svc = AppConfigService(db)
    return {"completed": svc.is_setup_completed()}


@router.post("/server-profile")
async def setup_server_profile(
    body: ServerProfilePayload,
    db: Session = Depends(get_db),
) -> dict:
    svc = _require_setup_not_complete(db)
    svc.set_many(
        {
            "server.domain": body.domain,
            "server.port": str(body.port),
            "server.environment": body.environment,
            "server.timezone": body.timezone,
            "server.currency": body.currency,
        },
        updated_by="setup_wizard",
    )
    return {"ok": True}


@router.post("/database")
async def setup_database(db: Session = Depends(get_db)) -> dict:
    _require_setup_not_complete(db)
    try:
        db.execute(text("SELECT 1"))
        connected = True
        error = None
    except Exception as exc:
        connected = False
        error = str(exc)

    # Read current Alembic revision from the alembic_version table
    migration_version: str | None = None
    try:
        row = db.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).fetchone()
        migration_version = row[0] if row else None
    except Exception:
        pass

    return {
        "connected": connected,
        "migration_version": migration_version,
        "migrations_current": migration_version == "beta_004",
        "error": error,
    }


@router.post("/admin")
async def setup_admin(
    body: AdminPayload,
    db: Session = Depends(get_db),
) -> dict:
    svc = _require_setup_not_complete(db)

    # Prevent creating a second admin through this endpoint
    existing_admin = db.query(BetaUser).filter(BetaUser.role == "admin").first()
    if existing_admin:
        raise HTTPException(
            status_code=409,
            detail="An administrator account already exists. This endpoint is locked.",
        )

    # Create the admin user
    hashed = hash_password(body.password)
    user = BetaUser(
        username=body.username,
        hashed_password=hashed,
        role="admin",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    create_audit_event(db, username=user.username, event="setup_admin_created", ip_address="setup_wizard")

    # Issue tokens so the wizard can continue authenticated if needed
    access = create_access_token(user.id, user.username, user.role)
    raw_refresh, refresh_hash = generate_refresh_token()
    expires_at = _utcnow() + timedelta(days=_REFRESH_EXPIRE_DAYS)
    store_refresh_token(db, user_id=user.id, token_hash=refresh_hash, expires_at=expires_at)

    return {"token": access, "refresh_token": raw_refresh, "username": user.username}


@router.post("/integrations/woocommerce")
async def setup_woocommerce(
    body: WooCommercePayload,
    db: Session = Depends(get_db),
) -> dict:
    svc = _require_setup_not_complete(db)

    # Save credentials first (regardless of connection test result)
    svc.set_many(
        {
            "woocommerce.url": body.url,
            "woocommerce.key": body.key,
            "woocommerce.secret": body.secret,
        },
        updated_by="setup_wizard",
    )

    # Test connection
    result = await _test_woocommerce(body.url, body.key, body.secret)
    return result


@router.post("/integrations/nextcloud")
async def setup_nextcloud(
    body: NextcloudPayload,
    db: Session = Depends(get_db),
) -> dict:
    svc = _require_setup_not_complete(db)

    # Save credentials first (regardless of connection test result)
    svc.set_many(
        {
            "nextcloud.url": body.url,
            "nextcloud.username": body.username,
            "nextcloud.password": body.password,
            "nextcloud.spreadsheet_path": body.spreadsheet_path,
        },
        updated_by="setup_wizard",
    )

    # Test connection
    result = await _test_nextcloud(body.url, body.username, body.password)
    return result


@router.post("/complete")
async def setup_complete(db: Session = Depends(get_db)) -> dict:
    svc = _require_setup_not_complete(db)

    # Require at least one admin user before allowing completion
    admin_exists = db.query(BetaUser).filter(BetaUser.role == "admin").first()
    if not admin_exists:
        raise HTTPException(
            status_code=422,
            detail="Cannot complete setup: no administrator account has been created.",
        )

    svc.mark_setup_complete(updated_by="setup_wizard")
    create_audit_event(db, username="system", event="setup_completed", ip_address="setup_wizard")
    return {"ok": True, "message": "Setup complete. You can now sign in."}


# ── Connection test helpers ───────────────────────────────────────────────────

async def _test_woocommerce(url: str, key: str, secret: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            r = await client.get(
                f"{url}/wp-json/wc/v3/products",
                params={"per_page": "1"},
                auth=(key, secret),
            )
        if r.status_code == 200:
            return {"ok": True, "message": "Connected successfully"}
        if r.status_code == 401:
            return {"ok": False, "message": "Authentication failed — check your consumer key and secret"}
        if r.status_code == 403:
            return {"ok": False, "message": "Access denied — ensure the API key has read permissions"}
        if r.status_code == 404:
            return {"ok": False, "message": "WooCommerce REST API not found — verify the store URL and that WooCommerce is installed"}
        return {"ok": False, "message": f"Unexpected response: HTTP {r.status_code}"}
    except httpx.ConnectError:
        return {"ok": False, "message": "Could not connect — check the URL and that the store is reachable"}
    except httpx.TimeoutException:
        return {"ok": False, "message": "Connection timed out — the store may be slow or unreachable"}
    except Exception as exc:
        return {"ok": False, "message": f"Connection error: {str(exc)[:200]}"}


async def _test_nextcloud(url: str, username: str, password: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            r = await client.request(
                "PROPFIND",
                f"{url}/remote.php/dav/files/{username}/",
                auth=(username, password),
                headers={"Depth": "0"},
            )
        if r.status_code in (200, 207):
            return {"ok": True, "message": "Connected successfully"}
        if r.status_code == 401:
            return {"ok": False, "message": "Authentication failed — check your username and app password"}
        if r.status_code == 404:
            return {"ok": False, "message": "User not found or WebDAV is disabled on this Nextcloud instance"}
        return {"ok": False, "message": f"Unexpected response: HTTP {r.status_code}"}
    except httpx.ConnectError:
        return {"ok": False, "message": "Could not connect — check the URL and that Nextcloud is reachable"}
    except httpx.TimeoutException:
        return {"ok": False, "message": "Connection timed out — Nextcloud may be slow or unreachable"}
    except Exception as exc:
        return {"ok": False, "message": f"Connection error: {str(exc)[:200]}"}
