"""FlowHub user administration API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.flowhub.auth.authorization import ADMIN_ROLES, is_privileged, is_privileged_role, require_admin
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.auth.password import hash_password
from app.flowhub.auth.repository import create_audit_event
from app.flowhub.database import get_db

router = APIRouter(prefix="/users", tags=["users"])

RoleName = Literal["owner", "super_admin", "admin", "viewer"]

class UserShape(BaseModel):
    id: int
    username: str
    role: str
    is_active: bool
    created_at: datetime
    is_admin: bool
    is_super_admin: bool


class UserListResponse(BaseModel):
    items: list[UserShape]
    total: int


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=150)
    password: str = Field(min_length=8, max_length=256)
    role: RoleName = "viewer"

    @field_validator("username")
    @classmethod
    def _clean_username(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Username is required.")
        return cleaned


class UserUpdateRequest(BaseModel):
    role: RoleName | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=256)


def _require_privileged_actor(user: FlowHubUser, message: str) -> None:
    if not is_privileged(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, message)


def _ensure_target_manageable(actor: FlowHubUser, target: FlowHubUser) -> None:
    if is_privileged(target) and not is_privileged(actor):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only owner or super-admin may modify privileged accounts.")


def _ensure_last_privileged_account_is_preserved(
    db: Session,
    target: FlowHubUser,
    *,
    next_role: str | None = None,
    next_active: bool | None = None,
) -> None:
    if not is_privileged(target):
        return
    remains_privileged = next_role is None or is_privileged_role(next_role)
    remains_active = next_active is None or next_active is True
    if remains_privileged and remains_active:
        return
    active_privileged_count = (
        db.query(FlowHubUser)
        .filter(FlowHubUser.role.in_({"owner", "super_admin"}), FlowHubUser.is_active.is_(True))
        .count()
    )
    if active_privileged_count <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "The last active owner or super-admin cannot be changed or disabled.")


def _shape(user: FlowHubUser) -> UserShape:
    return UserShape(
        id=user.id,
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
        is_admin=user.role in ADMIN_ROLES,
        is_super_admin=user.role in {"owner", "super_admin"},
    )


@router.get("", response_model=UserListResponse)
async def list_users(
    current_user: FlowHubUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserListResponse:
    rows = db.query(FlowHubUser).order_by(FlowHubUser.id.asc()).all()
    return UserListResponse(items=[_shape(row) for row in rows], total=len(rows))


@router.post("", response_model=UserShape, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreateRequest,
    current_user: FlowHubUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserShape:
    if is_privileged_role(body.role):
        _require_privileged_actor(current_user, "Only owner or super-admin may create privileged accounts.")
    existing = db.query(FlowHubUser).filter(FlowHubUser.username == body.username).first()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already exists.")
    row = FlowHubUser(
        username=body.username,
        hashed_password=hash_password(body.password),
        role=body.role,
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    create_audit_event(db, username=current_user.username, event="user_created", ip_address="api")
    return _shape(row)


@router.patch("/{user_id}", response_model=UserShape)
async def update_user(
    user_id: int,
    body: UserUpdateRequest,
    current_user: FlowHubUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserShape:
    row = db.get(FlowHubUser, user_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    _ensure_target_manageable(current_user, row)
    if body.role is not None and row.id == current_user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Users cannot change their own role.")
    if body.role is not None and is_privileged_role(body.role):
        _require_privileged_actor(current_user, "Only owner or super-admin may assign privileged roles.")
    _ensure_last_privileged_account_is_preserved(
        db,
        row,
        next_role=body.role,
        next_active=body.is_active,
    )
    original_role = row.role
    original_active = row.is_active
    if body.role is not None:
        row.role = body.role
    if body.is_active is not None:
        if row.id == current_user.id and body.is_active is False:
            raise HTTPException(status.HTTP_409_CONFLICT, "Current user cannot be deactivated.")
        row.is_active = body.is_active
    if body.password is not None:
        row.hashed_password = hash_password(body.password)
    db.commit()
    db.refresh(row)
    if row.role != original_role:
        create_audit_event(db, username=current_user.username, event="user_role_changed", ip_address="api")
    elif row.is_active != original_active:
        create_audit_event(db, username=current_user.username, event="user_activation_changed", ip_address="api")
    elif body.password is not None:
        create_audit_event(db, username=current_user.username, event="user_password_reset", ip_address="api")
    return _shape(row)
