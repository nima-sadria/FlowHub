"""FlowHub setup API.

Web Setup Wizard API. All endpoints are unauthenticated while setup is
incomplete. Once setup is marked complete every endpoint returns 409 so
that the wizard cannot be re-run through the API without a DB reset.

Routes:
  GET  /api/v2/setup/status                      - public, always available
  POST /api/v2/setup/server-profile              - save server profile
  POST /api/v2/setup/database                    - verify DB + migration status
  POST /api/v2/setup/admin                       - create first administrator
  POST /api/v2/setup/complete                    - finalize and lock wizard

Security: after POST /setup/complete all setup endpoints return 409.
          POST /setup/admin additionally checks that no admin user exists yet.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.flowhub.auth.jwt_service import create_access_token
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.auth.password import hash_password
from app.flowhub.auth.refresh_token import generate_refresh_token, hash_refresh_token
from app.flowhub.auth.repository import create_audit_event, store_refresh_token
from app.flowhub.database import get_db
from app.flowhub.setup.service import AppConfigService

router = APIRouter(prefix="/setup", tags=["setup"])
logger = logging.getLogger(__name__)

_REFRESH_EXPIRE_DAYS = 30
_ADMIN_ROLES = ("owner", "super_admin", "admin")

_UTC = timezone.utc
_EMAIL_ERROR = "Enter a valid email address."


def _utcnow() -> datetime:
    return datetime.now(_UTC).replace(tzinfo=None)


# -- Guard helpers -------------------------------------------------------------

def _require_setup_not_complete(db: Session) -> AppConfigService:
    """Raise 409 if setup has already been completed."""
    svc = AppConfigService(db)
    if svc.is_setup_completed():
        raise HTTPException(
            status_code=409,
            detail="Setup has already been completed. Use Settings to change configuration.",
        )
    return svc


def _request_id(request: Request) -> str:
    return request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex[:12]}"


def _table_exists(db: Session, table_name: str) -> bool:
    try:
        return inspect(db.get_bind()).has_table(table_name)
    except SQLAlchemyError:
        return False


def _is_setup_completed_if_available(db: Session, request: Request) -> bool:
    if not _table_exists(db, "flowhub_app_config"):
        return False
    try:
        return AppConfigService(db).is_setup_completed()
    except SQLAlchemyError:
        logger.exception(
            "setup_state_check_failed request_id=%s method=%s path=%s",
            _request_id(request),
            request.method,
            request.url.path,
        )
        return False


def _has_admin_if_available(db: Session, request: Request) -> bool:
    if not _table_exists(db, "flowhub_users"):
        return False
    try:
        return db.query(FlowHubUser).filter(FlowHubUser.role.in_(_ADMIN_ROLES)).first() is not None
    except SQLAlchemyError:
        logger.exception(
            "setup_admin_check_failed request_id=%s method=%s path=%s",
            _request_id(request),
            request.method,
            request.url.path,
        )
        return False


def _get_config_service(db: Session) -> AppConfigService:
    return AppConfigService(db)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _get_current_FLOWHUB_revision(db: Session) -> str | None:
    try:
        row = db.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def _get_latest_FLOWHUB_revision() -> str | None:
    try:
        root = _repo_root()
        config = AlembicConfig(str(root / "alembic_flowhub.ini"))
        config.set_main_option("script_location", str(root / "alembic_flowhub"))
        heads = ScriptDirectory.from_config(config).get_heads()
        return heads[0] if len(heads) == 1 else None
    except Exception:
        return None


def _validate_email_value(value: str) -> str:
    email = value.strip().lower()
    if not email:
        raise ValueError(_EMAIL_ERROR)
    if " " in email or email.count("@") != 1:
        raise ValueError(_EMAIL_ERROR)

    local, domain = email.split("@", 1)
    if not local or not domain or len(domain) > 253 or "." not in domain:
        raise ValueError(_EMAIL_ERROR)

    labels = domain.split(".")
    label_re = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$")
    if any(not label or len(label) > 63 or not label_re.match(label) for label in labels):
        raise ValueError(_EMAIL_ERROR)
    if not re.match(r"^[A-Za-z]{2,63}$", labels[-1]):
        raise ValueError(_EMAIL_ERROR)
    if not re.match(r"^[^\s@]+$", local):
        raise ValueError(_EMAIL_ERROR)

    return email


# -- Request / Response models -------------------------------------------------

class ServerProfilePayload(BaseModel):
    domain: str
    port: int = 8085
    environment: str = "production"
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
        if v != "production":
            raise ValueError("Environment must be 'production'")
        return v


class AdminPayload(BaseModel):
    username: str
    email: str
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

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        return _validate_email_value(v)

    @field_validator("password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


# -- Endpoints -----------------------------------------------------------------

@router.get("/status")
async def setup_status(request: Request, db: Session = Depends(get_db)) -> dict:
    """Public endpoint: returns whether setup has been completed and if an admin exists."""
    app_config_table_exists = _table_exists(db, "flowhub_app_config")
    users_table_exists = _table_exists(db, "flowhub_users")
    return {
        "completed": _is_setup_completed_if_available(db, request),
        "has_admin": _has_admin_if_available(db, request),
        "database_initialized": app_config_table_exists and users_table_exists,
        "migrations_required": not (app_config_table_exists and users_table_exists),
    }


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
            "server.environment": "production",
            "server.timezone": body.timezone,
            "server.currency": body.currency,
        },
        updated_by="setup_wizard",
    )
    return {"ok": True}


@router.post("/database")
async def setup_database(request: Request, db: Session = Depends(get_db)) -> dict:
    if _is_setup_completed_if_available(db, request):
        raise HTTPException(
            status_code=409,
            detail="Setup has already been completed. Use Settings to change configuration.",
        )
    try:
        db.execute(text("SELECT 1"))
        connected = True
        error = None
    except Exception as exc:
        connected = False
        error = str(exc)

    current_revision = _get_current_FLOWHUB_revision(db) if connected else None
    latest_revision = _get_latest_FLOWHUB_revision()
    is_current = (
        current_revision == latest_revision
        if current_revision is not None and latest_revision is not None
        else None
    )

    database_name: str | None = None
    try:
        row = db.execute(text("SELECT current_database()")).fetchone()
        database_name = row[0] if row else None
    except Exception:
        pass

    return {
        "connected": connected,
        "migration_version": current_revision,
        "migrations_current": is_current is True,
        "current_revision": current_revision,
        "latest_revision": latest_revision,
        "is_current": is_current,
        "database_name": database_name,
        "error": error,
    }


@router.post("/admin")
async def setup_admin(
    body: AdminPayload,
    db: Session = Depends(get_db),
) -> dict:
    svc = _require_setup_not_complete(db)

    # Prevent creating a second admin through this endpoint
    existing_admin = db.query(FlowHubUser).filter(FlowHubUser.role.in_(_ADMIN_ROLES)).first()
    if existing_admin:
        raise HTTPException(
            status_code=409,
            detail="An owner or administrator account already exists. This endpoint is locked.",
        )

    # The setup endpoint can create exactly one initial privileged operator.
    # A plain admin could not later create or promote an owner, leaving a fresh
    # installation without a privileged recovery and lifecycle actor.
    hashed = hash_password(body.password)
    user = FlowHubUser(
        username=body.username,
        hashed_password=hashed,
        role="owner",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    svc.set("admin.email", body.email, updated_by="setup_wizard")

    create_audit_event(db, username=user.username, event="setup_owner_created", ip_address="setup_wizard")

    # Issue tokens so the wizard can continue authenticated if needed
    access = create_access_token(user.id, user.username, user.role)
    raw_refresh, refresh_hash = generate_refresh_token()
    expires_at = _utcnow() + timedelta(days=_REFRESH_EXPIRE_DAYS)
    store_refresh_token(db, user_id=user.id, token_hash=refresh_hash, expires_at=expires_at)

    return {"token": access, "refresh_token": raw_refresh, "username": user.username}


@router.post("/complete")
async def setup_complete(db: Session = Depends(get_db)) -> dict:
    svc = _require_setup_not_complete(db)

    # Require at least one admin user before allowing completion
    admin_exists = db.query(FlowHubUser).filter(FlowHubUser.role.in_(_ADMIN_ROLES)).first()
    if not admin_exists:
        raise HTTPException(
            status_code=422,
            detail="Cannot complete setup: no owner or administrator account has been created.",
        )

    svc.mark_setup_complete(updated_by="setup_wizard")
    create_audit_event(db, username="system", event="setup_completed", ip_address="setup_wizard")
    return {"ok": True, "message": "Setup complete. You can now sign in."}


# -- Connection test helpers ---------------------------------------------------
