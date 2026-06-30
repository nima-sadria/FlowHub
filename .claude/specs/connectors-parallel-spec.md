# Connector Framework — Conflict-Safe Parallel Implementation Spec

**Status:** Planning — awaiting CHAT2 phase specification before code implementation  
**Owner Proposal:** Source Connector Framework + Parallel Implementation Planning  
**Date drafted:** 2026-06-30

---

## Background

FlowHub must never call external source or destination APIs directly from business logic. All external communication must pass through dedicated Connector classes. This spec defines the boundary between Developer A (Source Connectors) and Developer B (Destination Connectors) so both can work in parallel without merge conflicts.

The existing `app/a2/sources/` layer (Source Adapter Framework, A2.1 — Codex PASS) remains untouched. The new `app/connectors/` layer sits *below* the adapter layer: adapters call connectors; connectors call external APIs.

---

## 1. Shared Connector Contract

This contract must be committed and merged before either developer branches.

### Connector ID

```python
ConnectorID = str  # e.g. "nextcloud", "google-sheets", "woocommerce"
```

### ConnectorType

```python
from enum import Enum

class ConnectorType(Enum):
    SOURCE = "source"
    DESTINATION = "destination"
```

### ConnectorCapabilities

```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class ConnectorCapabilities:
    can_list_folders: bool = False
    can_list_files: bool = False
    can_list_worksheets: bool = False
    can_read_worksheet: bool = False
    can_get_metadata: bool = False
    can_watch_changes: bool = False
    can_list_products: bool = False      # destination
    can_read_inventory: bool = False     # destination
    extra: dict[str, bool] = field(default_factory=dict)
```

### HealthResult

```python
from dataclasses import dataclass
from enum import Enum

class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

@dataclass
class HealthResult:
    status: HealthStatus
    latency_ms: float | None = None
    detail: str | None = None
```

### AuthConfig

```python
from dataclasses import dataclass
from typing import Any

@dataclass
class AuthConfig:
    auth_type: str          # "basic", "api_key", "oauth2", "none"
    credentials: dict[str, Any] = field(default_factory=dict)
    # credentials keys are auth_type-specific:
    # basic:   {"username": str, "password": str}
    # api_key: {"key": str, "secret": str}
    # oauth2:  {"access_token": str, "refresh_token": str, "expires_at": float}
```

### Error Model

```python
from dataclasses import dataclass
from enum import Enum

class ConnectorErrorCode(Enum):
    AUTH_FAILED = "auth_failed"
    NOT_FOUND = "not_found"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    NETWORK = "network"
    PERMISSION = "permission"
    PROVIDER_ERROR = "provider_error"
    UNKNOWN = "unknown"

@dataclass
class ConnectorError(Exception):
    code: ConnectorErrorCode
    message: str
    provider: str           # e.g. "nextcloud", "woocommerce"
    retryable: bool = False
    http_status: int | None = None
    raw: str | None = None
```

### Retry Model

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class RetryConfig:
    max_attempts: int = 3
    base_delay_s: float = 1.0
    max_delay_s: float = 30.0
    backoff_factor: float = 2.0
    retryable_codes: frozenset[ConnectorErrorCode] = frozenset({
        ConnectorErrorCode.RATE_LIMITED,
        ConnectorErrorCode.TIMEOUT,
        ConnectorErrorCode.NETWORK,
    })
```

### Rate Limit Model

```python
from dataclasses import dataclass

@dataclass
class RateLimitConfig:
    requests_per_minute: int | None = None
    burst: int | None = None
    respect_retry_after: bool = True
```

### Connection Test Result

```python
from dataclasses import dataclass

@dataclass
class ConnectionTestResult:
    ok: bool
    message: str
    latency_ms: float | None = None
    detail: dict | None = None
```

### Abstract Base: SourceConnector

```python
from abc import ABC, abstractmethod

class SourceConnector(ABC):
    connector_id: ConnectorID
    connector_type = ConnectorType.SOURCE

    @abstractmethod
    def capabilities(self) -> ConnectorCapabilities: ...

    @abstractmethod
    async def connect(self, auth: AuthConfig) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def health(self) -> HealthResult: ...

    @abstractmethod
    async def test_connection(self, auth: AuthConfig) -> ConnectionTestResult: ...

    # Optional — raise NotImplementedError if capability is False
    async def list_folders(self, path: str = "/") -> list[str]:
        raise NotImplementedError

    async def list_files(self, path: str) -> list[str]:
        raise NotImplementedError

    async def list_worksheets(self, file_path: str) -> list[str]:
        raise NotImplementedError

    async def read_worksheet(self, file_path: str, worksheet: str) -> list[dict]:
        raise NotImplementedError

    async def get_metadata(self, path: str) -> dict:
        raise NotImplementedError

    async def watch_changes(self, path: str):
        raise NotImplementedError
```

### Abstract Base: DestinationConnector

```python
from abc import ABC, abstractmethod

class DestinationConnector(ABC):
    connector_id: ConnectorID
    connector_type = ConnectorType.DESTINATION

    @abstractmethod
    def capabilities(self) -> ConnectorCapabilities: ...

    @abstractmethod
    async def connect(self, auth: AuthConfig) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def health(self) -> HealthResult: ...

    @abstractmethod
    async def test_connection(self, auth: AuthConfig) -> ConnectionTestResult: ...

    # Optional — raise NotImplementedError if capability is False
    async def list_products(self, page: int = 1, per_page: int = 100) -> list[dict]:
        raise NotImplementedError

    async def read_inventory(self, product_id: int) -> dict:
        raise NotImplementedError
```

**Contract is frozen after `connectors/common-contract` merges to main. Any change requires Owner approval and both developers must rebase.**

---

## 2. Source Connector Scope — Developer A

**May modify:**
- `app/connectors/common/` (first commit only — then frozen)
- `app/connectors/sources/`
- `app/connectors/sources/nextcloud/`
- `tests/connectors/common/`
- `tests/connectors/sources/`
- `docs/connectors/`

**Must NOT modify:**
- `app/connectors/destinations/`
- `app/connectors/destinations/woocommerce/`
- `app/a2/` (existing Source Adapter Framework — read only for reference)
- `app/beta/` (existing beta API — read only for reference)
- `tests/connectors/destinations/`
- Any UI file
- Any rule engine, safety engine, pricing engine, or execution engine file

---

## 3. Destination Connector Scope — Developer B

**May modify:**
- `app/connectors/destinations/`
- `app/connectors/destinations/woocommerce/`
- `tests/connectors/destinations/`
- `docs/connectors/` (destination section only)

**Must NOT modify:**
- `app/connectors/common/` (frozen after contract merge)
- `app/connectors/sources/`
- `app/connectors/sources/nextcloud/`
- `app/a2/` (existing Source Adapter Framework)
- `tests/connectors/common/`
- `tests/connectors/sources/`
- Any UI file
- Any rule engine, safety engine, pricing engine, or execution engine file

---

## 4. File Ownership Plan

```
app/connectors/
  common/                         ← Developer A (first commit); frozen after merge
    __init__.py
    types.py                      # ConnectorID, ConnectorType, ConnectorCapabilities
    health.py                     # HealthStatus, HealthResult
    errors.py                     # ConnectorErrorCode, ConnectorError
    retry.py                      # RetryConfig
    rate_limit.py                 # RateLimitConfig
    test_result.py                # ConnectionTestResult
    auth.py                       # AuthConfig
    base.py                       # SourceConnector ABC, DestinationConnector ABC

  sources/                        ← Developer A owns
    __init__.py
    nextcloud/
      __init__.py
      connector.py                # NextcloudConnector(SourceConnector)
      auth.py                     # NextcloudAuth helpers
      webdav.py                   # WebDAV calls (isolated here only)
      ocs.py                      # OCS API calls (isolated here only)

  destinations/                   ← Developer B owns
    __init__.py
    woocommerce/
      __init__.py
      connector.py                # WooCommerceConnector(DestinationConnector)
      auth.py                     # WooCommerce auth helpers
      rest_client.py              # WC REST API calls (isolated here only)

tests/connectors/
  common/                         ← Developer A writes alongside common/
    __init__.py
    test_types.py
    test_health.py
    test_errors.py
    test_retry.py
    test_auth.py

  sources/                        ← Developer A writes
    __init__.py
    test_nextcloud_connector.py
    test_nextcloud_webdav.py

  destinations/                   ← Developer B writes
    __init__.py
    test_woocommerce_connector.py
    test_woocommerce_rest.py

docs/connectors/
  README.md
  common-contract.md
  source-connectors.md
  destination-connectors.md
```

---

## 5. No-Conflict Rule

- `app/connectors/common/` is written once in `connectors/common-contract` and merged before any other branch starts coding.
- After that merge, no file under `common/` may be changed without Owner approval.
- If a contract change is approved: both developers must rebase their branches against the new main before continuing.
- Any PR that touches `common/` outside of the initial contract commit is automatically blocked (enforced by PR review).

---

## 6. Branch Strategy

Three branches, all created from `main`:

| Branch | Purpose | Who |
|---|---|---|
| `connectors/common-contract` | Shared contract only — types, ABCs, no concrete connectors | Developer A |
| `connectors/source-nextcloud` | Nextcloud SourceConnector implementation | Developer A |
| `connectors/destination-woocommerce` | WooCommerce DestinationConnector implementation | Developer B |

**Merge order:**

```
Step 1:  connectors/common-contract          →  main
Step 2:  Developer A branches connectors/source-nextcloud from updated main
Step 3:  Developer B branches connectors/destination-woocommerce from updated main
Step 4:  Both work independently
Step 5:  connectors/source-nextcloud         →  main  (after acceptance criteria pass)
Step 6:  connectors/destination-woocommerce  →  main  (after acceptance criteria pass)
Step 7:  Integration audit (see §10)
```

Developer B should pull and rebase after Step 5 if B is not yet complete.

---

## 7. Implementation Constraints

**Do NOT implement in this framework:**

| Prohibited | Reason |
|---|---|
| Any pricing logic | Pricing engine is a separate protected system |
| Inventory write path | FlowHub remains READ-ONLY in Beta |
| Apply / Dry Run | Protected system — requires Owner approval |
| Safety Engine hooks | Separate phase |
| WooCommerce write (PUT/POST products) | Explicitly prohibited — read path only |
| Channel pricing profile execution | Separate phase |
| UI changes | Not in scope for connector framework |
| Rule engine integration | Connectors are standalone; rule engine wires them separately |

**Permitted:**
- Connection test (GET / PROPFIND only)
- List folders / files / worksheets / products
- Read worksheet data / product data / inventory data
- Health check
- Authentication helpers (credential storage abstraction only — no UI)

---

## 8. Acceptance Criteria

### Common Contract

- [ ] All types defined in `app/connectors/common/`
- [ ] `SourceConnector` ABC importable as `from app.connectors.common.base import SourceConnector`
- [ ] `DestinationConnector` ABC importable as `from app.connectors.common.base import DestinationConnector`
- [ ] `ConnectorCapabilities`, `HealthResult`, `ConnectorError`, `RetryConfig`, `RateLimitConfig`, `ConnectionTestResult`, `AuthConfig` all importable from `app.connectors.common`
- [ ] `tests/connectors/common/` passes `pytest`
- [ ] No concrete connector code in `common/`

### Source Connector — Nextcloud

- [ ] `NextcloudConnector` is a concrete subclass of `SourceConnector`
- [ ] `test_connection()` sends a WebDAV PROPFIND or OCS request and returns `ConnectionTestResult`
- [ ] `list_folders(path)` returns a list of folder paths
- [ ] `list_files(path)` returns a list of file paths
- [ ] `read_worksheet(file_path, worksheet)` returns row data (via WebDAV GET + parsing)
- [ ] All WebDAV and OCS calls are inside `app/connectors/sources/nextcloud/` — zero direct calls from any other module
- [ ] `tests/connectors/sources/` passes `pytest`
- [ ] `capabilities()` returns accurate `ConnectorCapabilities`

### Destination Connector — WooCommerce

- [ ] `WooCommerceConnector` is a concrete subclass of `DestinationConnector`
- [ ] `test_connection()` performs a GET to `wp-json/wc/v3/products?per_page=1` and returns `ConnectionTestResult`
- [ ] `list_products(page, per_page)` returns product list (read only)
- [ ] `read_inventory(product_id)` returns stock data (read only)
- [ ] All WooCommerce REST calls are inside `app/connectors/destinations/woocommerce/` — zero direct calls from any other module
- [ ] `tests/connectors/destinations/` passes `pytest`
- [ ] `capabilities()` returns accurate `ConnectorCapabilities`

---

## 9. Required Final Reports

Each developer must produce a report on their branch before requesting merge:

| Field | |
|---|---|
| Branch name | |
| Files added | List every new file |
| Files modified | List every changed existing file |
| Tests added | Names of new test files and total test count |
| Tests run | `pytest` output summary (pass / fail / skip) |
| External APIs touched | Exact endpoints, HTTP methods, auth scheme |
| Capabilities implemented | Which `ConnectorCapabilities` fields are `True` |
| Capabilities not implemented | Which remain `False` and why |
| Limitations | Known gaps, edge cases not handled |
| Remaining risks | What could break in production or future integration |

---

## 10. Integration Rule

After both branches merge, a mandatory integration audit runs before either connector is wired into any FlowHub business logic.

**Audit checklist:**

- [ ] **File ownership**: no file under `sources/` was modified by Developer B; no file under `destinations/` was modified by Developer A
- [ ] **Common contract integrity**: `git diff main..connectors/source-nextcloud -- app/connectors/common/` is empty (same for destination branch)
- [ ] **Isolation — Nextcloud**: `grep -r "webdav\|PROPFIND\|remote\.php\|OCS" app/ --include="*.py" -l` returns only files inside `app/connectors/sources/nextcloud/`
- [ ] **Isolation — WooCommerce**: `grep -r "wp-json/wc\|woocommerce" app/ --include="*.py" -l` returns only files inside `app/connectors/destinations/woocommerce/` and `app/beta/` (setup wizard only — existing, permitted)
- [ ] **All tests pass**: `pytest tests/connectors/` green
- [ ] **No write paths**: grep for `PUT\|POST\|PATCH\|DELETE` in connector files — only `test_connection()` calls are permitted (read tests)
- [ ] **No pricing logic**: no imports from `app/a2/engines/` or `app/a2/rules/` inside connectors

**Audit must be performed by CHAT2 (Step 6) before Owner phase exit approval (Step 7).**

---

## Architecture Diagram

```
FlowHub Business Logic (Rule Engine, Pricing Engine)
           ↓
   app/a2/sources/              ← Source Adapter Framework (A2.1 — existing, do not modify)
           ↓
   app/connectors/sources/      ← NEW: Source Connector Layer (this spec)
           ↓
   External Source
   (Nextcloud WebDAV / OCS API / Google Sheets / CSV / ERP / ...)


FlowHub Business Logic
           ↓
   app/connectors/destinations/ ← NEW: Destination Connector Layer (this spec)
           ↓
   External Destination
   (WooCommerce REST API / ...)
```

The A2 Source Adapter calls the Source Connector's public interface. The A2 Adapter never calls WebDAV or OCS directly.

---

## Next Steps

1. CHAT2 reviews this spec → returns APPROVE / REVISE / HOLD
2. Owner approves phase start
3. Developer A implements `connectors/common-contract` branch (contract files only)
4. PR: `connectors/common-contract` → `main`
5. Developer A creates `connectors/source-nextcloud` from updated main
6. Developer B creates `connectors/destination-woocommerce` from updated main
7. Parallel implementation within file ownership boundaries above
8. Each developer produces Final Report (§9)
9. Integration audit (§10) by CHAT2
10. Owner phase exit approval
