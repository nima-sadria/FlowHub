# FlowHub Data Layer Architecture

**Version:** 1.0
**Phase:** Data Layer Foundation (DL1)
**Date:** 2026-07-01
**Status:** Partially implemented - stores exist, population is manual (no background refresh yet)

---

## Table of Contents

A. [Product Cache](#a-product-cache)
B. [Inventory Cache](#b-inventory-cache)
C. [Source Snapshot Store](#c-source-snapshot-store)
D. [Destination Snapshot Store](#d-destination-snapshot-store)
E. [Connector Metadata Store](#e-connector-metadata-store)
F. [Connector Health Store](#f-connector-health-store)
G. [Connector Telemetry Store](#g-connector-telemetry-store)
H. [Refresh Queue](#h-refresh-queue)
I. [Invalidation Policy](#i-invalidation-policy)
J. [TTL Policy](#j-ttl-policy)
K. [Read Model](#k-read-model)
L. [Diagnostics Data](#l-diagnostics-data)
M. [Future Multi-Channel Support](#m-future-multi-channel-support)
N. [Safety Model](#n-safety-model)
O. [Database Model](#o-database-model)
P. [Data Flow Diagrams](#p-data-flow-diagrams)
Q. [Relationship to Existing FlowHub](#q-relationship-to-existing-flowhub)

---

## What is the FlowHub Data Layer?

The **FlowHub Data Layer** is the persistent read model that sits between external systems (WooCommerce, Nextcloud) and the FlowHub UI.

**Key point:** "Cache" is one internal mechanism inside the Data Layer. The Data Layer is the broader concept - it includes caches, snapshots, health records, telemetry, job queues, and invalidation events.

```
External Systems
  WooCommerce REST API
  Nextcloud WebDAV

       | read only (no writes)
       -¼

  ”Œ-----------------------------------------------------”گ
  |              FlowHub Data Layer                      |
  |                                                     |
  |  Product Cache    |  Source Snapshot Store          |
  |  Inventory Cache  |  Destination Snapshot Store     |
  |  Connector Health |  Connector Telemetry            |
  |  Refresh Queue    |  Invalidation Events            |
  ””-----------------------------------------------------”ک
       |
       -¼
  FlowHub UI
  /products  /sources  /workspace  /diagnostics  /activity  /settings
```

**What is NOT in the Data Layer:**
- Any write path to WooCommerce or Nextcloud
- Price mutations
- Apply engine
- Scheduler
- Automatic pricing

---

## A. Product Cache

**Purpose:** Persistent read model for WooCommerce products (and future connector products).

**Identity:**
- Primary key: `(connector_id, product_id)`
- `connector_id` - fully qualified connector instance ID (e.g. `woocommerce:primary`)
- `product_id` - connector-native product identifier (WC product ID as string)
- `external_id` - integer WC product ID when connector is WooCommerce
- `channel_id` - future multi-channel slot (NULL for current FLOWHUB)

**Fields per product:**

| Field | Type | Description |
|-------|------|-------------|
| sku | text | Stock-keeping unit |
| name | text | Product display name |
| product_type | varchar | simple \| variable \| variation |
| parent_id | varchar | Parent product_id for variations |
| status | varchar | publish \| draft \| private |
| price | text | Current price (text to avoid float precision loss) |
| regular_price | text | Regular (non-sale) price |
| sale_price | text | Sale price if active |
| stock_qty | integer | Quantity in stock |
| stock_status | varchar | instock \| outofstock \| onbackorder |
| manage_stock | boolean | Whether WC manages stock count |
| backorders_allowed | boolean | Whether backorders are permitted |
| categories | JSON | Array of category objects |
| images | JSON | Array of image objects |
| freshness | varchar | fresh \| stale \| error |
| last_fetched_at | datetime | When this record was last populated |
| expires_at | datetime | When this record should be considered stale (TTL) |
| raw_data | JSON | Full connector response for debugging |

**Freshness states:**
- `fresh` - data is within TTL, usable by UI
- `stale` - TTL expired or invalidated, refresh needed
- `error` - last fetch attempt failed; previous data preserved but flagged

**Current state (IP foundation):** Products are served from `dl_product_cache`
through the Integration Platform. The table may be empty until a refresh or
migration population step inserts records; the Products page shows an empty
read-only state instead of making a live WooCommerce call.

---

## B. Inventory Cache

**Purpose:** Inventory state per product per connector, separated from the product read model to allow independent refresh cadences.

**Identity:** `(connector_id, product_id)` - mirrors Product Cache keys.

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| stock_qty | integer | Quantity in stock |
| stock_status | varchar | instock \| outofstock \| onbackorder |
| manage_stock | boolean | WC stock management flag |
| backorders | varchar | no \| notify \| yes |
| channel_id | varchar | Future multi-channel slot |
| last_fetched_at | datetime | When this record was last populated |
| expires_at | datetime | TTL expiry |

**Design rationale:** Inventory can change more frequently than product metadata (name, images, categories). Separating it allows a faster inventory refresh cycle without re-fetching full product data.

**Current state (IP foundation):** Inventory table exists but is not populated
by active FLOWHUB v2 routes yet. Product Browser reads product-level inventory
fields from `dl_product_cache` through the Integration Platform. No live
WooCommerce inventory call is made from active FLOWHUB v2 routes.

**Future multi-location support:** `channel_id` is reserved for warehouse/location segmentation. Schema does not need to change when multi-location inventory is added.

---

## C. Source Snapshot Store

**Purpose:** Track the last-known state of source files (Nextcloud spreadsheets, CSVs, Google Sheets, etc.) without storing the full file content.

**Identity:** `(connector_id, file_path)` - one snapshot per file per connector instance.

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| etag | varchar | HTTP ETag from last fetch (for conditional GET) |
| last_modified | varchar | HTTP Last-Modified header value |
| parsed_row_count | integer | Number of rows successfully parsed |
| duplicate_count | integer | Duplicate product_id rows detected |
| invalid_row_count | integer | Rows that failed to parse |
| integrity_hash | varchar(64) | SHA-256 of file bytes for change detection |
| sheet_names | JSON | List of worksheet names found |
| version_seq | integer | Increments on every re-snapshot (audit trail) |
| snapshotted_at | datetime | When this snapshot was captured |

**Spreadsheet parse rules (current Nextcloud connector):**
- Column A: product name
- Column B: product_id (integer)
- Column C: price
- Rows start at row 3 (rows 1-2 are headers)
- Last-sheet-wins on duplicate product IDs
- 30 consecutive empty rows stops parsing
- Maximum 1000 rows
- Persian/Arabic-Indic digits are normalized to ASCII
- Out-of-stock markers -> price = None

**Invalidation trigger:** ETag or Last-Modified change on next fetch -> snapshot version_seq increments -> dependent product cache entries marked stale.

**Current state (IP foundation):** Source snapshot table exists and is read by
the Integration Platform Sources route. Active Workspace preview no longer
downloads or parses source files; it returns a read-only Data Layer preview
shell. Source snapshot population remains a future approved refresh/import
phase.

---

## D. Destination Snapshot Store

**Purpose:** Track the last-known state of products at the destination (WooCommerce) for change detection and conflict resolution.

**Identity:** `(connector_id, product_id)` - one snapshot per product per destination connector.

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| price | text | Last known price at destination |
| regular_price | text | Last known regular_price |
| sale_price | text | Last known sale_price |
| stock_status | varchar | Last known stock status |
| response_hash | varchar(64) | Hash of API response for efficient change detection |
| source_connector_id | varchar | Which source connector produced this snapshot |
| snapshotted_at | datetime | When this snapshot was captured |

**Use cases:**
1. Detect whether a price has drifted since last refresh
2. Skip Apply when destination already matches source (future Apply phase)
3. Show "current WC price" alongside "source price" in Workspace UI

**Current state (DL1):** Empty. Populated during future Apply or dedicated snapshot refresh phases.

---

## E. Connector Metadata Store

**Purpose:** Describe the configured connector instances - their type, capabilities, and operational parameters.

**Current state (IP foundation):** Connector metadata is owned by the Integration
Platform. Registry declarations live in `app/flowhub/integration_platform/registry.py`
and configured instances/settings/status/events live in the `ip_*` tables. The
Data Layer remains the read-model store for products, sources, health, and
telemetry.

**Integration Platform table: `ip_connector_instances`**

| Field | Description |
|-------|-------------|
| connector_id | Fully qualified instance ID (e.g. `woocommerce:primary`) |
| connector_type | source \| destination |
| provider | woocommerce \| nextcloud \| snappshop \| ... |
| display_name | Human-readable name |
| capabilities | JSON - serialized ConnectorCapabilities |
| can_read | boolean |
| can_write | boolean - always false in FLOWHUB |
| rate_limit_rps | float - requests per second limit |
| supports_pagination | boolean |
| supports_webhooks | boolean |
| supports_etag | boolean |
| entity_types | JSON - list: products, inventory, categories, files, ... |
| credentials_ref | Key name in flowhub_app_config where credentials live |
| enabled | boolean |
| created_at | datetime |

**Active connectors in FLOWHUB:**
- `woocommerce:primary` - destination, read-only, WC REST API v3
- `nextcloud:primary` - source, read-only, WebDAV + OCS APIs

---

## F. Connector Health Store

**Purpose:** Record the most recent health check result per connector instance.

**Table:** `dl_connector_health`
**Identity:** `connector_id` (unique)

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| connector_id | varchar | Instance ID |
| connector_type | varchar | source \| destination |
| status | varchar | healthy \| degraded \| unhealthy \| unknown |
| latency_ms | float | Round-trip latency of health check |
| detail | text | Human-readable status message |
| error_class | varchar | Error class name on failure |
| consecutive_failures | integer | Count of consecutive failed checks |
| checked_at | datetime | When this check was performed |
| last_success_at | datetime | When the last successful check occurred |

**Status definitions:**

| Status | Meaning |
|--------|---------|
| healthy | Check passed, latency within normal range |
| degraded | Check passed but latency elevated or partial response |
| unhealthy | Check failed - connector not reachable or auth failed |
| unknown | No check has been performed yet |

**Current state (IP foundation):** Table exists. Populated by
`ConnectorHealthService.upsert()` and read by Integration Platform diagnostics.
The active FLOWHUB v2 diagnostics routes are record-backed and do not perform live
WooCommerce or Nextcloud checks.

---

## G. Connector Telemetry Store

**Purpose:** Aggregate operational metrics per connector - request counts, error rates, latency, throughput.

**Table:** `dl_connector_telemetry`
**Identity:** `connector_id` (unique)

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| connector_id | varchar | Instance ID |
| connector_type | varchar | source \| destination |
| request_count | integer | Total requests made |
| error_count | integer | Total requests that resulted in errors |
| retry_count | integer | Total retry attempts |
| throttle_events | integer | Times rate limiting was triggered |
| avg_latency_ms | float | Rolling average response latency |
| p95_latency_ms | float | 95th percentile latency (populated in future) |
| products_fetched | integer | Total products retrieved |
| rows_parsed | integer | Total spreadsheet rows parsed |
| last_refresh_duration_ms | float | Duration of the last full refresh |
| last_preview_duration_ms | float | Duration of the last preview operation |
| window_start | datetime | Start of current telemetry window |
| window_end | datetime | End of current telemetry window |
| updated_at | datetime | Last update timestamp |

**Current state (IP foundation):** Table exists. `ConnectorTelemetryService.increment()`
remains the Data Layer aggregate write interface. The Integration Platform also
records local connector events in `ip_connector_events` and exposes both event
and aggregate views through `/api/v2/integrations/telemetry`.

---

## H. Refresh Queue

**Purpose:** Track refresh jobs - their type, target, status, and outcome.

**Table:** `dl_refresh_jobs`

**Job types:**
- `manual` - triggered by user action (e.g. clicking Refresh in UI)
- `webhook` - triggered by a WC/NC webhook event
- `etag` - triggered because ETag changed on source file check
- `scheduled` - triggered by background scheduler *(future phase)*

**Entity types:**
- `products` - refresh product cache from destination
- `source` - re-snapshot source file
- `destination` - snapshot destination product state
- `connectors` - health check all connectors

**Status lifecycle:**
```
pending -> running -> completed
                 †ک failed -> (retry -> running)
                 †ک cancelled
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| job_type | varchar | manual \| webhook \| etag \| scheduled |
| entity_type | varchar | products \| source \| destination \| connectors |
| connector_id | varchar | Which connector this job targets |
| status | varchar | pending \| running \| completed \| failed \| cancelled |
| triggered_by | varchar | Username or system component that triggered |
| retry_count | integer | How many retries attempted |
| max_retries | integer | Retry limit (default 3) |
| started_at | datetime | When processing began |
| completed_at | datetime | When job completed successfully |
| failed_at | datetime | When job failed permanently |
| duration_ms | float | Total processing time |
| error_message | text | Last error message |
| meta | JSON | Additional job-specific metadata |
| created_at | datetime | When job was enqueued |

**Retry and backoff:** *(future implementation)*
- Retry on transient errors (HTTP 5xx, timeout)
- Exponential backoff: 30s, 2m, 10m
- Dead-letter after `max_retries` exhausted

**Deduplication:** *(future implementation)*
- Same connector_id + entity_type cannot have two `running` jobs simultaneously
- New manual trigger for a running job returns the existing job ID

**Current state (DL1):** Table and service exist. No automated job creation yet - manual creation only via `RefreshJobService.create()`. Scheduler is strictly forbidden in FLOWHUB.

---

## I. Invalidation Policy

**Purpose:** Define when cached data is considered invalid and must be refreshed.

### Product Cache Invalidation

| Trigger | Mechanism | Scope |
|---------|-----------|-------|
| Manual | User clicks "Refresh" | All products for connector |
| Source file change | ETag/hash mismatch on source check | All products from that source |
| Destination webhook | WC product.updated webhook | Single product |
| Time (TTL) | expires_at passed | All expired entries |
| Dependency | Source snapshot invalidated | Products mapped from that source |

### Source Snapshot Invalidation

| Trigger | Mechanism |
|---------|-----------|
| ETag changed | Conditional GET returns new ETag |
| Last-Modified changed | HTTP Last-Modified header differs |
| Manual | User-triggered re-snapshot |
| Time | TTL for source snapshot expired |

### Destination Snapshot Invalidation

| Trigger | Mechanism |
|---------|-----------|
| Product changed in WC | webhook or periodic poll |
| Apply completed | After a write operation (future Apply phase) |
| Manual | User-triggered re-snapshot |

### Connector Health Invalidation

| Trigger | Mechanism |
|---------|-----------|
| Time | Health record older than health TTL |
| Error count increase | consecutive_failures threshold exceeded |
| Manual | Diagnostics page refresh |

**Invalidation event log:** Every invalidation is recorded in `dl_invalidation_events` with `event_type`, `entity_type`, `entity_id`, `connector_id`, and `reason`. This provides a complete audit trail of why data was refreshed.

**Current state (DL1):** Invalidation event recording works (`InvalidationService.record()`). Automated invalidation triggers are a future phase.

---

## J. TTL Policy

**Purpose:** Define how long each data type is considered fresh before requiring a refresh.

### Default TTLs

| Entity | Default TTL | Rationale |
|--------|-------------|-----------|
| Product cache | 30 minutes | WC products rarely change mid-session |
| Inventory cache | 5 minutes | Stock levels change more frequently |
| Source snapshot | 15 minutes | File changes are infrequent |
| Destination snapshot | 60 minutes | Destination state is stable |
| Connector health | 5 minutes | Health state checked on demand |
| Connector telemetry | No TTL | Accumulates; never expires |

### Connector Overrides

Future: connector-specific TTL overrides via Integration Platform connector instance metadata.

### Environment Overrides

Future: environment variable `FLOWHUB_TTL_PRODUCTS_MINUTES=N` overrides global default.

### Stale Data Surfacing

When `expires_at` is past, `freshness` is set to `stale`. The UI reads `freshness` and shows a staleness indicator. Users can trigger a manual refresh. The UI never blocks on stale data - it shows what it has with a warning.

**Current state (DL1):** TTL columns (`expires_at`) exist in schema. No background process enforces TTL yet. Stale marking is available via `ProductReadModelService.mark_stale()`.

---

## K. Read Model

**Purpose:** Define the complete set of read paths from the Data Layer to the UI.

### Read Path 1: Products Page (`/products`)

**Current (IP foundation):** Read from `dl_product_cache` through the Integration
Platform. Empty cache returns an empty read-only product list; it does not fall
back to live WooCommerce.

```
GET /api/v2/products
  -> ProductReadModelService.list(connector_id, page, page_size)
    -> dl_product_cache WHERE connector_id = 'woocommerce:primary'
      AND freshness = 'fresh'
      ORDER BY id DESC
```

### Read Path 2: Workspace Preview (`/workspace`)

**Current (IP foundation):** Record-backed read-only preview shell through the
Integration Platform. No live WC/NC calls are made. Future preview enrichment
will compose `dl_source_snapshots` and `dl_product_cache`.

### Read Path 3: Sources Page (`/sources`)

**Current (IP foundation):** Connector instances plus `dl_source_snapshots`.
The route returns last-known local source metadata without live Nextcloud calls.

### Read Path 4: Diagnostics Page (`/diagnostics`)

**Current (IP foundation):** Integration Platform diagnostics read connector
records, health snapshots, and telemetry records. They do not perform live
external checks.

### Read Path 5: Data Layer Status Views

**Current (DL1):** Reads all `dl_*` tables via Data Layer API endpoints.
Products, Sources, Workspace, Diagnostics, and Settings show empty or
uninitialized states until tables are populated.

### Read Path 6: Settings Page (`/settings`)

**Current (IP foundation):** Settings read local configuration and Integration
Platform setting records. Secrets are masked. Saving settings updates local
records only and does not test credentials through live external calls.

### Stale/Error/Loading State Representation

| State | UI behavior |
|-------|-------------|
| `initialized: false` | Show "Not initialized yet" empty state |
| `freshness: stale` | Show data with amber staleness indicator |
| `freshness: error` | Show last-known data with red error indicator |
| API error | Show error banner; previous data preserved if available |
| Loading | Show spinner; never block indefinitely |

---

## L. Diagnostics Data

**Purpose:** Define which diagnostic data reads from the Data Layer vs. live connections.

### Current Diagnostics (DL1)

`GET /api/v2/diagnostics/status` is record-backed:
- DB: local database status
- WooCommerce: Integration Platform/Data Layer connector records
- Nextcloud: Integration Platform/Data Layer connector records

Live external probes are reserved for a separately approved health-monitor or
refresh phase.

### Data Layer Diagnostics (added in DL1)

`GET /api/v2/data-layer/status` reads from `dl_*` tables only - no live HTTP calls.

This is correct: the Data Layer status endpoint shows the state of the Data Layer itself, not of the external connectors.

### Avoiding Slow Blocking

- Data Layer status endpoint: no external HTTP -> always fast
- Diagnostics status endpoint: record-backed, no direct external HTTP
- Future: a Health Monitor may update `dl_connector_health` using approved read-only probes

### Last Successful Refresh

`dl_connector_health.last_success_at` tracks when the connector last responded successfully. Surfaced in Data Layer page and future Diagnostics enhancement.

### Connector Degradation Display

`dl_connector_health.consecutive_failures` > 0 -> show degradation warning in Data Layer page connector health section.

---

## M. Future Multi-Channel Support

**Purpose:** Describe how new connectors plug into the Data Layer without architectural changes.

### Connector ID Convention

Every connector instance has a fully qualified ID:

```
{provider}:{instance_name}
```

Examples:
- `woocommerce:primary`
- `nextcloud:primary`
- `snappshop:main`
- `digikala:storefront`
- `shopify:us-store`
- `gsheets:price-list`
- `csv:import`
- `erp:sap`

### How New Connectors Plug In

1. Add connector implementation under `app/connectors/sources/<provider>/` or `app/connectors/destinations/<provider>/`
2. Register connector instance in Integration Platform `ip_connector_instances`
3. Wire connector to Data Layer services: call `ProductReadModelService.upsert()` and `ConnectorHealthService.upsert()` after each fetch
4. No changes needed to `dl_product_cache`, `dl_inventory_cache`, `dl_refresh_jobs`, or `dl_invalidation_events` - they already accept any `connector_id`

### Planned Future Connectors

| Connector | Type | Status |
|-----------|------|--------|
| WooCommerce | Destination | Active (FLOWHUB) |
| Nextcloud | Source | Active (FLOWHUB) |
| SnappShop | Destination | Planned |
| Digikala | Destination | Planned |
| Technolife | Destination | Planned |
| Shopify | Destination | Planned |
| Google Sheets | Source | Planned |
| CSV | Source | Planned |
| ERP | Source + Destination | Planned |
| Custom REST API | Source + Destination | Planned |

### Multi-Channel Product Browser

When multiple destination connectors are active, the Products page reads from `dl_product_cache` filtered by `channel_id`. Each channel shows its own product/price/inventory state. Unified view across channels is a future aggregation layer.

---

## N. Safety Model

**Purpose:** Enforce that the Data Layer never introduces write paths to external systems.

### FLOWHUB Read-Only Guarantee

The FlowHub Data Layer is read-only with respect to external systems in the first release:

| Operation | Status | Enforcement |
|-----------|--------|-------------|
| WooCommerce product read | Allowed | Via connector layer |
| WooCommerce price write | **Blocked** | No write path exists in code |
| WooCommerce stock write | **Blocked** | No write path exists in code |
| Nextcloud file read | Allowed | Via connector layer |
| Nextcloud file write | **Blocked** | No write path exists in code |
| Apply engine | **Blocked** | Not implemented |
| Scheduler | **Blocked** | Not implemented |
| Automatic pricing | **Blocked** | Not implemented |

### Read Cache ‰  Apply Permission

The existence of a product cache does not imply permission to write. The Data Layer is a read model. A cached product record carries no apply authorization. Future Apply requires:
1. Explicit Apply architecture (separate design phase)
2. Separate permission flag (`can_apply`)
3. Separate API endpoint (not part of Data Layer)
4. Separate write guard independent of the Data Layer

### Write Guard

The `data_layer_routes.py` router contains **zero** write endpoints to external systems. All API endpoints in the Data Layer router are `GET` methods. The router never imports `httpx` directly - verified by `TestNoWritePaths.test_router_does_not_import_httpx_directly`.

### API Safety Flags

Every `/api/v2/data-layer/status` response always includes:
```json
{
  "read_only": true,
  "apply_blocked": true
}
```

These are static - not computed from any state. They cannot be false.

---

## O. Database Model

**Purpose:** Conceptual description of all Data Layer tables. See `alembic_flowhub/versions/FLOWHUB_005_data_layer.py` for the authoritative DDL.

### Table Summary

| Table | Purpose | Key | Retention |
|-------|---------|-----|-----------|
| `dl_connector_health` | Health check results | `connector_id` UNIQUE | Overwritten per connector |
| `dl_connector_telemetry` | Telemetry aggregates | `connector_id` UNIQUE | Accumulates; no TTL |
| `dl_product_cache` | Product read model | `(connector_id, product_id)` | Until evicted by TTL |
| `dl_inventory_cache` | Inventory state | `(connector_id, product_id)` | Until evicted by TTL |
| `dl_source_snapshots` | Source file metadata | `(connector_id, file_path)` | Overwritten on re-snapshot |
| `dl_destination_snapshots` | Destination product/price | `(connector_id, product_id)` | Overwritten on re-snapshot |
| `dl_refresh_jobs` | Job history | `id` auto | Retain 90 days (future cleanup) |
| `dl_invalidation_events` | Invalidation audit log | `id` auto | Retain 30 days (future cleanup) |

### Key Indexes

| Table | Index | Purpose |
|-------|-------|---------|
| `dl_connector_health` | `connector_id` | Fast upsert per connector |
| `dl_connector_telemetry` | `connector_id` | Fast upsert per connector |
| `dl_product_cache` | `connector_id`, `product_id` | Fast upsert + filtered reads |
| `dl_inventory_cache` | `connector_id`, `product_id` | Fast upsert + filtered reads |
| `dl_source_snapshots` | `connector_id` | Fast upsert |
| `dl_destination_snapshots` | `connector_id`, `product_id` | Fast upsert |
| `dl_refresh_jobs` | `connector_id`, `created_at` | Recent jobs by connector |
| `dl_invalidation_events` | `entity_id`, `connector_id`, `created_at` | Recent events by entity/connector |

### JSON Columns

`categories`, `images`, `raw_data` (product cache), `sheet_names` (source snapshot), and `meta` (refresh jobs) use `sa.JSON()` which maps to native JSON on PostgreSQL and TEXT with JSON serialization on SQLite.

### Table Ownership

All `dl_*` tables are owned by the FlowHub runtime (`app/flowhub/`). Legacy Compatibility: they are never read or written by the legacy app runtime (`app/main.py`).

---

## P. Data Flow Diagrams

### Diagram 1: Product Browser Flow (Current - Integration Platform/Data Layer)

```
User opens /products
        |
        -¼
GET /api/v2/products
        |
        -¼
ProductsRouter
        |
        -¼
IntegrationPlatformService.list_products()
        |
        -¼ (reads from DB)
dl_product_cache
        |
        -¼
Response mapped -> products list -> JSON response -> UI
```

### Diagram 2: Product Refresh Flow (Future)

```
User opens /products
        |
        -¼
GET /api/v2/products
        |
        -¼
ProductsRouter
        |
        -¼
Approved refresh worker
        |
        -¼ (read-only external fetch)
WooCommerce REST API / future connector transport
        |
        -¼
ProductReadModelService.upsert()
```

### Diagram 3: Workspace Preview Flow (Current - Integration Platform/Data Layer)

```
User clicks Preview in /workspace
        |
        -¼
POST /api/v2/workspace/preview
        |
        -¼
IntegrationPlatformService.workspace_preview()
        |
        -¼
Read local connector records and Data Layer state
        |
        -¼
Return read-only preview shell -> JSON -> UI
```

### Diagram 4: Source File Refresh Flow (Future)

```
Trigger: manual / ETag change / scheduled
        |
        -¼
RefreshJobService.create(job_type, entity_type='source')
        |
        -¼ (job runner - future)
NextcloudConnector.list_files() -> check ETag
        |
        +- ETag unchanged -> job marked completed (no-op)
        |
        ””- ETag changed -> download file -> parse
                |
                -¼
        SourceSnapshotService.upsert(connector_id, file_path, etag=..., parsed_row_count=...)
                |
                -¼
        InvalidationService.record('etag', 'source_snapshot', ...)
                |
                -¼
        ProductReadModelService.mark_stale(connector_id=source_connector_id)
```

### Diagram 5: WC Product Refresh Flow (Future)

```
Trigger: manual / scheduled / webhook
        |
        -¼
RefreshJobService.create(job_type, entity_type='products')
        |
        -¼ (job runner - future)
WooCommerceConnector.list_products() -> paginated WC REST calls
        |
        -¼ (for each product)
ProductReadModelService.upsert(connector_id, product_id, data, freshness='fresh')
ConnectorTelemetryService.increment(connector_id, products_fetched=1)
        |
        -¼
RefreshJobService.update_status(job_id, 'completed')
```

### Diagram 6: Diagnostics Flow (Current)

```
User opens /diagnostics
        |
        -¼
GET /api/v2/diagnostics/status
        |
        +- local DB status
        +- Integration Platform connector records
        ””- Data Layer health/telemetry records
                |
                -¼
        Aggregated status -> JSON -> UI
        (does not perform external HTTP)
```

### Diagram 7: Future Multi-Channel Product Browser Flow

```
User opens /products?channel=snappshop
        |
        -¼
GET /api/v2/products?channelId=snappshop:main
        |
        -¼
ProductReadModelService.list(connector_id='snappshop:main', ...)
        |
        -¼
dl_product_cache WHERE connector_id = 'snappshop:main'
        |
        -¼
Products from SnappShop -> UI (same Products page, different channel tab)
```

---

## Q. Relationship to Existing FlowHub

**Purpose:** Map every Data Layer component to what is currently implemented vs. what is planned.

### app/connectors/ - Connector Layer

| Component | Current status | Data Layer relationship |
|-----------|---------------|------------------------|
| `app/connectors/destinations/woocommerce/` | Active | WC REST client. Future: called by refresh jobs, writes to `dl_product_cache` |
| `app/connectors/sources/nextcloud/` | Active | NC WebDAV client. Future: called by refresh jobs, writes to `dl_source_snapshots` |
| `app/connectors/common/health.py` | Active | `HealthResult` returned by `check_health()`. Future: written to `dl_connector_health` |
| `app/connectors/common/types.py` | Legacy connector framework | Integration Platform uses the canonical capability schema in `app/flowhub/integration_platform/contracts.py` |

### app/flowhub/integrations/ - Integration Layer

| Component | Current status | Data Layer relationship |
|-----------|---------------|------------------------|
| `WooCommerceClient` | Legacy compatibility wrapper | Not imported by active FLOWHUB v2 API routes |
| `NextcloudClient` | Legacy compatibility wrapper | Not imported by active FLOWHUB v2 API routes |
| `parse_price_list()` | Active - stateless parse | Future: result row counts written to `dl_source_snapshots` |

### app/flowhub/api/v2/ - API Routes

| Route file | Current status | Data Layer relationship |
|------------|---------------|------------------------|
| `products.py` | Active - Integration Platform | Reads from `dl_product_cache` |
| `workspace.py` | Active - Integration Platform | Record-backed preview shell; future enrichment from `dl_product_cache` + `dl_source_snapshots` |
| `sources.py` | Active - Integration Platform | Connector instances plus `dl_source_snapshots` |
| `diagnostics.py` | Active - Integration Platform | Reads connector records and `dl_connector_health`; no live external checks |
| `data_layer_routes.py` | **NEW (DL1)** - reads `dl_*` tables | Current. Shows empty states until stores are populated |

### Database Tables

| Table | Owner | Data Layer role |
|-------|-------|----------------|
| `flowhub_users` | Core FLOWHUB | No role in Data Layer |
| `flowhub_refresh_tokens` | Core FLOWHUB | No role in Data Layer |
| `flowhub_login_audit` | Core FLOWHUB | Source for Activity page (separate from invalidation log) |
| `flowhub_app_config` | Core FLOWHUB | Source for connector credentials (referenced by Connector Metadata Store) |
| `dl_connector_health` | **Data Layer (DL1)** | New |
| `dl_connector_telemetry` | **Data Layer (DL1)** | New |
| `dl_product_cache` | **Data Layer (DL1)** | New |
| `dl_inventory_cache` | **Data Layer (DL1)** | New |
| `dl_source_snapshots` | **Data Layer (DL1)** | New |
| `dl_destination_snapshots` | **Data Layer (DL1)** | New |
| `dl_refresh_jobs` | **Data Layer (DL1)** | New |
| `dl_invalidation_events` | **Data Layer (DL1)** | New |
| `ip_connector_instances` | **Integration Platform** | Connector instance metadata |
| `ip_connector_settings` | **Integration Platform** | Local connector settings with masked secrets in API responses |
| `ip_connector_health_snapshots` | **Integration Platform** | Connector status snapshots |
| `ip_connector_events` | **Integration Platform** | Connector diagnostics and telemetry events |
| `ip_connector_diagnostics` | **Integration Platform** | Read-only diagnostic run records |
| `ip_connector_telemetry` | **Integration Platform** | Canonical connector telemetry contract rows |
| `ip_webhook_events` | **Integration Platform** | Webhook receipt records; no direct product mutation |
| `ip_polling_policies` | **Integration Platform** | Polling policy configuration; Scheduler remains disabled |
| `logging_entries` | **Unified Logging Platform** | Structured application log entries |
| `logging_correlations` | **Unified Logging Platform** | Correlation ID rollups |
| `logging_request_traces` | **Unified Logging Platform** | Request-scoped trace rollups |
| `logging_retention_policies` | **Unified Logging Platform** | Retention policy settings |
| `logging_export_events` | **Unified Logging Platform** | Log export audit records |
| `logging_redaction_policy_versions` | **Unified Logging Platform** | Redaction policy visibility records |

### Frontend Pages

| Page | Route | Current status | Data Layer relationship |
|------|-------|---------------|------------------------|
| Dashboard | /home | Active | No Data Layer dependency yet |
| Products | /products | Active - Integration Platform | Reads Data Layer product cache |
| Sources | /sources | Active - Integration Platform | Shows connector/source snapshot metadata |
| SourceWizard | /sources/new | Active | No Data Layer dependency |
| Workspace | /workspace | Active - Integration Platform | Record-backed preview shell; no external calls |
| Activity | /activity | Active - audit log | No Data Layer dependency |
| Diagnostics | /diagnostics | Active - Integration Platform | Record-backed connector diagnostics |
| Settings | /settings | Active - Integration Platform | Local settings; secrets masked |

### What is Current vs. Planned vs. Future

**Current (DL1 + Integration Platform foundation):**
- All 8 `dl_*` tables created (migration FLOWHUB_005)
- Integration Platform `ip_*` tables created (migrations FLOWHUB_006 and FLOWHUB_007)
- Unified Logging Platform tables created (migration FLOWHUB_007)
- All 6 service modules implemented (`app/flowhub/data_layer/`)
- All 6 read-only API endpoints implemented (`/api/v2/data-layer/*`)
- Products, Sources, Workspace, Diagnostics, Settings, and telemetry routes are
  wired through Integration Platform/Data Layer records where approved
- Products, Sources, Workspace, Diagnostics, Settings, and Activity provide the
  production UI surfaces for Data Layer, connector, and log-backed status
- Strictly read-only; no scheduler; no Apply

**Planned (DL2):**
- Approved read-only refresh worker writes product/source records
- Approved Health Monitor writes `dl_connector_health`
- Approved telemetry writers increment `dl_connector_telemetry`
- Manual trigger endpoint: `POST /api/v2/data-layer/refresh` (read-only; fetches and stores, no writes to WC/NC)
- Show live data in Data Layer page when stores are populated

**Future (DL3+):**
- ETag-triggered source snapshot refresh
- Background product cache refresh (requires scheduler design review)
- Destination snapshot population
- Webhook ingestion -> invalidation -> refresh pipeline
- Multi-channel connector registration
