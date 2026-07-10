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

The installer clones FlowHub into `/opt/FlowHub`, generates `.env`, generates
secrets, builds Docker images, runs migrations, creates the initial owner,
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
cp .env.example .env
docker compose -f docker-compose.yml --env-file .env up -d --build
docker compose -f docker-compose.yml --env-file .env exec app alembic -c alembic_flowhub.ini upgrade head
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

The setup wizard creates the initial owner account. If it generated the password, it
prints it once. Store it immediately; FlowHub does not persist plaintext admin
passwords in logs or backups.

Connector configuration belongs in Settings after sign-in.

## Trusted Proxies

FlowHub ignores `X-Forwarded-For` unless the direct peer is listed in
`FLOWHUB_TRUSTED_PROXY_NETWORKS`. Leave the value empty for direct deployments.
For a reverse proxy on a private Docker network, use a CIDR such as
`172.18.0.0/16`; do not add public networks. This protects database-backed login
throttling from forged forwarded headers.

## CLI

After installation, run `flowhub` without arguments to open the interactive
management menu:

```text
FlowHub Management

Maintenance
1. Install
2. Update
3. Uninstall
4. Domain + SSL Setup
5. IP + Port Setup

Account
6. Admin Setup
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

On an installed host, option 1 prints `FlowHub is already installed. Use Update
instead.` Direct command mode remains available for automation and support:

```bash
flowhub status
flowhub health
flowhub restart
flowhub base-url
flowhub overview
flowhub errors
flowhub domain set kharidbezan.com
flowhub tls status
flowhub admin create
flowhub admin delete
flowhub admin reset-password --help
```

The installer also installs a root-owned FlowHub helper and sudoers allowlist.
Normal operators run `flowhub` commands without manually typing `sudo`, while
`.env` remains protected as `root:root 600` and is never sourced by the
unprivileged wrapper.

## Domain and TLS

The interactive menu includes **4. Domain + SSL Setup** for configuring the
public host, panel port, base URL, and recorded TLS mode. It prints URLs in this
form:

```text
https://example.com:PORT/
```

Use **5. IP + Port Setup** for local or private-network deployments without SSL:

```text
http://IP:PORT/
```

Direct command mode is also available:

```bash
flowhub domain set kharidbezan.com
flowhub start
```

The current Docker stack does not include a TLS-terminating reverse proxy.
Let's Encrypt certificates should be issued and renewed by the external reverse
proxy in front of FlowHub. The CLI can record the desired public URL mode:

```bash
flowhub tls letsencrypt kharidbezan.com
flowhub tls status
flowhub start
```

FlowHub does not store Let's Encrypt private keys in this release.
