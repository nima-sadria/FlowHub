"""Atomic Listing guard shared by Apply, Mapping, and cache mutation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import inspect
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from app.flowhub.unified_workspace.models import Listing

NON_TERMINAL_APPLY_STATES = frozenset(
    {"pending", "running", "reconciliation_required", "recovering"}
)


class ListingGuardConflict(RuntimeError):
    def __init__(self, channel_id: str, listing_id: str, apply_job_id: str) -> None:
        self.channel_id = channel_id
        self.listing_id = listing_id
        self.apply_job_id = apply_job_id
        super().__init__(f"Listing {channel_id}/{listing_id} is owned by Apply {apply_job_id}.")


def acquire_listing_guard(db: Session, channel_id: str, listing_id: str) -> Listing:
    """Lock the stable Listing row and reject any durable Apply ownership."""
    from app.flowhub.unified_workspace.models import ApplyJob, Listing, WorkspaceLock

    listing = (
        db.query(Listing).filter_by(id=listing_id, channel_id=channel_id).with_for_update().one()
    )
    lock = (
        db.query(WorkspaceLock)
        .filter_by(channel_id=channel_id, listing_id=listing_id)
        .with_for_update()
        .first()
    )
    if lock is not None:
        owner = db.get(ApplyJob, lock.apply_job_id)
        if owner is None or owner.status in NON_TERMINAL_APPLY_STATES:
            raise ListingGuardConflict(channel_id, listing_id, lock.apply_job_id)
        # A terminal lock is still owned until the Apply/recovery path releases
        # or atomically reclaims it. Cache and Mapping never reclaim Apply locks.
        raise ListingGuardConflict(channel_id, listing_id, lock.apply_job_id)
    return listing


def acquire_external_listing_guard(
    db: Session, channel_id: str, external_primary_id: str
) -> Listing | None:
    if db.bind is None or not inspect(db.bind).has_table("uw_listings"):
        return None
    from app.flowhub.unified_workspace.models import Listing

    listing = (
        db.query(Listing)
        .filter_by(channel_id=channel_id, external_primary_id=external_primary_id)
        .with_for_update()
        .first()
    )
    if listing is None:
        return None
    return acquire_listing_guard(db, channel_id, listing.id)


def acquire_channel_listing_guards(db: Session, channel_id: str) -> list[Listing]:
    if db.bind is None or not inspect(db.bind).has_table("uw_listings"):
        return []
    from app.flowhub.unified_workspace.models import Listing

    identities = (
        db.query(Listing.id).filter_by(channel_id=channel_id).order_by(Listing.id.asc()).all()
    )
    return [acquire_listing_guard(db, channel_id, listing_id) for (listing_id,) in identities]
