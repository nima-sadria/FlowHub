# Morning Handoff

Status: first-release finalization.

## Current State

- Main branch targets the first public FlowHub deployment.
- Canonical installation path is `/opt/FlowHub`.
- Legacy Compatibility migration covers older `/opt/flowhub` installations.
- Setup Wizard contains Welcome, Server Profile, Database, Admin Account, Finish.
- Connector configuration belongs in Settings -> Integrations.
- Integration Platform and Unified Logging Platform are implemented.
- Read-only safety remains active.

## Before Deployment

Run:

```bash
python -m pytest tests/beta -q
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
