# Backup and Restore

## Backup

```bash
flowhub backup
```

The command creates a local archive under `/opt/FlowHub/backups`.

## Restore

```bash
flowhub restore /opt/FlowHub/backups/flowhub-YYYYMMDDTHHMMSSZ.tar.gz
flowhub repair
```

For production database recovery, also keep infrastructure-level database volume
backups. The first-release CLI backup focuses on local configuration and storage.
