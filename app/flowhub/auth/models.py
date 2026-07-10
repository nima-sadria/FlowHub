"""FlowHub - auth ORM models (BU2).

Tables: flowhub_users, flowhub_refresh_tokens, flowhub_login_audit.
All tables are FlowHub-only; production schema is never touched.
"""

from __future__ import annotations

from datetime import datetime, timezone

_UTC = timezone.utc


def _utcnow() -> datetime:
    return datetime.now(_UTC).replace(tzinfo=None)

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.flowhub.database import FlowHubBase


class FlowHubUser(FlowHubBase):
    __tablename__ = "flowhub_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)

    refresh_tokens: Mapped[list[FlowHubRefreshToken]] = relationship(
        "FlowHubRefreshToken", back_populates="user", cascade="all, delete-orphan"
    )


class FlowHubRefreshToken(FlowHubBase):
    __tablename__ = "flowhub_refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("flowhub_users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)

    user: Mapped[FlowHubUser] = relationship("FlowHubUser", back_populates="refresh_tokens")


class FlowHubLoginAudit(FlowHubBase):
    __tablename__ = "flowhub_login_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    event: Mapped[str] = mapped_column(String(50), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)


class FlowHubLoginRateLimit(FlowHubBase):
    """Database-backed login attempt window shared by all application workers."""

    __tablename__ = "flowhub_login_rate_limits"

    ip_address: Mapped[str] = mapped_column(String(45), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
