"""Database-backed login throttling shared by every FlowHub application worker."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import FlowHubLoginRateLimit

_UTC = timezone.utc
MAX_ATTEMPTS = 5
WINDOW = timedelta(seconds=60)


def _utcnow() -> datetime:
    return datetime.now(_UTC).replace(tzinfo=None)


def consume_login_attempt(db: Session, ip_address: str, *, now: datetime | None = None) -> bool:
    """Atomically reserve one login attempt and return whether it is allowed."""
    now = now or _utcnow()
    for attempt in range(2):
        try:
            if db.get_bind().dialect.name == "sqlite":
                db.execute(text("BEGIN IMMEDIATE"))
            row = (
                db.query(FlowHubLoginRateLimit)
                .filter(FlowHubLoginRateLimit.ip_address == ip_address)
                .with_for_update()
                .one_or_none()
            )
            if row is None:
                row = FlowHubLoginRateLimit(
                    ip_address=ip_address,
                    window_started_at=now,
                    attempt_count=0,
                )
                db.add(row)
                db.flush()
            if now - row.window_started_at >= WINDOW:
                row.window_started_at = now
                row.attempt_count = 0
            if row.attempt_count >= MAX_ATTEMPTS:
                db.commit()
                return False
            row.attempt_count += 1
            db.commit()
            return True
        except IntegrityError:
            db.rollback()
            if attempt:
                raise
    return False  # pragma: no cover - defensive loop closure


def clear_login_attempts(db: Session, ip_address: str) -> None:
    """Clear an address after a successful login without retaining usernames."""
    db.query(FlowHubLoginRateLimit).filter(FlowHubLoginRateLimit.ip_address == ip_address).delete()
    db.commit()


def clear_all() -> None:
    """Legacy test compatibility hook; production state is database-backed."""
