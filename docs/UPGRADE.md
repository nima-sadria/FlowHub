# Upgrade Guide

```bash
cd /opt/FlowHub
git pull
sudo ./installer/install.sh --upgrade
```

Upgrade keeps `.env.beta`, generated secrets, database data, uploads, logs, and
backups. It rebuilds Docker images, runs migrations, restarts services, and runs
health checks.

Rollback depends on the deployment backup. Create a backup before major upgrades:

```bash
flowhub backup
```
