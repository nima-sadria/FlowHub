# FlowHub Integration Platform

**Version:** 2.0
**Date:** 2026-07-01
**Status:** Current architecture and API contract for the implemented platform component.

## Purpose

The Integration Platform is the permanent FlowHub boundary for connector
registry metadata, connector instances, connector settings, connector health,
diagnostics, telemetry, webhooks, polling policy, and future transport support.

This document describes the approved architecture and the implemented first-release
runtime surface. It does not authorize Scheduler execution, Apply, automatic
pricing, WooCommerce writes, or Nextcloud writes.

## Supported Connector Scope

Current implemented connectors:

- WooCommerce
- Nextcloud

Commerce Hub Channels:

- WooCommerce is the first implemented Channel.
- Snapp Shop and Tapsi Shop are planned read-only Channel placeholders in
  FlowHub 1.0.0.

Planned Channels:

- Snapp Shop
- Tapsi Shop
- Digikala
- Technolife

Future connector types:

- Shopify
- Magento
- ERP
- CSV
- Google Sheets
- Custom APIs

Supported transport families:

- REST API
- Webhook
- Polling
- File Import
- Message Queue
- Future transports

## Architecture Rules

- FlowHub Data Layer is the canonical data architecture.
- Cache is only an internal mechanism inside the Data Layer.
- Integration Platform owns connector metadata and orchestration contracts.
- Product UI terminology separates Sources from Channels.
- Sources feed FlowHub / Data Layer; Channels represent commerce systems.
- Channels are implemented internally under `app/connectors/destinations/`.
- Data Layer owns durable read models, snapshots, refresh records, and cache
  records populated by approved connector flows.
- Connector capabilities are metadata only.
- Authorization is enforced separately by the Safety Layer and future Write
  Guard.
- Execution is a third separate concern and is never granted by capability
  detection.
- In FlowHub, all write operations remain blocked, even when a connector
  advertises `write_prices` or `write_inventory`.
- Webhooks must not directly mutate products. They may validate, record, and
  enqueue an invalidation or refresh event after Owner-approved runtime work.
- Polling policy is future-ready only until Scheduler implementation is
  explicitly approved.

## Commerce Hub 1.0.0 Contract

Commerce Hub exposes product-facing APIs and UI for Sources and Channels while
retaining Integration Platform as the internal boundary.

API surface:

- `GET /api/v2/commerce/sources`
- `GET /api/v2/commerce/channels`
- `GET /api/v2/commerce/channels/{channel_id}`
- `POST /api/v2/commerce/channels/{channel_id}/test`
- `GET /api/v2/commerce/channels/{channel_id}/health`
- `GET /api/v2/commerce/channels/{channel_id}/capabilities`
- `PUT /api/v2/commerce/channels/{channel_id}/settings`

Rules:

- All responses report `read_only` and `runtime_write_blocked`.
- Credential values are write-only after save.
- Snapp Shop and Tapsi Shop do not perform real external calls in 1.0.0.
- Marketplace write paths remain unavailable in 1.0.0.
- WooCommerce price execution is manual and available only through the Write Pipeline after Preview, Dry Run, and Approval. Scheduler execution and automatic pricing remain disabled.

## Component Diagram

```text
Admin UI
  |
  | HTTPS, correlation_id
  v
FastAPI FLOWHUB v2
  |
  +-- Integration Platform API Contracts
  |     |
  |     +-- Connector Registry
  |     +-- Connector Manager
  |     +-- Settings Service
  |     +-- Health Service
  |     +-- Diagnostics Service
  |     +-- Telemetry Service
  |     +-- Webhook Receiver
  |     +-- Polling Policy Controller
  |
  +-- Safety Layer / Write Guard
  |
  +-- Data Layer
        |
        +-- Product cache and snapshots
        +-- Inventory cache and snapshots
        +-- Source and destination snapshots
        +-- Connector health
        +-- Connector telemetry
        +-- Invalidation events
        +-- Refresh jobs
```

## Canonical Connector Capability Schema

Connector capability objects use the Owner-approved baseline.

### Identity

- `id`
- `name`
- `type`
- `version`
- `enabled`
- `read_only`

### Capabilities

- `read_products`
- `read_categories`
- `read_inventory`
- `read_orders`
- `write_prices`
- `write_inventory`
- `webhook`
- `polling`
- `oauth`
- `api_key`

### Health / Status

- `healthy`
- `warning`
- `error`
- `disabled`
- `degraded`
- `authentication_failed`
- `rate_limited`
- `timeout`

## Shared API Contract Rules

Base path:

```text
/api/v2/integration-platform
```

Authentication:

- All endpoints require an authenticated FlowHub admin session or API token.
- Webhook receiver endpoints may use connector-specific webhook authentication
  instead of user session authentication.

Permission requirements:

- Read endpoints require `integration:read`.
- Configuration mutation endpoints require `integration:manage`.
- Diagnostic read probes require `integration:diagnose`.
- Webhook receiver endpoints require valid connector webhook credentials when
  configured.
- No permission grants write execution in FlowHub.

Correlation propagation:

- Requests accept `X-Correlation-ID`.
- If omitted, the API creates one.
- Responses return `X-Correlation-ID`.
- Events, diagnostics, telemetry, and logging records must persist the same
  correlation ID.

Standard error response:

```json
{
  "error": {
    "code": "connector_not_found",
    "message": "Connector was not found.",
    "details": {},
    "correlation_id": "corr_123",
    "retryable": false
  }
}
```

Common error codes:

- `unauthorized`
- `forbidden`
- `validation_error`
- `connector_not_found`
- `connector_type_not_found`
- `connector_disabled`
- `authentication_failed`
- `rate_limited`
- `timeout`
- `external_service_unavailable`
- `write_blocked_FLOWHUB`
- `conflict`

Pagination:

- Collection endpoints support `page` and `page_size` where the collection may
  grow.
- Default `page_size` is 50.
- Maximum `page_size` is 200 unless Owner approves a different limit.

Filtering:

- Collection endpoints expose explicit filters only.
- Unknown filters return `validation_error`.

Sorting:

- Collection endpoints support `sort` only when documented per endpoint.
- A leading `-` means descending order.

Redaction:

- Secrets are write-only.
- Settings responses may show `configured`, `not_configured`, `replaced_at`,
  and masked metadata.
- Raw secret values must never be returned, logged, exported, or included in
  diagnostics.

Rate-limit behavior:

- Admin read endpoints return `429` with `Retry-After` when FlowHub local API
  limits are exceeded.
- Connector test, diagnostics, capability detection, webhook, and future
  polling operations must also honor connector-specific external platform
  limits.
- Rate-limit events are recorded as telemetry.

Audit and logging behavior:

- Connector creation, update, enable, disable, delete, settings changes,
  diagnostics, capability detection, connection tests, webhook receipt, and
  write guard denials are audit-worthy events.
- Audit records must include actor, connector ID, connector type, operation,
  result, timestamp, and correlation ID.
- Secret values are never included.

Read-only safety behavior:

- Connector configuration changes affect FlowHub local records only.
- Deletes remove FlowHub connector configuration only.
- Test, diagnostics, detection, webhook, and telemetry endpoints must not write
  to external commerce, spreadsheet, ERP, or marketplace systems.
- Write-capable operations return the FLOWHUB write guard response until Owner
  approves write execution.

## Common Schema Fragments

### Connector Capability

```json
{
  "read_products": true,
  "read_categories": true,
  "read_inventory": true,
  "read_orders": false,
  "write_prices": true,
  "write_inventory": true,
  "webhook": true,
  "polling": true,
  "oauth": false,
  "api_key": true
}
```

### Connector Status

```json
{
  "status": "healthy",
  "health": {
    "healthy": true,
    "last_checked_at": "2026-07-01T12:00:00Z",
    "latency_ms": 180,
    "error_code": null,
    "message": "Connection is healthy."
  }
}
```

## API Contracts

### 1. Connector Registry

`GET /api/v2/integration-platform/registry`

Purpose: Return all connector types supported by the platform.

Auth: Required.

Permission: `integration:read`.

Query filters:

- `status`: `current`, `planned`, `future`, `disabled`
- `transport`: `rest_api`, `webhook`, `polling`, `file_import`,
  `message_queue`
- `capability`: one canonical capability key

Sorting:

- `name`
- `connector_type`
- `status`

Response:

```json
{
  "items": [
    {
      "connector_type": "woocommerce",
      "name": "WooCommerce",
      "version": "1.0",
      "description": "WooCommerce catalog and inventory connector.",
      "capabilities": {
        "read_products": true,
        "read_categories": true,
        "read_inventory": true,
        "read_orders": false,
        "write_prices": true,
        "write_inventory": true,
        "webhook": true,
        "polling": true,
        "oauth": false,
        "api_key": true
      },
      "authentication_types": ["api_key"],
      "supported_operations": ["read_products", "read_categories", "read_inventory"],
      "supported_transports": ["rest_api", "webhook", "polling"],
      "read_only_supported": true,
      "write_supported": true,
      "FLOWHUB_write_blocked": true,
      "status": "current"
    }
  ],
  "total": 1,
  "correlation_id": "corr_123"
}
```

Errors: `unauthorized`, `forbidden`, `validation_error`, `rate_limited`.

Read-only safety: Registry data is metadata only.

### 2. Connector Type Detail

`GET /api/v2/integration-platform/registry/{connector_type}`

Purpose: Return full metadata for one connector type.

Auth: Required.

Permission: `integration:read`.

Response includes all registry list fields plus:

- `settings_schema`
- `secret_fields`
- `health_checks`
- `diagnostic_checks`
- `webhook_events`
- `polling_defaults`
- `rate_limit_policy`
- `data_layer_mappings`
- `known_limitations`

Errors: `connector_type_not_found`, `unauthorized`, `forbidden`,
`rate_limited`.

Redaction: Schema may identify secret field names but never values.

### 3. Connector Instances

`GET /api/v2/integration-platform/connectors`

Purpose: Return configured connector instances.

Auth: Required.

Permission: `integration:read`.

Query filters:

- `connector_type`
- `enabled`
- `read_only`
- `status`
- `health`

Pagination: `page`, `page_size`.

Sorting: `name`, `connector_type`, `created_at`, `updated_at`,
`last_checked_at`, `status`.

Response:

```json
{
  "items": [
    {
      "id": "conn_woocommerce_primary",
      "connector_type": "woocommerce",
      "name": "Primary WooCommerce",
      "enabled": true,
      "read_only": true,
      "status": "healthy",
      "health": {
        "healthy": true,
        "last_checked_at": "2026-07-01T12:00:00Z",
        "latency_ms": 180,
        "error_code": null,
        "message": "Connection is healthy."
      },
      "capabilities": {
        "read_products": true,
        "read_categories": true,
        "read_inventory": true,
        "read_orders": false,
        "write_prices": true,
        "write_inventory": true,
        "webhook": true,
        "polling": true,
        "oauth": false,
        "api_key": true
      },
      "created_at": "2026-07-01T10:00:00Z",
      "updated_at": "2026-07-01T11:00:00Z",
      "last_checked_at": "2026-07-01T12:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 50,
  "correlation_id": "corr_123"
}
```

`POST /api/v2/integration-platform/connectors`

Purpose: Create a connector instance.

Auth: Required.

Permission: `integration:manage`.

Request:

```json
{
  "connector_type": "woocommerce",
  "name": "Primary WooCommerce",
  "enabled": true,
  "read_only": true,
  "settings": {
    "base_url": "https://store.example.com",
    "consumer_key": "write-only-secret",
    "consumer_secret": "write-only-secret"
  }
}
```

Response: `201 Created` with connector instance metadata and masked setting
status.

Safety: Creates FlowHub local configuration only. Must not perform external
writes.

`PUT /api/v2/integration-platform/connectors/{connector_id}`

Purpose: Update connector instance metadata and settings references.

Auth: Required.

Permission: `integration:manage`.

Request fields:

- `name`
- `enabled`
- `read_only`
- `settings`

Response: Updated connector instance metadata with secret status only.

Safety: Updates FlowHub local configuration only.

`PATCH /api/v2/integration-platform/connectors/{connector_id}/enable`

Purpose: Enable connector instance.

Auth: Required.

Permission: `integration:manage`.

Request body: Optional `{"reason": "Owner-approved setup"}`.

Response: Updated connector instance with `enabled: true`.

Safety: Enabling does not start Scheduler execution unless separately approved.

`PATCH /api/v2/integration-platform/connectors/{connector_id}/disable`

Purpose: Disable connector instance.

Auth: Required.

Permission: `integration:manage`.

Request body: Optional `{"reason": "Paused by operator"}`.

Response: Updated connector instance with `enabled: false`.

`DELETE /api/v2/integration-platform/connectors/{connector_id}`

Purpose: Remove connector instance configuration from FlowHub only.

Auth: Required.

Permission: `integration:manage`.

Response:

```json
{
  "deleted": true,
  "external_platform_unchanged": true,
  "correlation_id": "corr_123"
}
```

Safety: Must not delete anything in an external platform.

### 4. Connector Settings

`GET /api/v2/integration-platform/connectors/{connector_id}/settings`

Purpose: Return non-secret settings only.

Auth: Required.

Permission: `integration:read`.

Response:

```json
{
  "connector_id": "conn_woocommerce_primary",
  "settings": {
    "base_url": "https://store.example.com",
    "api_version": "wc/v3"
  },
  "secrets": {
    "consumer_key": {
      "status": "configured",
      "replaced_at": "2026-07-01T11:00:00Z"
    },
    "consumer_secret": {
      "status": "configured",
      "replaced_at": "2026-07-01T11:00:00Z"
    }
  },
  "correlation_id": "corr_123"
}
```

Redaction: Secrets must never be returned.

`PUT /api/v2/integration-platform/connectors/{connector_id}/settings`

Purpose: Update connector settings.

Auth: Required.

Permission: `integration:manage`.

Request:

```json
{
  "settings": {
    "base_url": "https://store.example.com"
  },
  "secrets": {
    "consumer_key": "write-only-secret",
    "consumer_secret": "write-only-secret"
  }
}
```

Response:

```json
{
  "connector_id": "conn_woocommerce_primary",
  "settings": {
    "base_url": "https://store.example.com"
  },
  "secrets": {
    "consumer_key": {
      "status": "configured",
      "replaced_at": "2026-07-01T12:10:00Z"
    },
    "consumer_secret": {
      "status": "configured",
      "replaced_at": "2026-07-01T12:10:00Z"
    }
  },
  "correlation_id": "corr_123"
}
```

Safety: Secrets are write-only and local to FlowHub configuration storage.

### 5. Connection Test

`POST /api/v2/integration-platform/connectors/{connector_id}/test`

Purpose: Test connection and authentication.

Auth: Required.

Permission: `integration:diagnose`.

Request:

```json
{
  "timeout_ms": 5000
}
```

Response:

```json
{
  "ok": true,
  "status": "healthy",
  "latency_ms": 180,
  "connector_version": "1.0",
  "detected_capabilities": {
    "read_products": true,
    "read_categories": true,
    "read_inventory": true,
    "read_orders": false,
    "write_prices": true,
    "write_inventory": true,
    "webhook": true,
    "polling": true,
    "oauth": false,
    "api_key": true
  },
  "authentication_valid": true,
  "error_code": null,
  "message": "Connection test succeeded.",
  "correlation_id": "corr_123"
}
```

Safety: The test may perform only read-only authentication or metadata probes.

### 6. Capability Detection

`POST /api/v2/integration-platform/connectors/{connector_id}/detect-capabilities`

Purpose: Detect capabilities from the external platform.

Auth: Required.

Permission: `integration:diagnose`.

Request:

```json
{
  "refresh_registry_metadata": false
}
```

Response:

```json
{
  "canonical_capabilities": {
    "read_products": true,
    "read_categories": true,
    "read_inventory": true,
    "read_orders": false,
    "write_prices": true,
    "write_inventory": true,
    "webhook": true,
    "polling": true,
    "oauth": false,
    "api_key": true
  },
  "native_capabilities": {
    "wc_products_endpoint": true,
    "wc_webhooks_endpoint": true
  },
  "detected_at": "2026-07-01T12:00:00Z",
  "confidence": "high",
  "warnings": [],
  "correlation_id": "corr_123"
}
```

Safety: Detection must not grant authorization or execute writes.

### 7. Connector Health

`GET /api/v2/integration-platform/connectors/{connector_id}/health`

Purpose: Return latest health snapshot.

Auth: Required.

Permission: `integration:read`.

Response: Connector status object with status, health, last error, last
successful check, and correlation ID.

`GET /api/v2/integration-platform/health`

Purpose: Return health summary for all connectors.

Auth: Required.

Permission: `integration:read`.

Query filters: `connector_type`, `status`, `enabled`.

Response:

```json
{
  "summary": {
    "healthy": 1,
    "warning": 0,
    "error": 0,
    "disabled": 0,
    "degraded": 0,
    "authentication_failed": 0,
    "rate_limited": 0,
    "timeout": 0
  },
  "items": [],
  "correlation_id": "corr_123"
}
```

### 8. Connector Diagnostics

`POST /api/v2/integration-platform/connectors/{connector_id}/diagnostics/run`

Purpose: Run read-only diagnostics for one connector.

Auth: Required.

Permission: `integration:diagnose`.

Request:

```json
{
  "checks": ["settings", "authentication", "data_layer_snapshot"],
  "timeout_ms": 10000
}
```

Response fields:

- `connector_id`
- `status`
- `checks`
- `started_at`
- `finished_at`
- `duration_ms`
- `warnings`
- `errors`
- `correlation_id`

Supported statuses:

- `healthy`
- `warning`
- `error`
- `disabled`
- `degraded`
- `authentication_failed`
- `rate_limited`
- `timeout`

`POST /api/v2/integration-platform/diagnostics/run`

Purpose: Run read-only diagnostics for all enabled connectors.

Auth: Required.

Permission: `integration:diagnose`.

Request:

```json
{
  "connector_types": ["woocommerce", "nextcloud"],
  "timeout_ms": 30000
}
```

Response: Summary plus per-connector diagnostic results.

Safety: Diagnostics must remain read-only and must not trigger Apply,
Scheduler, automatic pricing, or external writes.

### 9. Connector Telemetry

`GET /api/v2/integration-platform/connectors/{connector_id}/telemetry`

`GET /api/v2/integration-platform/telemetry`

Purpose: Return request counts, errors, latency, retry count, rate-limit
events, refresh duration, and records fetched.

Auth: Required.

Permission: `integration:read`.

Query filters:

- `from`
- `to`
- `connector_type`
- `operation`
- `transport`
- `bucket`: `minute`, `hour`, `day`

Response:

```json
{
  "items": [
    {
      "connector_id": "conn_woocommerce_primary",
      "connector_type": "woocommerce",
      "operation": "read_products",
      "request_count": 10,
      "error_count": 0,
      "latency_ms_p50": 120,
      "latency_ms_p95": 400,
      "retry_count": 1,
      "rate_limit_events": 0,
      "refresh_duration_ms": 1200,
      "records_fetched": 250,
      "bucket_start": "2026-07-01T12:00:00Z"
    }
  ],
  "correlation_id": "corr_123"
}
```

### 10. Connector Events

`GET /api/v2/integration-platform/events`

Purpose: Return connector lifecycle and diagnostics events.

Auth: Required.

Permission: `integration:read`.

Query filters:

- `from`
- `to`
- `connector_id`
- `connector_type`
- `event_type`
- `severity`
- `correlation_id`
- `page`
- `page_size`

Sorting: `timestamp`, `connector_type`, `event_type`, `severity`.

Response: Paginated event list with event ID, timestamp, connector ID,
connector type, event type, severity, message, actor, result, and correlation
ID.

### 11. Webhook Receiver

`POST /api/v2/integration-platform/webhooks/{connector_type}/{connector_id}`

Purpose: Receive platform webhooks.

Auth: Connector webhook signature or shared secret when configured.

Permission: Not user-session based. Valid webhook authentication is required.

Request: Connector-native webhook payload.

Response:

```json
{
  "accepted": true,
  "rejected": false,
  "reason": null,
  "event_id": "evt_123",
  "correlation_id": "corr_123"
}
```

Required behavior:

- Verify webhook signature if configured.
- Reject invalid signatures with `401` or `403`.
- Never directly mutate products.
- Record webhook receipt event.
- Enqueue invalidation or refresh event only after Owner-approved runtime
  implementation exists.

Safety: Webhook processing must not write to WooCommerce, Nextcloud,
spreadsheet, marketplace, or product records directly.

### 12. Polling Control

`GET /api/v2/integration-platform/connectors/{connector_id}/polling`

Purpose: Return polling policy for a connector.

Auth: Required.

Permission: `integration:read`.

Response:

```json
{
  "connector_id": "conn_woocommerce_primary",
  "enabled": false,
  "interval_seconds": 900,
  "jitter_seconds": 60,
  "last_run_at": null,
  "next_run_at": null,
  "scheduler_implemented": false,
  "correlation_id": "corr_123"
}
```

`PUT /api/v2/integration-platform/connectors/{connector_id}/polling`

Purpose: Configure polling policy.

Auth: Required.

Permission: `integration:manage`.

Request:

```json
{
  "enabled": false,
  "interval_seconds": 900,
  "jitter_seconds": 60
}
```

Response: Updated policy.

Safety: This is future-ready. It must not enable Scheduler implementation or
start background jobs unless explicitly approved.

### 13. Read-only Write Guard

`POST /api/v2/integration-platform/connectors/{connector_id}/write-test`

Purpose: Document write guard behavior and verify that write-capable operations
remain blocked in FlowHub.

Auth: Required.

Permission: `integration:manage`.

Request:

```json
{
  "operation": "write_prices"
}
```

Response:

```json
{
  "allowed": false,
  "status": "blocked",
  "error_code": "write_blocked_FLOWHUB",
  "message": "Write operations are disabled in FlowHub.",
  "capability_advertised": true,
  "authorization_granted": false,
  "execution_attempted": false,
  "correlation_id": "corr_123"
}
```

Required separation:

- Capability: connector may advertise write support.
- Authorization: Safety Layer and Write Guard deny write authorization in FLOWHUB.
- Execution: write execution is not attempted.

## Frontend Architecture

The Integration Platform UI is an admin/operator surface with these sections:

- Registry: connector types, status, capabilities, supported transports.
- Connectors: configured instances, health, enabled/read-only state.
- Settings: non-secret settings plus secret configuration status.
- Diagnostics: read-only diagnostic runs and latest results.
- Telemetry: request counts, errors, latency, retries, records fetched.
- Events: lifecycle, diagnostics, webhook, and write guard events.
- Polling policy: visible as future-ready, with no Scheduler execution.

UI requirements:

- Show write capabilities as connector metadata, not as permission.
- Display FLOWHUB write blocked state wherever write support is shown.
- Never display raw secret values.
- Preserve and display correlation IDs for diagnostics and support workflows.
- Use severity colors consistently:
  - Healthy: green
  - Warning/degraded/rate-limited: amber
  - Error/authentication_failed/timeout: red
  - Disabled: gray

## Backend Architecture

Logical services:

- Connector Registry: canonical connector type metadata.
- Connector Manager: local connector instance lifecycle.
- Settings Service: non-secret settings and write-only secret metadata.
- Health Service: latest status snapshots.
- Diagnostics Service: read-only probes and diagnostic result contracts.
- Telemetry Service: metrics and aggregates.
- Event Bus Contract: connector lifecycle, webhook, diagnostics, and telemetry
  events.
- Webhook Receiver: authentication, validation, event creation.
- Polling Policy Controller: configuration only until Scheduler approval.
- Write Guard: FLOWHUB write denial contract.

## Data Model

Architecture-level entities:

- `integration_connector_types`
- `integration_connector_instances`
- `integration_connector_settings`
- `integration_connector_secrets`
- `integration_connector_health`
- `integration_connector_diagnostics`
- `integration_connector_telemetry`
- `integration_connector_events`
- `integration_webhook_events`
- `integration_polling_policies`

Data Layer relationships:

- Product read models remain in the Data Layer.
- Inventory read models remain in the Data Layer.
- Source and destination snapshots remain in the Data Layer.
- Integration Platform records may reference Data Layer snapshots by ID.
- Integration Platform must not duplicate durable product cache ownership.

## Folder Structure

Architecture target, not implementation instruction:

```text
app/flowhub/integration_platform/
  contracts.py
  registry.py
  manager.py
  settings.py
  health.py
  diagnostics.py
  telemetry.py
  events.py
  webhooks.py
  polling.py
  write_guard.py

app/flowhub/api/v2/
  integration_platform.py

frontend/src/features/integration-platform/
  api.ts
  types.ts
  IntegrationPlatformPage.tsx
  RegistryPanel.tsx
  ConnectorList.tsx
  SettingsPanel.tsx
  DiagnosticsPanel.tsx
  TelemetryPanel.tsx
  EventsPanel.tsx
```

## Future Compatibility

- Additional connector types must register capabilities through the canonical
  schema.
- Future write execution must pass through Safety Layer, Write Guard,
  authorization, audit logging, and Owner-approved execution contracts.
- Future Scheduler and polling implementation must use polling policy records
  rather than ad hoc timers.
- Future message queue support should reuse connector events and Data Layer
  invalidation events.
- Future transport-specific details must map into canonical connector
  operations and telemetry fields.

## Open Owner Decisions

- Final permission names for `integration:read`, `integration:manage`, and
  `integration:diagnose`.
- Whether connection test and capability detection may contact external
  platforms in the first runtime implementation.
- Webhook queue technology and invalidation event retention.
- Polling Scheduler approval and execution boundaries.
- Connector delete retention policy and audit retention period.
- Telemetry aggregation windows and retention policy.
- Whether existing `/api/v2/integrations` endpoints remain as aliases or move
  fully to `/api/v2/integration-platform`.
