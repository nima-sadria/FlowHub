# FlowHub — Current Architecture

**Document scope:** What is actually deployed and implemented as of BU5.
Planned and future items are clearly labelled. Do not treat any "future" section
as implemented behavior.

---

## Table of Contents

- [A. Current Deployed Architecture](#a-current-deployed-architecture)
- [B. Request and Data Flow](#b-request-and-data-flow)
- [C. Read-Only Safety Model](#c-read-only-safety-model)
- [D. Database Schema](#d-database-schema)
- [E. Deployment Model](#e-deployment-model)
- [F. Connector Framework](#f-connector-framework)
- [G. Integration Layer](#g-integration-layer)
- [H. Frontend Architecture](#h-frontend-architecture)
- [I. Authentication Model](#i-authentication-model)
- [J. Future Architecture Direction](#j-future-architecture-direction)

---

## A. Current Deployed Architecture

```
┌───────────────────────────────────────────────────────────────────────┐
│                           External Browser                            │
└─────────────────────────────────┬─────────────────────────────────────┘
                                  │ HTTPS (port 443)
                                  ▼
┌───────────────────────────────────────────────────────────────────────┐
│               Reverse Proxy  (Nginx Proxy Manager)                    │
│               TLS termination — external, not in this stack           │
└─────────────────────────────────┬─────────────────────────────────────┘
                                  │ HTTP  →  localhost:8085
                                  ▼
┌───────────────────────────────────────────────────────────────────────┐
│  Docker: app container  (flowhub-beta:latest)                         │
│  Build: Dockerfile.beta  (multi-stage: Node 20 → Python 3.12-slim)   │
│                                                                       │
│  Uvicorn  →  FastAPI (app.beta.app:app)                               │
│                                                                       │
│  ┌─── Static SPA ──────────────────────────────────────────────────┐  │
│  │  React 18 + Vite + Tailwind CSS                                 │  │
│  │  Bundled at build time; served at /*  (non-/api/ routes)        │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  ┌─── FastAPI Routers ─────────────────────────────────────────────┐  │
│  │  /api/health            health.router     (public)              │  │
│  │  /api/auth/*            auth.router       (JWT issue/refresh)   │  │
│  │  /api/v2/setup/*        setup.router      (setup wizard)        │  │
│  │  /api/v2/products/*     products.router   (WC browse)           │  │
│  │  /api/v2/sources        sources.router    (NC source status)    │  │
│  │  /api/v2/workspace/*    workspace.router  (preview)             │  │
│  │  /api/v2/settings/*     settings.router   (config management)   │  │
│  │  /api/v2/activity       activity.router   (audit log)           │  │
│  │  /api/v2/diagnostics/*  diagnostics.router(system status)       │  │
│  └───────────────────────────┬─────────────────────────────────────┘  │
│                              │                                        │
│  ┌─── Integration Layer ─────▼─────────────────────────────────────┐  │
│  │  app/beta/integrations/                                         │  │
│  │  WooCommerceClient    — thin wrapper, error translation         │  │
│  │  NextcloudClient      — thin wrapper, error translation         │  │
│  │  IntegrationError     — maps ConnectorError → HTTP 502          │  │
│  └───────────────────────────┬─────────────────────────────────────┘  │
│                              │                                        │
│  ┌─── Connector Framework ───▼─────────────────────────────────────┐  │
│  │  app/connectors/                                                │  │
│  │                                                                 │  │
│  │  ┌── WooCommerce destination ────┐  ┌── Nextcloud source ─────┐ │  │
│  │  │  connector.py                │  │  connector.py            │ │  │
│  │  │  rest_client.py  (GET only)  │  │  webdav.py               │ │  │
│  │  │  auth.py                     │  │  ocs.py                  │ │  │
│  │  └──────────────────────────────┘  │  auth.py                 │ │  │
│  │                                    └──────────────────────────┘ │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  ┌─── Database Layer ──────────────────────────────────────────────┐  │
│  │  SQLAlchemy ORM + Alembic migrations                            │  │
│  │  Connects to: postgres container (see below)                    │  │
│  └─────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────┘
                              │  external HTTP (GET only)
          ┌───────────────────┴────────────────────┐
          ▼                                        ▼
┌─────────────────────┐              ┌─────────────────────────────┐
│   WooCommerce       │              │        Nextcloud             │
│   REST API v3       │              │   WebDAV + OCS API           │
│   (your store)      │              │   (your instance)            │
└─────────────────────┘              └─────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────┐
│  Docker: postgres container  (postgres:16-alpine)                     │
│  Named volume: beta_pgdata                                            │
│                                                                       │
│  Tables: beta_users  beta_refresh_tokens  beta_login_audit            │
│          beta_app_config  alembic_version                             │
└───────────────────────────────────────────────────────────────────────┘
```

---

## B. Request and Data Flow

### Authentication flow

```
POST /api/auth/login  {username, password}
  │
  ├─ Look up beta_users by username
  ├─ Argon2 verify hashed_password
  ├─ Create JWT access token  (short-lived, signed with JWT_SECRET)
  ├─ Generate refresh token   (cryptographically random, hashed, stored in beta_refresh_tokens)
  ├─ Write beta_login_audit event ("login_success" or "login_failed")
  └─ Return {access_token, refresh_token, token_type: "bearer"}
```

### Setup wizard flow

```
GET /api/v2/setup/status  →  {completed: false}
  → Frontend redirects all routes to /setup
  → User steps through wizard:
      Step 1: POST /api/v2/setup/server-profile  → stores server.* in beta_app_config
      Step 2: POST /api/v2/setup/database        → verifies DB, checks Alembic version
      Step 3: POST /api/v2/setup/admin           → creates beta_users row, issues tokens
      Step 4a: POST /api/v2/setup/integrations/woocommerce
                 → stores woocommerce.* in beta_app_config
                 → registers masked Integration Platform settings
      Step 4b: POST /api/v2/setup/integrations/nextcloud
                 → stores nextcloud.* in beta_app_config
                 → registers masked Integration Platform settings
      Step 5: POST /api/v2/setup/complete
                 → sets beta_app_config["setup.completed"] = "true"
                 → all setup endpoints now return 409
  → Frontend clears /setup gate, shows normal routes
```

### Price preview flow

```
POST /api/v2/workspace/preview
  │
  ├─ IntegrationPlatformService.workspace_preview()
  ├─ Read local connector instance/settings state
  ├─ Read Data Layer records where available
  ├─ Return read-only preview shell with no changes
  └─ No external call, no Apply, no Scheduler, no pricing automation
```

### Diagnostics flow

```
GET /api/v2/diagnostics/status
  │
  ├─ Database: local DB status
  ├─ IntegrationPlatformService.diagnostics_status()
  ├─ Reads connector instances/settings and Data Layer health records
  └─ No external WooCommerce/Nextcloud probe in active Beta v2 routes
```

---

## C. Read-Only Safety Model

FlowHub Beta enforces read-only access at multiple levels.

### Enforcement levels

**Level 1 — No write path in code**

`app/connectors/destinations/woocommerce/rest_client.py` exposes only:
- `ping()` — GET /wc/v3/products?per_page=1
- `list_products_paged()` — GET /wc/v3/products
- `list_all_products()` — GET /wc/v3/products (all pages)
- `list_categories_all()` — GET /wc/v3/products/categories
- `count_products()` — GET /wc/v3/products?per_page=1 (reads X-WP-Total)

There is no PUT, POST, or DELETE call anywhere in `app/connectors/`.

**Level 2 — Abstract interface declares read-only intent**

`DestinationConnector` (base class, `app/connectors/common/base.py`) has this
docstring: _"All methods are READ-ONLY. No write path is permitted in FlowHub Beta."_

**Level 3 — No Apply endpoint**

No route or handler for applying prices exists in `app/beta/app.py` or any
registered router.

**Level 4 — No spreadsheet write path**

`NextcloudClient` exposes only `download_file()` and `get_file_meta()`.
No upload or write operation is exposed.

**Level 5 — Audit test**

`tests/beta/test_no_direct_httpx.py` contains two enforced checks:
- No file in `app/beta/` (except the generic adapter) may import `httpx` directly.
- No file in `app/beta/` may import the legacy `app.services.*` modules.

### Write-guard behavior (settings routes)

Settings endpoints (`POST /api/v2/settings/woocommerce`, etc.) write only to
`beta_app_config` in the PostgreSQL database. They do not write to WooCommerce or
Nextcloud.

### What is permanently blocked

| Operation | Status |
|---|---|
| Write prices to WooCommerce | No code path exists |
| Apply / bulk update | No code path exists |
| Scheduler / automatic pricing | No code path exists |
| Write to Nextcloud spreadsheet | No code path exists |
| WooCommerce batch update | No code path exists |

---

## D. Database Schema

**Alembic chain:** `beta_001` → `beta_002` → `beta_003` → `beta_004` (current head)

### `beta_users`  (beta_001)

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `username` | VARCHAR(150) UNIQUE NOT NULL | |
| `hashed_password` | VARCHAR(512) NOT NULL | Argon2id |
| `role` | VARCHAR(50) NOT NULL | Default: `viewer`. Values: `admin`, `viewer` |
| `is_active` | BOOLEAN NOT NULL | Default: `true` |
| `created_at` | DATETIME NOT NULL | Server default: `CURRENT_TIMESTAMP` |

Indexes: `ix_beta_users_id`, `ix_beta_users_username` (unique)

### `beta_refresh_tokens`  (beta_002)

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `user_id` | INTEGER NOT NULL | FK → `beta_users.id` ON DELETE CASCADE |
| `token_hash` | VARCHAR(64) UNIQUE NOT NULL | SHA-256 of the raw token |
| `expires_at` | DATETIME NOT NULL | 30-day lifetime |
| `revoked_at` | DATETIME NULL | Set on logout |

Indexes: `ix_beta_refresh_tokens_id`, `ix_beta_refresh_tokens_token_hash` (unique),
`ix_beta_refresh_tokens_user_id`

### `beta_login_audit`  (beta_003)

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `username` | VARCHAR(150) NOT NULL | |
| `event` | VARCHAR(50) NOT NULL | See event types below |
| `ip_address` | VARCHAR(45) NOT NULL | IPv4 or IPv6 |
| `created_at` | DATETIME NOT NULL | Server default: `CURRENT_TIMESTAMP` |

Indexes: `ix_beta_login_audit_id`, `ix_beta_login_audit_username`

**Current audit event types:** `login_success`, `login_failed`, `logout`,
`token_refreshed`, `setup_admin_created`, `setup_completed`, `settings_changed`,
`woocommerce_connected`, `nextcloud_connected`, `preview_started`,
`preview_completed`, `preview_failed`

### `beta_app_config`  (beta_004)

| Column | Type | Notes |
|---|---|---|
| `key` | VARCHAR(255) PK | Config key (dot-notation) |
| `value` | TEXT NULL | String value |
| `updated_at` | DATETIME NULL | Last write timestamp |
| `updated_by` | VARCHAR(150) NULL | Username or `setup_wizard` / `migration` |

**Known keys:**

| Key | Set by | Purpose |
|---|---|---|
| `setup.completed` | Setup wizard | `true` locks the wizard |
| `server.domain` | Setup step 1 | Public hostname |
| `server.port` | Setup step 1 | Public port |
| `server.environment` | Setup step 1 | Always `beta` |
| `server.timezone` | Setup step 1 | IANA timezone (e.g. `UTC`) |
| `server.currency` | Setup step 1 | ISO 4217 code (e.g. `USD`) |
| `server.sync_interval_minutes` | Settings | Metadata only; no scheduler in Beta |
| `woocommerce.url` | Setup step 4a / Settings | WC store URL |
| `woocommerce.key` | Setup step 4a / Settings | WC consumer key |
| `woocommerce.secret` | Setup step 4a / Settings | WC consumer secret |
| `nextcloud.url` | Setup step 4b / Settings | Nextcloud instance URL |
| `nextcloud.username` | Setup step 4b / Settings | Nextcloud username |
| `nextcloud.password` | Setup step 4b / Settings | Nextcloud app password |
| `nextcloud.spreadsheet_path` | Setup step 4b / Settings | DAV path to `.xlsx` file |

### `alembic_version`  (Alembic built-in)

Single row: `version_num = "beta_004"` on a fresh or fully migrated install.

---

## E. Deployment Model

### Docker Compose stack  (`docker-compose.beta.yml`)

```yaml
services:
  app:
    image: flowhub-beta:latest        # built from Dockerfile.beta
    ports:
      - "${BETA_PORT:-8085}:8085"     # host:container
    depends_on:
      postgres: {condition: service_healthy}
    healthcheck:
      test: curl -sf http://localhost:8085/api/health
      interval: 30s

  postgres:
    image: postgres:16-alpine
    volumes:
      - beta_pgdata:/var/lib/postgresql/data
    healthcheck:
      test: pg_isready -U $POSTGRES_USER -d $POSTGRES_DB
      interval: 10s

volumes:
  beta_pgdata:   # named volume — survives container restarts
```

**What is NOT in this stack:**
- Nginx (TLS handled by external Nginx Proxy Manager)
- Redis (noted as not required until B6)
- Celery or any task queue
- Any scheduler process

### Dockerfile.beta (multi-stage)

```
Stage 1: node:20-alpine
  npm ci → npm run build → /frontend/dist

Stage 2: python:3.12-slim
  apt: curl tzdata
  pip install -r requirements.txt
  COPY source + frontend/dist
  CMD: uvicorn app.beta.app:app --host 0.0.0.0 --port 8085
```

The React SPA is baked into the image. The FastAPI app serves it for all
non-`/api/` routes via a `/{full_path:path}` catch-all.

### Environment variables  (`.env.beta`)

Bootstrap secrets (not stored in DB):
- `BETA_POSTGRES_DB`, `BETA_POSTGRES_USER`, `BETA_POSTGRES_PASSWORD`
- `DATABASE_URL` — PostgreSQL connection string
- `JWT_SECRET` — minimum 32 bytes (64+ recommended)
- `BETA_PORT` — host port (default `8085`)
- `BETA_SSL_MODE` — `off` / `self-signed` / `manual` / `letsencrypt`

Runtime config (stored in `beta_app_config` after setup):
- WooCommerce credentials
- Nextcloud credentials
- Domain, timezone, currency

### Bind mounts

| Host path | Container path | Purpose |
|---|---|---|
| `./storage` | `/data/storage` | Persistent storage |
| `./backups` | `/data/backups` | Backups |
| `./logs` | `/data/logs` | Application logs |

### Installer

`installer/install.sh` is a bash-based guided installer.

```
install.sh
├── lib/wizard.sh       — interactive prompts (domain, SSL, DB credentials)
├── lib/env_gen.sh      — generates .env.beta from template
├── lib/secrets.sh      — generates JWT_SECRET and DB passwords
├── lib/ssl.sh          — Certbot / manual certificate handling
├── lib/docker_deploy.sh— docker compose up + migration run
├── lib/db_init.sh      — Alembic upgrade head
├── lib/admin.sh        — CLI create-admin
├── lib/storage.sh      — storage directory setup
├── lib/compose_gen.sh  — generates docker-compose.beta.yml from template
├── lib/checks.sh       — pre-install requirement checks
└── lib/uninstall.sh    — removal logic
```

The installer produces a management menu after first install:
1. Reinstall / update
2. Restart
3. Check status
4. Uninstall

---

## F. Connector Framework

### Design principles

1. **Isolation rule:** No code outside `app/connectors/<type>/<provider>/` may
   make HTTP calls to WooCommerce or Nextcloud. Enforced by AST audit test.
2. **No httpx in integration layer:** `app/beta/integrations/` must not import
   httpx. Enforced by `tests/beta/test_no_direct_httpx.py`.
3. **Error translation:** `ConnectorError` is translated to `IntegrationError`
   at the integration layer boundary. Routers catch `IntegrationError` and
   return HTTP 502.
4. **Connection test result:** `test_connection()` always returns
   `ConnectionTestResult(ok: bool, message: str, latency_ms: float)`.

### Common layer  (`app/connectors/common/`)

| Module | Purpose |
|---|---|
| `base.py` | `SourceConnector` and `DestinationConnector` abstract bases |
| `auth.py` | `AuthConfig(auth_type, credentials: dict)` — connector credentials envelope |
| `errors.py` | `ConnectorError(code, message, provider, retryable, http_status)` |
| `test_result.py` | `ConnectionTestResult(ok, message, latency_ms)` |
| `health.py` | `HealthResult` |
| `rate_limit.py` | Rate-limit helpers |
| `retry.py` | Retry helpers |
| `types.py` | `ConnectorCapabilities`, `ConnectorID`, `ConnectorType` |

### `ConnectorErrorCode` values

`AUTH_FAILED`, `NOT_FOUND`, `RATE_LIMITED`, `TIMEOUT`, `NETWORK`,
`PERMISSION`, `PROVIDER_ERROR`, `UNKNOWN`

### WooCommerce destination connector  (`destinations/woocommerce/`)

```
WooCommerceConnector (DestinationConnector)
  test_connection(auth) → ConnectionTestResult
    └─ rest_client.ping(creds)
         GET /wp-json/wc/v3/products?per_page=1
         returns {reachable, sample_count}

rest_client.py  (all GET, no writes)
  _get_raw(creds, path, params, timeout)    — GET with retry
    Retry: exponential backoff on {429, 500, 502, 503, 504}
    Max 3 retries, max 90s total sleep, honours Retry-After header
  list_products_paged(creds, page, per_page, search, category_id, product_type, fields, status)
    → (list[dict], total_count: int, total_pages: int)
    Preserves X-WP-Total and X-WP-TotalPages response headers
  list_all_products(creds, fields, status)  → list[dict]  (all pages, 100/page)
  list_categories_all(creds, fields)        → list[dict]  (all pages, 100/page)
  count_products(creds, status)             → int  (from X-WP-Total)
  ping(creds)                               → dict  {reachable, sample_count}
```

### Nextcloud source connector  (`sources/nextcloud/`)

```
NextcloudConnector (SourceConnector)
  test_connection(auth) → ConnectionTestResult
    └─ ocs.get_user_info(creds)  — OCS /ocs/v2.php/cloud/users/{username}
                                   measures latency

webdav.py
  get_file(creds, path)           → (bytes, meta: dict)
    WebDAV GET — returns file content + {etag, last_modified, content_type, content_length}
    Raises ConnectorError on auth/network/not-found failures
  head_file(creds, path)          → dict  {etag, last_modified, content_length}
    HEAD request — never raises (returns None-valued dict on any failure)
  get_metadata(creds, path)       → dict  {etag, last_modified, is_collection, ...}
    PROPFIND depth=0 — raises ConnectorError on failures

ocs.py
  get_user_info(creds)            → dict  OCS user data + latency
  Raises ConnectorError on auth/network failures
```

### Integration Platform wiring summary

| Beta route | Integration method | External connector call |
|---|---|---|
| `GET /api/v2/products` | `IntegrationPlatformService.list_products()` | None |
| `GET /api/v2/products/categories` | `IntegrationPlatformService.list_categories()` | None |
| `GET /api/v2/sources` | `IntegrationPlatformService.list_sources()` | None |
| `GET /api/v2/workspace` | `IntegrationPlatformService.workspace_state()` | None |
| `POST /api/v2/workspace/preview` | `IntegrationPlatformService.workspace_preview()` | None |
| `GET /api/v2/diagnostics/status` | `IntegrationPlatformService.diagnostics_status()` | None |
| `POST /api/v2/diagnostics/run` | `IntegrationPlatformService.diagnostics_run()` | None |
| `GET/PATCH /api/v2/integrations/*/settings` | `IntegrationPlatformService` settings APIs | None |
| `POST /api/v2/setup/integrations/woocommerce` | `IntegrationPlatformService.ensure_connector_from_settings()` | None |
| `POST /api/v2/setup/integrations/nextcloud` | `IntegrationPlatformService.ensure_connector_from_settings()` | None |

Active Beta v2 product, source, workspace, diagnostics, settings, and
Integration Platform routes are record-backed. They do not import legacy
WooCommerce/Nextcloud clients and do not perform direct `httpx` calls.

### Legacy layer (isolated, not used by Beta runtime)

`app/services/woocommerce.py` and `app/services/nextcloud.py` are legacy
WooPrice (v1) service modules. They are used exclusively by `app/main.py`
(the original WooPrice app on port 8000). They make direct httpx calls and are
explicitly marked as LEGACY in their module headers. No `app/beta/` module
imports them (verified by `tests/beta/test_no_direct_httpx.py:test_legacy_services_not_imported_by_beta`).

---

## G. Integration Layer

`app/beta/integrations/` provides the boundary between route handlers and the
connector framework.

```
app/beta/integrations/
├── woocommerce.py   WooCommerceClient — wraps rest_client functions
├── nextcloud.py     NextcloudClient  — wraps webdav/ocs functions
├── spreadsheet.py   load_workbook_bytes(), parse_price_list()
└── errors.py        IntegrationError(message, detail)
                       → caught by routers → HTTP 502
```

**`WooCommerceClient`** is constructed with `(url, key, secret)` and exposes:
- `get_products_page(page, per_page, search, category_id, product_type)` → `(list, total)`
- `get_all_products_for_preview()` → `list`
- `get_categories()` → `list`
- `count_products()` → `int`
- `test_connection()` → `(bool, str, float)`
- `from_config(cfg)` — class method, returns `None` if not configured

**`NextcloudClient`** is constructed with `(url, username, password)` and exposes:
- `download_file(path)` → `(bytes, meta_dict)`
- `get_file_meta(path)` → `meta_dict` — never raises
- `test_connection()` → `(bool, str, float)`
- `from_config(cfg)` — class method, returns `None` if not configured

**Error translation** (`_to_integration_error`):

| `ConnectorErrorCode` | `IntegrationError.message` |
|---|---|
| `AUTH_FAILED` | `Authentication failed — check credentials` |
| `PERMISSION` | `Access denied — check permissions` |
| `NOT_FOUND` | `Not found: {endpoint}` |
| `TIMEOUT` | `Connection timed out` |
| `NETWORK` | `Could not connect to {provider}` |
| `RATE_LIMITED` | `Rate limited — retry budget exhausted` |
| `PROVIDER_ERROR` | `Provider error` |
| `UNKNOWN` | `Unexpected error` |

---

## H. Frontend Architecture

### Build and serving

The React SPA is built by Vite at Docker image build time and served by the
FastAPI app's catch-all route (`/{full_path:path}`). The `/api/` prefix is
reserved for API routes; all other paths return `index.html`.

### Route map

```
SetupGate
  └─ if setup not complete → /setup (Setup wizard) only
  └─ if setup complete →
       /login              Login (unauthenticated)
       /                   → redirect to /home
       AuthGuard
         AppShell
           /home           BetaDashboard   (can_access_site)
           /products       Products        (can_fetch)
           /sources        Sources         (can_access_site)
           /sources/new    SourceWizard    (can_access_site)
           /workspace      Workspace       (can_fetch)
           /activity       Activity        (can_view_logs)
           /diagnostics    Diagnostics     (can_view_settings)
           /settings       Settings        (can_view_settings)
         *                 NotFound
```

### Service layer (frontend)

The frontend uses a service abstraction for all API calls:

| Service interface | Real implementation | Mock implementation |
|---|---|---|
| `HealthService` | `ApiHealthService` | `MockHealthService` |
| `ProductService` | `ApiProductService` | `MockProductService` |
| `SourceService` | `ApiSourceService` | `MockSourceService` |
| `WorkspaceService` | `ApiWorkspaceService` | `MockWorkspaceService` |
| `SettingsService` | `ApiSettingsService` | `MockSettingsService` |
| `ActivityService` | `ApiActivityService` | `MockActivityService` |

Mocks are activated when `VITE_DEV_MOCK=true` (development only). Production
always uses real API services.

### Permissions enforced client-side (also enforced server-side)

| Permission | Guards |
|---|---|
| `can_access_site` | `/home`, `/sources`, `/sources/new` |
| `can_fetch` | `/products`, `/workspace` |
| `can_view_logs` | `/activity` |
| `can_view_settings` | `/diagnostics`, `/settings` |

---

## I. Authentication Model

### JWT access tokens

- Algorithm: HS256 (HMAC-SHA256)
- Secret: `JWT_SECRET` environment variable (min 32 bytes, recommended 64+)
- Payload: `{sub: username, role, pv: permission_version, exp, iat}`
- Short-lived (exact TTL configured in JWT service)

### Refresh tokens

- Generated: `secrets.token_bytes(32)` → hex string
- Stored: SHA-256 hash in `beta_refresh_tokens.token_hash`
- Lifetime: 30 days from issue
- Rotation: each `POST /api/auth/refresh` issues a new token and revokes the old one
- Revocation: `POST /api/auth/logout` sets `revoked_at` on the token row

### Password hashing

Argon2id via the `passlib` library. Hashes stored in `beta_users.hashed_password`.

### Roles

| Role | Value | Capabilities |
|---|---|---|
| Admin | `admin` | Full access including settings and diagnostics |
| Viewer | `viewer` | Read access scoped by permission flags |

---

## J. Future Architecture Direction

> **This section distinguishes the implemented Integration Platform foundation
> from planned future orchestration.**

### Integration Platform Foundation

The current system includes the Integration Platform foundation:

- Canonical connector capability metadata.
- Connector registry for WooCommerce and Nextcloud.
- Local connector instance, setting, health/status, diagnostics, and telemetry
  records.
- Beta v2 Products, Sources, Workspace, Diagnostics, Settings, and telemetry
  routes wired through Integration Platform/Data Layer records.
- Read-only safety: no Apply, Scheduler execution, automatic pricing,
  WooCommerce writes, or Nextcloud writes.

### Future Integration Platform Orchestration

The long-term vision is to extend the foundation into centralised orchestration:

```
FlowHub Frontend
      │
      ▼
FlowHub Backend  (FastAPI)
      │
      ▼
Integration Platform
      │
      ├── Connector Manager     — register, configure, and lifecycle-manage connectors
      │
      ├── Event Bus             — internal pub/sub for connector events and state changes
      │
      ├── Cache Manager         — per-connector data cache with TTL and invalidation
      │
      ├── Sync Engine           — orchestrate reads across sources and destinations
      │         └─ (future) Apply Engine  — orchestrate writes (price updates, stock)
      │
      ├── Health Monitor        — continuous background health probes per connector
      │
      ├── Metrics / Audit       — structured event log for all platform operations
      │
      ├── Webhook Receiver      — receive push events from external systems
      │
      └── Polling Engine        — scheduled polling for systems without webhooks
            │
            ▼
      Connector Layer
            │
            ├── Sources (read)
            │     ├── Nextcloud     (implemented)
            │     ├── CSV
            │     ├── Google Sheets
            │     └── Custom APIs
            │
            └── Destinations (read + write when Apply is enabled)
                  ├── WooCommerce   (implemented, read-only in Beta)
                  ├── SnappShop
                  ├── Digikala
                  ├── Technolife
                  ├── Shopify
                  ├── ERP
                  └── Custom APIs
```

### What needs to change from current architecture

| Current | Future |
|---|---|
| Record-backed Integration Platform foundation | Sync Engine orchestrates approved connector reads |
| No background tasks or scheduling | Polling Engine + Event Bus |
| No Apply | Apply Engine gated behind approval flow |
| PostgreSQL only | PostgreSQL + Redis (cache + task queue) |
| Single store per install | Multi-store Channel Profiles |
| Per-route health checks (diagnostics endpoint) | Continuous background Health Monitor |
| Beta-only read path | Full read/write lifecycle with audit trail |

### Not in current scope

The following are permanently blocked in Beta and require explicit Owner approval
to unlock in any future phase:
- WooCommerce write path (Apply)
- Spreadsheet write path
- Automatic / scheduled pricing
- Multi-store support
- External marketplace connectors

---

*This document reflects the state of FlowHub at commit `73af5c8` (Connector Wiring Phase complete, 2026-07-01).*
