# Backup and Restore

## Backup

```bash
flowhub backup
```

The command creates a local archive under `/opt/FlowHub/backups`. Plaintext
generated admin credentials are not written by the installer and are excluded
from backups if a legacy credentials file exists.

Each archive includes `postgres.sql`, `.env`, `storage/`, and a
`backup_manifest.json` checksum manifest. Restore rejects missing, corrupt, or
unsafe archives before changing the live installation.

Use an administrator recovery procedure, such as creating a replacement admin in
the application database, instead of relying on stored plaintext passwords.

## Restore

```bash
flowhub restore /opt/FlowHub/backups/flowhub-YYYYMMDDTHHMMSSZ.tar.gz
flowhub repair
```

For production database recovery, also keep infrastructure-level database volume
backups. FlowHub restores its PostgreSQL dump with `ON_ERROR_STOP=1` and a
single transaction, then swaps local runtime files only after database success.
Before mutation it creates a safety backup. If final file replacement fails,
FlowHub restores the prior runtime files and attempts database recovery from the
safety archive. Restore is always an explicit operator action; FlowHub does not
perform automatic rollback.

The current migration head is `FLOWHUB_019`. Verify a completed restore with
`flowhub repair`, `flowhub health`, sign-in, Diagnostics, and a read-only
Workspace Preview before approving any price update.
