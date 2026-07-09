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

## Failed Upgrade Recovery

1. Stop operator activity in the UI.
2. Run `flowhub restore <archive>`.
3. Run `flowhub repair`.
4. Run `flowhub health`.
5. Sign in and verify Diagnostics before running any price workflow.

Rollback is explicit by design. FlowHub does not run an unattended restore after
a failed migration because an operator must confirm the target archive and then
verify database health.
