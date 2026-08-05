# FlowHub continuation handover

## Read this first

This repository contains substantial **unfinished, unique, uncommitted work** for the Source Architecture and Pricing Matrix initiatives. Do not reset, restore, stash, clean, checkout over, or delete the listed files. The worktree was intentionally preserved for the next Codex session.

Implementation resumed for the Workspace Pricing Matrix binding boundary. This document records the current handover state; feature changes remain uncommitted and must be reviewed as one coherent phase before publication.

## Repository state

- Canonical repository: `C:\Users\nima\Documents\GitHub\FlowHub`
- Branch: `main`
- Feature-work base commit: `df928cc7a3cff50b0055bcf7cb94117034ff8986`
- Base commit message: `docs(architecture): add pricing matrix ADR`
- `origin/main` after a fresh fetch during stabilization: `df928cc7a3cff50b0055bcf7cb94117034ff8986`
- Handover commit: current `HEAD` (this file is the only file committed on top of the feature-work base)
- Registered Git worktrees: exactly one, the canonical repository above
- Staging area after handover: expected to be empty
- Worktree cleanliness: intentionally dirty because unfinished feature work is preserved

At the start of stabilization, local `main` and `origin/main` were identical. After committing this handover, local `main` is expected to be one documentation commit ahead of `origin/main`. No push or deployment is part of stabilization.

## Git integrity checks

The following conditions were verified before this handover was written:

- No merge is in progress.
- No rebase is in progress.
- No cherry-pick, revert, bisect, or sequencer operation is in progress.
- No staged files exist.
- No conflict markers were found.
- `git diff --check` passed. The only Git output was Windows LF-to-CRLF conversion warnings; no whitespace errors were reported.
- Workspace binding methods are now present in `app/flowhub/pricing_matrix/service.py`; the Review/Apply integration and regression tests listed below are implemented in the current worktree.
- No `TODO` or `FIXME` marker was introduced in the new Pricing Matrix files or the touched Source Configuration UI.
- No source work appears lost.

## Uncommitted tracked files

These files are modified and contain unfinished feature work. Preserve all of them:

### Backend and API

- `app/flowhub/api/v2/commerce.py`
- `app/flowhub/api/v2/settings_routes.py`
- `app/flowhub/api/v2/setup.py`
- `app/flowhub/api/v2/source_workspace.py`
- `app/flowhub/app.py`
- `app/flowhub/commerce/service.py`
- `app/flowhub/source_workspace/service.py`

### Architecture documents

- `docs/architecture/ADR_PRICING_MATRIX.md`
- `docs/architecture/PRICING_MATRIX_DESIGN.md`
- `docs/architecture/SOURCE_ACQUISITION_DESIGN.md`

### Frontend

- `frontend/src/api/types.ts`
- `frontend/src/features/sourceWorkspace/api.ts`
- `frontend/src/features/sourceWorkspace/types.ts`
- `frontend/src/globals.css`
- `frontend/src/i18n/locales/en/commerce.json`
- `frontend/src/i18n/locales/en/settings.json`
- `frontend/src/i18n/locales/fa/commerce.json`
- `frontend/src/i18n/locales/fa/settings.json`
- `frontend/src/pages/CommerceHub.test.tsx`
- `frontend/src/pages/CommerceHub.tsx`
- `frontend/src/pages/Settings.test.tsx`
- `frontend/src/pages/Settings.tsx`
- `frontend/src/pages/Setup.tsx`
- `frontend/src/pages/SourceConfiguration.test.tsx`
- `frontend/src/pages/SourceConfiguration.tsx`
- `frontend/src/services/commerce/CommerceService.ts`

### Backend test stabilization

- `tests/flowhub/api/v2/test_settings_routes.py`
- `tests/flowhub/api/v2/test_unified_workspace.py`
- `tests/flowhub/migration/test_exchange_rates_022.py`
- `tests/flowhub/migration/test_release_compatibility.py`
- `tests/flowhub/migration/test_tapsishop_webhook_identity_023.py`
- `tests/flowhub/source_workspace/test_workspace_integration.py`
- `tests/flowhub/test_no_direct_httpx.py`
- `tests/flowhub/test_release_terms_guard.py`

The two settings tests in this file were minimally aligned with the unfinished explicit IRR unit contract by sending `currencyUnit: RIAL` and asserting `server.currency_unit`. This was required for the preserved worktree to pass its relevant backend tests; it does not extend product behavior.

## Untracked files created by the unfinished feature

These files contain unique work and must be preserved:

### Migration and API

- `alembic_flowhub/versions/flowhub_024_pricing_matrix.py`
- `app/flowhub/api/v2/pricing_matrix.py`

### Pricing Matrix package

- `app/flowhub/pricing_matrix/__init__.py`
- `app/flowhub/pricing_matrix/arithmetic.py`
- `app/flowhub/pricing_matrix/contracts.py`
- `app/flowhub/pricing_matrix/errors.py`
- `app/flowhub/pricing_matrix/evaluator.py`
- `app/flowhub/pricing_matrix/guards.py`
- `app/flowhub/pricing_matrix/models.py`
- `app/flowhub/pricing_matrix/service.py`
- `app/flowhub/pricing_matrix/units.py`

### Architecture and UI contracts

- `docs/architecture/ADR_SOURCE_UI_OBSERVABILITY_ADDENDUM.md`
- `docs/architecture/PRICING_UI_CONTRACT.md`

### Pricing Matrix tests

- `tests/flowhub/pricing_matrix/test_arithmetic.py`
- `tests/flowhub/pricing_matrix/test_evaluator.py`
- `tests/flowhub/pricing_matrix/test_guards.py`
- `tests/flowhub/pricing_matrix/test_units.py`

## Deleted files

None.

## Ignored local artifacts

Ignored files were inspected but not removed. They include `.env`, virtual environments, dependency directories, caches, runtime logs, test output, local data, backups, screenshots, and frontend build output. In particular:

- `.env` is local/secret-related and must not be deleted or committed.
- `.codex-runtime-logs/`, `.pytest_cache/`, `.ruff_cache/`, `.uv-cache/`, `__pycache__/`, `frontend/test-results/`, and `frontend/dist/` are disposable generated artifacts, but cleanup was not part of this stabilization task.
- `.venv/`, `frontend/node_modules/`, `data/`, and `backups/` were left untouched.

## What the unfinished implementation currently contains

### Pricing Matrix core

- Exact rational arithmetic without floating point.
- Explicit rounding modes and one-round semantics.
- Canonical currency/unit handling, including IRR `RIAL`/`TOMAN` factor 10.
- Quote evaluation, eligibility, basis selection, rule application, and guards.
- Unit, arithmetic, evaluator, and guard tests.

### Persistence and API skeleton

- Policy revisions and rule entries.
- Product group revisions and members.
- Channel configuration revisions.
- Append-only policy lifecycle events and mutable channel policy heads.
- Workspace binding and attention signal models.
- Pricing Matrix service and API router registration.
- Draft Alembic migration `FLOWHUB_024` with `FLOWHUB_023` as its parent.

### Explicit currency/unit declarations

- Setup and Settings accept an explicit currency unit.
- IRR requires `RIAL` or `TOMAN`; non-IRR units match the currency.
- Source and Channel configuration paths carry currency/unit declarations.
- Commerce Hub, Setup, Settings, and Source Configuration UI/types contain the corresponding unfinished changes in English and Persian.

### Documents

- Pricing Matrix ADR/design refinements.
- Source Acquisition design refinements.
- Source UI observability addendum.
- Pricing UI contract for backend/frontend coordination.

## Current phase status

The **Workspace and Write Pipeline integration for Pricing Matrix bindings** is implemented in the current worktree:

1. Review generation binds only price-changing Channels and stores activation, policy, Channel config, execution-policy snapshot, and frozen evaluation time.
2. Binding identity and issues participate in the Review response and checksum.
3. Apply revalidates bindings before job creation, after listing locks, and immediately before Write Pipeline dispatch.
4. All external writes remain inside the existing `WritePipelineService`.
5. Regression coverage includes missing activation, stale activation, stale Channel config, per-Channel isolation, and a pre-dispatch race.

The Pricing Matrix API and persistence contract is complete for policy revisions,
Product Group revisions, unit declarations, and Channel activation lifecycle.
`FRONTEND_CONTRACT.md` is the callable backend contract for the frontend team.

Phase 1B is complete. Lifecycle mutations use only the pre-seeded authoritative
Channel Policy Head and fail closed when it is missing. Stale activation and
deactivation attempts return `409 pricing_policy_head_conflict`; retry requires
refetching the Head version. Workspace binding revalidation remains enforced at
Review creation, Apply start, after locks, and before Write Pipeline dispatch.

Phase 2A is complete. `FLOWHUB_024` now imports Pricing Matrix metadata into
Alembic, matches the persistence model's indexes and constraints, seeds one
version-zero Channel Policy Head for every pre-existing Channel without
inferring currency units, and is explicitly forward-only. SQLite coverage
verifies clean installation, `FLOWHUB_023 -> FLOWHUB_024` preservation,
idempotent seed behavior, schema parity, and non-destructive downgrade refusal.
PostgreSQL clean-install coverage is present and requires the configured local
disposable `FLOWHUB_TEST_POSTGRES_URL`.

Phase 2B is complete. Source and Channel declarations are independently
versioned Currency Profiles. Missing declarations remain unresolved; no
RIAL/TOMAN inference occurs. Source-backed Workspace creation now fails closed
before a Pricing Review can be created when its Source declaration is missing.
Raw Source preview remains outside that gate. Existing Pricing Matrix binding
continues to isolate unresolved Channels as per-Channel Review issues.

Phase 3A is complete. `FLOWHUB_025` adds durable append-safe Source Acquisition
Runs only: lifecycle status/result separation, Source/scope idempotency,
database-enforced active-run uniqueness, worker lease ownership, cancellation,
abandonment, and retry lineage. No provider read, Observation, Binding,
Diagnostics, scheduler, or callable API was added. Idempotency keys are NFKC
normalized opaque identifiers and replay the exact retained Run; keys with a
different intent conflict. The Run migration is forward-only because deleting
Run audit and retry lineage is unsafe.

Exact next task: Phase 3B - implement immutable Source Observations and
evidence/provenance records that are produced by a completed Run. Do not add
provider acquisition, diagnostics, schema assessment, or UI in that phase.

## Temporary TODOs

There are no temporary `TODO`/`FIXME` comments in code. The remaining work is represented by the phases below, not by placeholder implementation.

## Remaining blockers

1. PostgreSQL migration coverage is skipped locally until `FLOWHUB_TEST_POSTGRES_URL`
   points to an isolated local test database.
2. Browser verification has not been performed for this backend phase.
3. The new Pricing UI described by `PRICING_UI_CONTRACT.md` has not been implemented.
4. Source Acquisition runtime described by `SOURCE_ACQUISITION_DESIGN.md` has not been implemented.
5. The i18n validator exits nonzero because of two pre-existing hardcoded strings:
   - `frontend/src/components/SiteFooter.tsx`: `FlowHub v`
   - `frontend/src/pages/ExchangeRates.tsx`: `/ day ·`
6. Migration rollout gates remain: complete Appendix A from the real translator inventory, add a fixture for every supported legacy formula shape, and resolve or explicitly quarantine the documented 255 broken formulas before activation.
7. The full backend suite has one unrelated pre-existing failure in `tests/beta/test_multi_channel_pricing.py`: a validation failure is currently projected as `reconciliation_required` while the test expects `failed`.

## Required migrations

`alembic_flowhub/versions/flowhub_024_pricing_matrix.py` is a linear migration from
`FLOWHUB_023`. It creates:

- `pm_policy_revisions`
- `pm_product_group_revisions`
- `pm_product_group_members`
- `pm_rule_entries`
- `pm_channel_config_revisions`
- `pm_policy_lifecycle_events`
- `pm_channel_policy_heads`
- `pm_workspace_bindings`
- `pm_attention_signals`

Migration integrity completed for SQLite. `FLOWHUB_024` is explicitly
**forward-only**: downgrade raises `NotImplementedError` rather than deleting
immutable policy, activation, or Workspace-binding audit records. Restore a
verified backup for rollback. The migration seeds heads deterministically for
existing Channels and creates no currency profile or Channel configuration
revision, so currency units remain unresolved until Phase 2B explicitly handles
them. PostgreSQL has an isolated clean-install test that remains pending local
execution until `FLOWHUB_TEST_POSTGRES_URL` is configured.

`alembic_flowhub/versions/flowhub_025_source_acquisition_runs.py` is a linear,
forward-only migration from `FLOWHUB_024`. It creates `saq_runs` with the
status/result checks, self-referential retry lineage, idempotency uniqueness,
and partial unique active-run lease constraint. SQLite migration and model-parity
tests pass. PostgreSQL migration execution remains pending until
`FLOWHUB_TEST_POSTGRES_URL` is configured.

## Verification completed during stabilization

- Fresh `git fetch origin --prune`: local feature base and `origin/main` both `df928cc7a3cff50b0055bcf7cb94117034ff8986`.
- `git diff --check`: passed.
- Python syntax compilation of all new/touched Pricing Matrix and affected backend files: passed.
- Frontend TypeScript check: passed as part of the production build.
- Frontend full unit suite: 67 files, 485 tests passed.
- Frontend production build: passed with Vite 8.1.4; no chunk-size warning was emitted.
- Relevant backend suite: 181 tests passed with 30 deprecation warnings.
  - Pricing Matrix core tests
  - Setup API tests
  - Settings API tests
  - Commerce Hub backend tests
  - Source Workspace service tests
- Workspace integration suite: 39 passed.
- Pricing Matrix plus migration suites: 48 passed, 6 skipped.
- Full backend suite: 3114 passed, 25 skipped, 1 unrelated failure.
- Frontend full unit suite: 67 files, 485 tests passed.
- Frontend production build and TypeScript check: passed.

Known test noise: the frontend suite emitted jsdom/Handsontable CSS parse warnings, and backend tests emitted existing FastAPI/Starlette/SQLite/Alembic deprecation warnings. These did not fail the suites.

## Required tests still pending

1. Resolve or explicitly accept the unrelated beta multi-channel pricing projection mismatch.
2. Execute the PostgreSQL `FLOWHUB_024` clean-install test when the disposable
   `FLOWHUB_TEST_POSTGRES_URL` is available.
3. Write Pipeline fold/projection tests for all documented terminal states.
4. Explicit Source/Channel unit migration and unresolved-unit tests.
5. Frontend tests for all new Pricing UI states after that UI exists.
6. i18n validation after the two pre-existing hardcoded strings are addressed in a separate scoped change.
7. Implement Source Acquisition Phase 3B Observations and evidence records.

## Browser verification still pending

No live URL was presented and no browser verification was performed after the unfinished implementation. Before review or deployment, verify a build tied to the current `origin/main` commit plus the eventual feature commit, following the repository live-version rule.

Required browser matrix:

- `/setup`: explicit currency and RIAL/TOMAN unit selection.
- `/settings`: persisted global currency/display unit and validation errors.
- `/commerce`: Source and Channel currency/unit declarations and unresolved states.
- Source Configuration: currency profile display plus existing mapping workflow.
- Future Pricing Matrix screens: policy editing, activation, readiness, attention signals, and per-channel blocked states.
- English LTR and Persian RTL.
- Light and dark themes.
- Mobile, tablet, and desktop.
- Console errors, failed network requests, 401 refresh behavior, and accessibility/touch targets.

## Risks and assumptions

- The work is not release-ready. Passing focused tests does not prove end-to-end correctness.
- Existing Sources and Channels may have no explicit unit. They must remain `unresolved`; magnitude-based inference is forbidden.
- Source/Channel unit updates and related connector/settings persistence may not yet be transactionally atomic. Verify rollback behavior.
- `SettingsPatch` now requires currency and unit together. Compatibility with older clients needs explicit tests.
- Setup clients that omit the new unit may depend on backend defaults for non-IRR currencies; IRR must fail without an explicit unit.
- Migration/model drift and circular imports remain possible until integration and migration tests pass.
- Workspace binding models exist, but the service and execution boundary are incomplete. Applying prices before that work would violate the ADR.
- Source Acquisition documents are ahead of runtime implementation; do not present their behavior as shipped.
- The browser and deployed server have not been tied to this unfinished work. Any existing live instance is stale or unverified relative to it.
- LF-to-CRLF warnings are present on Windows but `git diff --check` is clean. Avoid broad line-ending rewrites.
- All listed modified and untracked files contain unique work. Deleting them would lose work.

## Remaining phases and token estimate

These are engineering estimates, not budgets or guarantees:

| Phase | Scope | Expected tokens |
|---|---|---:|
| 1 | Workspace/Write Pipeline binding, revalidation, and race-safe tests | completed this phase |
| 2A | Verify Pricing Matrix migration integrity | completed |
| 2B | Implement explicit Source/Channel currency-unit migration semantics | 12k-20k |
| 3A | Source Acquisition Run lifecycle, idempotency, lease, cancellation, retry persistence | completed |
| 3B | Immutable Source Observations, evidence, and provenance | 10k-18k |
| 3C-3E | Binding, schema assessment, Diagnostics, security, and Source integration | 30k-52k |
| 4 | Implement Pricing/Source UI contract in EN/FA, RTL/LTR, light/dark, responsive layouts | 35k-60k |
| 5 | Translator inventory, Appendix A, legacy fixtures, and broken-formula rollout gates | 10k-15k |
| 6 | Full regression, browser matrix, cleanup, documentation, commits, and deployment verification | 10k-20k |

Estimated total remaining for release-grade completion: **125k-215k tokens**. The next backend slice is approximately **10k-18k tokens**, excluding Source Acquisition runtime and complete UI.

## Resume checklist

1. Read this file completely.
2. Run `git status --short` and confirm all listed unique files are still present.
3. Confirm `git diff --cached --stat` is empty before making feature commits.
4. Do not reset, restore, clean, or stash the preserved work.
5. Re-run the relevant backend and frontend checks if the environment changed.
6. Resume with Phase 2B explicit Source/Channel currency-unit migration semantics.
7. Review the current uncommitted feature set before committing; do not mix unrelated legacy test behavior changes into the Pricing Matrix commit.
