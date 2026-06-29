# FlowHub

FlowHub is a self-hosted pricing/operations hub built on the A2 Platform Core.
It ships as a Docker stack: a FastAPI backend (with a bundled React SPA) and a
PostgreSQL database. This document covers the **Beta** environment, which runs
from `/opt/flowhub` on port `8085`.

> **Status:** Beta. The backend serves the API under `/api/*` and the built SPA
> for all other routes.

---

## Architecture

| Component   | Detail                                                            |
|-------------|-------------------------------------------------------------------|
| Backend     | FastAPI (`app.beta.app:app`), Uvicorn, port `8085` in-container   |
| Frontend    | React + Vite SPA, built and baked into the image at build time    |
| Database    | PostgreSQL 16 (`postgres:16-alpine`), named volume `beta_pgdata`   |
| Auth        | JWT access/refresh tokens, Argon2 password hashing                |
| Migrations  | Alembic (`alembic_beta.ini`, revisions under `alembic_beta/`)     |
| Reverse proxy | External (Nginx Proxy Manager) — not managed by this stack      |

Key files:

- `docker-compose.beta.yml` — the Beta stack (app + postgres)
- `.env.beta` — environment + secrets (mode `600`, never committed)
- `.env.beta.example` — template; copy to `.env.beta` and fill in real values
- `Dockerfile.beta` — multi-stage build (Vite frontend → Python app)
- `installer/install.sh` — guided installer
- `cli/main.py` — management CLI (`python -m cli.main ...`)

---

## Requirements

- Docker Engine with the Compose v2 plugin (`docker compose`)
- A user in the `docker` group (or root)
- Ports: host `8085` free (configurable via `BETA_PORT`)

---

## Install

### Option A — Guided installer

```bash
cd /opt/flowhub
sudo ./installer/install.sh
```

The installer runs the wizard, generates `.env.beta`, builds and starts the
stack, runs migrations, and creates the initial admin account (printing the
generated password once).

### Option B — Manual

```bash
cd /opt/flowhub

# 1. Configure environment
cp .env.beta.example .env.beta
nano .env.beta            # set DB user/password, JWT secret, integrations

# 2. Validate the compose config
docker compose -f docker-compose.beta.yml --env-file .env.beta config

# 3. Build and start
docker compose -f docker-compose.beta.yml --env-file .env.beta up -d --build

# 4. Run database migrations
docker compose -f docker-compose.beta.yml --env-file .env.beta \
  exec app alembic -c alembic_beta.ini upgrade head

# 5. Create the initial admin user (prompts for username + password)
docker compose -f docker-compose.beta.yml --env-file .env.beta \
  exec app python -m cli.main create-admin
```

> **Important — database credentials.** PostgreSQL only initialises the role and
> database named in `.env.beta` (`BETA_POSTGRES_USER` / `BETA_POSTGRES_DB`) on
> the **first** start with an empty data volume. If you change those values
> after the volume exists, Postgres keeps the old role and the app fails to
> authenticate. To re-initialise from scratch (destroys all data):
>
> ```bash
> docker compose -f docker-compose.beta.yml --env-file .env.beta down
> docker volume rm flowhub_beta_pgdata
> docker compose -f docker-compose.beta.yml --env-file .env.beta up -d
> ```

---

## Network and Domain

### Public URL vs Internal Docker Port

FlowHub binds internally on the port configured as `BETA_PORT` (default `8085`).
This is the port Docker uses — it is the upstream target for Nginx Proxy Manager
and is never exposed as part of the public-facing URL when a reverse proxy handles TLS.

| SSL mode | Public URL | Internal Docker Port |
|---|---|---|
| `off` | `http://domain:8085` | `8085` |
| `self-signed` | `https://domain:8085` | `8085` |
| `manual` | `https://domain` | `8085` |
| `letsencrypt` | `https://domain` | `8085` |

In `manual` and `letsencrypt` modes the port is omitted from the public URL because
an external reverse proxy (e.g., Nginx Proxy Manager) listens on port 443 and
forwards traffic to `localhost:8085` on the same host.

### Reverse Proxy Mode (`manual`)

Select SSL mode `manual` when you already have Nginx Proxy Manager (or similar)
running and want it to handle TLS termination. The installer will:
- Set `BETA_SSL_MODE=manual` in `.env.beta`
- Not configure any certificate itself
- Print the public URL without a port (`https://your-domain.com`)

Configure your proxy host to forward HTTPS → `http://localhost:8085` (or the
container's internal address if running in the same Docker network).

### Manual SSL Mode vs Let's Encrypt

Both `manual` and `letsencrypt` produce `https://domain` public URLs.
The difference is who manages the certificate:
- `letsencrypt` — the installer provisions a certificate via Certbot automatically.
  Requires DNS pointing to this server and port 80 open.
- `manual` — you supply an existing certificate. The installer copies it into
  `BETA_STORAGE_PATH/ssl/` and configures Nginx to use it.

### Hostname Input Rules

The wizard normalizes the domain you enter before saving it:

1. Leading and trailing whitespace is stripped.
2. If you paste a full URL (`https://beta.example.com`) the protocol is removed
   automatically and the message *"Protocol removed automatically. Please enter the
   hostname only."* is displayed.
3. Any path (`/some/path`) and port (`:8085`) suffix are stripped.
4. A trailing dot is removed.
5. Non-hostname bytes (invisible Unicode characters, RTL marks, zero-width joiners)
   are stripped.
6. The hostname is converted to lowercase.

Valid input examples:
- `beta.example.com`
- `https://beta.example.com/` → normalized to `beta.example.com`
- `BETA.EXAMPLE.COM` → normalized to `beta.example.com`

The normalized hostname must match RFC 1123: letters, digits, hyphens, and dots;
each label must start and end with a letter or digit.

---

## Uninstall

Re-run the installer and select **4. Uninstall** from the management menu:

```bash
sudo bash /opt/flowhub/installer/install.sh
# → Select 4. Uninstall
```

Or invoke directly with the `--uninstall` flag (works even without an active installation):

```bash
sudo bash installer/install.sh --uninstall
```

The interactive uninstaller lets you choose exactly what to remove:

| Resource | Default |
|---|---|
| Docker containers | Yes |
| Docker images | Yes |
| Docker volumes (database) | Yes |
| Docker network | Yes |
| Project directory (`/opt/flowhub`) | Yes |
| CLI (`/usr/local/bin/flowhub`) | Yes |
| Systemd services (if any) | Yes |
| Generated configuration (`.env.beta`) | Yes |
| Logs | Yes |
| Backups | **No** (off by default) |

You must type `UNINSTALL` to confirm before anything is removed.

The uninstaller removes only resources belonging to the `flowhub` Docker Compose
project. WooPrice and all other Docker projects are not affected. All removal steps
are idempotent — safe to run even if FlowHub is partially or fully absent.

After uninstall, a clean reinstall can be run immediately:

```bash
sudo bash installer/install.sh
```

---

## Verify

```bash
# Health
curl -s http://localhost:8085/api/health
# -> {"status":"ok","env":"beta","version":"..."}

# Login (returns access + refresh tokens)
curl -s -X POST http://localhost:8085/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<your-password>"}'

# Current user (use the token from login)
curl -s http://localhost:8085/api/auth/me \
  -H "Authorization: Bearer <access-token>"
```

In a browser, open `http://<host>:8085/login` and sign in with the admin
credentials.

---

## Authentication endpoints

| Method | Path                | Auth        | Purpose                          |
|--------|---------------------|-------------|----------------------------------|
| GET    | `/api/health`       | public      | Health probe                     |
| POST   | `/api/auth/login`   | public      | Issue access + refresh tokens    |
| POST   | `/api/auth/refresh` | public      | Rotate refresh token             |
| POST   | `/api/auth/logout`  | bearer      | Revoke refresh token             |
| GET    | `/api/auth/me`      | bearer      | Current user profile             |

All non-API routes serve the React SPA (`/login`, dashboard, etc.).

---

## Management CLI

```bash
# Inside the app container
docker compose -f docker-compose.beta.yml --env-file .env.beta exec app \
  python -m cli.main --help

# Common commands
python -m cli.main create-admin      # create the initial admin user
python -m cli.main status            # environment / config status
python -m cli.main health            # local health checks
python -m cli.main migrate           # database migration management
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

# Stop (keeps data volume)
docker compose -f docker-compose.beta.yml --env-file .env.beta down
```

Bind mounts (host → container): `./storage → /data/storage`,
`./backups → /data/backups`, `./logs → /data/logs`.

---

## Documentation

Design and architecture documents live under [`docs/`](docs/) — see
`docs/beta/` for Beta architecture, installer, security, and deployment notes.
