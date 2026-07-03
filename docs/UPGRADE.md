# Upgrade Guide

```bash
cd /opt/FlowHub
git pull
sudo ./installer/install.sh --upgrade
```

Upgrade keeps `.env`, generated secrets, database data, uploads, logs, and
backups. It rebuilds Docker images, runs migrations, restarts services, and runs
health checks.

`flowhub update` is an alias for `flowhub upgrade`.

Running the installer without flags on an existing `/opt/FlowHub` installation
also shows Upgrade, Repair, Reinstall, and Exit. Upgrade preserves configuration,
secrets, database data, uploads, backups, logs, and Docker volumes.

Rollback depends on the deployment backup. Create a backup before major upgrades:

```bash
flowhub backup
```
