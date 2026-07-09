"""FlowHub user administration API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.flowhub.auth.dependencies import get_current_user
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.auth.password import hash_password
from app.flowhub.database import get_db

router = APIRouter(prefix="/users", tags=["users"])

RoleName = Literal["owner", "super_admin", "admin", "viewer"]
ADMIN_ROLES = frozenset({"owner", "super_admin", "admin"})


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


def _require_admin(user: FlowHubUser) -> None:
    if user.role not in ADMIN_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin permission required.")


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
    current_user: FlowHubUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserListResponse:
    _require_admin(current_user)
    rows = db.query(FlowHubUser).order_by(FlowHubUser.id.asc()).all()
    return UserListResponse(items=[_shape(row) for row in rows], total=len(rows))


@router.post("", response_model=UserShape, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreateRequest,
    current_user: FlowHubUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserShape:
    _require_admin(current_user)
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
    return _shape(row)


@router.patch("/{user_id}", response_model=UserShape)
async def update_user(
    user_id: int,
    body: UserUpdateRequest,
    current_user: FlowHubUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserShape:
    _require_admin(current_user)
    row = db.get(FlowHubUser, user_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
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
    return _shape(row)
