"""Add a typed fencing timestamp for FULL-vs-LIGHT write conflicts.

dl_product_cache.last_modified is a raw String(100) that only sorts
correctly today because WooCommerce happens to emit zero-padded GMT
ISO-8601 -- too fragile to fence a provider-neutral write path on. This
adds a typed, parsed DateTime column every read path (FULL batch upsert,
LIGHT targeted upsert) writes through, so a slow FULL page can never
overwrite a newer targeted observation. last_modified and its one existing
reader are untouched. See docs/architecture/ADR_CHANNEL_READ_ARCHITECTURE.md.

Revision ID: FLOWHUB_039
Revises: FLOWHUB_038
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "FLOWHUB_039"
down_revision = "FLOWHUB_038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns("dl_product_cache")}
    if "provider_observed_at" not in columns:
        op.add_column("dl_product_cache", sa.Column("provider_observed_at", sa.DateTime(), nullable=True))
    op.create_index(
        "ix_dl_product_cache_connector_last_fetched",
        "dl_product_cache",
        ["connector_id", "last_fetched_at"],
        if_not_exists=True,
    )


def downgrade() -> None:
    raise NotImplementedError("FLOWHUB_039 is forward-only; provider_observed_at is fencing evidence.")
