"""Retire connector bindings restored as archived lifecycle history.

Revision ID: FLOWHUB_035
Revises: FLOWHUB_034
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "FLOWHUB_035"
down_revision = "FLOWHUB_034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The connector reference remains intact for audit/history. Only its
    # operational state is retired; no Source, secret, run, or event is
    # deleted or rewritten.
    op.get_bind().execute(
        sa.text(
            "UPDATE ip_connector_instances "
            "SET enabled = false, status = 'disabled' "
            "WHERE id IN ("
            "SELECT external_source_id FROM sc_sources "
            "WHERE status = 'archived' AND external_source_id IS NOT NULL"
            ") AND (enabled = true OR status <> 'disabled')"
        )
    )


def downgrade() -> None:
    raise RuntimeError(
        "FLOWHUB_035 preserves terminal archived Source semantics. "
        "Restore a verified backup instead of downgrading."
    )
