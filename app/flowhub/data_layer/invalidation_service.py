"""Invalidation event recording service - reads and writes dl_invalidation_events."""

from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.flowhub.data_layer.models import DlInvalidationEvent


class InvalidationService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_summary(self) -> dict:
        """Return invalidation event count."""
        total = self._db.query(DlInvalidationEvent).count()
        return {"initialized": total > 0, "total": total}

    def list_recent(
        self,
        limit: int = 50,
        entity_type: Optional[str] = None,
    ) -> list[dict]:
        """Return recent invalidation events, newest first."""
        q = self._db.query(DlInvalidationEvent)
        if entity_type:
            q = q.filter(DlInvalidationEvent.entity_type == entity_type)
        rows = q.order_by(DlInvalidationEvent.created_at.desc()).limit(limit).all()
        return [_event_to_dict(r) for r in rows]

    def record(
        self,
        event_type: str,
        entity_type: str,
        entity_id: Optional[str] = None,
        connector_id: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> DlInvalidationEvent:
        """Record an invalidation event."""
        ev = DlInvalidationEvent(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            connector_id=connector_id,
            reason=reason,
            created_at=datetime.datetime.utcnow(),
        )
        self._db.add(ev)
        self._db.commit()
        self._db.refresh(ev)
        return ev


def _event_to_dict(r: DlInvalidationEvent) -> dict:
    return {
        "id": r.id,
        "event_type": r.event_type,
        "entity_type": r.entity_type,
        "entity_id": r.entity_id,
        "connector_id": r.connector_id,
        "reason": r.reason,
        "created_at": r.created_at.isoformat() + "Z" if r.created_at else None,
    }
