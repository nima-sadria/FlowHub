# FlowHub Workspace Implementation Phases

## Phase 0: Baseline and Traceability

**Status:** Complete for adoption start.

Work:

- Verify clean implementation checkout and base commit.
- Read the complete Owner-provided reference specification.
- Map reference concepts to Source Workspace, Unified Workspace, Write
  Pipeline, Channel Cache, and Audit.
- Record pre-existing validation failures separately.

Exit criteria:

- Adoption documents exist.
- No Production access or provider write is performed.

## Phase 1: Authorization Contract

**Status:** Complete in `557e221`.

Work:

- Add canonical Workspace permissions to `/api/auth/me`.
- Preserve legacy permission aliases.
- Use canonical permission constants in frontend guards.
- Gate Source create/import, configuration edit, Sheet edit, Review, and Apply
  actions independently.
- Keep ordinary HTTP 403 responses local to the action.
- Make the maintenance-aware write dependency enforce `apply.execute`.

Validation:

- Backend role/permission contract tests.
- Frontend route guard and read-only component tests.
- Focused Source, Sheet, and Unified Workspace tests.
- Frontend build and i18n validation.

Commit boundary:

- One documentation commit.
- One backend/frontend authorization contract commit, or smaller commits if
  validation isolates concerns.

## Phase 2: Integration Audit Resume

**Status:** Complete for current routes and controls.

Audit each page:

| Page | Required audit |
| --- | --- |
| Dashboard | Reads, loading, empty/error state, navigation |
| Sources | list/create/read/edit/archive/import, permissions, validation |
| Channels | list/configure/test/cache refresh, permissions, provider status |
| Products | list/detail/price review/dry run/apply, exact contracts |
| Orders | list/detail/sync actions, role checks, errors |
| Settings | read/update credentials/config, secret handling, admin gates |
| Workspace | Preview/Draft/Review/selection/Apply/reconcile lifecycle |

For every action, trace:

```text
visible control
  -> event handler
  -> frontend service method
  -> HTTP method/path/body
  -> backend request model/dependency
  -> domain service/repository
  -> response model
  -> frontend success/error/loading state
```

Small and medium fixes are committed by coherent page or contract boundary.
Architecture changes are added to `WORKSPACE_OWNER_DECISIONS.md` and stop that
specific implementation path.

Completed remediation:

- `acaff4d`: Channels authorization/recovery/localization, Source creation
  feedback, and Order-detail recovery.
- `b0615d8`: Activity history load recovery.
- `2e836ef`: Source-list total-failure recovery.

Validation:

- 58 frontend files and 419 tests passed.
- Frontend production build and i18n validation passed.
- The full backend suite passed with only environment-dependent skips.
- Focused auth, activity, Sources, Sheets, logging, and installer suites passed.

## Phase 3: Canonical Workspace UX

**Status:** In progress. OD-004 and OD-005 are approved (Unified Workspace,
reachable at `/products` via `DensePricingWorkspace.tsx`, is canonical; a
real pre-Apply operation manifest is being built).

Current work item: **Apply Manifest feature** — an immutable, checksummed
`ApplyManifest`/`ApplyManifestOperation` pair generated when a Review
selection is saved, displayed in the existing confirmation dialog before any
write, and re-verified fresh by the server before Apply job creation and
again immediately before dispatch. Closes WS-002 and WS-003.

**Phase B business classification correctness pass** — an Owner-reference-
specification review of the Price/Quantity/Stock Status/Warning/Eligibility
classification engine (shipped in `feat/workspace-phase-b-completion`)
found and fixed three P0 defects (canonical availability precedence,
identifier-zero truthiness loss, an unmapped-Price crash) and two P1
defects (an all-unchanged Review incorrectly reporting `blocked`; the Review
dialog showing unchanged fields as `Blocked`). See `WORKSPACE_GAP_ANALYSIS.md`
CLS-001 through CLS-015 for the full disposition, including deferred P1/P2
badge-completeness gaps (percentage delta, badge staleness, Review-dialog
classification DTO) that are real but out of this pass's scope.

Remaining potential work after this item:

- Frontend route consolidation for WS-001 is done (`/workspace` redirects to
  `/products`, `d49d0e4`); the legacy backend route
  (`POST /api/v2/workspace/preview`) and dead `frontend/src/pages/Workspace.tsx`
  page/translations/tests are still mounted/present (CLS-015) and still need
  removal on the deprecation timeline OD-004 leaves open.
- Align stale, cancelled, blocked, partial, and reconciliation state naming
  across entry points (WS-004).
- The deferred Phase B badge-completeness gaps above (CLS-006 through
  CLS-013).

Safety gate:

- No Apply behavior changes ship until exact-scope and confirmation tests
  pass.

## Phase 4: Contract Convergence

**Status:** Planned.

Work:

- Retire legacy permission aliases after consumer migration.
- Publish a versioned Workspace frontend contract.
- Add cross-route contract tests for permission and error envelopes.
- Confirm all Preview/Review paths expose explainable source accounting.

## Phase 5: Release Readiness

**Status:** Out of scope for this audit.

Required later:

- All P0 Workspace tests pass.
- No provider writes occur in Preview or Review.
- Apply uses only persisted selected scope.
- Ambiguous outcomes require reconciliation.
- Build, i18n, backend, frontend, and disposable integration tests pass.
- Owner approves merge/release/deployment separately.

This audit does not merge, release, deploy, or access Production.
