# Installation Guide

## Supported Host

- Ubuntu 24.04 LTS recommended
- Debian/Ubuntu supported by the installer
- amd64 or arm64
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

## First Login

The installer creates an administrator account. If it generated the password, it
prints it once and stores a root-readable copy in the installation logs.

Connector configuration belongs in Settings -> Integrations after sign-in.
