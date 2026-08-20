"""Canonicalize legacy Nextcloud Source identities when resolution is unique.

Revision ID: FLOWHUB_042
Revises: FLOWHUB_041

Only active/disabled operational Source profiles are eligible. Archived and
deleted profiles retain their historical connector identity. A generic or
legacy profile is migrated only when exactly one generated active connector
exists and that connector is not already bound to another Source. Ambiguous
rows remain untouched and require an explicit Owner rebind.
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision = "FLOWHUB_042"
down_revision = "FLOWHUB_041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(UTC).replace(tzinfo=None)
    source_rows = bind.execute(
        sa.text(
            "SELECT id, external_source_id, status "
            "FROM sc_sources "
            "WHERE external_source_id IN ('nextcloud', 'nextcloud:primary') "
            "AND status IN ('active', 'disabled')"
        )
    ).all()

    for source in source_rows:
        exact = bind.execute(
            sa.text(
                "SELECT id, enabled, status FROM ip_connector_instances "
                "WHERE id = :connector_id AND connector_type = 'nextcloud'"
            ),
            {"connector_id": source.external_source_id},
        ).first()
        # An enabled exact connector id is already canonical, including an
        # explicitly managed nextcloud:primary instance.
        if exact is not None and bool(exact.enabled) and exact.status != "disabled":
            continue

        candidates = bind.execute(
            sa.text(
                "SELECT id FROM ip_connector_instances "
                "WHERE connector_type = 'nextcloud' "
                "AND id <> 'nextcloud:primary' "
                "AND enabled = true AND status <> 'disabled' "
                "ORDER BY id"
            )
        ).all()
        if len(candidates) != 1:
            # Zero candidates means the legacy configuration still needs an
            # explicit rebind; multiple candidates are intentionally ambiguous.
            continue
        candidate_id = candidates[0].id
        already_bound = bind.execute(
            sa.text(
                "SELECT id FROM sc_sources "
                "WHERE external_source_id = :candidate_id AND id <> :source_id"
            ),
            {"candidate_id": candidate_id, "source_id": source.id},
        ).first()
        if already_bound is not None:
            continue

        bind.execute(
            sa.text(
                "UPDATE sc_sources "
                "SET external_source_id = :candidate_id, "
                "version = version + 1, updated_at = :updated_at "
                "WHERE id = :source_id "
                "AND external_source_id IN ('nextcloud', 'nextcloud:primary') "
                "AND status IN ('active', 'disabled')"
            ),
            {
                "candidate_id": candidate_id,
                "updated_at": now,
                "source_id": source.id,
            },
        )


def downgrade() -> None:
    raise RuntimeError(
        "FLOWHUB_042 canonicalizes Source identity without retaining a safe "
        "reverse mapping. Restore a verified backup instead of downgrading."
    )
