"""Add lease evidence for durable data-layer refresh jobs.

Revision ID: FLOWHUB_037
Revises: FLOWHUB_036
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "FLOWHUB_037"
down_revision = "FLOWHUB_036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("dl_refresh_jobs")}
    for name, column in {
        "heartbeat_at": sa.Column("heartbeat_at", sa.DateTime(), nullable=True),
        "lease_expires_at": sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        "recovery_reason": sa.Column("recovery_reason", sa.String(120), nullable=True),
    }.items():
        if name not in columns:
            op.add_column("dl_refresh_jobs", column)
    op.create_index("ix_dl_refresh_jobs_lease_expires_at", "dl_refresh_jobs", ["lease_expires_at"], if_not_exists=True)


def downgrade() -> None:
    raise NotImplementedError("FLOWHUB_037 is forward-only; stale-job evidence is audit data.")
