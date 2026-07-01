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
