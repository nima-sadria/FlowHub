"""Preserve archived Source lifecycle state explicitly.

Revision ID: FLOWHUB_034
Revises: FLOWHUB_033
"""

from __future__ import annotations

import json
from typing import Any

from alembic import op
import sqlalchemy as sa


revision = "FLOWHUB_034"
down_revision = "FLOWHUB_033"
branch_labels = None
depends_on = None


def _metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def upgrade() -> None:
    bind = op.get_bind()
    dialect_name = bind.dialect.name

    op.add_column("sc_sources", sa.Column("archived_at", sa.DateTime(), nullable=True))
    if dialect_name == "sqlite":
        with op.batch_alter_table("sc_sources", recreate="always") as batch:
            batch.drop_constraint("ck_sc_source_status", type_="check")
            batch.create_check_constraint(
                "ck_sc_source_status",
                "status IN ('active','disabled','archived')",
            )
    else:
        op.drop_constraint("ck_sc_source_status", "sc_sources", type_="check")
        op.create_check_constraint(
            "ck_sc_source_status",
            "sc_sources",
            "status IN ('active','disabled','archived')",
        )

    # Earlier archive commands wrote `disabled`. Immutable archive audit
    # evidence is the only safe basis for reclassifying an existing row.
    archived_events = bind.execute(
        sa.text(
            "SELECT occurred_at, metadata_json FROM uw_audit_entries "
            "WHERE event_type = 'source_archived' ORDER BY occurred_at ASC"
        )
    ).mappings()
    archived_at_by_source: dict[str, Any] = {}
    for event in archived_events:
        source_id = str(_metadata(event["metadata_json"]).get("sourceId") or "").strip()
        if source_id:
            archived_at_by_source[source_id] = event["occurred_at"]

    for source_id, archived_at in archived_at_by_source.items():
        bind.execute(
            sa.text(
                "UPDATE sc_sources SET status = 'archived', archived_at = :archived_at "
                "WHERE id = :source_id AND status = 'disabled'"
            ),
            {"source_id": source_id, "archived_at": archived_at},
        )


def downgrade() -> None:
    raise RuntimeError(
        "FLOWHUB_034 makes archived Source identity explicit. "
        "Restore a verified backup instead of downgrading."
    )
