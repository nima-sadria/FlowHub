"""Synchronous transaction-bound domain event bus for Workspace use cases."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.flowhub.unified_workspace.domain import checksum, utcnow
from app.flowhub.unified_workspace.models import UnifiedAuditEntry


@dataclass(frozen=True, slots=True)
class DomainEvent:
    event_type: str
    correlation_id: str
    user_id: int
    occurred_at: datetime = field(default_factory=utcnow)
    attributes: dict[str, Any] = field(default_factory=dict)


class DomainEventBus:
    def __init__(self) -> None:
        self._subscribers: list[Callable[[DomainEvent], None]] = []

    def subscribe(self, subscriber: Callable[[DomainEvent], None]) -> None:
        self._subscribers.append(subscriber)

    def publish(self, event: DomainEvent) -> None:
        for subscriber in tuple(self._subscribers):
            subscriber(event)


class PersistenceAuditSubscriber:
    """Append a domain event to the immutable business Audit in the caller transaction."""

    def __init__(self, db: Session, id_factory: Callable[[], str]) -> None:
        self.db = db
        self.id_factory = id_factory

    def __call__(self, event: DomainEvent) -> None:
        fields = dict(event.attributes)
        metadata = dict(fields.pop("metadata", {}) or {})
        safe_metadata = {
            key: value
            for key, value in metadata.items()
            if not any(
                token in key.lower() for token in ("password", "secret", "token", "credential")
            )
        }
        self.db.add(
            UnifiedAuditEntry(
                id=self.id_factory(),
                correlation_id=event.correlation_id,
                event_type=event.event_type,
                user_id=event.user_id,
                occurred_at=event.occurred_at,
                metadata_json=safe_metadata,
                request_metadata_json={},
                metadata_checksum=checksum(
                    {
                        "event": event.event_type,
                        "user": event.user_id,
                        "correlation": event.correlation_id,
                        "fields": fields,
                        "metadata": safe_metadata,
                    }
                ),
                **fields,
            )
        )
