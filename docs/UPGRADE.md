# Upgrade Guide

## Canonical Ubuntu deployment server

The authoritative procedure for the Ubuntu deployment server is in the
[Operations Runbook](../OPERATIONS_RUNBOOK.md). Its only checkout is
`/home/nima/Projects/FlowHub`; `/opt/FlowHub` is retired and must not be used.

```bash
cd /home/nima/Projects/FlowHub
flowhub
```

Run the update as `nima`. Do not use `sudo git`, create another checkout, or
reset the database. The normal update preserves `.env`, database data, uploads,
logs, backups, and Docker volumes while rebuilding, migrating, restarting, and
checking health.

## Historical installer-managed installations

These notes do not identify the current deployment server. Never use a
historical installer target, old container, preview, or alternate checkout to
determine the deployed version.

Rollback depends on the deployment backup. Create a backup before major upgrades:

```bash
flowhub backup
```
