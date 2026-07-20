# Morning Handoff

Status: first-release finalization.

## Current State

- Main branch targets the first public FlowHub deployment.
- Canonical installation path is `/opt/FlowHub`.
- Legacy Compatibility migration covers older `/opt/flowhub` installations.
- Setup Wizard contains Workspace, Database, Owner, and Review.
- Connector configuration belongs in Settings.
- The current UI release includes Application Shell, Dashboard, Products,
  Orders, Sources, Channels, Activity, Data Quality, Diagnostics, Settings,
  User Management, Rate Limits, Setup Wizard, and Login.
- The current Alembic head is `FLOWHUB_019`.
- Integration Platform and Unified Logging Platform are implemented.
- Read-only safety remains active.

## Before Deployment

Run:

```bash
python -m pytest tests/flowhub -q
npm run build
npm test -- --run
git diff --check
```

On the deployment host, verify:

```bash
curl -fsSL https://raw.githubusercontent.com/nima-sadria/FlowHub/main/installer/install.sh | sudo bash
flowhub status
flowhub health
```

## Known Planned Work

- Additional connectors.
- Live logging tail.
- Write execution only after separate approval.
