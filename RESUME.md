# FlowHub RC1 release handover

## RC1 status -- 2026-08-06

This section supersedes the older continuation notes below. The older material
is retained as implementation history, not as the current release state.

### Candidate

- Candidate branch: `main`
- Candidate before this documentation update: `e39ce0fed8e0bcceee251e2b8d1ab1839a4a6ae9`
- Merge baseline: `f17c7768585c7071a16c7ef3722943d50ec6c473`
- Rollback reference: `df928cc7a3cff50b0055bcf7cb94117034ff8986` (`origin/main`)
- Push/deployment status: neither has been performed.

### Verified evidence

- Backend at the Stage 10B baseline: `3201 passed, 26 skipped, 0 failed`.
- Migration suite: `34 passed, 7 skipped`; the linear head is
  `FLOWHUB_027` (`022 -> 023 -> 024 -> 025 -> 026 -> 027`).
- Frontend after the RC1 i18n correction: `74` files and `590` tests passed;
  TypeScript and production build passed.
- i18n validation: `2429` messages, with `0` missing keys, `0` placeholder
  mismatches, `0` unapproved hardcoded strings, and `0` critical Persian
  leakage values.
- Final targeted release guards, Pricing Matrix backend, and Source
  Acquisition integration: `58 passed`.

### Browser evidence

Claude UI Stage 6 performed authenticated Pricing Matrix browser verification
on frontend commit `21664cb8b7ccb72c39685097d8a0ebab2af80b0a` and backend
commit `f86f07d`. The later integration commits did not change the callable
Pricing contract. A direct Stage 10C browser run against the final merged
build could not be completed because the isolated Codex browser could not
connect to the locally started Vite server (`ERR_CONNECTION_REFUSED`), despite
the frontend production build succeeding. Treat a fresh authenticated browser
sanity run on the deployment-equivalent environment as a release gate before
public deployment.

### Release gates

| Item | Classification | Required resolution |
|---|---|---|
| PostgreSQL migration/persistence verification | **BLOCKING RELEASE** | FlowHub documentation identifies PostgreSQL as canonical production persistence. Configure an isolated `FLOWHUB_TEST_POSTGRES_URL` and run PostgreSQL migration plus targeted persistence tests. |
| Final authenticated browser sanity on final merged build | **BLOCKING RELEASE** | Verify Pricing routes, EN/FA, RTL/LTR, light/dark, and a mobile viewport against the final merged commits. |
| Fresh remote verification | **PUSH PREREQUISITE** | The final `git fetch origin --prune` could not reach GitHub. Restore network access and fetch successfully before push so `origin/main` is not ahead. |
| Private Nextcloud network | **DEPLOYMENT PREREQUISITE** | Keep `SourceHttpPolicy.allowed_private_networks` fail-closed in source. The current runtime constructs the default policy and has no deployment configuration binding for a CIDR, so private Nextcloud cannot be enabled by environment configuration yet. Before such deployment, add and verify an approved deployment-owned injection path; credentials and network ranges must never be committed. |
| Pricing formula migration activation | **BLOCKING FEATURE ACTIVATION** | Complete Appendix A from the real translator inventory, add fixtures for every supported formula shape, and resolve or explicitly quarantine the 255 broken formulas. Automatic conversion/activation remains disabled. |
| Root `node_modules/` | **NON-BLOCKING LOCAL ARTIFACT** | It is an untracked Vite cache from an incorrect root `npx` invocation, contains no tracked source, and is reproducible. Removal was blocked by the local execution policy; it must remain unstaged and must not be pushed. |

### RC1 verdict and next action

**NOT READY.** Do not push or deploy this candidate until the two blocking
release gates above have evidence. Once they pass, confirm `git status` still
contains only the disposable root `node_modules/` cache, then push `main` and
deploy from the resulting `origin/main` commit. Rebuild/restart any review
service after that push and verify its revision before sharing a live URL.

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

Phase 3B is complete. `FLOWHUB_026` adds immutable, provider-neutral Source
Observations that are permanently linked to exactly one successful Acquisition
Run. Each Observation has a deterministic per-Source/per-scope version, resource
identity and checksum, observed timestamp, bounded non-secret provenance, an
append-only checksum-linked Evidence chain, and append-only generic Snapshot
References. Replaying identical persistence for the same Run is idempotent;
divergent replay conflicts. A retry never changes prior records and may create
only a new Observation for its new successful Run. No provider execution,
resource binding, parsing, schema assessment, Diagnostics, scheduler, API, or UI
was added.

Exact next task: Phase 3C - implement Source schema assessment and structural
drift handling over persisted Observations. Do not add provider execution,
resource binding runtime, SSRF protection, scheduling, UI, or browser work in
that phase.

## Stage 9 completed: acquisition execution integration

Stage 9 adds one authoritative `SourceAcquisitionExecutor` that claims a
durable Run before provider execution, sends Nextcloud/WebDAV reads only through
`SourceHttpClient`, validates the captured workbook before persistence, and
atomically commits the immutable Observation/evidence graph with the terminal
successful Run transition. Security, timeout, cancellation, ownership, and
provider failures retain stable codes and create no Observation.

The existing spreadsheet read path now consumes the executor's validated
in-memory capture and updates the legacy `dl_source_snapshots` projection without
performing a second download. Exact retained intent replays the authoritative
Run; retries remain linked Runs and create separate Observations. Identical
capture/parse contracts reuse the previous Observation with `not_modified`,
while an identical capture under a changed parse contract creates a new
Observation with `content_unchanged_reparse`.

Schema assessment is invoked after the Observation transaction commits. It is
therefore unable to corrupt the authoritative Run/Observation pair; when no
Mapping exists it records `no_mapping`, and missing schema evidence remains a
distinct failed assessment rather than fabricated health. No callable API,
scheduler, Source UI, migration, or provider type was added in Stage 9.

Operational follow-up for Stage 10: production deployments that intentionally
use private-address Source targets must supply the deployment-owned
`SourceHttpPolicy.allowed_private_networks`; the default remains fail-closed.
PostgreSQL execution was not claimed because no disposable
`FLOWHUB_TEST_POSTGRES_URL` was configured for this stage.

## Stage 10A.1 completed: release test infrastructure and fixture alignment

`requirements-test.txt` is the authoritative test dependency manifest and
already declares `pytest-asyncio>=0.23.0`; the failure was a local environment
that had not been installed from that manifest, not a missing production or
test dependency declaration. `uv pip install -r requirements-test.txt` restores
the complete test environment and async collection succeeds without temporary
pytest dependency injection.

Legacy beta Source and Workspace fixtures now provide workbook responses through
the current `SourceHttpClient` boundary. The shared `tests/beta_source_http.py`
helper converts their synthetic logical WebDAV download fixtures into bounded,
network-free `SourceHttpResponse` values; no retired direct Nextcloud download
path is restored. The upstream-error fixture now asserts the Stage 9 stable
gateway contract (`502` / `upstream_rejected`) and continues to prove that raw
HTML and secrets never reach the response.

The historical beta_007 migration fixture now excludes `saq_` Source
Acquisition tables, preventing current ORM metadata from pre-creating the
`FLOWHUB_025` migration target. It still upgrades through the complete chain
and retains its data-loss assertions.

Verification for this stage:

- Source/Workspace fixture and historical compatibility test: 129 passed.
- Full migration suite: 34 passed, 7 skipped.
- Source/Workspace/Acquisition/connector/no-direct-HTTP regression selection:
  198 passed, 6 skipped.
- Full backend suite after Stage 10A.2: 3201 passed, 26 skipped, 0 failures.

The multi-channel outcome mismatch was resolved in Stage 10A.2 by correcting
the fixture so it reaches the intended provider results and proves their
durable attempt evidence.

## Stage 7 completed: schema assessment and structural drift

Stage 7 adds `FLOWHUB_027`, the provider-neutral
`SourceSchemaAssessmentService`, immutable Mapping schema expectations,
immutable Assessments, structural Diff records, machine-readable Diagnostics,
focused tests, and `SOURCE_SCHEMA_ASSESSMENT_CONTRACT.md`. It adds no API,
provider execution, UI, scheduler, or drift-acceptance path.

Schema comparison preserves raw headers and compares a deterministic
`header-canonical-v1` representation: NFKC, Arabic Yeh/Kaf normalization,
bidi-control removal, and whitespace/ZWNJ removal. Assessment execution status
and freshness are independent. Freshness is a read-time projection and becomes
stale when a newer scoped Observation, Mapping revision, or algorithm exists.

The local build environment was repaired without changing dependency policy:
`pyproject.toml` now uses the valid `setuptools.build_meta` backend and
explicitly discovers only `app*` and `cli*` packages. The prior
`setuptools.backends.legacy:build` value was the verified cause of
`ModuleNotFoundError: setuptools.backends`; the isolated uv build reproduced it
before the repair. `uv sync`, an isolated wheel build, project import, Python,
pytest, and the focused Stage 7 suite now pass.

Focused verification completed:

```text
tests/flowhub/source_acquisition/test_schema_assessment.py
tests/flowhub/source_acquisition/test_observations.py
tests/flowhub/source_acquisition/test_run_service.py
tests/flowhub/migration/test_source_schema_assessments_027.py
tests/flowhub/migration/test_source_observations_026.py
```

The Stage 7 files are:

- `alembic_flowhub/versions/flowhub_027_source_schema_assessments.py`
- `app/flowhub/source_acquisition/models.py`
- `app/flowhub/source_acquisition/schema_assessment.py`
- `app/flowhub/source_acquisition/__init__.py`
- `docs/architecture/SOURCE_SCHEMA_ASSESSMENT_CONTRACT.md`
- `tests/flowhub/source_acquisition/test_schema_assessment.py`
- `tests/flowhub/migration/test_source_schema_assessments_027.py`

PostgreSQL execution remains pending unless `FLOWHUB_TEST_POSTGRES_URL` is
actually configured.

## Stage 8 completed: Source acquisition network-security boundary

`app.connectors.common.source_http` is the provider-neutral, injectable
egress boundary for future Source acquisition stages. It accepts HTTPS by
default; HTTP requires an explicit deployment-owned host allow-list. URL
userinfo and unsupported schemes are rejected. Literal IPs and every DNS
answer are validated fail-closed, including loopback, private networks unless
explicitly allow-listed, link-local, multicast, unspecified, reserved, CGNAT,
and IPv4-mapped IPv6 destinations.

The boundary resolves once before each request, sends to the validated address
while retaining Host/SNI, disables automatic redirects, revalidates every
redirect, strips Authorization and Cookie across origins, and bounds redirects,
headers, decoded response bytes, and total/connect/read time. Errors are stable
codes only and `redact_url` masks secret-bearing query values and URL userinfo.

This phase intentionally does not attach the boundary to a provider Run or the
legacy Nextcloud connector: provider execution and Source stage wiring belong
to Stage 9. Therefore Stage 8 proves that unsafe requests are blocked before
the boundary sends them, but it does not yet create Run failure/Observation
integration records. Do not claim runtime provider acquisition is hardened
until Stage 9 wires every Source adapter through this boundary.

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
7. The full backend suite previously had one multi-channel pricing fixture failure: a validation failure was projected as `reconciliation_required` while the test expected `failed`.

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

`alembic_flowhub/versions/flowhub_026_source_observations.py` is a linear,
forward-only migration from `FLOWHUB_025`. It creates the immutable Observation,
Evidence, Snapshot Reference, and per-Source/per-scope Observation-version head
tables. SQLite coverage verifies clean installation, `FLOWHUB_025 ->
FLOWHUB_026` preservation, model parity, append-only application behavior, retry
lineage, and non-destructive downgrade refusal. PostgreSQL migration execution
remains pending until `FLOWHUB_TEST_POSTGRES_URL` is configured.

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

1. Execute the PostgreSQL `FLOWHUB_024` clean-install test when the disposable
   `FLOWHUB_TEST_POSTGRES_URL` is available.
2. Write Pipeline fold/projection tests for all documented terminal states.
3. Explicit Source/Channel unit migration and unresolved-unit tests.
4. Frontend tests for all new Pricing UI states after that UI exists.
5. i18n validation after the two pre-existing hardcoded strings are addressed in a separate scoped change.
6. Implement Source Acquisition Phase 3C schema assessment and structural drift handling.

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
| 3B | Immutable Source Observations, evidence, and provenance | completed |
| 3C | Schema assessment, structural drift, mapping invalidation, and Diagnostics | 10k-18k |
| 3D-3E | Acquisition security and Source integration | 18k-30k |
| 4 | Implement Pricing/Source UI contract in EN/FA, RTL/LTR, light/dark, responsive layouts | 35k-60k |
| 5 | Translator inventory, Appendix A, legacy fixtures, and broken-formula rollout gates | 10k-15k |
| 6 | Full regression, browser matrix, cleanup, documentation, commits, and deployment verification | 10k-20k |

Estimated total remaining for release-grade completion: **115k-197k tokens**. The next backend slice is approximately **10k-18k tokens**, excluding provider execution and complete UI.

## Resume checklist

1. Read this file completely.
2. Run `git status --short` and confirm all listed unique files are still present.
3. Confirm `git diff --cached --stat` is empty before making feature commits.
4. Do not reset, restore, clean, or stash the preserved work.
5. Re-run the relevant backend and frontend checks if the environment changed.
6. Resume with Phase 3C schema assessment and structural drift handling over persisted Observations.
7. Review the current uncommitted feature set before committing; do not mix unrelated legacy test behavior changes into the Pricing Matrix commit.

## Backend Stage 10A.2 outcome semantics

The remaining multi-channel mismatch was a fixture defect, not a production
projection defect. The fixture marked SnappShop writable but omitted the three
configured-setting records required by the authoritative Commerce gate. As a
result, the synthetic provider validation rejection was never reached and the
post-intent local gate exception was conservatively classified as
`reconciliation_required`.

The corrected fixture now reaches both providers and asserts durable evidence:

- SnappShop returns a deterministic validation rejection, records `failed`, and
  never records `reconciliation_required`.
- TapsiShop accepts the write without exact read-back, records
  `provider_accepted` plus `reconciliation_required`.
- The aggregate remains `reconciliation_required` because one external final
  state is genuinely unknown.

No callable API, enum, production projection, or frontend contract changed.
PostgreSQL verification remains pending until an isolated
`FLOWHUB_TEST_POSTGRES_URL` is configured.
