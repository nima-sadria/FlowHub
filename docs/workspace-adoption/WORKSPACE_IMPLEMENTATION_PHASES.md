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

**Status:** Apply Manifest feature complete (PR #12, `5277706`); Phase B
badge-completeness and legacy-route removal complete (see below). OD-004,
OD-005, and OD-008 are approved and implemented. OD-008's Products/Workspace
product split (2026-08-22) resolves the dead Handsontable grid this
section previously listed as open.

**Apply Manifest feature** — an immutable, checksummed
`ApplyManifest`/`ApplyManifestOperation` pair generated when a Review
selection is saved, displayed in the existing confirmation dialog before any
write, and re-verified fresh by the server before Apply job creation and
again immediately before dispatch. Closed WS-002 and WS-003 (confirmed
still present and enforced in current `main`: `apply_selected` requires
`manifest_id`/`expected_manifest_checksum`, loads the persisted manifest
rows, and re-verifies the checksum before any write).

**Phase B business classification correctness pass** — an Owner-reference-
specification review of the Price/Quantity/Stock Status/Warning/Eligibility
classification engine (shipped in `feat/workspace-phase-b-completion`)
found and fixed three P0 defects (canonical availability precedence,
identifier-zero truthiness loss, an unmapped-Price crash), a fourth P0
(a missing currency precision contract that unconditionally blocked Price
classification for every non-RIAL/TOMAN currency), and closed the P1
badge-completeness gaps (percentage delta, neutral badge states, badge
staleness, Review-dialog classification DTO, per-warning-code localization,
grid input grouping). See `WORKSPACE_GAP_ANALYSIS.md` CLS-001 through
CLS-015 for the full disposition; CLS-006 (a backend `eligible`/`actionable`
split) and CLS-013 (full float-to-Decimal migration through the write-pipeline
wire boundary) remain deliberately deferred as higher-risk, separately-scoped
follow-ups.

**Legacy `/workspace` removal** — WS-001/CLS-015 fully resolved: the legacy
backend router (`app/flowhub/api/v2/workspace.py`), its service
(`price_workflow.py`), the dead frontend page and its dedicated client
service, and the now-orphaned `IntegrationPlatformService` summary/preview
methods are deleted (`d49d0e4`/`e16e7e9`). `/workspace` no longer redirects
to `/products` — see the Products/Workspace product split below (OD-008),
which superseded that redirect.

**Products/Workspace product split (OD-008, 2026-08-22)** — a
reconciliation review found the `/workspace` → `/products` redirect above
directly contradicted an explicit, repeated Owner architecture rule:
Workspace must remain a first-class, independent product, never reduced
to `/products` or a redirect to it. Resolved by making `/products` and
`/workspace` two genuinely separate surfaces — `/products` the Manual
Channel Editor (no Workspace automation), `/workspace` the automated
Source-to-Channel reconciliation engine (the full canonical pipeline) —
sharing only low-level infrastructure, never business logic. Delivered in
four steps: Phase 1 gave `/workspace` its own real page mounting the
existing automation engine (PR #22); Phase 2 rebuilt `/products` against
the pre-existing, previously-orphaned `ProductPricingService` backend,
fully detached from `unified_workspace` (PR #23); a P1 item generalized
that backend from Price-only/3-hardcoded-channels to real channel
enumeration and Price/Stock QTY/Stock Status (PR #24); Phase 3 removed
the dead Handsontable `/workspace/:workspaceId` grid
(`frontend/src/pages/UnifiedWorkspace.tsx` and its page-only supporting
modules — `gridModel`, `handsontableIdentity`, `handsontableLicense`,
`statusDisplay`, `useUnifiedWorkspaceController`), the *other* dead
surface OD-004 had left open. `/workspace/:workspaceId` now redirects to
`/workspace?workspace=:id` for bookmarked links, resolved by the real
page's own resume mechanism. Full detail:
`docs/workspace-adoption/WORKSPACE_OWNER_DECISIONS.md` OD-008,
`WORKSPACE_CANONICAL_OWNER_SPEC_2026-08-22.md`,
`WORKSPACE_RECONCILIATION_AUDIT_2026-08-22.md`, and
`WORKSPACE_CORRECTION_PLAN_2026-08-22.md`.

Remaining potential work after this item:

- Align stale, cancelled, blocked, partial, and reconciliation state naming
  across entry points (WS-004).
- The deferred Phase B badge-completeness gaps above (CLS-006 through
  CLS-013).
- Orphaned `unifiedWorkspace.*`-prefixed i18n keys (translation copy for
  the now-deleted Handsontable grid) were left in place — the i18n
  validator does not flag unused keys, and pruning them individually was
  judged lower-value than the architecture work itself; noted here rather
  than silently left undocumented.

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
