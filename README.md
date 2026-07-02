# FlowHub

[![Build](https://img.shields.io/badge/build-ready_for_release-16a34a)](https://github.com/nima-sadria/FlowHub)
[![Docker](https://img.shields.io/badge/docker-compose-2496ed)](docker-compose.beta.yml)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Latest Release](https://img.shields.io/badge/release-first_public_release-7c3aed)](RELEASE_NOTES.md)

FlowHub is a self-hosted multi-channel commerce operations platform. It centralizes product, source, workspace, diagnostics, integration, and logging views behind a read-only first-release safety model.

The first release is designed for safe deployment: connectors can read and diagnose external systems, but write execution remains disabled until explicitly approved in a future release.

## Architecture

```mermaid
flowchart LR
    UI[FlowHub Web UI] --> API[FastAPI Backend]
    CLI[flowhub CLI] --> API
    API --> DL[Canonical Data Layer]
    API --> IP[Integration Platform]
    API --> LOG[Unified Logging Platform]
    IP --> WC[WooCommerce Connector]
    IP --> NC[Nextcloud Connector]
    DL --> DB[(PostgreSQL)]
    LOG --> DB
```

```mermaid
flowchart TD
    Setup[Setup Wizard] --> Login[Login]
    Login --> Dashboard[Dashboard]
    Dashboard --> Products[Products]
    Dashboard --> Sources[Sources]
    Dashboard --> Workspace[Workspace]
    Dashboard --> Integrations[Settings -> Integrations]
    Dashboard --> Diagnostics[Diagnostics]
    Dashboard --> Logging[Logging]
```

## Features

- Clean first-run setup: Welcome, Server Profile, Database, Admin Account, Finish.
- Connector configuration in one place: Settings -> Integrations.
- Canonical Data Layer for products, sources, workspace state, and snapshots.
- Integration Platform with connector registry, settings, health, diagnostics, telemetry, and webhook contracts.
- Unified Logging Platform with structured logs, search, correlation IDs, redaction, retention, and export contracts.
- Read-only first-release safety: no Apply, no scheduler execution, no automatic pricing, no WooCommerce writes, no spreadsheet writes.
- Professional installer and `flowhub` server management command.

## Quick Start

Install with curl:

```bash
curl -fsSL https://raw.githubusercontent.com/nima-sadria/FlowHub/main/installer/install.sh | sudo bash
```

Install with wget:

```bash
wget -qO- https://raw.githubusercontent.com/nima-sadria/FlowHub/main/installer/install.sh | sudo bash
```

Clone repository:

```bash
git clone https://github.com/nima-sadria/FlowHub.git
cd FlowHub
sudo ./installer/install.sh
```

## Docker Install

```bash
git clone https://github.com/nima-sadria/FlowHub.git
cd FlowHub

cp .env.beta.example .env.beta

docker compose -f docker-compose.beta.yml \
  --env-file .env.beta up -d --build
```

Run migrations after the Docker stack is healthy:

```bash
docker compose -f docker-compose.beta.yml \
  --env-file .env.beta exec app alembic -c alembic_beta.ini upgrade head
```

## Installer

The installer supports Ubuntu Server 24.04 LTS and Ubuntu Server 26.04 LTS on
x86_64/amd64 hosts. Ubuntu Core is not supported. Other Debian/Ubuntu hosts are
best-effort only and require explicit confirmation.

FlowHub installs into:

```text
/opt/FlowHub
```

It detects distribution, Ubuntu version, Ubuntu Core, architecture, `apt-get`,
curl/wget, CPU, RAM, disk, Docker, Docker Compose, existing installations, and
Legacy Compatibility installations at `/opt/flowhub`.

Installer actions:

```bash
sudo ./installer/install.sh
sudo ./installer/install.sh --upgrade
sudo ./installer/install.sh --repair
sudo ./installer/install.sh --reinstall
sudo ./installer/install.sh --uninstall
```

If `/opt/FlowHub` already exists, the installer does not overwrite it blindly.
It offers Upgrade, Repair, Reinstall, or Exit. Upgrade and Repair preserve
configuration, generated secrets, database data, uploads, backups, logs, and
Docker volumes. Reinstall warns before destructive actions.

Generated administrator passwords are printed once during installation and are
not stored in plaintext logs or backups.

## Update

```bash
cd /opt/FlowHub
git pull
sudo ./installer/install.sh --upgrade
```

## Uninstall

```bash
sudo ./installer/install.sh --uninstall
```

## CLI

After installation, the `flowhub` command is available:

```bash
flowhub
```

Running `flowhub` without arguments opens the interactive management menu. Direct
command mode also remains available:

```bash
flowhub install
flowhub upgrade
flowhub update
flowhub repair
flowhub status
flowhub health
flowhub logs
flowhub start
flowhub restart
flowhub stop
flowhub uninstall
flowhub backup
flowhub restore backups/flowhub-YYYYMMDDTHHMMSSZ.tar.gz
flowhub admin list
flowhub admin create
flowhub admin reset-username
flowhub admin reset-password
```

The installed `flowhub` wrapper is Docker-backed. Runtime commands use a
root-owned helper with a strict sudoers allowlist, so the normal installing
operator can run FlowHub management commands without manually typing `sudo`.
The wrapper does not read `.env.beta` directly; `.env.beta` remains protected as
`root:root 600`. `flowhub restart` waits for the application health endpoint
before returning successfully.

## Verification

```bash
curl http://localhost:8085/api/health
docker compose -f /opt/FlowHub/docker-compose.beta.yml \
  --env-file /opt/FlowHub/.env.beta ps
flowhub health
```

## Screenshots

Current release UI previews are stored in `docs/assets/screenshots/`.

| Dashboard | Workspace | Integrations |
| --- | --- | --- |
| ![Dashboard](docs/assets/screenshots/dashboard.svg) | ![Workspace](docs/assets/screenshots/workspace.svg) | ![Integrations](docs/assets/screenshots/integrations.svg) |

| Data Layer | Settings |
| --- | --- |
| ![Data Layer](docs/assets/screenshots/data-layer.svg) | ![Settings](docs/assets/screenshots/settings.svg) |

## Documentation

- [Current Architecture](docs/architecture/CURRENT_ARCHITECTURE.md)
- [Integration Platform](docs/architecture/INTEGRATION_PLATFORM.md)
- [Unified Logging Platform](docs/architecture/UNIFIED_LOGGING_PLATFORM.md)
- [Installer Architecture](docs/beta/INSTALLER_ARCHITECTURE.md)
- [Installation Guide](docs/INSTALLATION.md)
- [Upgrade Guide](docs/UPGRADE.md)
- [Backup and Restore](docs/BACKUP_RESTORE.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [FAQ](docs/FAQ.md)
- [Release Checklist](docs/RELEASE_CHECKLIST.md)
- [Roadmap](ROADMAP.md)
- [Support](SUPPORT.md)

## Current vs Planned

Current:

- FlowHub web app, installer, CLI, setup wizard, Data Layer, Integration Platform, Unified Logging Platform, Diagnostics, Settings, and read-only connector management.

Planned:

- Additional connectors including Shopify, Magento, ERP, CSV, Google Sheets, and custom APIs.
- Scheduler execution, Apply flows, and write automation only after Owner approval and new safety review.
- Live logging tail and advanced telemetry visualizations.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md), [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), and [SECURITY.md](SECURITY.md).

## License

FlowHub is released under the [MIT License](LICENSE).

## Support

For usage help, deployment issues, and security reporting, see [SUPPORT.md](SUPPORT.md).
