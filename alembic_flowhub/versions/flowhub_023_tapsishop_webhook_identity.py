"""Add durable item-level webhook identities for TapsiShop.

Revision ID: FLOWHUB_023
Revises: FLOWHUB_022
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op


revision = "FLOWHUB_023"
down_revision = "FLOWHUB_022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "webhook_provider_event_identities" not in tables:
        op.create_table(
            "webhook_provider_event_identities",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("receipt_id", sa.Integer(), nullable=False),
            sa.Column("channel_id", sa.String(length=120), nullable=False),
            sa.Column("provider", sa.String(length=80), nullable=False),
            sa.Column("provider_event_id", sa.String(length=160), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ["receipt_id"],
                ["webhook_receipts.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "channel_id",
                "provider_event_id",
                name="uq_webhook_provider_event_identity_channel_event",
            ),
        )
    _create_index_if_missing(
        "ix_webhook_provider_event_identities_receipt_id",
        "webhook_provider_event_identities",
        ["receipt_id"],
    )
    _create_index_if_missing(
        "ix_webhook_provider_event_identities_channel_id",
        "webhook_provider_event_identities",
        ["channel_id"],
    )
    _create_index_if_missing(
        "ix_webhook_provider_event_identities_provider",
        "webhook_provider_event_identities",
        ["provider"],
    )
    _create_index_if_missing(
        "ix_webhook_provider_event_identities_provider_event_id",
        "webhook_provider_event_identities",
        ["provider_event_id"],
    )
    op.execute(
        sa.text(
            """
            INSERT INTO webhook_provider_event_identities
                (receipt_id, channel_id, provider, provider_event_id, created_at)
            SELECT id, channel_id, provider, provider_event_id, received_at
            FROM webhook_receipts
            WHERE NOT EXISTS (
                SELECT 1
                FROM webhook_provider_event_identities existing
                WHERE existing.channel_id = webhook_receipts.channel_id
                  AND existing.provider_event_id = webhook_receipts.provider_event_id
            )
            """
        )
    )


def downgrade() -> None:
    if "webhook_provider_event_identities" in set(
        sa.inspect(op.get_bind()).get_table_names()
    ):
        op.drop_table("webhook_provider_event_identities")


def _create_index_if_missing(
    index_name: str,
    table_name: str,
    columns: list[str],
) -> None:
    inspector = sa.inspect(op.get_bind())
    if index_name not in {
        index["name"] for index in inspector.get_indexes(table_name)
    }:
        op.create_index(index_name, table_name, columns)
