# FlowHub Integration Platform

**Version:** 1.0
**Date:** 2026-07-01
**Status:** Foundation implemented for FlowHub Beta v2

## Scope

The Integration Platform is the canonical Beta v2 boundary for connector
metadata, connector settings, connector status, diagnostics, telemetry, and
Data Layer-backed read paths.

This implementation covers the foundation and API wiring only. It does not
execute Apply, Scheduler jobs, automatic pricing, WooCommerce writes, or
Nextcloud writes.

## Current Behavior

FlowHub Beta v2 routes read from Integration Platform and Data Layer records:

| Area | Current route | Current source |
|---|---|---|
| Products | `GET /api/v2/products` | `dl_product_cache` via Integration Platform |
| Categories | `GET /api/v2/products/categories` | Product cache category metadata |
| Sources | `GET /api/v2/sources` | Connector instances and `dl_source_snapshots` |
| Workspace | `GET /api/v2/workspace`, `POST /api/v2/workspace/preview` | Local connector records and Data Layer preview shell |
| Diagnostics | `GET /api/v2/diagnostics/status`, `POST /api/v2/diagnostics/run` | Connector records, Data Layer health, Integration Platform diagnostics contracts |
| Settings | `GET/PATCH /api/v2/config/*`, `GET/PATCH /api/v2/integrations/*/settings` | Local configuration and masked Integration Platform settings |
| Telemetry | `GET /api/v2/integrations/telemetry` | Integration Platform events and Data Layer telemetry aggregates |

Active Beta v2 API routes do not import the legacy WooCommerce or Nextcloud
clients and do not perform direct `httpx` external calls.

## Canonical Capability Model

Connector capabilities are metadata, not runtime authorization.

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

In Beta, a connector may advertise write capabilities, but runtime write
authorization remains blocked. The Safety Layer and future Write Guard enforce
authorization separately from capability detection.

## Data Layer Relationship

The Integration Platform owns connector registry, instances, settings, status,
diagnostics contracts, and connector telemetry events.

The Data Layer owns persistent read models:

- `dl_product_cache`
- `dl_inventory_cache`
- `dl_source_snapshots`
- `dl_destination_snapshots`
- `dl_connector_health`
- `dl_connector_telemetry`
- `dl_refresh_jobs`
- `dl_invalidation_events`

Integration Platform APIs compose these records for UI routes. Cache remains an
internal mechanism inside the Data Layer, not the architecture itself.

## Backend Modules

| Module | Responsibility |
|---|---|
| `app/beta/integration_platform/contracts.py` | Canonical API/data contracts |
| `app/beta/integration_platform/registry.py` | Static connector registry entries |
| `app/beta/integration_platform/models.py` | Connector instance, setting, health, and event tables |
| `app/beta/integration_platform/service.py` | Record-backed routing, diagnostics, settings, and telemetry |
| `app/beta/api/v2/integrations.py` | Integration Platform HTTP API |

## API Contracts

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v2/integrations/registry` | List connector registry entries |
| `GET` | `/api/v2/integrations/registry/{connector_type}` | Read one registry entry |
| `GET` | `/api/v2/integrations/connectors` | List configured connector instances |
| `POST` | `/api/v2/integrations/connectors` | Create a local connector instance record |
| `GET` | `/api/v2/integrations/connectors/{connector_id}` | Read connector instance metadata |
| `GET` | `/api/v2/integrations/connectors/{connector_id}/status` | Read connector status/health |
| `GET` | `/api/v2/integrations/connectors/{connector_id}/settings` | Read masked connector settings |
| `PATCH` | `/api/v2/integrations/connectors/{connector_id}/settings` | Update local connector settings |
| `GET` | `/api/v2/integrations/telemetry` | Read connector telemetry summary |

All responses mask secrets. Settings writes update local configuration only and
do not validate credentials through external calls.

## Frontend

The `/integrations` page is a read-only operational view for connector registry,
connector instances, advertised capabilities, runtime write blocking, and
telemetry. It is visible to users with `can_view_settings`.

The page intentionally has no Apply, Scheduler, pricing automation, or external
test button.

## Read-Only Safety

Beta safety rules:

- No Apply.
- No Scheduler execution.
- No automatic pricing.
- No WooCommerce writes.
- No Nextcloud writes.
- Connector `write_prices` and `write_inventory` are metadata only.
- Capability detection never grants authorization.
- Active Beta v2 routes do not perform direct external `httpx` calls.

## Current vs Future

Current:

- Local connector registry and instance records.
- Masked connector settings.
- Record-backed diagnostics contracts.
- Telemetry endpoint backed by local records.
- Product, Source, Workspace, Diagnostics, and Settings routes wired through
  Integration Platform/Data Layer records where available.

Future:

- Webhook receivers.
- Polling engine.
- File import engine.
- Message queue transports.
- Background refresh orchestration.
- Additional connectors: SnappShop, Tapsi Shop, Digikala, Technolife, Shopify,
  Magento, ERP, CSV, Google Sheets, and custom APIs.
- Write execution only after separate Owner approval and Write Guard design.
