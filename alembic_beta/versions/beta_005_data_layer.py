"""beta_005 - create Data Layer tables (dl_*)

Establishes the FlowHub Data Layer persistence foundation.
All tables use the 'dl_' prefix to distinguish them from core Beta tables.

No data is pre-populated. The Data Layer starts empty and is populated
incrementally by future refresh operations (manual trigger, webhook,
background refresh). The UI shows empty/uninitialized states until then.

Tables created:
  dl_connector_health        - per-connector health check results
  dl_connector_telemetry     - per-connector telemetry aggregates
  dl_product_cache           - product read model
  dl_inventory_cache         - inventory state
  dl_source_snapshots        - source file snapshot metadata
  dl_destination_snapshots   - destination product/price snapshot
  dl_refresh_jobs            - refresh job history
  dl_invalidation_events     - invalidation event log

Safety: no WooCommerce or Nextcloud write paths are introduced.
        These tables are populated by FlowHub Beta read operations only.

Revision ID: beta_005
Revises: beta_004
Create Date: 2026-07-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "beta_005"
down_revision = "beta_004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dl_connector_health",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("connector_id", sa.String(length=255), nullable=False),
        sa.Column("connector_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="unknown"),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("error_class", sa.String(length=100), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("checked_at", sa.DateTime(), nullable=False),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connector_id"),
    )
    op.create_index("ix_dl_connector_health_connector_id", "dl_connector_health", ["connector_id"])

    op.create_table(
        "dl_connector_telemetry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("connector_id", sa.String(length=255), nullable=False),
        sa.Column("connector_type", sa.String(length=50), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("retry_count", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("throttle_events", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("avg_latency_ms", sa.Float(), nullable=True),
        sa.Column("p95_latency_ms", sa.Float(), nullable=True),
        sa.Column("products_fetched", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("rows_parsed", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("last_refresh_duration_ms", sa.Float(), nullable=True),
        sa.Column("last_preview_duration_ms", sa.Float(), nullable=True),
        sa.Column("window_start", sa.DateTime(), nullable=True),
        sa.Column("window_end", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connector_id"),
    )
    op.create_index("ix_dl_connector_telemetry_connector_id", "dl_connector_telemetry", ["connector_id"])

    op.create_table(
        "dl_product_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("connector_id", sa.String(length=255), nullable=False),
        sa.Column("product_id", sa.String(length=255), nullable=False),
        sa.Column("external_id", sa.Integer(), nullable=True),
        sa.Column("sku", sa.String(length=255), nullable=True),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("product_type", sa.String(length=50), nullable=True),
        sa.Column("parent_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("price", sa.Text(), nullable=True),
        sa.Column("regular_price", sa.Text(), nullable=True),
        sa.Column("sale_price", sa.Text(), nullable=True),
        sa.Column("stock_qty", sa.Integer(), nullable=True),
        sa.Column("stock_status", sa.String(length=50), nullable=True),
        sa.Column("manage_stock", sa.Boolean(), nullable=True),
        sa.Column("backorders_allowed", sa.Boolean(), nullable=True),
        sa.Column("categories", sa.JSON(), nullable=True),
        sa.Column("images", sa.JSON(), nullable=True),
        sa.Column("channel_id", sa.String(length=100), nullable=True),
        sa.Column("freshness", sa.String(length=20), nullable=True, server_default="stale"),
        sa.Column("last_fetched_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connector_id", "product_id", name="uq_dl_product"),
    )
    op.create_index("ix_dl_product_cache_connector_id", "dl_product_cache", ["connector_id"])
    op.create_index("ix_dl_product_cache_product_id", "dl_product_cache", ["product_id"])

    op.create_table(
        "dl_inventory_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("connector_id", sa.String(length=255), nullable=False),
        sa.Column("product_id", sa.String(length=255), nullable=False),
        sa.Column("stock_qty", sa.Integer(), nullable=True),
        sa.Column("stock_status", sa.String(length=50), nullable=True),
        sa.Column("manage_stock", sa.Boolean(), nullable=True),
        sa.Column("backorders", sa.String(length=50), nullable=True),
        sa.Column("channel_id", sa.String(length=100), nullable=True),
        sa.Column("last_fetched_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connector_id", "product_id", name="uq_dl_inventory"),
    )
    op.create_index("ix_dl_inventory_cache_connector_id", "dl_inventory_cache", ["connector_id"])
    op.create_index("ix_dl_inventory_cache_product_id", "dl_inventory_cache", ["product_id"])

    op.create_table(
        "dl_source_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("connector_id", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("etag", sa.String(length=255), nullable=True),
        sa.Column("last_modified", sa.String(length=100), nullable=True),
        sa.Column("parsed_row_count", sa.Integer(), nullable=True),
        sa.Column("duplicate_count", sa.Integer(), nullable=True),
        sa.Column("invalid_row_count", sa.Integer(), nullable=True),
        sa.Column("integrity_hash", sa.String(length=64), nullable=True),
        sa.Column("sheet_names", sa.JSON(), nullable=True),
        sa.Column("version_seq", sa.Integer(), nullable=True, server_default="1"),
        sa.Column("snapshotted_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connector_id", "file_path", name="uq_dl_src_snap"),
    )
    op.create_index("ix_dl_source_snapshots_connector_id", "dl_source_snapshots", ["connector_id"])

    op.create_table(
        "dl_destination_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("connector_id", sa.String(length=255), nullable=False),
        sa.Column("product_id", sa.String(length=255), nullable=False),
        sa.Column("price", sa.Text(), nullable=True),
        sa.Column("regular_price", sa.Text(), nullable=True),
        sa.Column("sale_price", sa.Text(), nullable=True),
        sa.Column("stock_status", sa.String(length=50), nullable=True),
        sa.Column("response_hash", sa.String(length=64), nullable=True),
        sa.Column("source_connector_id", sa.String(length=255), nullable=True),
        sa.Column("snapshotted_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connector_id", "product_id", name="uq_dl_dst_snap"),
    )
    op.create_index("ix_dl_destination_snapshots_connector_id", "dl_destination_snapshots", ["connector_id"])
    op.create_index("ix_dl_destination_snapshots_product_id", "dl_destination_snapshots", ["product_id"])

    op.create_table(
        "dl_refresh_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_type", sa.String(length=50), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("connector_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("triggered_by", sa.String(length=100), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=True, server_default="3"),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("failed_at", sa.DateTime(), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dl_refresh_jobs_connector_id", "dl_refresh_jobs", ["connector_id"])
    op.create_index("ix_dl_refresh_jobs_created_at", "dl_refresh_jobs", ["created_at"])

    op.create_table(
        "dl_invalidation_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.String(length=255), nullable=True),
        sa.Column("connector_id", sa.String(length=255), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dl_invalidation_events_entity_id", "dl_invalidation_events", ["entity_id"])
    op.create_index("ix_dl_invalidation_events_connector_id", "dl_invalidation_events", ["connector_id"])
    op.create_index("ix_dl_invalidation_events_created_at", "dl_invalidation_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("dl_invalidation_events")
    op.drop_table("dl_refresh_jobs")
    op.drop_table("dl_destination_snapshots")
    op.drop_table("dl_source_snapshots")
    op.drop_table("dl_inventory_cache")
    op.drop_table("dl_product_cache")
    op.drop_table("dl_connector_telemetry")
    op.drop_table("dl_connector_health")
