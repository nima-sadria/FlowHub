"""FlowHub - Data Layer ORM models.

All Data Layer tables use the 'dl_' prefix to distinguish them from
core Beta tables (beta_users, beta_app_config, etc.).

Tables:
  dl_product_cache           - product read model, per connector + product ID
  dl_inventory_cache         - inventory state, per connector + product ID
  dl_source_snapshots        - source file snapshot metadata (ETag, rows, etc.)
  dl_destination_snapshots   - destination (WC) product/price snapshot
  dl_connector_health        - per-connector last health check result
  dl_connector_telemetry     - per-connector telemetry aggregates
  dl_refresh_jobs            - refresh job history and status
  dl_invalidation_events     - invalidation event log

Multi-channel readiness: connector_id and channel_id columns are present
on cache tables so that future connectors (SnappShop, Digikala, Shopify,
etc.) can populate the same tables without schema changes.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)

from app.beta.database import BetaBase


class DlConnectorHealth(BetaBase):
    """Per-connector health check result. One row per connector_id."""

    __tablename__ = "dl_connector_health"

    id = Column(Integer, primary_key=True, autoincrement=True)
    connector_id = Column(String(255), nullable=False, unique=True, index=True)
    connector_type = Column(String(50), nullable=False)      # source | destination
    status = Column(String(20), nullable=False, default="unknown")  # healthy | degraded | unhealthy | unknown
    latency_ms = Column(Float, nullable=True)
    detail = Column(Text, nullable=True)
    error_class = Column(String(100), nullable=True)
    consecutive_failures = Column(Integer, default=0)
    checked_at = Column(DateTime, nullable=False)
    last_success_at = Column(DateTime, nullable=True)


class DlConnectorTelemetry(BetaBase):
    """Per-connector telemetry aggregates. One row per connector_id."""

    __tablename__ = "dl_connector_telemetry"

    id = Column(Integer, primary_key=True, autoincrement=True)
    connector_id = Column(String(255), nullable=False, unique=True, index=True)
    connector_type = Column(String(50), nullable=False)
    request_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    retry_count = Column(Integer, default=0)
    throttle_events = Column(Integer, default=0)
    avg_latency_ms = Column(Float, nullable=True)
    p95_latency_ms = Column(Float, nullable=True)
    products_fetched = Column(Integer, default=0)
    rows_parsed = Column(Integer, default=0)
    last_refresh_duration_ms = Column(Float, nullable=True)
    last_preview_duration_ms = Column(Float, nullable=True)
    window_start = Column(DateTime, nullable=True)
    window_end = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)


class DlProductCache(BetaBase):
    """Product read model. One row per (connector_id, product_id)."""

    __tablename__ = "dl_product_cache"
    __table_args__ = (UniqueConstraint("connector_id", "product_id", name="uq_dl_product"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    connector_id = Column(String(255), nullable=False, index=True)
    product_id = Column(String(255), nullable=False, index=True)
    external_id = Column(Integer, nullable=True)           # WC product_id when connector=woocommerce
    sku = Column(String(255), nullable=True)
    name = Column(Text, nullable=True)
    product_type = Column(String(50), nullable=True)       # simple | variable | variation
    parent_id = Column(String(255), nullable=True)         # parent product_id for variations
    status = Column(String(50), nullable=True)             # publish | draft | private
    price = Column(Text, nullable=True)
    regular_price = Column(Text, nullable=True)
    sale_price = Column(Text, nullable=True)
    stock_qty = Column(Integer, nullable=True)
    stock_status = Column(String(50), nullable=True)       # instock | outofstock | onbackorder
    manage_stock = Column(Boolean, nullable=True)
    backorders_allowed = Column(Boolean, nullable=True)
    categories = Column(JSON, nullable=True)
    images = Column(JSON, nullable=True)
    channel_id = Column(String(100), nullable=True)        # future multi-channel support
    freshness = Column(String(20), default="stale")        # fresh | stale | error
    last_fetched_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    raw_data = Column(JSON, nullable=True)


class DlInventoryCache(BetaBase):
    """Inventory state. One row per (connector_id, product_id)."""

    __tablename__ = "dl_inventory_cache"
    __table_args__ = (UniqueConstraint("connector_id", "product_id", name="uq_dl_inventory"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    connector_id = Column(String(255), nullable=False, index=True)
    product_id = Column(String(255), nullable=False, index=True)
    stock_qty = Column(Integer, nullable=True)
    stock_status = Column(String(50), nullable=True)       # instock | outofstock | onbackorder
    manage_stock = Column(Boolean, nullable=True)
    backorders = Column(String(50), nullable=True)         # no | notify | yes
    channel_id = Column(String(100), nullable=True)        # future multi-channel support
    last_fetched_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)


class DlSourceSnapshot(BetaBase):
    """Source file snapshot metadata. One row per (connector_id, file_path)."""

    __tablename__ = "dl_source_snapshots"
    __table_args__ = (UniqueConstraint("connector_id", "file_path", name="uq_dl_src_snap"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    connector_id = Column(String(255), nullable=False, index=True)
    file_path = Column(Text, nullable=False)
    etag = Column(String(255), nullable=True)
    last_modified = Column(String(100), nullable=True)
    parsed_row_count = Column(Integer, nullable=True)
    duplicate_count = Column(Integer, nullable=True)
    invalid_row_count = Column(Integer, nullable=True)
    integrity_hash = Column(String(64), nullable=True)     # SHA-256 of file bytes
    sheet_names = Column(JSON, nullable=True)              # list of worksheet names
    version_seq = Column(Integer, default=1)               # increments on each re-snapshot
    snapshotted_at = Column(DateTime, nullable=False)


class DlDestinationSnapshot(BetaBase):
    """Destination product/price snapshot. One row per (connector_id, product_id)."""

    __tablename__ = "dl_destination_snapshots"
    __table_args__ = (UniqueConstraint("connector_id", "product_id", name="uq_dl_dst_snap"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    connector_id = Column(String(255), nullable=False, index=True)
    product_id = Column(String(255), nullable=False, index=True)
    price = Column(Text, nullable=True)
    regular_price = Column(Text, nullable=True)
    sale_price = Column(Text, nullable=True)
    stock_status = Column(String(50), nullable=True)
    response_hash = Column(String(64), nullable=True)      # hash of API response for change detection
    source_connector_id = Column(String(255), nullable=True)
    snapshotted_at = Column(DateTime, nullable=False)


class DlRefreshJob(BetaBase):
    """Refresh job history and status."""

    __tablename__ = "dl_refresh_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_type = Column(String(50), nullable=False)          # manual | webhook | etag | scheduled
    entity_type = Column(String(50), nullable=False)       # products | source | destination | connectors
    connector_id = Column(String(255), nullable=True, index=True)
    status = Column(String(20), nullable=False, default="pending")  # pending | running | completed | failed | cancelled
    triggered_by = Column(String(100), nullable=True)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    failed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, index=True)


class DlInvalidationEvent(BetaBase):
    """Invalidation event log."""

    __tablename__ = "dl_invalidation_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(50), nullable=False)        # manual | webhook | time | dependency
    entity_type = Column(String(50), nullable=False)       # product | source_snapshot | destination_snapshot | connector_health
    entity_id = Column(String(255), nullable=True, index=True)
    connector_id = Column(String(255), nullable=True, index=True)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, index=True)
