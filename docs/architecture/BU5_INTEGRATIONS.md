# BU5 Integration Architecture

**Phase:** BU5 — Real Backend Integration (Read-Only)
**Version:** 0.3.0-bu5
**Status:** COMPLETE

---

## Overview

BU5 replaces all mock services with real read-only backend APIs. The integration layer connects FlowHub Beta to two external systems:

- **WooCommerce** — product catalogue via REST API v3
- **Nextcloud** — XLSX spreadsheet via WebDAV

All external communication is **read-only**. No writes, no Apply, no Scheduler. Write attempts return HTTP 403 from the write guard.

---

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────┐
│                     Frontend (React)                      │
│                                                           │
│  Products   Workspace   Settings   Diagnostics  Activity  │
│  page       page        page       page         page      │
└─────────────────────────┬────────────────────────────────┘
                          │  JWT Bearer token (authFetch)
                          │
┌─────────────────────────▼────────────────────────────────┐
│                  FastAPI (app/beta/app.py)                 │
│                                                           │
│  /api/v2/products       /api/v2/workspace/preview         │
│  /api/v2/sources        /api/v2/settings                  │
│  /api/v2/activity       /api/v2/diagnostics/status        │
└────────┬───────────────────────────────────┬─────────────┘
         │                                   │
┌────────▼────────┐               ┌──────────▼──────────┐
│ WooCommerceClient│               │  NextcloudClient    │
│ (integrations/  │               │  (integrations/     │
│  woocommerce.py)│               │   nextcloud.py)     │
│                 │               │                     │
│ REST v3 + retry │               │ WebDAV GET/HEAD/    │
│ Timeout policy  │               │ PROPFIND            │
│ IntegrationError│               │ IntegrationError    │
└────────┬────────┘               └──────────┬──────────┘
         │                                   │
         │  HTTPS                            │  HTTPS
         ▼                                   ▼
  ┌─────────────┐                   ┌──────────────────┐
  │ WooCommerce │                   │    Nextcloud     │
  │ (external)  │                   │    (external)    │
  └─────────────┘                   └────────┬─────────┘
                                             │ bytes
                                    ┌────────▼─────────┐
                                    │ spreadsheet.py   │
                                    │ parse_price_list │
                                    └──────────────────┘
```

---

## Integration Layer

All external integrations live in `app/beta/integrations/`:

| Module | Purpose |
|---|---|
| `errors.py` | `IntegrationError` — unified error type for all providers |
| `woocommerce.py` | `WooCommerceClient` — read-only WC REST v3 client |
| `nextcloud.py` | `NextcloudClient` — read-only WebDAV client |
| `spreadsheet.py` | `parse_price_list()` — XLSX parser, all sheets, last-sheet-wins |
| `write_guard.py` | `raise_write_blocked()` — HTTP 403 for any write attempt |

**Abstraction rule**: API routers import the client classes and `IntegrationError`. They never import httpx directly. No router knows about retry logic, timeout values, or WebDAV internals.

---

## Error Model

Every integration client raises `IntegrationError` instead of letting httpx or stdlib exceptions propagate. Routers map it to HTTP 502.

```python
class IntegrationError(Exception):
    provider: str      # "WooCommerce" | "Nextcloud"
    endpoint: str      # URL that failed
    message: str       # human-readable, no secrets
    status_code: int   # HTTP status if applicable, else None

    @property
    def detail(self) -> str:
        return f"{self.provider}: {self.message}"
```

Routers catch it:
```python
try:
    products, total = await wc.get_products_page(...)
except IntegrationError as exc:
    raise HTTPException(status_code=502, detail=exc.detail)
```

---

## Logging

Every external request is logged with structured fields. No secrets are logged.

```
# Format:
# {client} {method} provider={P} endpoint={URL} status={N} duration_ms={N} success={bool}
# {client} retry provider={P} endpoint={URL} status={N} attempt={N}/{MAX} wait_s={N}
# {client} error provider={P} endpoint={URL} error={msg} duration_ms={N}
```

Example log output:
```
INFO  app.beta.integrations.woocommerce  wc request provider=WooCommerce endpoint=.../products status=200 duration_ms=234 success=true
INFO  app.beta.integrations.woocommerce  wc get_products_page provider=WooCommerce total=148 returned=20
WARN  app.beta.integrations.woocommerce  wc retry provider=WooCommerce endpoint=.../products status=429 attempt=1/4 wait_s=2 retry_after=none
INFO  app.beta.integrations.nextcloud    nc download_file provider=Nextcloud path=/prices.xlsx status=200 bytes=45312 duration_ms=1841 success=true
INFO  app.beta.integrations.spreadsheet  spreadsheet parse_price_list sheets=3 names=['Jan', 'Feb', 'Mar']
INFO  app.beta.integrations.spreadsheet  spreadsheet parse_price_list total_unique=132 duplicates=4
```

---

## Timeout Policy

### WooCommerce

| Operation | Connect | Read | Notes |
|---|---|---|---|
| `test_connection` | 10 s | 15 s | Quick probe |
| `count_products` | 10 s | 15 s | 1-row request |
| `get_products_page` | 10 s | 45 s | Per page |
| `get_categories` | 10 s | 45 s | Paginated |
| `get_all_products_for_preview` | 10 s | 120 s | All pages, 100/page |

### Nextcloud

| Operation | Connect | Read | Notes |
|---|---|---|---|
| `test_connection` | 10 s | 15 s | PROPFIND on root |
| `get_file_meta` | 10 s | 15 s | HEAD then PROPFIND |
| `download_file` | 10 s | 60 s | Large file allowed |

---

## Retry Policy (WooCommerce)

Adapted from production-proven WooPrice retry logic.

| Parameter | Value |
|---|---|
| Retry statuses | 429, 500, 502, 503, 504 |
| Max retries | 3 |
| Per-retry sleep cap | 30 s |
| Total sleep budget | 90 s |
| Back-off | Exponential (2^n), capped at 30 s |
| Retry-After header | Honoured when present |
| Budget exhaustion | Raises `IntegrationError` |

Nextcloud does not have a retry policy — a single failed read is reported as `IntegrationError` immediately (preview will surface this to the user).

---

## Flow: Product Browser

```
GET /api/v2/products?page=1&pageSize=20&search=...&categoryId=...&productType=...
  → RequireAuth (JWT)
  → WooCommerceClient.from_config(cfg)
      if None → return {items: [], configured: false}
  → wc.get_products_page(page, per_page, search, category_id, product_type)
      → GET /wp-json/wc/v3/products with retry
      → _parse_wc_product() for each item (skip non-published)
      → returns (list[dict], total: int from X-WP-Total header)
  → fill currency from AppConfigService
  → return {items, total, page, pageSize, configured: true}

IntegrationError → HTTP 502
```

```
GET /api/v2/products/categories
  → RequireAuth (JWT)
  → WooCommerceClient.from_config(cfg) — 503 if not configured
  → wc.get_categories() — all pages 100/page
  → return {items: [{id, name, parent, count}], total}

IntegrationError → HTTP 502
```

---

## Flow: Workspace Preview

```
POST /api/v2/workspace/preview
  → RequireAuth (JWT)
  → AppConfigService checks wc configured → 503 if not
  → AppConfigService checks nc configured + path → 503 if not
  → audit: preview_started
  → asyncio.create_task for parallel fetch:
      ├── wc.get_all_products_for_preview() → all pages 100/page
      └── nc.download_file(nc_path) → (bytes, meta)
  → await both tasks
  → load_workbook_bytes(xlsx_bytes) → openpyxl.Workbook (read_only=True)
  → parse_price_list(wb) → (entries: dict[id→row], duplicates: list)
  → _compute_preview(wc_products, entries, currency)
      for each WC product:
        match by wcId in entries
        skip if sheet_price is None (OOS)
        skip if |wc_price - sheet_price| < 0.001
        compute difference, changePct
  → audit: preview_completed (N changes) or preview_failed
  → return {id, state: "preview_ready", totalChanges, changes, duplicateWarnings, startedAt}

IntegrationError → audit: preview_failed → HTTP 502
```

---

## Flow: Diagnostics

```
GET /api/v2/diagnostics/status
  → RequireAuth (JWT)
  → DB: SELECT 1 → {status: "ok"|"error"}
  → WooCommerceClient.from_config():
      if None → {status: "unconfigured", detail: "...not set"}
      else → wc.test_connection() → (ok, msg, latency_ms)
            wc.count_products() → int
            → {status: "ok"|"error", latencyMs, productCount, detail}
  → NextcloudClient.from_config():
      if None → {status: "unconfigured", detail: "...not set"}
      else → nc.test_connection() → (ok, msg, latency_ms)
            nc.get_file_meta(path) → {last_modified}
            → {status: "ok"|"error", latencyMs, lastModified, detail}
  → return {database, woocommerce, nextcloud, checkedAt}
```

---

## Flow: Settings

```
GET /api/v2/settings
  → RequireAuth (JWT)
  → AppConfigService.get(key) for each setting
  → NEVER return: woocommerce.key, woocommerce.secret, nextcloud.password
  → return {woocommerceUrl, nextcloudUrl, syncIntervalMinutes,
            timezone, currency, environment, wcConfigured, ncConfigured}

POST /api/v2/settings/woocommerce (Replace Credentials)
  → RequireAuth (JWT)
  → Validate URL (must start http/https)
  → _test_woocommerce_connection(url, key, secret)
      if not ok → return {ok: false, message} WITHOUT saving
  → AppConfigService.set_many({url, key, secret})
  → audit: woocommerce_connected
  → return {ok: true, message: "Connected successfully"}

POST /api/v2/settings/nextcloud (Replace Credentials)
  → same pattern: test first, save only if ok
  → audit: nextcloud_connected
```

---

## Spreadsheet Parsing

Adapted from production-proven WooPrice `parse_price_list()` with one key difference: BU5 uses `float` prices for in-memory comparison (vs. WooPrice's `str` prices for DB storage).

### Rules (identical to WooPrice):

| Rule | Behaviour |
|---|---|
| All sheets | Every worksheet is read, in order |
| Last-sheet-wins | Duplicate product IDs: later sheet overrides earlier |
| Headers | Rows 1–2 are skipped |
| Data rows | Row 3 to 1002 (max 1000 rows) |
| Stop condition | 30 consecutive empty rows in column B |
| Column A | Product name (display only) |
| Column B | Product ID — must be positive integer |
| Column C | Price — see price parsing rules |
| OOS markers | `0`, `-`, `ناموجود`, `out of stock`, etc. → `price=None`, no error |
| Persian digits | U+06F0–U+06F9 translated to ASCII |
| Arabic-Indic | U+0660–U+0669 translated to ASCII |
| Arabic thousands | U+066C removed |
| Negative price | `price=None`, `price_parse_error=True` |
| Non-numeric | `price=None`, `price_parse_error=True` |
| Row colour | Not available in `read_only=True` mode; always `None` |

---

## Read-Only Enforcement

### Write Guard

`app/beta/integrations/write_guard.py` exports two items:

```python
BETA_WRITE_BLOCKED = "Write operations are disabled in FlowHub Beta."

def raise_write_blocked() -> None:
    raise HTTPException(status_code=403, detail=BETA_WRITE_BLOCKED)
```

Any route that would write to WooCommerce or Nextcloud must call `raise_write_blocked()` immediately. The write guard is a permanent compile-time constraint, not a feature flag.

### What BU5 Does NOT Implement

| Capability | Status |
|---|---|
| Apply prices to WooCommerce | Permanently blocked (HTTP 403) |
| Write-back to spreadsheet | Permanently blocked (HTTP 403) |
| Scheduler / auto-sync | Not implemented |
| Price history persistence | Not implemented |
| Variation fetching | Not implemented (BU5 reads top-level products only) |

---

## Source Code Map

```
app/beta/integrations/
├── __init__.py              Package init
├── errors.py                IntegrationError
├── write_guard.py           BETA_WRITE_BLOCKED + raise_write_blocked()
├── woocommerce.py           WooCommerceClient
├── nextcloud.py             NextcloudClient
└── spreadsheet.py           parse_price_list(), load_workbook_bytes()

app/beta/api/v2/
├── products.py              GET /products, GET /products/categories
├── sources.py               GET /sources
├── workspace.py             POST /workspace/preview, GET /workspace/state
├── settings_routes.py       GET/POST /settings, /settings/woocommerce, /settings/nextcloud
├── activity.py              GET /activity
└── diagnostics.py           GET /diagnostics/status

tests/beta/integrations/
└── test_spreadsheet.py      17 tests for parser correctness

tests/beta/api/v2/
├── test_workspace.py        7 tests (auth, 503 paths, preview shape, write guard)
├── test_settings_routes.py  10 tests (secrets, flags, validation, credential replace)
└── test_activity.py         6 tests (auth, shape, ordering, pagination)
```
