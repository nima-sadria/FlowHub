# FlowHub Unified Logging Platform

**Version:** 1.0
**Date:** 2026-07-01
**Status:** Architecture and API contract. Runtime changes require separate Owner approval.

## Purpose

The Unified Logging Platform is FlowHub's permanent application logging
architecture. It covers backend logs, frontend application logs, connector logs,
correlation, telemetry, storage, search, filtering, export, retention, viewer
UI, dashboard, log explorer, correlation viewer, severity colors, time
filtering, and future-ready live tail.

This is application logging, not console logging. This document is
architecture-only. It does not implement ingestion, storage, runtime routers,
migrations, frontend runtime changes, or live tail.

## Architecture Rules

- Logs are structured records, not raw console output.
- Secrets and sensitive payload values are redacted before storage and before
  API response.
- Correlation IDs connect frontend, backend, connector, Data Layer, and
  Integration Platform activity.
- Request IDs connect all logs emitted for one HTTP request.
- Connector telemetry may be summarized in the Integration Platform, but log
  events are owned by the Unified Logging Platform.
- Frontend user-action logging is limited to operational and error events.
- Broad click tracking is not allowed.
- Live Tail is future-ready and must not be required in the first version.

## Component Diagram

```text
Frontend App
  |
  +-- Frontend Log Contract
  |
  v
FastAPI Beta v2
  |
  +-- Backend Log Contract
  +-- Connector Log Contract
  +-- Request/Correlation Middleware
  |
  v
Unified Logging Platform
  |
  +-- Ingestion
  +-- Redaction
  +-- Storage
  +-- Search Index
  +-- Retention
  +-- Export
  +-- Log Explorer API
  +-- Correlation Viewer API
  +-- Live Tail Contract
  |
  v
Admin UI
```

## Shared API Contract Rules

Base path:

```text
/api/v2/logging
```

Authentication:

- Viewer, search, detail, export, retention, redaction policy, and live tail
  endpoints require an authenticated FlowHub admin session or API token.
- Frontend ingestion requires an authenticated browser session or a signed
  application logging token issued by FlowHub.
- Backend ingestion is internal-only unless Owner approves external ingestion.

Permission requirements:

- Read/search endpoints require `logging:read`.
- Export requires `logging:export`.
- Retention configuration requires `logging:manage`.
- Frontend ingestion requires `logging:frontend:write`.
- Backend ingestion requires internal service authorization.

Correlation propagation:

- APIs accept `X-Correlation-ID`.
- If omitted, FlowHub creates one.
- APIs return `X-Correlation-ID`.
- Ingested logs may include `correlation_id`; otherwise ingestion assigns one.
- Logs emitted during request handling must include the request ID and
  correlation ID.

Standard error response:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Invalid logging filter.",
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
- `log_not_found`
- `correlation_not_found`
- `request_not_found`
- `retention_policy_invalid`
- `export_too_large`
- `rate_limited`

Pagination:

- Search-like endpoints support `page` and `page_size`.
- Default `page_size` is 50.
- Maximum `page_size` is 500 for search and 10,000 for export unless Owner
  approves async export jobs.

Filtering:

- Unknown filters return `validation_error`.
- Time filters use ISO 8601 UTC timestamps.

Sorting:

- `GET /logs` supports `sort=timestamp` and `sort=-timestamp`.
- Default sorting is `-timestamp`.

Rate-limit behavior:

- Frontend ingestion is rate-limited per session and per IP.
- Search and export are rate-limited per admin.
- Rate-limit responses return `429` with `Retry-After`.

Audit and logging behavior:

- Export and retention updates are audit-worthy operations.
- Log reads may be audit-worthy when they access security/audit categories.
- Redaction policy reads are logged at low severity for admin visibility.

Read-only safety behavior:

- Logging endpoints must not trigger Apply, Scheduler, automatic pricing,
  connector writes, WooCommerce writes, spreadsheet writes, or product mutation.

Redaction rules:

- Secrets, API keys, tokens, passwords, cookies, authorization headers, and
  webhook signatures are always redacted.
- Personal data and business-sensitive payload fields follow Owner-approved
  redaction categories.
- Raw payloads are never returned unless they have already passed redaction.

## Severity and Category Model

Severity values:

- `debug`
- `info`
- `warning`
- `error`
- `critical`

Severity colors:

- Debug: gray
- Info: blue
- Warning: amber
- Error: red
- Critical: purple/red emphasis

Frontend allowed categories:

- `UI Events`
- `API Errors`
- `Page Errors`
- `Unexpected Exceptions`
- `Performance Warnings`
- `Network Errors`
- `Component Errors`

Frontend user-action logging is limited to operational/error events. Examples:

- Failed form submission.
- API call failed after user action.
- Page load error.
- Component render failure.
- Performance warning for a degraded workflow.

Disallowed frontend logging:

- Broad click tracking.
- Full session replay.
- Raw keystroke capture.
- Raw form values.

## Common Log Item Schema

```json
{
  "id": "log_123",
  "timestamp": "2026-07-01T12:00:00Z",
  "severity": "error",
  "component": "backend",
  "module": "integration_platform",
  "operation": "diagnostics_run",
  "category": "Connector Diagnostics",
  "message": "Connector diagnostics failed.",
  "correlation_id": "corr_123",
  "request_id": "req_123",
  "user": "admin@example.com",
  "connector": "conn_woocommerce_primary",
  "channel": "api",
  "duration_ms": 240,
  "result": "failed",
  "exception_summary": "Authentication failed."
}
```

## API Contracts

### 1. Log Dashboard

`GET /api/v2/logging/summary`

Purpose: Return high-level logging summary.

Auth: Required.

Permission: `logging:read`.

Query filters:

- `from`
- `to`
- `component`
- `connector`
- `severity`

Response:

```json
{
  "total_logs": 1200,
  "error_count": 12,
  "warning_count": 40,
  "critical_count": 1,
  "top_components": [
    {"component": "backend", "count": 700}
  ],
  "top_connectors": [
    {"connector": "conn_woocommerce_primary", "count": 120}
  ],
  "recent_errors": [
    {
      "id": "log_123",
      "timestamp": "2026-07-01T12:00:00Z",
      "severity": "error",
      "component": "backend",
      "message": "Connector diagnostics failed.",
      "correlation_id": "corr_123"
    }
  ],
  "time_range": {
    "from": "2026-07-01T00:00:00Z",
    "to": "2026-07-01T23:59:59Z"
  },
  "correlation_id": "corr_summary"
}
```

Errors: `unauthorized`, `forbidden`, `validation_error`, `rate_limited`.

### 2. Log Search / Explorer

`GET /api/v2/logging/logs`

Purpose: Search and filter log records.

Auth: Required.

Permission: `logging:read`.

Query filters:

- `from`
- `to`
- `severity`
- `component`
- `module`
- `operation`
- `category`
- `connector`
- `channel`
- `user`
- `correlation_id`
- `request_id`
- `result`
- `search`
- `page`
- `page_size`

Sorting: `timestamp`, `-timestamp`.

Response:

```json
{
  "items": [
    {
      "id": "log_123",
      "timestamp": "2026-07-01T12:00:00Z",
      "severity": "error",
      "component": "backend",
      "module": "integration_platform",
      "operation": "diagnostics_run",
      "category": "Connector Diagnostics",
      "message": "Connector diagnostics failed.",
      "correlation_id": "corr_123",
      "request_id": "req_123",
      "user": "admin@example.com",
      "connector": "conn_woocommerce_primary",
      "channel": "api",
      "duration_ms": 240,
      "result": "failed",
      "exception_summary": "Authentication failed."
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 50,
  "correlation_id": "corr_search"
}
```

Redaction: Returned messages and summaries must be redacted.

### 3. Log Detail

`GET /api/v2/logging/logs/{log_id}`

Purpose: Return full log entry.

Auth: Required.

Permission: `logging:read`.

Response must include:

- Structured fields.
- Exception details when allowed by role and redaction policy.
- Related correlation entries.
- Redacted payloads only.

Response:

```json
{
  "item": {
    "id": "log_123",
    "timestamp": "2026-07-01T12:00:00Z",
    "severity": "error",
    "component": "backend",
    "module": "integration_platform",
    "operation": "diagnostics_run",
    "category": "Connector Diagnostics",
    "message": "Connector diagnostics failed.",
    "structured": {},
    "exception": {
      "type": "AuthenticationError",
      "summary": "Authentication failed.",
      "stacktrace": null
    },
    "payload": {
      "connector_id": "conn_woocommerce_primary",
      "secret": "[REDACTED]"
    },
    "related_correlation_entries": []
  },
  "correlation_id": "corr_123"
}
```

Errors: `log_not_found`, `unauthorized`, `forbidden`, `rate_limited`.

### 4. Correlation Viewer

`GET /api/v2/logging/correlations/{correlation_id}`

Purpose: Return all logs sharing one correlation ID.

Auth: Required.

Permission: `logging:read`.

Query filters:

- `severity`
- `component`
- `page`
- `page_size`

Response: Paginated list of log items plus a timeline summary and duration
between first and last event.

### 5. Request Trace

`GET /api/v2/logging/requests/{request_id}`

Purpose: Return all logs for one request.

Auth: Required.

Permission: `logging:read`.

Response: Request metadata, ordered log entries, request duration, result, user,
route, status code, and correlation ID.

### 6. Frontend Log Ingestion

`POST /api/v2/logging/frontend`

Purpose: Receive frontend application logs.

Auth: Required browser session or signed app logging token.

Permission: `logging:frontend:write`.

Request:

```json
{
  "logs": [
    {
      "timestamp": "2026-07-01T12:00:00Z",
      "severity": "error",
      "category": "API Errors",
      "component": "ProductBrowser",
      "module": "frontend",
      "operation": "fetch_products",
      "message": "Product request failed.",
      "correlation_id": "corr_123",
      "request_id": "req_123",
      "duration_ms": 800,
      "result": "failed",
      "details": {
        "status": 500,
        "route": "/api/v2/products"
      }
    }
  ]
}
```

Response:

```json
{
  "accepted": 1,
  "rejected": 0,
  "rejections": [],
  "correlation_id": "corr_123"
}
```

Allowed categories:

- `UI Events`
- `API Errors`
- `Page Errors`
- `Unexpected Exceptions`
- `Performance Warnings`
- `Network Errors`
- `Component Errors`

Safety and privacy:

- Operational/error events only.
- No broad click tracking.
- No raw form values, passwords, tokens, cookies, or session replay data.

### 7. Backend Log Ingestion

`POST /api/v2/logging/backend`

Purpose: Internal backend ingestion contract.

Auth: Internal service authorization.

Permission: Internal-only.

Request:

```json
{
  "logs": [
    {
      "timestamp": "2026-07-01T12:00:00Z",
      "severity": "warning",
      "component": "connector",
      "module": "woocommerce",
      "operation": "read_products",
      "category": "Connector",
      "message": "External API returned a retryable warning.",
      "correlation_id": "corr_123",
      "request_id": "req_123",
      "connector": "conn_woocommerce_primary",
      "channel": "rest_api",
      "duration_ms": 300,
      "result": "retryable"
    }
  ]
}
```

Response: Accepted/rejected counts and correlation ID.

Redaction: Backend ingestion must redact before persistence.

### 8. Export

`GET /api/v2/logging/export`

Purpose: Export filtered logs.

Auth: Required.

Permission: `logging:export`.

Query filters: Same as log search.

Additional query:

- `format`: `json` or `csv`

Response:

- `application/json` for JSON export.
- `text/csv` for CSV export.

Errors:

- `export_too_large` when result exceeds synchronous export limits.
- `validation_error` for unsupported format.

Redaction: Exports use the same or stricter redaction policy as API responses.

Audit: Every export is audit-worthy.

### 9. Retention

`GET /api/v2/logging/retention`

Purpose: Return current retention policy.

Auth: Required.

Permission: `logging:read`.

Response:

```json
{
  "policies": [
    {
      "category": "operational",
      "retention_days": 30
    },
    {
      "category": "connector_telemetry",
      "retention_days": 90
    },
    {
      "category": "audit_security",
      "retention_days": 365
    }
  ],
  "correlation_id": "corr_123"
}
```

Default retention:

- Operational logs: 30 days.
- Connector telemetry: 90 days.
- Audit/security logs: 365 days.

`PUT /api/v2/logging/retention`

Purpose: Update retention policy.

Auth: Required.

Permission: `logging:manage`.

Request:

```json
{
  "policies": [
    {
      "category": "operational",
      "retention_days": 30
    }
  ],
  "reason": "Owner-approved retention update"
}
```

Response: Updated policy and correlation ID.

Audit: Retention updates are audit-worthy.

### 10. Live Tail

`GET /api/v2/logging/live`

Purpose: Stream recent logs for live operations.

Status: Future-ready. Not required in first version.

Auth: Required.

Permission: `logging:read`.

Query filters:

- `severity`
- `component`
- `connector`
- `correlation_id`

Transport decision: SSE or WebSocket remains an Owner decision.

Safety: Live Tail is read-only and must apply the same redaction rules as
search.

### 11. Redaction Policy

`GET /api/v2/logging/redaction-policy`

Purpose: Expose current redaction categories and rules for admin visibility.

Auth: Required.

Permission: `logging:read`.

Response:

```json
{
  "categories": [
    {
      "name": "secrets",
      "examples": ["api_key", "token", "password", "authorization_header"],
      "action": "redact"
    },
    {
      "name": "personal_data",
      "examples": ["email", "phone"],
      "action": "mask_or_hash"
    }
  ],
  "never_exposed": [
    "secret_values",
    "authorization_headers",
    "cookies",
    "webhook_signatures"
  ],
  "correlation_id": "corr_123"
}
```

Safety: This endpoint must never expose secret values.

## Viewer UI

Unified Logging Platform UI sections:

- Dashboard: totals, error counts, warnings, criticals, top components,
  top connectors, recent errors, and time range.
- Log Explorer: filterable table with severity, component, module, operation,
  category, connector, channel, result, correlation ID, and request ID.
- Log Detail: structured fields, exception summary, redacted payloads, related
  correlation entries.
- Correlation Viewer: ordered event timeline for one correlation ID.
- Request Trace: request-scoped timeline with route, status, user, and duration.
- Export: filtered JSON or CSV export.
- Retention: current policy and Owner-approved updates.
- Redaction Policy: admin-visible redaction categories.
- Live Tail: future-ready view, hidden or disabled until implemented.

UI requirements:

- Time filtering must be visible and persistent.
- Severity colors must be consistent with the severity model.
- Correlation ID and request ID must be copyable.
- Redacted values must display as `[REDACTED]`.
- Frontend ingestion settings must make clear that broad click tracking is not
  supported.

## Backend Architecture

Logical services:

- Logging Ingestion Service.
- Redaction Service.
- Correlation Service.
- Search Service.
- Export Service.
- Retention Service.
- Live Tail Contract.
- Viewer API.

Storage entities:

- `logging_entries`
- `logging_payloads`
- `logging_correlations`
- `logging_request_traces`
- `logging_retention_policies`
- `logging_export_events`
- `logging_redaction_policy_versions`

Indexes:

- `timestamp`
- `severity`
- `component`
- `module`
- `operation`
- `category`
- `connector`
- `channel`
- `user`
- `correlation_id`
- `request_id`
- `result`

## Frontend Architecture

Architecture target, not implementation instruction:

```text
frontend/src/features/logging/
  api.ts
  types.ts
  LoggingDashboard.tsx
  LogExplorer.tsx
  LogDetail.tsx
  CorrelationViewer.tsx
  RequestTrace.tsx
  RetentionPanel.tsx
  RedactionPolicyPanel.tsx
  LiveTailPanel.tsx
```

Frontend logging contract:

- Capture operational errors and performance warnings.
- Attach correlation ID and request ID from API responses when available.
- Batch ingestion to reduce request overhead.
- Redact before sending whenever possible.
- Never send raw secrets, cookies, tokens, broad click streams, or raw form
  values.

## Data Model Relationship

- Integration Platform telemetry can link to logging records by correlation ID.
- Data Layer refresh, invalidation, and cache activity can emit structured logs.
- Product, inventory, source, and workspace records remain owned by the Data
  Layer and are not owned by logging.
- Logging stores operational evidence and diagnostics, not business source of
  truth records.

## Future Compatibility

- Live Tail may use SSE or WebSocket after Owner decision.
- High-volume log storage may move to a dedicated search backend without API
  contract changes.
- Export may become async for large data sets.
- Retention may support per-severity and per-component policies later.
- Security/audit logs may move to write-once storage without changing viewer
  contracts.

## Open Owner Decisions

- Final permission names for logging read, export, manage, and ingestion.
- Storage backend and search indexing technology.
- Whether Live Tail uses SSE or WebSocket.
- Synchronous export size limits and whether async export jobs are required.
- Exact PII masking policy for emails, names, phone numbers, and IP addresses.
- Whether security/audit log reads require additional audit records.
- Frontend ingestion sampling limits and per-session budgets.
