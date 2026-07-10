"""Shared authorization helpers for state-changing FlowHub routes."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status

from .dependencies import get_current_user
from .models import FlowHubUser


ROLE_RANK = {
    "viewer": 0,
    "admin": 1,
    "super_admin": 2,
    "owner": 3,
}
ADMIN_ROLES = frozenset({"owner", "super_admin", "admin"})
PRIVILEGED_ROLES = frozenset({"owner", "super_admin"})


def role_rank(role: str) -> int:
    return ROLE_RANK.get(role, -1)


def is_admin(user: FlowHubUser) -> bool:
    return user.role in ADMIN_ROLES


def is_privileged(user: FlowHubUser) -> bool:
    return role_rank(user.role) >= role_rank("super_admin")


def is_privileged_role(role: str) -> bool:
    return role_rank(role) >= role_rank("super_admin")


def require_admin(current_user: FlowHubUser = Depends(get_current_user)) -> FlowHubUser:
    """Require an owner, super-admin, or admin for configuration mutations."""
    if not is_admin(current_user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin permission required.")
    return current_user
