# Release Checklist

## Local Verification

- `python -m pytest tests/beta -q`
- `npm run build`
- `npm test -- --run`
- `git diff --check`
- direct-call audit for active Beta v2 routes
- release identity search

## Deployment Host Verification

Run on a brand-new Ubuntu 24.04 host after the release commit is available on
`main`:

```bash
curl -fsSL https://raw.githubusercontent.com/nima-sadria/FlowHub/main/installer/install.sh | sudo bash
```

or:

```bash
wget -qO- https://raw.githubusercontent.com/nima-sadria/FlowHub/main/installer/install.sh | sudo bash
```

Then verify:

```bash
flowhub status
flowhub health
curl http://localhost:8085/api/health
```

Expected result:

- services are running
- setup wizard opens
- setup steps are Welcome, Server Profile, Database, Admin Account, Finish
- connector configuration is only under Settings -> Integrations
- `/opt/FlowHub` is the installation path

## Release Gate Validation Record

Date: 2026-07-02

Verified commit: `00fd7b0eac81ca548a875639617ac6a4b0724a92`

Environment:

- Fresh Ubuntu Server 26.04 LTS VM
- Host: `192.168.100.14`
- Normal operator: `codex`

Decision: PASS

Verified controls:

- `flowhub` works for the normal operator without manually typing `sudo`.
- Protected configuration remains `root:root 600`: `/opt/FlowHub/.env.beta`.
- Docker-backed CLI commands work through the restricted FlowHub helper.
- `flowhub status`, `flowhub health`, `flowhub restart`, `flowhub backup`, and the interactive menu work.
- `flowhub restart` waits for readiness; immediate `/api/health` returns HTTP 200.
- Backup succeeds.
- Installed-host menu shows the simplified operator menu; Install is visible but disabled with "Use Update instead."
- Status Overview shows concise database, panel, and API state.
- No secrets were printed during tested CLI operations.
- Apply, scheduler, WooCommerce writes, and spreadsheet writes remain disabled/read-only.

This record documents release-gate validation only. It does not indicate that
public production deployment has occurred.
