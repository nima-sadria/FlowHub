# FlowHub Beta — Morning Handoff

**Prepared:** 2026-06-29 (overnight remediation session)
**Environment:** Beta · host `/opt/FlowHub` · port `8085`

---

## Current commit

- **HEAD:** `fcb48a0` — `fix(beta): wire real admin creation, FlowHub rebrand, README`
- Branch `main`, in sync with `origin/main` (pushed).

## Server status (verified at handoff)

| Item | State |
|------|-------|
| `flowhub-app-1` | Up, **healthy**, `0.0.0.0:8085->8085` (image `flowhub-beta:latest`) |
| `flowhub-postgres-1` | Up, **healthy** (`postgres:16-alpine`) |
| Volume | `flowhub_beta_pgdata` (freshly initialised for role/db `nima`/`flowhub`) |
| Migrations | `alembic_version = beta_003` (head) |
| Admin user | `admin` (role `admin`, active) |
| `/api/health` | 200 `{"status":"ok","env":"beta",...}` |
| Login flow | 200 (login + me); wrong password returns 401 |

## Login credentials — location & reset

- The initial **`admin`** password was generated during remediation and handed to
  the operator in the session chat. It is **not stored in this repository** and
  was **not written to disk** (the admin was created directly via the CLI, so
  `logs/admin-credentials.txt` was not produced).
- If the password is lost, **reset it** by deleting and recreating the user:

  ```bash
  # Remove the existing admin row
  docker exec flowhub-postgres-1 psql -U nima -d flowhub \
    -c "DELETE FROM beta_users WHERE username='admin';"

  # Recreate (interactive prompts for username + password)
  docker compose -f docker-compose.beta.yml --env-file .env.beta \
    exec app python -m cli.main create-admin
  ```

  > When the installer's `step_create_admin` runs a fresh install, it auto-generates
  > the password, prints it once, and saves it to `logs/admin-credentials.txt` (mode 600).

## Exact verification commands

```bash
# 1. Containers
docker ps

# 2. Health
curl -s http://localhost:8085/api/health
# -> {"status":"ok","env":"beta","version":"..."}

# 3. Login (returns access + refresh tokens)
curl -s -X POST http://localhost:8085/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<password>"}'

# 4. Current user (paste the token from step 3)
curl -s http://localhost:8085/api/auth/me \
  -H "Authorization: Bearer <access-token>"

# Browser: open http://<host>:8085/login and sign in.
```

## Known issues (deferred — not addressed tonight, by request)

- **Shallow health check:** `/api/health` reports `ok` even if Postgres is down,
  so `(healthy)` can mislead. Login surfaces a raw 500 (not a graceful error)
  if the DB ever becomes unreachable.
- **No migrate-on-startup:** migrations run only via the installer or manually.
- **Docs not rebranded:** ~40 design docs under `docs/` still say "WooPrice"
  (intentionally left; needs a reviewed pass). README is fully FlowHub.
- **Internal identifiers unchanged:** `pyproject` name `wooprice-beta`, Typer app
  `name="wooprice"`, `scripts/wooprice` wrapper filename.
- **`.env.beta` oddities (pre-existing, untouched):** `BETA_TIMEZONE` looks like a
  config-store token; typos in `BETA_NEXTCLOUD_URL` and `BETA_ADMIN_EMAIL`.
- The installer's new `step_create_admin` path was syntax-checked (`bash -n`) but
  not exercised through a full clean `install.sh` run.

## Next recommended task

**Harden `/api/health` to verify the database** (cheap `SELECT 1`) and add a
graceful 503/handled error on DB failure, so container health and the login
endpoint reflect real DB state instead of returning a raw 500. This is the
highest-value follow-up because it turns the next DB-credential/connectivity
problem into an obvious signal rather than a silent "healthy" + 500.

> Reminder: do NOT change health behavior, migrations, docs rebrand, or internal
> identifiers without explicit sign-off — those were deferred deliberately.
