"""FlowHub - auth data access layer (BU2)."""

from __future__ import annotations

from datetime import datetime, timezone

_UTC = timezone.utc


def _utcnow() -> datetime:
    return datetime.now(_UTC).replace(tzinfo=None)

from sqlalchemy.orm import Session

from .models import FlowHubLoginAudit, FlowHubRefreshToken, FlowHubUser


def get_user_by_username(db: Session, username: str) -> FlowHubUser | None:
    return db.query(FlowHubUser).filter(FlowHubUser.username == username).first()


def get_user_by_id(db: Session, user_id: int) -> FlowHubUser | None:
    return db.query(FlowHubUser).filter(FlowHubUser.id == user_id).first()


def create_user(
    db: Session, *, username: str, hashed_password: str, role: str = "admin"
) -> FlowHubUser:
    user = FlowHubUser(username=username, hashed_password=hashed_password, role=role, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def store_refresh_token(
    db: Session, *, user_id: int, token_hash: str, expires_at: datetime
) -> FlowHubRefreshToken:
    rt = FlowHubRefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
    db.add(rt)
    db.commit()
    db.refresh(rt)
    return rt


def get_active_refresh_token(db: Session, token_hash: str) -> FlowHubRefreshToken | None:
    return (
        db.query(FlowHubRefreshToken)
        .filter(
            FlowHubRefreshToken.token_hash == token_hash,
            FlowHubRefreshToken.revoked_at == None,  # noqa: E711
        )
        .first()
    )


def revoke_refresh_token(db: Session, token_hash: str) -> None:
    rt = db.query(FlowHubRefreshToken).filter(FlowHubRefreshToken.token_hash == token_hash).first()
    if rt:
        rt.revoked_at = _utcnow()
        db.commit()


def revoke_all_user_tokens(db: Session, user_id: int) -> None:
    db.query(FlowHubRefreshToken).filter(
        FlowHubRefreshToken.user_id == user_id,
        FlowHubRefreshToken.revoked_at == None,  # noqa: E711
    ).update({"revoked_at": _utcnow()})
    db.commit()


def create_audit_event(
    db: Session, *, username: str, event: str, ip_address: str
) -> None:
    audit = FlowHubLoginAudit(username=username, event=event, ip_address=ip_address)
    db.add(audit)
    db.commit()
