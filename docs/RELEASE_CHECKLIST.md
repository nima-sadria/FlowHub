# Release Checklist

## Release-Candidate Verification

- `python3 -m pytest -q`
- `python3 -m pytest tests/flowhub -q`
- `python3 -m pytest tests/flowhub/test_release_terms_guard.py -q`
- `python3 -m pytest tests/flowhub/migration/test_release_compatibility.py -q`
- `npm test -- --run` and `npm run build` from `frontend/`
- `git diff --check`
- Confirm `FLOWHUB_013` is the Alembic head.
- Confirm a backup manifest and restore-control-flow test pass before tagging.
- Confirm Docker build and an isolated-stack smoke test on a host with Docker.

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
- setup steps are Welcome, Server Profile, Database, Owner Account, Finish
- Nextcloud Source and WooCommerce Channel configuration are available in Commerce Hub
- `/opt/FlowHub` is the installation path

## Production Verification

Record the actual release commit, environment, backup archive identity, Docker
health result, and smoke-test evidence at deployment time. Do not record public
host addresses, credentials, tokens, or copied log bodies in this repository.
