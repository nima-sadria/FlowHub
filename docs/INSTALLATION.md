# Installation Guide

## Supported Host

- Ubuntu Server 24.04 LTS supported
- Ubuntu Server 26.04 LTS supported
- Ubuntu Core is not supported
- Other Debian/Ubuntu hosts are best-effort only after confirmation
- amd64 / x86_64
- 2 CPU cores minimum
- 4 GB RAM recommended
- 20 GB free disk minimum

## One-Line Install

```bash
curl -fsSL https://raw.githubusercontent.com/nima-sadria/FlowHub/main/installer/install.sh | sudo bash
```

```bash
wget -qO- https://raw.githubusercontent.com/nima-sadria/FlowHub/main/installer/install.sh | sudo bash
```

The installer clones FlowHub into `/opt/FlowHub`, generates `.env.beta`, generates
secrets, builds Docker images, runs migrations, creates the first administrator,
starts services, runs health checks, and prints the application URL.

## Clone Install

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
docker compose -f docker-compose.beta.yml --env-file .env.beta up -d --build
docker compose -f docker-compose.beta.yml --env-file .env.beta exec app alembic -c alembic_beta.ini upgrade head
```

## Legacy Compatibility

Older deployments may exist at `/opt/flowhub`. The installer detects this path,
offers migration to `/opt/FlowHub`, preserves configuration and generated data,
and removes the legacy directory only after successful migration.

## Existing Installations

If `/opt/FlowHub` already exists, the installer presents:

1. Upgrade
2. Repair
3. Reinstall
4. Exit

Upgrade and Repair preserve configuration, secrets, database data, uploads,
backups, logs, and Docker volumes. Reinstall displays a destructive-action
warning before continuing. Exit makes no changes.

## First Login

The installer creates an administrator account. If it generated the password, it
prints it once. Store it immediately; FlowHub does not persist plaintext admin
passwords in logs or backups.

Connector configuration belongs in Settings -> Integrations after sign-in.

## CLI

After installation, run `flowhub` without arguments to open the interactive
management menu. Direct command mode remains available:

```bash
flowhub status
flowhub health
flowhub restart
flowhub admin reset-password --help
```

The installer also installs a root-owned FlowHub helper and sudoers allowlist.
Normal operators run `flowhub` commands without manually typing `sudo`, while
`.env.beta` remains protected as `root:root 600` and is never sourced by the
unprivileged wrapper.
