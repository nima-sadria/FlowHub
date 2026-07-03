# Installer Architecture

Status: current first-release installer contract.

## Canonical Path

FlowHub installs to:

```text
/opt/FlowHub
```

Legacy Compatibility: if `/opt/flowhub` exists, the installer detects it, offers
migration, preserves configuration and generated data, rewrites known paths, and
removes the legacy directory only after successful migration.

## Entry Points

```bash
curl -fsSL https://raw.githubusercontent.com/nima-sadria/FlowHub/main/installer/install.sh | sudo bash
wget -qO- https://raw.githubusercontent.com/nima-sadria/FlowHub/main/installer/install.sh | sudo bash
sudo ./installer/install.sh
sudo ./installer/install.sh --upgrade
sudo ./installer/install.sh --repair
sudo ./installer/install.sh --reinstall
sudo ./installer/install.sh --uninstall
```

## Installer Responsibilities

- Detect Linux distribution.
- Verify architecture, CPU, RAM, and free disk.
- Install Docker if missing.
- Install Docker Compose if missing.
- Clone or update the FlowHub repository.
- Generate `.env`.
- Generate required secrets.
- Build Docker images.
- Run database migrations.
- Create the first administrator account.
- Start services.
- Run health checks.
- Print URL, admin username, generated password once, and next-step commands.

## CLI Wrapper

The installed `flowhub` command supports:

- `flowhub install`
- `flowhub upgrade`
- `flowhub repair`
- `flowhub status`
- `flowhub health`
- `flowhub logs`
- `flowhub restart`
- `flowhub stop`
- `flowhub uninstall`
- `flowhub backup`
- `flowhub restore`

## Safety

Installer actions do not enable Apply, Scheduler execution, automatic pricing,
WooCommerce writes, or spreadsheet writes.
