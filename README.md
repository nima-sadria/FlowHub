# FlowHub

[![Build](https://img.shields.io/badge/build-ready_for_release-16a34a)](https://github.com/nima-sadria/FlowHub)
[![Docker](https://img.shields.io/badge/docker-compose-2496ed)](docker-compose.yml)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Latest Release](https://img.shields.io/badge/release-FlowHub_v1.2_Stable-7c3aed)](docs/releases/FLOWHUB_V1.2_STABLE.md)

FlowHub v1.2 Stable is the approved self-hosted multi-channel workspace release.
The approved release commit is
[`4a02fbbcf25f0d82d05f7dc5f0f1dd3efa322a0c`](docs/releases/FLOWHUB_V1.2_STABLE.md).

FlowHub v1.3 development adds a [Source-centric pricing Workspace](docs/architecture/SOURCE_CENTRIC_PRICING_WORKSPACE.md), explicit per-Channel Source mappings, Data Quality workflow, and a managed internal FlowHub Sheet while preserving the frozen v1.2 safety pipeline.

FlowHub is a self-hosted WooCommerce price-management platform. It reads a
Nextcloud-hosted spreadsheet through WebDAV, validates proposed price changes
against a manually refreshed WooCommerce product cache, and performs only
explicitly approved manual price updates.

## Architecture

The v1.2 architecture is complete and frozen for normal feature development.
See the [official v1.2 release registration](docs/releases/FLOWHUB_V1.2_STABLE.md)
and [current architecture](docs/architecture/CURRENT_ARCHITECTURE.md).

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
    Dashboard --> Settings[Settings]
    Dashboard --> Diagnostics[Diagnostics]
    Dashboard --> Activity[Activity]
```

## Features

- Source Product parent rows group independent Channel Listings for daily pricing.
- Explicit Source Product and per-Channel mappings support irregular spreadsheets.
- FlowHub Sheet provides versioned rows, safe formulas, CSV/XLSX import, and a
  virtualized 10,000-row editor independent of Handsontable functionality.
- Data Quality separates blocked technical issues from eligible daily changes.
- First-run setup creates the initial owner account, then locks setup.
- Nextcloud Sources are read-only: test WebDAV access, browse/select a workbook,
  map columns, select worksheets, and manually read within a source quota.
- WooCommerce Channels provide read-only connection checks and manual product-cache
  refreshes for simple products, variable parents, and variations.
- The Workspace workflow is server-authoritative: Preview, row selection, Dry
  Run, Approval, manual Apply, read-back verification, and audit.
- WooCommerce writes support price fields only for simple products and variations.
  Stock writes, source writes, schedulers, and automatic Apply are not available.
- Integration, diagnostics, logging, rate limiting, redaction, backup, and
  rollback controls are included for production operation.
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

cp .env.example .env

docker compose -f docker-compose.yml \
  --env-file .env up -d --build
```

Run migrations after the Docker stack is healthy:

```bash
docker compose -f docker-compose.yml \
  --env-file .env exec app alembic -c alembic_flowhub.ini upgrade head
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

Generated initial-owner passwords are printed once during installation and are
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

Running `flowhub` without arguments opens the simple operator menu:

```text
FlowHub Management

Maintenance
1. Install
2. Update
3. Uninstall
4. Domain + SSL Setup
5. IP + Port Setup

Account
6. Owner Setup
7. Show Base URL
8. Show Admin Users
9. Add Admin User
10. Delete Admin User

Status
11. Status Overview

Diagnostics
12. Logs
13. Errors & Warnings

0. Exit
```

On installed hosts, menu option 1 is disabled and prints:

```text
FlowHub is already installed. Use Update instead.
```

Advanced recovery and support commands remain available only through direct
command mode:

```bash
flowhub install
flowhub upgrade
flowhub update
flowhub repair
flowhub reinstall
flowhub status
flowhub health
flowhub logs
flowhub start
flowhub restart
flowhub stop
flowhub uninstall
flowhub backup
flowhub restore backups/flowhub-YYYYMMDDTHHMMSSZ.tar.gz
flowhub base-url
flowhub overview
flowhub errors
flowhub domain set kharidbezan.com
flowhub tls status
flowhub tls letsencrypt kharidbezan.com
flowhub admin list
flowhub admin create
flowhub admin delete
flowhub admin reset-username
flowhub admin reset-password
```

The installed `flowhub` wrapper is Docker-backed. Runtime commands use a
root-owned helper with a strict sudoers allowlist, so the normal installing
operator can run FlowHub management commands without manually typing `sudo`.
The wrapper does not read `.env` directly; `.env` remains protected as
`root:root 600`. `flowhub restart` waits for the application health endpoint
before returning successfully.

On an installed host, `flowhub install` does not re-enter the installer workflow;
use Update from the menu or `flowhub upgrade` from direct command mode instead.

### Domain and TLS

Use menu option **4. Domain + SSL Setup** to configure the public domain, panel
port, and recorded TLS mode. It prints the resulting URL as:

```text
https://example.com:PORT/
```

Use menu option **5. IP + Port Setup** for local or private-network deployments
without SSL. It prints:

```text
http://IP:PORT/
```

Direct command mode is still available for support sessions:

```bash
flowhub domain set kharidbezan.com
flowhub tls letsencrypt kharidbezan.com
flowhub tls status
flowhub start
```

FlowHub's current Docker stack exposes the app and expects certificate issuance
and renewal to be handled by an external reverse proxy. FlowHub records the
desired public URL and TLS mode; it does not store Let's Encrypt private keys in
this release.

## Verification

```bash
curl http://localhost:8085/api/health
docker compose -f /opt/FlowHub/docker-compose.yml \
  --env-file /opt/FlowHub/.env ps
flowhub health
```

## Screenshots

Current release UI previews are stored in `docs/assets/screenshots/`.

| Dashboard | Workspace | Settings |
| --- | --- |
| ![Dashboard](docs/assets/screenshots/dashboard.svg) | ![Workspace](docs/assets/screenshots/workspace.svg) | ![Settings](docs/assets/screenshots/settings.svg) |

## Documentation

- [Current Architecture](docs/architecture/CURRENT_ARCHITECTURE.md)
- [Integration Platform](docs/architecture/INTEGRATION_PLATFORM.md)
- [Unified Logging Platform](docs/architecture/UNIFIED_LOGGING_PLATFORM.md)
- [Installer Architecture](docs/platform/INSTALLER_ARCHITECTURE.md)
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
