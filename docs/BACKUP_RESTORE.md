# Backup and Restore

## Backup

```bash
flowhub backup
```

The command creates a local archive under `/opt/FlowHub/backups`. Plaintext
generated admin credentials are not written by the installer and are excluded
from backups if a legacy credentials file exists.

Use an administrator recovery procedure, such as creating a replacement admin in
the application database, instead of relying on stored plaintext passwords.

## Restore

```bash
flowhub restore /opt/FlowHub/backups/flowhub-YYYYMMDDTHHMMSSZ.tar.gz
flowhub repair
```

For production database recovery, also keep infrastructure-level database volume
backups. The first-release CLI backup focuses on local configuration and storage.
