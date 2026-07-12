# ruff: noqa: B008
"""Role-compatible permission mapping for Unified Workspace operations."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status

from app.flowhub.auth.dependencies import get_current_user
from app.flowhub.auth.models import FlowHubUser

WORKSPACE_PERMISSIONS = frozenset(
    {
        "workspace.read",
        "workspace.create",
        "workspace.edit",
        "draft.save",
        "review.generate",
        "apply.execute",
        "channel_cache.refresh",
        "mapping.approve",
        "audit.read",
        "workspace.admin",
    }
)

ROLE_WORKSPACE_PERMISSIONS: dict[str, frozenset[str]] = {
    "owner": WORKSPACE_PERMISSIONS,
    "super_admin": WORKSPACE_PERMISSIONS,
    "admin": WORKSPACE_PERMISSIONS,
    "viewer": frozenset({"workspace.read", "audit.read"}),
}


def has_workspace_permission(user: FlowHubUser, permission: str) -> bool:
    return permission in ROLE_WORKSPACE_PERMISSIONS.get(user.role, frozenset())


def require_workspace_permission(permission: str):
    if permission not in WORKSPACE_PERMISSIONS:
        raise ValueError(f"Unknown Workspace permission: {permission}")

    async def dependency(user: FlowHubUser = Depends(get_current_user)) -> FlowHubUser:
        if not has_workspace_permission(user, permission):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                {
                    "code": "WORKSPACE_PERMISSION_DENIED",
                    "message": f"Permission {permission} is required.",
                },
            )
        return user

    return dependency
