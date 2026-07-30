"""Authenticated exchange-rate APIs. Provider credentials never cross this boundary."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.flowhub.auth.authorization import is_privileged
from app.flowhub.auth.dependencies import get_current_user
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.auth.repository import create_audit_event
from app.flowhub.database import get_db
from app.flowhub.exchange_rates.provider import ExchangeRateProviderError
from app.flowhub.exchange_rates.service import ExchangeRateService

router = APIRouter(prefix="/exchange-rates", tags=["exchange-rates"])


class SelectionUpdate(BaseModel):
    selections: list[str] = Field(min_length=3, max_length=3)

    @field_validator("selections")
    @classmethod
    def distinct(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized) or len(set(normalized)) != 3:
            raise ValueError("Exactly three distinct exchange rates are required.")
        return normalized


class AdminConfigUpdate(BaseModel):
    enabled: bool | None = None
    api_key: str | None = Field(default=None, max_length=500)
    refreshes_per_day: int | None = Field(default=None, ge=1)
    daily_request_limit: int | None = Field(default=None, ge=1)
    reserved_request_count: int | None = Field(default=None, ge=0)
    request_timeout: int | None = Field(default=None, ge=2, le=30)


def _service(db: Session) -> ExchangeRateService:
    return ExchangeRateService(db)


def _require_super_admin(user: FlowHubUser) -> FlowHubUser:
    if not is_privileged(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super Admin permission required.")
    return user


@router.get("/supported")
async def supported_rates(current_user: FlowHubUser = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    _ = current_user
    return {"items": [
        {
            "provider": row.provider_id,
            "external_symbol": row.external_symbol,
            "canonical_code": row.canonical_code,
            "display_name": row.display_name,
            "display_name_fa": row.display_name_fa,
            "classification": row.classification,
            "side": row.side,
            "unit": row.unit,
        }
        for row in _service(db).definitions()
    ]}


@router.get("/me")
async def current_selections(current_user: FlowHubUser = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    service = _service(db)
    return {"selections": [row.external_symbol for row in service.selections(current_user.id)], "rates": service.latest_for_user(current_user.id)}


@router.put("/me")
async def update_selections(body: SelectionUpdate, current_user: FlowHubUser = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    try:
        service = _service(db)
        service.update_selections(current_user.id, body.selections)
        return {"selections": body.selections, "rates": service.latest_for_user(current_user.id)}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/latest")
async def latest_rates(current_user: FlowHubUser = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return {"rates": _service(db).latest_for_user(current_user.id)}


@router.get("/admin/config")
async def admin_config(current_user: FlowHubUser = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    _require_super_admin(current_user)
    return _service(db).admin_config()


@router.put("/admin/config")
async def update_admin_config(body: AdminConfigUpdate, current_user: FlowHubUser = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    _require_super_admin(current_user)
    try:
        result = _service(db).update_admin_config(body.model_dump(exclude_none=True), current_user.username)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    create_audit_event(db, username=current_user.username, event="exchange_rate_provider_config_changed", ip_address="api")
    return result


@router.post("/admin/test-connection")
async def test_connection(current_user: FlowHubUser = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    _require_super_admin(current_user)
    service = _service(db)
    try:
        result = service.test_connection()
    except ExchangeRateProviderError as exc:
        create_audit_event(db, username=current_user.username, event="exchange_rate_connection_test_failed", ip_address="api")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"code": exc.code, "message": str(exc)}) from exc
    create_audit_event(db, username=current_user.username, event="exchange_rate_provider_connection_tested", ip_address="api")
    return result


@router.get("/admin/diagnostics")
async def diagnostics(current_user: FlowHubUser = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    _require_super_admin(current_user)
    return _service(db).diagnostics()


@router.post("/admin/refresh")
async def manual_refresh(current_user: FlowHubUser = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    _require_super_admin(current_user)
    result = _service(db).refresh(trigger="manual")
    create_audit_event(db, username=current_user.username, event="exchange_rate_manual_refresh", ip_address="api")
    if result.get("status") == "failed":
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=result)
    if result.get("status") in {"blocked", "unavailable", "disabled"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=result)
    return result


@router.post("/admin/usage-sync")
async def synchronize_usage(
    current_user: FlowHubUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _require_super_admin(current_user)
    result = _service(db).sync_usage(force=True)
    create_audit_event(
        db,
        username=current_user.username,
        event="exchange_rate_usage_reconciled",
        ip_address="api",
    )
    if result.get("status") == "error":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=result
        )
    return result
