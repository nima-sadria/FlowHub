# FlowHub

FlowHub is a self-hosted price-intelligence hub. It connects a WooCommerce store
to a Nextcloud spreadsheet, lets operators preview which product prices need
updating, and presents the comparison in a web dashboard. All reads, no writes —
every change must be applied by a human.

> **Status: Beta (BU5).**
> FlowHub Beta is a fully read-only system. No prices are ever written to
> WooCommerce and nothing is written to the spreadsheet. See
> [Read-Only Safety Rule](#read-only-safety-rule) below.

---

## Architecture Contracts

- [Integration Platform](docs/architecture/INTEGRATION_PLATFORM.md) documents
  the connector registry, connector lifecycle, diagnostics, telemetry,
  webhook, polling, and Beta write guard API contracts.
- [Unified Logging Platform](docs/architecture/UNIFIED_LOGGING_PLATFORM.md)
  documents application logging, search, correlation, export, retention,
  redaction, and future Live Tail API contracts.

---

## Table of Contents

1. [What FlowHub Does](#what-flowhub-does)
2. [Read-Only Safety Rule](#read-only-safety-rule)
3. [Architecture Overview](#architecture-overview)
4. [How the Preview Flow Works](#how-the-preview-flow-works)
5. [Requirements](#requirements)
6. [Install](#install)
7. [Web Setup Wizard](#web-setup-wizard)
8. [Verify](#verify)
9. [Frontend Pages](#frontend-pages)
10. [API Layers](#api-layers)
11. [Connector Framework](#connector-framework)
12. [Database Tables](#database-tables)
13. [FlowHub Data Layer](#flowhub-data-layer)
14. [What is Real Now vs Planned](#what-is-real-now-vs-planned)
14. [Management CLI](#management-cli)
15. [Operations](#operations)
16. [Documentation](#documentation)

---

## What FlowHub Does

1. The operator uploads a spreadsheet to Nextcloud containing WooCommerce product
   IDs and target prices.
2. FlowHub downloads the spreadsheet, fetches all WooCommerce products, and
   compares them in memory.
3. The web UI shows a live preview: which products have price differences, by how
   much, and in which direction.
4. The operator reviews the diff and decides what to do — FlowHub does not write
   anything.

---

## Read-Only Safety Rule

**FlowHub Beta is strictly read-only.**

| Forbidden action | Status |
|---|---|
| Write prices to WooCommerce | Permanently blocked — no write path exists in code |
| Apply / bulk update | Not implemented |
| Scheduler / automatic pricing | Not implemented |
| Write to the Nextcloud spreadsheet | Not implemented |
| Channel Profile / multi-store | Not implemented |

The WooCommerce connector (`app/connectors/destinations/woocommerce/`) exposes
only GET operations: product listing, category listing, count, and ping. There is
no PUT, POST, or DELETE path in the entire Beta codebase.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Browser                                 │
│               React SPA  (Vite / Tailwind)                      │
└────────────────────────────┬────────────────────────────────────┘
                             │  HTTPS
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              Reverse Proxy  (Nginx Proxy Manager)               │
│              TLS termination — not managed by this stack        │
└────────────────────────────┬────────────────────────────────────┘
                             │  HTTP  → localhost:8085
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│         Docker container: app  (flowhub-beta:latest)            │
│                                                                 │
│   Uvicorn → FastAPI  (app.beta.app:app)                         │
│                                                                 │
│   ┌────────────┬──────────┬──────────┬──────────┬──────────┐   │
│   │   /api/    │ /api/v2/ │ /api/v2/ │ /api/v2/ │ /api/v2/ │   │
│   │   health   │  setup   │ products │ workspace│ settings │   │
│   │   auth/*   │          │ sources  │          │ activity │   │
│   │            │          │          │          │diagnostics│  │
│   └─────┬──────┴────┬─────┴────┬─────┴────┬─────┴──────────┘   │
│         │           │          │          │                     │
│   ┌─────▼───────────▼──────────▼──────────▼──────────────────┐ │
│   │         Integration Layer  (app/beta/integrations/)       │ │
│   │      WooCommerceClient          NextcloudClient           │ │
│   └───────────────┬─────────────────────────┬────────────────┘ │
│                   │                         │                   │
│   ┌───────────────▼──────┐   ┌──────────────▼───────────────┐  │
│   │  Connector Framework │   │  Connector Framework         │  │
│   │  destinations/       │   │  sources/                    │  │
│   │  woocommerce/        │   │  nextcloud/                  │  │
│   │  rest_client.py      │   │  webdav.py  ocs.py           │  │
│   └───────────────┬──────┘   └──────────────┬───────────────┘  │
└───────────────────┼──────────────────────────┼──────────────────┘
                    │  WC REST API v3 (GET)     │  WebDAV / OCS
                    ▼                           ▼
             WooCommerce                    Nextcloud

┌─────────────────────────────────────────────────────────────────┐
│  Docker container: postgres  (postgres:16-alpine)               │
│  Named volume: beta_pgdata                                      │
│  Tables: beta_users  beta_refresh_tokens  beta_login_audit      │
│          beta_app_config  alembic_version                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## How the Preview Flow Works

```
POST /api/v2/workspace/preview
         │
         ├─ WooCommerceClient.get_all_products_for_preview()
         │      └─ rest_client.list_all_products()  [GET /wc/v3/products, all pages]
         │
         ├─ NextcloudClient.download_file(nc_path)
         │      └─ webdav.get_file()  [WebDAV GET]
         │
         ├─ spreadsheet.load_workbook_bytes()  +  parse_price_list()
         │      └─ openpyxl — col B = WC product ID, col C = target price
         │
         └─ _compute_preview()  [in-memory diff, no writes]
                  │
                  └─ Returns: {id, changes[], totalChanges, duplicateWarnings}

Nothing is persisted. The result is returned and discarded.
```

---

## Requirements

- Docker Engine with the Compose v2 plugin (`docker compose`)
- A user in the `docker` group (or root)
- Port `8085` available on the host (configurable via `BETA_PORT` in `.env.beta`)
- A running WooCommerce store with REST API enabled (Consumer Key + Secret)
- A running Nextcloud instance with a price-list spreadsheet (`.xlsx`)

---

## Install

### Option A — Guided installer (recommended)

```bash
cd /opt/flowhub
sudo ./installer/install.sh
```

The installer:
1. Prompts for domain, SSL mode, database credentials, and integration credentials
2. Generates `.env.beta` (mode `600`, never committed)
3. Builds the Docker image (multi-stage: Node 20 → Python 3.12-slim)
4. Starts the stack and runs Alembic migrations
5. Prints the generated admin password once

After the installer completes, open the web setup wizard at `https://your-domain/setup`
to configure the application settings.

### Option B — Manual

```bash
cd /opt/flowhub

# 1. Configure environment
cp .env.beta.example .env.beta
nano .env.beta            # set DB credentials, JWT secret, integration credentials

# 2. Validate the compose config
docker compose -f docker-compose.beta.yml --env-file .env.beta config

# 3. Build and start
docker compose -f docker-compose.beta.yml --env-file .env.beta up -d --build

# 4. Run database migrations
docker compose -f docker-compose.beta.yml --env-file .env.beta \
  exec app alembic -c alembic_beta.ini upgrade head

# 5. Create the initial admin user
docker compose -f docker-compose.beta.yml --env-file .env.beta \
  exec app python -m cli.main create-admin
```

> **Database credentials:** PostgreSQL only initialises the role and database
> on the **first** start with an empty data volume. Changing credentials after
> the volume exists requires a full reset:
>
> ```bash
> docker compose -f docker-compose.beta.yml --env-file .env.beta down
> docker volume rm flowhub_beta_pgdata
> docker compose -f docker-compose.beta.yml --env-file .env.beta up -d
> ```

---

## Web Setup Wizard

After the Docker stack is running, the web app gates all routes behind `/setup`
until setup is marked complete.

**Wizard steps (in order):**

| Step | Endpoint | Purpose |
|---|---|---|
| 1 | `POST /api/v2/setup/server-profile` | Domain, port, timezone, currency |
| 2 | `POST /api/v2/setup/database` | Verify DB connection + migration version |
| 3 | `POST /api/v2/setup/admin` | Create the first administrator account |
| 4a | `POST /api/v2/setup/integrations/woocommerce` | Save + test WC credentials |
| 4b | `POST /api/v2/setup/integrations/nextcloud` | Save + test NC credentials |
| 5 | `POST /api/v2/setup/complete` | Lock the wizard (cannot be re-run via API) |

Once `setup.completed = true` is stored in `beta_app_config`, all setup endpoints
return `409 Conflict`. A database reset is required to re-run setup.

---

## Network and Domain

FlowHub binds internally on port `8085`. Nginx Proxy Manager (or any reverse proxy)
forwards HTTPS traffic to `localhost:8085`.

| SSL mode | Public URL | Internal port |
|---|---|---|
| `off` | `http://domain:8085` | `8085` |
| `self-signed` | `https://domain:8085` | `8085` |
| `manual` | `https://domain` | `8085` |
| `letsencrypt` | `https://domain` | `8085` |

---

## Verify

```bash
# Health probe (no auth required)
curl -s http://localhost:8085/api/health
# → {"status":"ok","env":"beta","version":"0.1.0-dev"}

# Login
curl -s -X POST http://localhost:8085/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<password>"}'
# → {"access_token":"...","refresh_token":"...","token_type":"bearer"}

# Current user
curl -s http://localhost:8085/api/auth/me \
  -H "Authorization: Bearer <access_token>"
```

---

## Frontend Pages

All pages are served from the compiled React SPA. The `/setup` gate is active
until setup is complete.

| Route | Page | Auth required | Purpose |
|---|---|---|---|
| `/setup` | Setup | No | First-run wizard (locked once complete) |
| `/login` | Login | No | Sign in |
| `/home` | Dashboard | Yes | Status overview |
| `/products` | Products | Yes (`can_fetch`) | Browse WooCommerce products |
| `/sources` | Sources | Yes | View configured sources (Nextcloud) |
| `/sources/new` | Source Wizard | Yes | Add a new source |
| `/workspace` | Workspace | Yes (`can_fetch`) | Run and view price preview |
| `/activity` | Activity | Yes (`can_view_logs`) | Audit event log |
| `/data-layer` | Data Layer | Yes (`can_view_settings`) | Data Layer status — all stores, health, telemetry |
| `/diagnostics` | Diagnostics | Yes (`can_view_settings`) | Live system diagnostics |
| `/settings` | Settings | Yes (`can_view_settings`) | Credentials and runtime config |

---

## API Layers

### Public endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Liveness probe — always 200 when running |
| `GET` | `/api/v2/setup/status` | Setup completion check — drives the setup gate |

### Auth endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/auth/login` | Issue JWT access + refresh tokens |
| `POST` | `/api/auth/refresh` | Rotate refresh token |
| `POST` | `/api/auth/logout` | Revoke refresh token |
| `GET` | `/api/auth/me` | Current user profile |

### Setup wizard (unauthenticated while setup is incomplete)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v2/setup/server-profile` | Step 1: domain, timezone, currency |
| `POST` | `/api/v2/setup/database` | Step 2: verify DB + migration version |
| `POST` | `/api/v2/setup/admin` | Step 3: create first admin |
| `POST` | `/api/v2/setup/integrations/woocommerce` | Step 4a: WC credentials |
| `POST` | `/api/v2/setup/integrations/nextcloud` | Step 4b: NC credentials |
| `POST` | `/api/v2/setup/complete` | Step 5: lock wizard |

### Runtime API (JWT bearer required)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v2/products` | Paginated WooCommerce product list |
| `GET` | `/api/v2/products/categories` | WooCommerce category list |
| `GET` | `/api/v2/sources` | Configured sources (Nextcloud) |
| `POST` | `/api/v2/workspace/preview` | Compute read-only price preview |
| `GET` | `/api/v2/workspace/state` | Workspace state (always `idle` in Beta) |
| `GET` | `/api/v2/settings` | Non-secret settings + configured flags |
| `POST` | `/api/v2/settings` | Update timezone / currency / sync interval |
| `POST` | `/api/v2/settings/woocommerce` | Replace WooCommerce credentials |
| `POST` | `/api/v2/settings/nextcloud` | Replace Nextcloud credentials |
| `GET` | `/api/v2/activity` | Paginated audit event log |
| `GET` | `/api/v2/diagnostics/status` | Live system diagnostics (WC + NC + DB) |
| `POST` | `/api/v2/diagnostics/run` | **Stub — not implemented (planned B6)** |
| `GET` | `/api/v2/diagnostics/history` | **Stub — not implemented (planned B6)** |

---

## Connector Framework

All external HTTP calls go through `app/connectors/`. No code outside this
directory may make WooCommerce or Nextcloud HTTP requests directly.

```
app/connectors/
├── common/
│   ├── base.py          SourceConnector / DestinationConnector (abstract bases)
│   ├── auth.py          AuthConfig — connector credentials envelope
│   ├── errors.py        ConnectorError + ConnectorErrorCode enum
│   ├── test_result.py   ConnectionTestResult(ok, message, latency_ms)
│   ├── health.py        HealthResult
│   ├── rate_limit.py    Rate-limit helpers
│   ├── retry.py         Retry helpers
│   └── types.py         ConnectorCapabilities, ConnectorID, ConnectorType
│
├── sources/
│   └── nextcloud/       Nextcloud source connector (IMPLEMENTED)
│       ├── connector.py NextcloudConnector — test_connection, health
│       ├── webdav.py    WebDAV: get_file, head_file, get_metadata (PROPFIND)
│       ├── ocs.py       OCS API: user info, capabilities check
│       └── auth.py      NextcloudCredentials
│
└── destinations/
    └── woocommerce/     WooCommerce destination connector (IMPLEMENTED, READ-ONLY)
        ├── connector.py WooCommerceConnector — test_connection, health
        ├── rest_client.py WC REST API v3 GET: products, categories, count, ping
        └── auth.py      WooCommerceCredentials
```

**Currently implemented connectors:** WooCommerce (destination, read-only),
Nextcloud (source).

**Not yet implemented:** SnappShop, Digikala, Technolife, Shopify, ERP, CSV,
Google Sheets, custom APIs. The current Integration Platform provides the
registry, connector instance, settings, diagnostics, telemetry, webhook,
polling policy, and write guard contracts for current and future connectors.

The integration layer (`app/beta/integrations/`) provides thin wrapper classes
(`WooCommerceClient`, `NextcloudClient`) that translate `ConnectorError` →
`IntegrationError` → HTTP 502 for the API routers. Route handlers never
interact with the connector layer directly.

---

## Database Tables

Platform tables are created by Alembic migrations (`alembic_beta/versions/`).
Current head revision: `beta_007`.

| Table | Migration | Purpose |
|---|---|---|
| `beta_users` | beta_001 | User accounts (username, hashed password, role, is_active) |
| `beta_refresh_tokens` | beta_002 | JWT refresh token store (hashed, with expiry and revocation) |
| `beta_login_audit` | beta_003 | Audit log (login, logout, setup events, settings changes) |
| `beta_app_config` | beta_004 | Key-value runtime config (credentials, timezone, currency, setup flag) |
| `dl_*` tables | beta_005 | FlowHub Data Layer read models and telemetry |
| `ip_*` tables | beta_006, beta_007 | Integration Platform registry, settings, diagnostics, telemetry, webhook, polling records |
| `logging_*` tables | beta_007 | Unified Logging Platform entries, correlation, retention, export, and redaction records |
| `alembic_version` | built-in | Alembic migration tracking |

**Key config keys stored in `beta_app_config`:**
- `setup.completed` — `true`/`false`, drives the setup gate
- `woocommerce.url`, `woocommerce.key`, `woocommerce.secret`
- `nextcloud.url`, `nextcloud.username`, `nextcloud.password`, `nextcloud.spreadsheet_path`
- `server.domain`, `server.port`, `server.timezone`, `server.currency`, `server.environment`
- `server.sync_interval_minutes`

Credentials are stored in this table and never returned to the frontend. The
settings API returns only `wcConfigured: true/false` and `ncConfigured: true/false`.

---

## FlowHub Data Layer

The **FlowHub Data Layer** is the persistent read model that sits between external systems
(WooCommerce, Nextcloud) and the FlowHub UI. It provides a structured store for product
data, connector health, telemetry, refresh job history, and invalidation events.

> **Important:** "Cache" is one internal mechanism inside the Data Layer.
> The canonical name is "FlowHub Data Layer" — not "Cache Architecture."

### Data Layer UI Route

A dedicated page is available at `/data-layer` in the web UI. It shows:
- Product cache status (initialized / total / fresh / stale)
- Source and destination snapshot status
- Connector health (healthy / degraded / unhealthy per connector)
- Connector telemetry (request counts, error counts, throughput)
- Refresh queue status and recent job history
- Invalidation event log
- TTL policy status
- Multi-channel readiness (current + future connectors)
- Read-only safety confirmation

### Data Layer Tables (DL1)

| Table | Purpose |
|---|---|
| `dl_connector_health` | Per-connector health check results |
| `dl_connector_telemetry` | Per-connector telemetry aggregates |
| `dl_product_cache` | Product read model (name, price, stock, freshness) |
| `dl_inventory_cache` | Inventory state (stock qty, status, backorders) |
| `dl_source_snapshots` | Source file snapshot metadata (ETag, row count) |
| `dl_destination_snapshots` | Destination product/price snapshot |
| `dl_refresh_jobs` | Refresh job history and status |
| `dl_invalidation_events` | Invalidation event audit log |

### Current State (DL1)

The Data Layer schema and service layer are implemented. All `dl_*` tables exist.
In DL1, tables start empty because there is no background refresh yet. The UI shows
"Not initialized yet" empty states — this is correct and expected. Data populates
as products are browsed and connector interactions occur in future phases.

### Reference

See [`docs/architecture/DATA_LAYER_ARCHITECTURE.md`](docs/architecture/DATA_LAYER_ARCHITECTURE.md)
for the complete architecture including all stores, TTL policy, invalidation policy,
data flow diagrams, multi-channel readiness, and the full database model.

---

## What is Real Now vs Planned

### Implemented and active

- Docker Compose stack (app + postgres)
- Guided bash installer with SSL mode selection
- Web setup wizard (5-step, locks on completion)
- JWT auth (access + refresh tokens, Argon2 hashing)
- Role-based permissions (admin, viewer)
- Audit logging to `beta_login_audit`
- Connector Framework with WooCommerce and Nextcloud connectors
- WooCommerce product browser (paginated, search, category filter)
- Price preview (stateless in-memory diff)
- Sources view (Nextcloud source status)
- Settings management (credentials, timezone, currency)
- Activity log (audit events)
- Live diagnostics backed by Integration Platform/Data Layer records
- Integration Platform APIs and `/integrations` UI
- Unified Logging Platform APIs and `/logging` UI
- Management CLI (`python -m cli.main`)

### Stubs — endpoint exists, not implemented

| Endpoint | Planned phase |
|---|---|
| `GET /api/v2/diagnostics/history` | B6 — Advanced Diagnostics |

### Planned but not started

- Apply (write prices to WooCommerce) — permanently blocked in Beta by design
- Scheduler / automatic pricing — permanently blocked in Beta by design
- Spreadsheet write path — permanently blocked in Beta by design
- Additional connectors (SnappShop, Digikala, Shopify, ERP, CSV, Google Sheets)
- Integration Platform Sync Engine execution and approved connector refresh workers
- Redis cache layer (noted in docker-compose.beta.yml: not required until B6)
- Channel Profile (multi-store management)
- A2 pricing rule engine (exists in `app/a2/` but not wired to Beta runtime)

---

## Management CLI

```bash
# Inside the container
docker compose -f docker-compose.beta.yml --env-file .env.beta exec app \
  python -m cli.main --help

# Common commands
python -m cli.main create-admin   # create the initial admin account
python -m cli.main status         # environment and configuration status
python -m cli.main health         # local health checks
python -m cli.main migrate        # run or check database migrations
```

---

## Operations

```bash
# Status
docker compose -f docker-compose.beta.yml --env-file .env.beta ps

# Logs
docker compose -f docker-compose.beta.yml --env-file .env.beta logs -f app

# Restart
docker compose -f docker-compose.beta.yml --env-file .env.beta restart app

# Stop (data volume preserved)
docker compose -f docker-compose.beta.yml --env-file .env.beta down
```

Bind mounts: `./storage → /data/storage`, `./backups → /data/backups`,
`./logs → /data/logs`.

### Uninstall

```bash
sudo bash installer/install.sh --uninstall
```

The uninstaller removes containers, images, volumes, and the CLI symlink.
Backups are excluded by default. A clean reinstall can follow immediately.

---

## Documentation

Detailed architecture, security, and deployment documents live under `docs/`.

| Document | Purpose |
|---|---|
| [`docs/architecture/CURRENT_ARCHITECTURE.md`](docs/architecture/CURRENT_ARCHITECTURE.md) | Full technical architecture reference |
| [`docs/architecture/DATA_LAYER_ARCHITECTURE.md`](docs/architecture/DATA_LAYER_ARCHITECTURE.md) | FlowHub Data Layer — stores, TTL, invalidation, data flows |
| [`docs/beta/DEPLOYMENT_ARCHITECTURE.md`](docs/beta/DEPLOYMENT_ARCHITECTURE.md) | Docker deployment details |
| [`docs/beta/SECURITY_ARCHITECTURE.md`](docs/beta/SECURITY_ARCHITECTURE.md) | Auth and security model |
| [`docs/beta/INSTALLER_ARCHITECTURE.md`](docs/beta/INSTALLER_ARCHITECTURE.md) | Installer internals |
| [`docs/beta/BU2_AUTH_ARCHITECTURE.md`](docs/beta/BU2_AUTH_ARCHITECTURE.md) | JWT and session model |
