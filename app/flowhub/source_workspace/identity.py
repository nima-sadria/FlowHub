"""Canonical Source-to-connector identity resolution.

Source profiles store the exact Integration Platform connector instance id.
The two legacy Nextcloud values are accepted only at compatibility boundaries;
they are never used to select a connector when the choice is ambiguous.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.flowhub.integration_platform.models import IntegrationConnectorInstance
from app.flowhub.source_workspace.models import SourceProfile

LEGACY_NEXTCLOUD_SOURCE_IDS = frozenset({"nextcloud", "nextcloud:primary"})
LEGACY_NEXTCLOUD_PRIMARY_ID = "nextcloud:primary"


def _active_candidates(db: Session) -> list[IntegrationConnectorInstance]:
    return (
        db.query(IntegrationConnectorInstance)
        .filter(
            IntegrationConnectorInstance.connector_type == "nextcloud",
            IntegrationConnectorInstance.id != LEGACY_NEXTCLOUD_PRIMARY_ID,
            IntegrationConnectorInstance.enabled.is_(True),
            IntegrationConnectorInstance.status != "disabled",
        )
        .order_by(IntegrationConnectorInstance.id.asc())
        .all()
    )


def _rebind_required(candidates: list[IntegrationConnectorInstance]) -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT,
        {
            "code": "SOURCE_CONNECTOR_REBIND_REQUIRED",
            "message": (
                "The legacy Nextcloud Source identity cannot be resolved safely. "
                "Bind the Source to one exact active connector instance."
            ),
            "candidate_source_ids": [item.id for item in candidates],
        },
    )


def canonical_nextcloud_connector_id(
    db: Session,
    requested_id: str,
    *,
    allow_unresolved_legacy: bool = True,
) -> str:
    """Return the exact connector id for a Source-profile boundary.

    Existing exact connector ids are authoritative. A legacy generic id can
    migrate only to one active, unbound replacement. A disabled primary may
    migrate to one such replacement, but is never re-enabled or selected as a
    fallback. Unresolved ``nextcloud:primary`` remains readable for historical
    compatibility and is blocked by operational callers until explicitly
    rebound.
    """

    requested = str(requested_id or "").strip()
    if not requested:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"code": "EXTERNAL_SOURCE_REQUIRED", "message": "External Source identity is required."},
        )

    exact = db.get(IntegrationConnectorInstance, requested)
    if exact is not None:
        if exact.connector_type != "nextcloud":
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {
                    "code": "SOURCE_CONNECTOR_TYPE_MISMATCH",
                    "message": "The Source identity is not a Nextcloud connector instance.",
                },
            )
        if requested != LEGACY_NEXTCLOUD_PRIMARY_ID or (
            exact.enabled and exact.status != "disabled"
        ):
            return exact.id

    if requested not in LEGACY_NEXTCLOUD_SOURCE_IDS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {
                "code": "SOURCE_CONNECTOR_NOT_FOUND",
                "message": "External Source identity must match an existing connector instance.",
            },
        )

    candidates = _active_candidates(db)
    if len(candidates) > 1:
        raise _rebind_required(candidates)
    if len(candidates) == 1:
        candidate = candidates[0]
        already_bound = (
            db.query(SourceProfile.id)
            .filter(SourceProfile.external_source_id == candidate.id)
            .first()
        )
        if already_bound is not None:
            raise _rebind_required(candidates)
        return candidate.id

    if requested == "nextcloud" or not allow_unresolved_legacy:
        raise _rebind_required([])
    return requested


def has_active_replacement(db: Session) -> bool:
    """Whether a generated active Nextcloud instance supersedes legacy bootstrap."""

    return bool(_active_candidates(db))

