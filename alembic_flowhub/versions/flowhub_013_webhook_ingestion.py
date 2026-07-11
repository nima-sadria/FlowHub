"""Add durable webhook ingestion tables.

Revision ID: FLOWHUB_013
Revises: FLOWHUB_012
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "FLOWHUB_013"
down_revision = "FLOWHUB_012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "webhook_receipts" not in tables:
        op.create_table(
            "webhook_receipts",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("channel_id", sa.String(length=120), nullable=False),
            sa.Column("provider", sa.String(length=80), nullable=False),
            sa.Column("provider_event_id", sa.String(length=160), nullable=False),
            sa.Column("payload_hash", sa.String(length=64), nullable=False),
            sa.Column("payload_summary_json", sa.JSON(), nullable=False),
            sa.Column("normalized_event_json", sa.JSON(), nullable=False),
            sa.Column("received_at", sa.DateTime(), nullable=False),
            sa.Column("acknowledged_at", sa.DateTime(), nullable=True),
            sa.Column("processing_state", sa.String(length=40), nullable=False, server_default="queued"),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_error_category", sa.String(length=80), nullable=True),
            sa.Column("processed_at", sa.DateTime(), nullable=True),
            sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
            sa.Column("retention_until", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("channel_id", "provider_event_id", name="uq_webhook_receipt_channel_event"),
        )
    _create_index_if_missing("ix_webhook_receipts_channel_id", "webhook_receipts", ["channel_id"])
    _create_index_if_missing("ix_webhook_receipts_provider", "webhook_receipts", ["provider"])
    _create_index_if_missing("ix_webhook_receipts_provider_event_id", "webhook_receipts", ["provider_event_id"])
    _create_index_if_missing("ix_webhook_receipts_processing_state", "webhook_receipts", ["processing_state"])

    if "webhook_processing_attempts" not in tables:
        op.create_table(
            "webhook_processing_attempts",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("receipt_id", sa.Integer(), nullable=False),
            sa.Column("channel_id", sa.String(length=120), nullable=False),
            sa.Column("provider", sa.String(length=80), nullable=False),
            sa.Column("attempt_number", sa.Integer(), nullable=False),
            sa.Column("state", sa.String(length=40), nullable=False),
            sa.Column("error_category", sa.String(length=80), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("ix_webhook_processing_attempts_receipt_id", "webhook_processing_attempts", ["receipt_id"])
    _create_index_if_missing("ix_webhook_processing_attempts_channel_id", "webhook_processing_attempts", ["channel_id"])
    _create_index_if_missing("ix_webhook_processing_attempts_provider", "webhook_processing_attempts", ["provider"])

    if "webhook_dead_letters" not in tables:
        op.create_table(
            "webhook_dead_letters",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("receipt_id", sa.Integer(), nullable=False),
            sa.Column("channel_id", sa.String(length=120), nullable=False),
            sa.Column("provider", sa.String(length=80), nullable=False),
            sa.Column("provider_event_id", sa.String(length=160), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("error_category", sa.String(length=80), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing("ix_webhook_dead_letters_receipt_id", "webhook_dead_letters", ["receipt_id"])
    _create_index_if_missing("ix_webhook_dead_letters_channel_id", "webhook_dead_letters", ["channel_id"])
    _create_index_if_missing("ix_webhook_dead_letters_provider", "webhook_dead_letters", ["provider"])
    _create_index_if_missing("ix_webhook_dead_letters_provider_event_id", "webhook_dead_letters", ["provider_event_id"])


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "webhook_dead_letters" in tables:
        op.drop_table("webhook_dead_letters")
    if "webhook_processing_attempts" in tables:
        op.drop_table("webhook_processing_attempts")
    if "webhook_receipts" in tables:
        op.drop_table("webhook_receipts")


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    inspector = sa.inspect(op.get_bind())
    if index_name not in {index["name"] for index in inspector.get_indexes(table_name)}:
        op.create_index(index_name, table_name, columns)
