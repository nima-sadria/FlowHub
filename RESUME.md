# FlowHub continuation handover

## Read this first

This repository contains substantial **unfinished, unique, uncommitted work** for the Source Architecture and Pricing Matrix initiatives. Do not reset, restore, stash, clean, checkout over, or delete the listed files. The worktree was intentionally preserved for the next Codex session.

Implementation was stopped on 2026-08-05 at the Owner's request. This document is the only stabilization artifact intended to be committed. No feature code is included in the handover commit.

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
- The interrupted `apply_patch` for Workspace pricing bindings was atomic and did not modify `app/flowhub/pricing_matrix/service.py`. Methods named `bind_workspace_channels`, `verify_workspace_channels`, and `workspace_bindings` are still absent.
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

## Exact point where implementation stopped

The next task was **Workspace and Write Pipeline integration for Pricing Matrix bindings**. An attempted patch was interrupted before application, so none of the following methods exist yet.

Resume in this exact order:

1. Add service methods in `app/flowhub/pricing_matrix/service.py` to create, list, and verify Workspace pricing bindings. Suggested responsibilities are `bind_workspace_channels`, `workspace_bindings`, and `verify_workspace_channels`; names may be adjusted to existing conventions, but behavior must follow the ADR.
2. Integrate binding creation into `UnifiedWorkspaceService.generate_review` only for channels whose review includes price changes.
3. Pin at least the pricing policy activation, channel configuration revision, policy revision, and `workspace_pricing_evaluated_at` required by the accepted contracts.
4. Include the binding identity in the review/checksum contract so a review cannot silently change under the same decision.
5. Revalidate bindings before Apply job creation and again after the existing listing lock is acquired, immediately before execution.
6. Keep all writes inside the existing `WritePipelineService`. Do not create a Pricing Matrix write path in parallel.
7. Add focused tests for stale activation, stale channel configuration, missing activation, per-channel blocking, and the race between review and Apply.

Do not resume with UI work or Source Acquisition runtime work before this binding boundary is correct and tested.

## Temporary TODOs

There are no temporary `TODO`/`FIXME` comments in code. The unfinished boundary is represented by the absent Workspace binding service methods and the phases below, rather than placeholder code.

## Remaining blockers

1. Workspace decisions are not yet bound to and revalidated against Pricing Matrix activation/configuration state.
2. `FLOWHUB_024` has not been applied, downgraded, or tested against a disposable database.
3. Full backend test suite has not been run after these changes.
4. Pricing Matrix service/API/migration integration tests are incomplete; only the arithmetic/evaluator/guard/unit core is directly tested.
5. Browser verification has not been performed.
6. The new Pricing UI described by `PRICING_UI_CONTRACT.md` has not been implemented.
7. Source Acquisition runtime described by `SOURCE_ACQUISITION_DESIGN.md` has not been implemented.
8. The i18n validator exits nonzero because of two pre-existing hardcoded strings:
   - `frontend/src/components/SiteFooter.tsx`: `FlowHub v`
   - `frontend/src/pages/ExchangeRates.tsx`: `/ day ·`
9. Migration rollout gates remain: complete Appendix A from the real translator inventory, add a fixture for every supported legacy formula shape, and resolve or explicitly quarantine the documented 255 broken formulas before activation.

## Required migrations

`alembic_flowhub/versions/flowhub_024_pricing_matrix.py` is a draft linear migration from `FLOWHUB_023`. It creates:

- `pm_policy_revisions`
- `pm_product_group_revisions`
- `pm_product_group_members`
- `pm_rule_entries`
- `pm_channel_config_revisions`
- `pm_policy_lifecycle_events`
- `pm_channel_policy_heads`
- `pm_workspace_bindings`
- `pm_attention_signals`

Before any commit or deployment of the feature:

1. Compare every table, column, constraint, and index against `app/flowhub/pricing_matrix/models.py`.
2. Test upgrade from a real `FLOWHUB_023` schema.
3. Verify the channel-head seed statement is deterministic and idempotent for the supported database engines.
4. Test downgrade on a disposable database.
5. Define and test migration handling for existing Sources and Channels whose units are unresolved. Never infer RIAL/TOMAN from price magnitude.
6. Confirm unresolved units permit only the raw/unit-resolution views allowed by the design and block Pricing Preview, Dry Run, and Apply.

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

Known test noise: the frontend suite emitted jsdom/Handsontable CSS parse warnings, and backend tests emitted existing FastAPI/Starlette/SQLite/Alembic deprecation warnings. These did not fail the suites.

## Required tests still pending

1. Full backend test suite.
2. Pricing Matrix API authorization, validation, lifecycle, concurrency/CAS, and persistence tests.
3. Alembic `FLOWHUB_023 -> FLOWHUB_024 -> FLOWHUB_023` migration test.
4. Workspace binding and stale-decision tests at Review, Dry Run, and Apply boundaries.
5. Write Pipeline fold/projection tests for `pending`, `running`, `applied`, `partially_applied`, `blocked`, `no_changes`, `failed`, and `reconciliation_required`.
6. Explicit Source/Channel unit migration and unresolved-unit tests.
7. Frontend tests for all new Pricing UI states after that UI exists.
8. i18n validation after the two pre-existing hardcoded strings are addressed in a separate scoped change.

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
| 1 | Complete Workspace/Write Pipeline binding, revalidation, and race-safe tests | 25k-40k |
| 2 | Finish Pricing Matrix service/API/lifecycle/concurrency and migration tests | 25k-40k |
| 3 | Implement Source Acquisition runs, observations, resource bindings, schema assessment, diagnostics, telemetry, SSRF controls, and retention holds | 45k-75k |
| 4 | Implement Pricing/Source UI contract in EN/FA, RTL/LTR, light/dark, responsive layouts | 35k-60k |
| 5 | Translator inventory, Appendix A, legacy fixtures, and broken-formula rollout gates | 10k-15k |
| 6 | Full regression, browser matrix, cleanup, documentation, commits, and deployment verification | 10k-20k |

Estimated total remaining for release-grade completion: **150k-250k tokens**. A backend-first usable slice through phases 1-2 is approximately **50k-80k tokens**, excluding full Source Acquisition runtime and complete UI.

## Resume checklist

1. Read this file completely.
2. Run `git status --short` and confirm all listed unique files are still present.
3. Confirm `git diff --cached --stat` is empty before making feature commits.
4. Do not reset, restore, clean, or stash the preserved work.
5. Re-run the relevant backend and frontend checks if the environment changed.
6. Resume exactly at Workspace Pricing Matrix binding and Write Pipeline revalidation.
7. Make feature commits only after the full migration and integration boundary is tested; do not mix this handover commit with feature work.
