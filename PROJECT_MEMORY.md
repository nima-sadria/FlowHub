# FlowHub Project Memory

This document is the durable memory for the current project state. A new Codex thread should be able to continue from this file plus the repo itself, without reading prior chats.

## 1. What FlowHub is

FlowHub is a release-oriented system for:

- declarative Pricing Matrix configuration and activation
- Source acquisition, observations, schema assessment, and diagnostics
- Workspace review / dry-run / apply safety around pricing decisions
- authenticated operator workflows in a separate frontend worktree

The project is deliberately conservative:

- backend owns truth, validation, persistence, and execution safety
- frontend owns presentation only
- deployment owns secrets, private-network reachability, and environment-specific settings

## 2. Repository layout and worktrees

### Main repository

- `C:\Users\nima\Documents\GitHub\FlowHub`
- Branch: `main`
- Current verified head: `9a75d145e89980e9e42a59d8d38f08162cea7ae4`
- `origin/main` currently matches that head

### Claude UI worktree

- `C:\Users\nima\Documents\GitHub\FlowHub-Claude-UI`
- Branch: `claude/ui-phase-1`
- Separate from the backend worktree
- Used for Pricing Matrix UI implementation only

## 3. Release state

### Current release stage

RC1 handover / final release readiness.

### What is complete

- Pricing Matrix backend contract
- Pricing Matrix concurrency and lifecycle safety
- Pricing Matrix migration integrity
- Currency unit semantics
- Source Acquisition run contract
- Immutable observations and provenance
- Schema assessment and drift detection
- Source acquisition network security
- Source acquisition execution integration
- UI integration and release verification work from the Claude branch

### What is still intentionally open

- final exact browser verification on the canonical merged pricing route
- Pricing migration activation gate
- deployment-owned private Nextcloud network allow-list
- release push / deployment approval

## 4. Verified state of the repo

### Git state

- branch is `main`
- `origin/main` is in sync with local `main`
- no merge/rebase/cherry-pick state remains
- the only known local residue is an untracked root `node_modules/` cache

### Important commits

- latest verified commit: `9a75d145e89980e9e42a59d8d38f08162cea7ae4`
- latest merged commit: `3b7445dd040abd5ac2e29b5e453548f71645b4b6`
- latest frontend commit: `21664cb8b7ccb72c39685097d8a0ebab2af80b0a`
- latest backend commit: `619e8ef5e4503871d313a0fa523603606c2b7b5f`
- latest migration head: `FLOWHUB_027`

## 5. Current baselines

- Backend: `3201 passed, 26 skipped, 0 failed`
- Frontend: `74` files, `590 passed, 0 failed`
- Migration: `34 passed, 7 skipped`
- PostgreSQL-gated subset: `24 passed, 0 failed` in the isolated test environment

## 6. Current architecture memory

### Backend architecture

The backend is split into three large domain areas:

1. Pricing Matrix
2. Source Acquisition
3. Cross-cutting release / verification / migration support

The backend exposes authoritative APIs from `app/flowhub/api/v2/` and owns all safety-sensitive business logic. The frontend must treat the backend contract as the source of truth.

### Pricing Matrix architecture

The pricing system is declarative and revisioned.

Core concepts:

- `PolicyRevision`
- `ProductGroupRevision`
- `UnitDeclaration`
- `ChannelPolicyHead`
- `LifecycleEvent`
- Apply / review / binding projections

Important rules:

- no runtime formula engine
- exact arithmetic only
- a policy revision is inert until explicitly activated per Channel
- a blocked Channel must not block a healthy Channel
- IRR requires explicit `RIAL` or `TOMAN`
- source, channel, and display units are explicit and never inferred from magnitude
- apply state is per Channel and must remain explicit
- all conversions are performed by FlowHub, not the frontend
- migration activation stays gated until the formula inventory and fixtures are complete

### Source Acquisition architecture

The Source subsystem is built around durable, append-only records:

- Acquisition Runs
- immutable Source Observations
- evidence / provenance
- schema assessments
- diagnostics
- workspace binding and resource identity

Important rules:

- `SourceHttpClient` is the only approved outbound network boundary
- no direct ad hoc `requests` / `httpx` calls outside the approved abstraction
- security rejection fails before unsafe network access
- Observations never mutate
- schema assessments are versioned and immutable or append-safe
- raw and canonical schema representations are both preserved
- diagnostics are machine-readable and avoid secret-bearing text

## 7. Contracts

### Callable backend contract

`FRONTEND_CONTRACT.md` is authoritative for what the current frontend may call.

Key contract facts:

- no common envelope / `contract_version`
- no pagination on the current callable Pricing Matrix lists
- requests use the documented casing
- responses use the documented object shapes
- monetary integers and exact identifiers must be handled as string-safe / BigInt-safe values in the UI
- `workspace_precondition` is not exposed as a callable API in the current phase

### Architecture / future contract

`docs/architecture/PRICING_UI_CONTRACT.md` is proposed future architecture only.

It is not callable today and must not be treated as a backend API contract.

## 8. Ownership boundaries

- Backend owns code, migrations, tests, data model, execution safety, and release readiness.
- Claude UI owns the dedicated frontend worktree.
- Deployment owns environment-specific secrets, private network CIDRs, and runtime config.
- The backend repo owns `FRONTEND_CONTRACT.md`; changes to callable behavior must update it together with `RESUME.md`.

## 9. Environment

### Windows development environment

- Shell: PowerShell
- Python virtual environment is available in the repo
- Node.js is available for frontend work
- Docker may be present depending on the host machine

### Ubuntu release-verification environment

- Host: `192.168.100.80`
- Project path: `/home/nima/Projects/FlowHub`
- PostgreSQL test container: `flowhub-postgres-test`
- PostgreSQL URL:

```text
postgresql+psycopg://flowhub_test:flowhub_test_password@127.0.0.1:54329/flowhub_test
```

## 10. Commands that matter most

### Repo inspection

```powershell
git status --short --branch
git fetch origin --prune
git rev-list --left-right --count origin/main...main
git log --oneline --decorate -n 20
git worktree list
```

### Targeted verification

```powershell
python -m pytest tests/flowhub/pricing_matrix -q
python -m pytest tests/flowhub/source_workspace -q
python -m pytest -m postgres -q
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

## 11. How to continue safely

1. Read `PROJECT_STATUS.md`.
2. Read `DEVELOPER_RESUME.md`.
3. Confirm `git status --short --branch`.
4. Confirm `origin/main` is in sync.
5. Decide whether the next task is:
   - final browser repair / verification,
   - pricing activation gate work,
   - deployment prerequisite documentation,
   - or push preparation.

Do not start new feature implementation from this state without re-checking the release blockers and the callable contract first.

## 12. Known technical debt

- Root `node_modules/` local cache remains untracked residue.
- Pricing migration activation is still intentionally disabled.
- Final merged browser verification for `/settings/pricing` still needs a fresh exact confirmation.
- Private Nextcloud deployment configuration still needs an explicit deployment-owned allow-list path.

## 13. Current release conclusion

The repository is in a release-handover state, not a push-ready state. The codebase is broadly verified, but the final browser route and the remaining deployment / activation gates mean RC1 is not yet cleanly released.
