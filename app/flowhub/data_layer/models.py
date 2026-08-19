"""FlowHub - Data Layer ORM models.

All Data Layer tables use the 'dl_' prefix to distinguish them from
core FLOWHUB tables (flowhub_users, flowhub_app_config, etc.).

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
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)

from app.flowhub.database import FlowHubBase

# DlChannelEntityWorkReceipt below has a ForeignKey into webhook_receipts.
# SQLAlchemy resolves string FK targets against whatever tables happen to be
# registered on FlowHubBase.metadata at DDL-compile time, which depends on
# import order elsewhere -- so this module must import webhooks.models
# itself rather than relying on some other caller having done so first.
from app.flowhub.webhooks import models as _webhook_models  # noqa: E402, F401


class DlConnectorHealth(FlowHubBase):
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


class DlConnectorTelemetry(FlowHubBase):
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
    queue_length = Column(Integer, default=0)
    last_throttle_at = Column(DateTime, nullable=True)
    last_connector_delay_ms = Column(Float, nullable=True)
    last_request_duration_ms = Column(Float, nullable=True)
    window_start = Column(DateTime, nullable=True)
    window_end = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)


class DlProductCache(FlowHubBase):
    """Product read model. One row per (connector_id, product_id)."""

    __tablename__ = "dl_product_cache"
    __table_args__ = (
        UniqueConstraint("connector_id", "product_id", name="uq_dl_product"),
        Index("ix_dl_product_cache_connector_last_fetched", "connector_id", "last_fetched_at"),
        Index("ix_dl_product_cache_observation_confidence", "connector_id", "observation_confidence"),
    )

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
    last_price = Column(Text, nullable=True)
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
    last_successful_read = Column(DateTime, nullable=True)
    last_modified = Column(String(100), nullable=True)
    # Typed, parsed fencing timestamp (provider-reported modification time).
    # Distinct from last_modified (raw string) -- see Phase D fencing rule
    # in ADR_CHANNEL_READ_ARCHITECTURE.md. Every write path (FULL batch
    # upsert, LIGHT targeted upsert) sets this; a write may never overwrite
    # a row whose provider_observed_at is newer than its own.
    provider_observed_at = Column(DateTime, nullable=True)
    # Distinct axis from freshness (untouched, still fresh|stale|error):
    # CONFIRMED | LIKELY_FRESH | STALE | UNKNOWN | RECOVERY_REQUIRED. A
    # write-time snapshot (read_engine.observation_confidence.compute());
    # Diagnostics recomputes live for decay/RECOVERY_REQUIRED escalation
    # rather than trusting this column as the sole source of truth.
    observation_confidence = Column(String(20), default="UNKNOWN")
    observation_confidence_reason = Column(String(50), nullable=True)
    observation_confidence_computed_at = Column(DateTime, nullable=True)
    exists = Column(Boolean, nullable=False, default=True)
    record_hash = Column(String(64), nullable=True)
    expires_at = Column(DateTime, nullable=True)
    raw_data = Column(JSON, nullable=True)


class DlInventoryCache(FlowHubBase):
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


class DlSourceSnapshot(FlowHubBase):
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


class DlWorkspacePreview(FlowHubBase):
    """Immutable server-owned Workspace preview used to authorize Dry Run rows."""

    __tablename__ = "dl_workspace_previews"

    id = Column(String(120), primary_key=True)
    source_id = Column(String(255), nullable=False, index=True)
    source_snapshot_id = Column(Integer, nullable=False, index=True)
    source_integrity_hash = Column(String(64), nullable=False)
    owner_user_id = Column(Integer, nullable=False, index=True)
    owner_username = Column(String(160), nullable=False)
    preview_hash = Column(String(64), nullable=False)
    rows_json = Column(JSON, nullable=False)
    row_hashes_json = Column(JSON, nullable=False)
    summary_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)


class DlSourceReadLock(FlowHubBase):
    """Per-source database lock row used to serialize quota reservations."""

    __tablename__ = "dl_source_read_locks"

    source_id = Column(String(255), primary_key=True)
    updated_at = Column(DateTime, nullable=False)


class DlSourceReadReservation(FlowHubBase):
    """Durable accounting for every outbound source-read attempt."""

    __tablename__ = "dl_source_read_reservations"

    id = Column(String(120), primary_key=True)
    source_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(160), nullable=False, index=True)
    reserved_at = Column(DateTime, nullable=False, index=True)
    status = Column(String(30), nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)
    error_code = Column(String(120), nullable=True)


class DlSourceDiscoveryLock(FlowHubBase):
    """Per-source lock used to serialize worksheet-discovery reservations."""

    __tablename__ = "dl_source_discovery_locks"

    source_id = Column(String(255), primary_key=True)
    updated_at = Column(DateTime, nullable=False)


class DlSourceDiscoveryReservation(FlowHubBase):
    """Durable accounting for bounded remote worksheet metadata refreshes."""

    __tablename__ = "dl_source_discovery_reservations"

    id = Column(String(120), primary_key=True)
    source_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(160), nullable=False, index=True)
    reserved_at = Column(DateTime, nullable=False, index=True)
    status = Column(String(30), nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)
    error_code = Column(String(120), nullable=True)


class DlWorksheetDiscoveryCache(FlowHubBase):
    """Latest non-business worksheet/header metadata for one Source."""

    __tablename__ = "dl_worksheet_discovery_cache"

    source_id = Column(String(255), primary_key=True)
    file_path = Column(Text, nullable=False)
    provider_change_token = Column(String(255), nullable=True)
    worksheets = Column(JSON, nullable=False)
    metadata_checksum = Column(String(64), nullable=False)
    discovered_at = Column(DateTime, nullable=False)


class DlSourceIdentityValidation(FlowHubBase):
    """Latest authoritative preview validation for one candidate Mapping."""

    __tablename__ = "dl_source_identity_validations"

    source_id = Column(String(255), primary_key=True)
    source_version = Column(Integer, nullable=False)
    candidate_checksum = Column(String(64), nullable=False)
    source_revision_id = Column(String(255), nullable=True)
    valid = Column(Boolean, nullable=False)
    conflicts = Column(JSON, nullable=False)
    validated_at = Column(DateTime, nullable=False)


class DlDestinationSnapshot(FlowHubBase):
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


class DlRefreshJob(FlowHubBase):
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
    heartbeat_at = Column(DateTime, nullable=True)
    lease_expires_at = Column(DateTime, nullable=True, index=True)
    completed_at = Column(DateTime, nullable=True)
    failed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    recovery_reason = Column(String(120), nullable=True)
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, index=True)


class DlInvalidationEvent(FlowHubBase):
    """Invalidation event log."""

    __tablename__ = "dl_invalidation_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(50), nullable=False)        # manual | webhook | time | dependency
    entity_type = Column(String(50), nullable=False)       # product | source_snapshot | destination_snapshot | connector_health
    entity_id = Column(String(255), nullable=True, index=True)
    connector_id = Column(String(255), nullable=True, index=True)
    reason = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, index=True)


class DlChannelEntityWork(FlowHubBase):
    """Per-entity Channel Read work queue -- LIGHT/PRODUCT targeted reads.

    Independent lease scope from DlRefreshJob: DlRefreshJob stays
    (connector_id, entity_type)-scoped for FULL/DEEP channel-wide work;
    this table is (connector_id, entity_type, entity_id)-scoped, claimed by
    workers via SELECT ... FOR UPDATE SKIP LOCKED. See entity_work.py and
    ADR_CHANNEL_READ_ARCHITECTURE.md.
    """

    __tablename__ = "dl_channel_entity_work"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','completed','failed','cancelled')",
            name="ck_dl_channel_entity_work_status",
        ),
        CheckConstraint("strategy IN ('LIGHT','FULL','DEEP')", name="ck_dl_channel_entity_work_strategy"),
        Index("ix_dl_channel_entity_work_claim", "status", "next_attempt_at", "latest_event_at"),
        Index("ix_dl_channel_entity_work_connector_entity", "connector_id", "entity_type", "entity_id"),
        # Exactly one active (pending|running) row per entity -- the
        # coalescing target. Historical completed/failed rows are unlimited:
        # they are evidence for Observation Confidence, not leases.
        Index(
            "uq_dl_channel_entity_work_active",
            "connector_id",
            "entity_type",
            "entity_id",
            unique=True,
            sqlite_where=text("status IN ('pending', 'running')"),
            postgresql_where=text("status IN ('pending', 'running')"),
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    connector_id = Column(String(255), nullable=False)
    entity_type = Column(String(50), nullable=False, default="products")
    entity_id = Column(String(255), nullable=False)
    parent_entity_id = Column(String(255), nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    strategy = Column(String(20), nullable=False, default="LIGHT")
    reason = Column(String(50), nullable=False)
    latest_reason = Column(String(50), nullable=False)
    worker_id = Column(String(160), nullable=True)
    lease_expires_at = Column(DateTime, nullable=True)
    heartbeat_at = Column(DateTime, nullable=True)
    latest_event_at = Column(DateTime, nullable=False)
    latest_provider_event_id = Column(String(160), nullable=True)
    superseded_at = Column(DateTime, nullable=True)
    next_attempt_at = Column(DateTime, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=5)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    failed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    error_category = Column(String(80), nullable=True)
    meta = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)


class DlChannelEntityWorkReceipt(FlowHubBase):
    """Links a webhook receipt to the DlChannelEntityWork execution that
    covers it. Many receipts can map to one work item (coalescing); every
    linked receipt transitions atomically when that work item completes."""

    __tablename__ = "dl_channel_entity_work_receipts"

    work_id = Column(Integer, ForeignKey("dl_channel_entity_work.id", ondelete="CASCADE"), primary_key=True)
    receipt_id = Column(Integer, ForeignKey("webhook_receipts.id", ondelete="CASCADE"), primary_key=True, index=True)
    linked_at = Column(DateTime, nullable=False)
