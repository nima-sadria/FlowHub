# FlowHub Developer Resume

This file is the shortest safe continuation guide for a new Codex thread.

## Repository

- Deployment authority: [Authoritative Ubuntu Deployment Topology](OPERATIONS_RUNBOOK.md).
  The deployment-server checkout is `/home/nima/Projects/FlowHub`; `/opt/FlowHub`
  is retired. Any Windows clone is development-only, not a deployment checkout.
- Current branch: `main`
- Current verified head: `9a75d145e89980e9e42a59d8d38f08162cea7ae4`
- `origin/main` matches `main`

## Worktrees

- Main worktree: `C:\Users\nima\Documents\GitHub\FlowHub`
- Claude UI worktree: `C:\Users\nima\Documents\GitHub\FlowHub-Claude-UI`

Do not modify the Claude worktree unless the task is explicitly UI integration and the owner approves it.

## Current RC state

- RC1 release handover exists.
- Backend feature work through Stage 10B is complete.
- Final release verification remains incomplete because the canonical pricing route still needs a fresh exact browser confirmation on the merged build.
- Pricing migration activation is intentionally still gated.
- Private Nextcloud deployment configuration is intentionally fail-closed by default.

## Remaining work

1. Close the final release-browser verification gap on the exact merged build.
2. Keep Pricing Matrix migration activation disabled until the translation inventory and formula gate are complete.
3. Keep private-network deployment configuration deployment-owned and outside source control.
4. Push only after the owner explicitly approves the release state.

## Known technical debt

- Root-level `node_modules/` is an untracked disposable cache from an incorrect `npx` run.
- Pricing migration activation still depends on Appendix A inventory completion and broken-formula remediation.
- Public release browser sanity is not yet fully closed for the final merged build.

## Environment

### Windows development environment

- Shell: PowerShell
- Python: project virtual environment available under the repository
- Node: installed and usable for frontend checks
- Docker: available when the host environment provides it

### Ubuntu release-verification environment

- Host: `192.168.100.80`
- Project path: `/home/nima/Projects/FlowHub`
- Normal updates use `flowhub` as user `nima`; see the Operations Runbook for
  canonical runtime, database, proxy, and deployed-version identity rules.
- PostgreSQL test container: `flowhub-postgres-test`
- PostgreSQL test URL: `postgresql+psycopg://flowhub_test:flowhub_test_password@127.0.0.1:54329/flowhub_test`

## Installed / expected tooling

- Python 3.12
- Node.js 22
- npm
- uv
- Docker / Docker Compose
- Git

## Commands that matter

### Repo health

```powershell
git status --short --branch
git fetch origin --prune
git rev-list --left-right --count origin/main...main
git log --oneline --decorate -n 20
```

### Focused verification

```powershell
python -m pytest -m postgres -q
python -m pytest tests/flowhub/pricing_matrix -q
python -m pytest tests/flowhub/source_workspace -q
npx vitest run
npx tsc -b
```

### Release environment verification

```powershell
ssh nima@192.168.100.80
cd /home/nima/Projects/FlowHub
export FLOWHUB_TEST_POSTGRES_URL='postgresql+psycopg://flowhub_test:flowhub_test_password@127.0.0.1:54329/flowhub_test'
python -m pytest -m postgres -q
```

## Commands / checks to avoid forgetting

- Always verify `origin/main` before describing a live release URL.
- Never push or deploy without owner approval.
- Do not infer pricing or currency conversions in the frontend.
- Keep `SourceHttpPolicy.allowed_private_networks` fail-closed in source control.
