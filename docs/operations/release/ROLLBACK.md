# FlowHub Release Rollback

FlowHub upgrades are manual operator actions. The installer runs database
migrations after PostgreSQL is healthy. If a migration or health check fails,
do not continue applying changes.

## Before Upgrade

1. Run `flowhub backup`.
2. Confirm the command prints a backup archive path.
3. Keep that archive on the host until the upgraded release has passed health
   checks and a Workspace price run has completed.

Each backup archive contains:

- PostgreSQL SQL dump: `postgres.sql`
- Runtime environment file: `.env`
- FlowHub storage directory
- FlowHub logs, excluding administrator credential export files
- `backup_manifest.json` with the archive format, application version,
  migration head, and SHA-256 checksums for every included file

## Failed Upgrade Recovery

1. Stop operator activity in the UI.
2. Run `flowhub restore <archive>`.
3. Run `flowhub repair`.
4. Run `flowhub health`.
5. Sign in and verify Diagnostics before running any price workflow.

Restore validates archive paths, manifest checksums, required configuration,
storage, and the PostgreSQL dump before extraction. It creates a safety backup
of the running installation, restores PostgreSQL with immediate SQL error
handling in a transaction, then swaps environment and storage files. If file
finalization fails, FlowHub restores the prior files and database from the
safety backup. Rollback remains an explicit operator action.
