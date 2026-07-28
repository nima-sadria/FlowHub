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

**Status:** Approved for implementation.

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

**Status:** Starts after Phase 1 passes.

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

## Phase 3: Canonical Workspace UX

**Status:** Blocked on OD-004 and OD-005.

Potential work after approval:

- Establish one canonical Workspace entry point.
- Add exact operation evidence before Apply.
- Add an accessible, invalidation-aware confirmation.
- Align stale, cancelled, blocked, partial, and reconciliation states.
- Preserve Source and Channel identity boundaries.

Safety gate:

- No Apply behavior changes until exact-scope and confirmation tests pass.

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
