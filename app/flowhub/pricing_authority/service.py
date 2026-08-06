"""CAS-protected authority decisions for Channel price writes."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.pricing_authority.contracts import PricingAuthority, PricingOrigin
from app.flowhub.pricing_authority.errors import PricingAuthorityConflict, PricingAuthorityError
from app.flowhub.pricing_authority.models import (
    ChannelPricingAuthorityEvent,
    ChannelPricingAuthorityHead,
    PricingAuthorityWriteRejection,
)
from app.flowhub.unified_workspace.domain import utcnow
from app.flowhub.unified_workspace.models import WorkspaceChannel


def _id() -> str:
    return str(uuid.uuid4())


@dataclass(frozen=True, slots=True)
class PricingAuthoritySnapshot:
    channel_id: str
    authority: PricingAuthority
    event_id: str
    head_version: int


_ALLOWED_TRANSITIONS: dict[PricingAuthority, frozenset[PricingAuthority]] = {
    PricingAuthority.LEGACY_FORMULA_ENGINE: frozenset({PricingAuthority.MIGRATION_LOCKED}),
    PricingAuthority.MIGRATION_LOCKED: frozenset(
        {PricingAuthority.LEGACY_FORMULA_ENGINE, PricingAuthority.PRICING_MATRIX}
    ),
    PricingAuthority.PRICING_MATRIX: frozenset({PricingAuthority.MIGRATION_LOCKED}),
}


class ChannelPricingAuthorityService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def ensure_channel_head(
        self,
        channel_id: str,
        *,
        actor_reference: str = "system:channel-seed",
        correlation_id: str = "",
    ) -> PricingAuthoritySnapshot:
        """Create the deterministic legacy default for a Channel without a head."""
        head = self.db.get(ChannelPricingAuthorityHead, channel_id)
        if head is not None:
            return self._snapshot(head)
        if self.db.get(WorkspaceChannel, channel_id) is None:
            raise PricingAuthorityError("pricing_authority_channel_not_found")

        event_id = _id()
        event = ChannelPricingAuthorityEvent(
            id=event_id,
            channel_id=channel_id,
            previous_authority=None,
            new_authority=PricingAuthority.LEGACY_FORMULA_ENGINE.value,
            expected_head_version=0,
            predecessor_event_id=None,
            actor_user_id=None,
            actor_reference=actor_reference,
            reason="Initial Channel pricing authority seed.",
            correlation_id=correlation_id,
            request_metadata_json={},
        )
        head = ChannelPricingAuthorityHead(
            channel_id=channel_id,
            current_authority=PricingAuthority.LEGACY_FORMULA_ENGINE.value,
            effective_event_id=event_id,
            head_version=0,
        )
        try:
            with self.db.begin_nested():
                self.db.add_all((event, head))
                self.db.flush()
        except IntegrityError:
            self.db.expire_all()
            existing = self.db.get(ChannelPricingAuthorityHead, channel_id)
            if existing is not None:
                return self._snapshot(existing)
            raise
        return self._snapshot(head)

    def snapshot(self, channel_id: str) -> PricingAuthoritySnapshot:
        return self.ensure_channel_head(channel_id)

    def transition(
        self,
        *,
        channel_id: str,
        new_authority: PricingAuthority,
        expected_head_version: int,
        reason: str,
        user: FlowHubUser,
        correlation_id: str = "",
        request_metadata: dict[str, Any] | None = None,
    ) -> PricingAuthoritySnapshot:
        head = self.ensure_channel_head(channel_id)
        if head.head_version != expected_head_version:
            raise PricingAuthorityConflict()
        if new_authority not in _ALLOWED_TRANSITIONS[head.authority]:
            raise PricingAuthorityError("pricing_authority_transition_invalid")

        event_id = _id()
        event = ChannelPricingAuthorityEvent(
            id=event_id,
            channel_id=channel_id,
            previous_authority=head.authority.value,
            new_authority=new_authority.value,
            expected_head_version=expected_head_version,
            predecessor_event_id=head.event_id,
            actor_user_id=user.id,
            actor_reference=user.username,
            reason=reason.strip(),
            correlation_id=correlation_id,
            request_metadata_json=dict(request_metadata or {}),
        )
        try:
            self.db.add(event)
            self.db.flush()
            updated = (
                self.db.query(ChannelPricingAuthorityHead)
                .filter(
                    ChannelPricingAuthorityHead.channel_id == channel_id,
                    ChannelPricingAuthorityHead.head_version == expected_head_version,
                )
                .update(
                    {
                        ChannelPricingAuthorityHead.current_authority: new_authority.value,
                        ChannelPricingAuthorityHead.effective_event_id: event_id,
                        ChannelPricingAuthorityHead.head_version: expected_head_version + 1,
                        ChannelPricingAuthorityHead.updated_at: utcnow(),
                    },
                    synchronize_session=False,
                )
            )
            if updated != 1:
                raise PricingAuthorityConflict()
            self.db.commit()
            self.db.expire_all()
        except Exception:
            self.db.rollback()
            raise
        return self.snapshot(channel_id)

    def assert_write_authorized(
        self,
        *,
        channel_id: str,
        origin: PricingOrigin | None,
        expected_event_id: str | None,
        expected_head_version: int | None,
    ) -> PricingAuthoritySnapshot:
        head = self.snapshot(channel_id)
        if origin is None:
            raise PricingAuthorityError("pricing_origin_not_authorized")
        if expected_event_id is not None and expected_event_id != head.event_id:
            raise PricingAuthorityError("pricing_authority_conflict")
        if expected_head_version is not None and expected_head_version != head.head_version:
            raise PricingAuthorityError("pricing_authority_conflict")
        if head.authority is PricingAuthority.MIGRATION_LOCKED:
            raise PricingAuthorityError("pricing_authority_locked")
        if origin.value != head.authority.value:
            raise PricingAuthorityError("pricing_origin_not_authorized")
        return head

    def record_write_rejection(
        self,
        *,
        channel_id: str,
        listing_id: str,
        operation_id: str,
        origin: PricingOrigin | None,
        expected_event_id: str | None,
        expected_head_version: int | None,
        reason_code: str,
        correlation_id: str,
    ) -> None:
        head = self.db.get(ChannelPricingAuthorityHead, channel_id)
        self.db.add(
            PricingAuthorityWriteRejection(
                id=_id(),
                channel_id=channel_id,
                listing_id=listing_id,
                operation_id=operation_id,
                pricing_origin=origin.value if origin is not None else None,
                current_authority=head.current_authority if head is not None else None,
                current_event_id=head.effective_event_id if head is not None else None,
                current_head_version=head.head_version if head is not None else None,
                expected_event_id=expected_event_id,
                expected_head_version=expected_head_version,
                reason_code=reason_code,
                correlation_id=correlation_id,
            )
        )

    @staticmethod
    def _snapshot(head: ChannelPricingAuthorityHead) -> PricingAuthoritySnapshot:
        return PricingAuthoritySnapshot(
            channel_id=head.channel_id,
            authority=PricingAuthority(head.current_authority),
            event_id=head.effective_event_id,
            head_version=head.head_version,
        )
