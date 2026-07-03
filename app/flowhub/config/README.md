# FlowHub - Configuration Core

**Phase:** B3 Configuration Foundation
**Architecture:** Framework-independent. No FastAPI, Typer, or HTTP imports.

---

## Quick Start

```python
from pathlib import Path
from app.flowhub.config import ConfigurationManager

manager = ConfigurationManager(env_file=Path(".env"))
manager.load()
result = manager.validate()
if not result:
    print(result.format_errors())
    raise SystemExit(1)
config = manager.get()
print(config.domain)
print(config.jwt_secret.get_secret_value())  # SecretStr - use .get_secret_value()
```

---

## Environment Variables

### Required (22)

| Variable | Type | Validation |
|---|---|---|
| `FLOWHUB_ENV` | `dev` \| `FLOWHUB` \| `production` | Enum membership |
| `FLOWHUB_DOMAIN` | string | Non-empty |
| `FLOWHUB_PORT` | integer | 1024-65535 |
| `FLOWHUB_DATABASE_URL` | string | `postgresql://` prefix |
| `FLOWHUB_POSTGRES_DB` | string | Non-empty |
| `FLOWHUB_POSTGRES_USER` | string | Non-empty |
| `FLOWHUB_POSTGRES_PASSWORD` | **secret** | Non-empty |
| `FLOWHUB_JWT_SECRET` | **secret** | Min 64 chars |
| `FLOWHUB_REST_API_SECRET` | **secret** | Min 32 chars |
| `FLOWHUB_NEXTCLOUD_URL` | URL | `http(s)://` prefix |
| `FLOWHUB_NEXTCLOUD_FILE_PATH` | path | Non-empty |
| `FLOWHUB_NEXTCLOUD_USERNAME` | string | Non-empty |
| `FLOWHUB_NEXTCLOUD_PASSWORD` | **secret** | Non-empty |
| `FLOWHUB_WOOCOMMERCE_URL` | URL | `http(s)://` prefix |
| `FLOWHUB_WOOCOMMERCE_KEY` | **secret** | Non-empty |
| `FLOWHUB_WOOCOMMERCE_SECRET` | **secret** | Non-empty |
| `FLOWHUB_TIMEZONE` | IANA tz string | `zoneinfo.ZoneInfo()` |
| `FLOWHUB_CURRENCY` | ISO 4217 | 3 uppercase letters |
| `FLOWHUB_ADMIN_EMAIL` | email | Basic format check |
| `FLOWHUB_STORAGE_PATH` | path | Exists + writable |
| `FLOWHUB_BACKUP_PATH` | path | Exists + writable |
| `FLOWHUB_SSL_MODE` | enum | `off` \| `self-signed` \| `letsencrypt` \| `manual` |

### Optional (8, with defaults)

| Variable | Default | Description |
|---|---|---|
| `FLOWHUB_LOG_LEVEL` | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` \| `CRITICAL` |
| `FLOWHUB_JWT_ACCESS_TTL_MINUTES` | `15` | Access token lifetime |
| `FLOWHUB_JWT_REFRESH_TTL_DAYS` | `7` | Refresh token lifetime |
| `FLOWHUB_MAX_UPLOAD_MB` | `50` | Max upload size in MB |
| `FLOWHUB_PLUGIN_DIR` | `$FLOWHUB_STORAGE_PATH/plugins` | Plugin installation directory |
| `FLOWHUB_WORKER_CONCURRENCY` | `2` | Background worker concurrency |
| `FLOWHUB_SCHEDULER_POLL_SECONDS` | `30` | Scheduler polling interval |
| `FLOWHUB_BACKUP_RETAIN_DAYS` | `30` | Backup retention period |

---

## Secret Separation Model

Secrets live **only** in environment variables (`.env` file, mode 600).
They are **never** stored in:
- The managed TOML config file (`$FLOWHUB_STORAGE_PATH/config/flowhub.toml`)
- The database
- Log files
- API responses

The six secret variables are `FLOWHUB_JWT_SECRET`, `FLOWHUB_REST_API_SECRET`,
`FLOWHUB_POSTGRES_PASSWORD`, `FLOWHUB_NEXTCLOUD_PASSWORD`, `FLOWHUB_WOOCOMMERCE_KEY`,
`FLOWHUB_WOOCOMMERCE_SECRET`. They are declared in `SECRET_FIELDS`.

In `FlowHubConfig`, secrets are `pydantic.SecretStr`. They are redacted in `repr()`
and `str()`. To access the raw value: `config.jwt_secret.get_secret_value()`.

---

## Profile Behavior

| Profile | `FLOWHUB_ENV` value | CLI banner | Behavior |
|---|---|---|---|
| `ConfigProfile.PRODUCTION` | `"production"` | `[FLOWHUB]` | Normal FlowHub operation |
| `ConfigProfile.DEV` | `"dev"` | `[DEVELOPMENT ENVIRONMENT]` | Debug output; relaxed guards |
| `ConfigProfile.PRODUCTION` | `"production"` | `[PRODUCTION]` | All guards active; destructive CLI ops blocked |

---

## Validation

`ConfigValidator.validate(env)` never raises. It returns a `ValidationResult`:

```python
result = manager.validate()
if not result.is_valid:
    print(result.format_errors())  # structured field-level errors
if result.warnings:
    print(result.format_warnings())
```

Errors list all problems at once - no fail-fast. Callers decide whether to abort.

Path existence and writability checks (`FLOWHUB_STORAGE_PATH`, `FLOWHUB_BACKUP_PATH`)
can be disabled with `ConfigValidator(check_paths=False)` for unit tests.

---

## Managed TOML Config File

The installer writes `$FLOWHUB_STORAGE_PATH/config/flowhub.toml`.

The config file may contain `${VAR}` template_variables referencing env vars.
These are expanded at read time by `expand_template_variables()`. Expanded values
are never written back to disk.

```toml
[meta]
version = "FLOWHUB-1.0.0"

[app]
env = "${FLOWHUB_ENV}"
domain = "${FLOWHUB_DOMAIN}"
port = 8080
```

To check for drift between live env and config file:

```python
drifts = manager.verify()
for drift in drifts:
    print(drift)
```

---

## Emergency Manual Editing

Manual edits to `.env` or the TOML config are emergency-only. After any manual
edit, run:

```python
manager.load()
drifts = manager.verify()
```

(or: `flowhub configure --verify` once CLI is implemented in B5)

---

## Config Migration

When upgrading FlowHub between versions, `manager.migrate()` applies any
necessary schema changes to the TOML config dict:

```python
changes = manager.migrate()
for change in changes:
    print(f"Migrated: {change}")
```

File write after migration is implemented in B4 (Installer Foundation).
