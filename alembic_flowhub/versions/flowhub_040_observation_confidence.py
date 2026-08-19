"""Add Observation Confidence columns to dl_product_cache.

Purely additive, alongside the existing freshness column (fresh|stale|
error), which is left completely untouched -- Observation Confidence is a
distinct axis, not a replacement. See
docs/architecture/ADR_CHANNEL_READ_ARCHITECTURE.md.

Revision ID: FLOWHUB_040
Revises: FLOWHUB_039
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "FLOWHUB_040"
down_revision = "FLOWHUB_039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("dl_product_cache")}
    for name, column in {
        "observation_confidence": sa.Column(
            "observation_confidence", sa.String(20), nullable=False, server_default="UNKNOWN"
        ),
        "observation_confidence_reason": sa.Column("observation_confidence_reason", sa.String(50), nullable=True),
        "observation_confidence_computed_at": sa.Column(
            "observation_confidence_computed_at", sa.DateTime(), nullable=True
        ),
    }.items():
        if name not in columns:
            op.add_column("dl_product_cache", column)
    op.create_index(
        "ix_dl_product_cache_observation_confidence",
        "dl_product_cache",
        ["connector_id", "observation_confidence"],
        if_not_exists=True,
    )


def downgrade() -> None:
    raise NotImplementedError("FLOWHUB_040 is forward-only; observation confidence is derived evidence.")
