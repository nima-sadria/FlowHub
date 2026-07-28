# FlowHub Workspace Adoption Assessment

## Purpose

This assessment adopts the owner-approved Workspace specification as FlowHub's
canonical business model. The reference behavior is translated into FlowHub's
existing Source, Channel, Snapshot, Draft, Review, Write Pipeline, and Audit
architecture. No WooPrice code or framework-specific implementation is copied.

## Reference Reviewed

The assessment covers all documents under `docs/reference/workspace-spec/`:

- `WORKSPACE_BUSINESS_SPEC.md`
- `WORKSPACE_STATE_MACHINE.md`
- `WORKSPACE_DATA_CONTRACTS.md`
- `WORKSPACE_DECISION_TABLES.md`
- `WORKSPACE_REFERENCE_PSEUDOCODE.md`
- `WORKSPACE_MIGRATION_GUIDE.md`
- `WORKSPACE_TEST_MATRIX.md`
- `WORKSPACE_CODE_TRACEABILITY.md`

The source documents are behavioral evidence. FlowHub terminology and stronger
existing guarantees remain authoritative where they satisfy the same safety
invariant.

## Canonical FlowHub Workflow

```text
Source or managed FlowHub Sheet
  -> one immutable source acquisition
  -> normalized Source Products and Channel Listings
  -> immutable Workspace Snapshot
  -> explicit Draft changes
  -> deterministic Review
  -> explicit selected Listing scope and checksum
  -> user confirmation
  -> durable provider-neutral write intents
  -> Write Pipeline dispatch
  -> exact verification or reconciliation required
  -> verified-only Channel Cache update
  -> append-only Audit
```

## Existing Strengths

FlowHub already implements substantial portions of the target model:

| Target behavior | Existing FlowHub mechanism | Assessment |
| --- | --- | --- |
| Read source once | Source Workspace acquisition and immutable Snapshot | Aligned |
| Stable identities | Canonical Product, Listing, Channel, row and column keys | Aligned |
| Source and Channel separation | Source Profiles and independent Channel Listings | Aligned |
| Immutable review inputs | Snapshot, Draft Revision, Review items | Aligned |
| Explicit selected scope | Review Selection plus SHA-256 checksum | Aligned |
| No optimistic success | Verified-only cache mutation | Stronger/aligned |
| Ambiguous outcome handling | `reconciliation_required` and durable attempts | Aligned |
| No blind retry | Write Pipeline reconciliation path | Aligned |
| Durable actor evidence | Provider attempts, events, and Unified Audit entries | Aligned |
| Concurrency protection | Listing guards, job ownership, idempotency keys | Aligned |
| Granular backend permissions | Workspace permission dependency and role map | Partially aligned |

## Immediate Adoption Boundary

The first adoption phase is the authorization contract. The backend already
defines canonical Workspace permissions, but `/api/auth/me` exposes only
legacy aliases and the frontend routes/actions still rely on those aliases.
This prevents the browser from representing read, create, edit, draft, review,
apply, cache-refresh, mapping, audit, and admin capabilities independently.

The approved immediate change is:

1. Expose canonical Workspace permissions in `/api/auth/me`.
2. Preserve legacy permissions as compatibility aliases.
3. Gate Workspace routes and actions with canonical permissions.
4. Keep action-level HTTP 403 responses local to the action.
5. Make read-only roles genuinely read-only in Source and Workspace surfaces.
6. Make the maintenance-aware Apply dependency enforce `apply.execute`.

## Safety Invariants

The adoption must preserve these invariants:

1. Source data provides proposed or desired values.
2. Channel state provides observed identity and current values.
3. Preview and Review do not write to providers.
4. Apply operates only on the exact persisted and checksummed selected scope.
5. UI row order, filters, formatting, or pagination cannot expand scope.
6. Provider ambiguity is never reported as success.
7. Cache changes occur only after exact provider verification.
8. A stale Review requires regeneration.
9. Reconciliation reads state and never blindly retransmits an uncertain write.
10. Every write is attributable to an authenticated actor.

## Integration Audit Coverage

The resumed audit traced each visible action through its frontend service,
HTTP method/path, backend dependency, domain service, response handling, and
loading/error state.

| Surface | Principal contract | Result |
| --- | --- | --- |
| Login and Setup | `/api/auth/*`, `/api/v2/setup/*` | Aligned; guarded forms and tested error states |
| Dashboard | dashboard, product, order, Source, activity, and diagnostics reads | Aligned; read-only navigation and partial-data behavior preserved |
| Sources | `/api/v2/source-profiles`, `/sources`, `/sheets`, `/data-quality` | Aligned after capability, read-only, creation, removal, and recovery fixes |
| Channels and Commerce | `/api/v2/commerce/*` | Aligned; admin-only configuration/actions and reader-safe list UI |
| Products | catalog Workspace, grouped grid, Draft, Review, Selection, Apply | Contract-aligned; final confirmation architecture remains OD-005 |
| Orders | list, detail, sync status, explicit WooCommerce read sync | Aligned after detail-error recovery; provider mutation remains false |
| Activity | `/api/v2/activity` plus local CSV export | Aligned after load-error recovery |
| Settings and Rate Limits | `/api/v2/settings*` | Aligned; admin route and backend dependency agree |
| Users | `/api/v2/users*` | Aligned; admin-only CRUD and validation tests |
| Diagnostics | `/api/v2/diagnostics/*` and health reads | Aligned; explicit refresh and failure presentation |
| Legacy Workspace | `/api/v2/workspace`, `/api/v2/write-pipeline` | Operational but not canonical; blocked on OD-004 |
| Unified Workspace | `/api/v2/unified-workspaces/*` | Strong persistence and reconciliation; blocked on OD-005 confirmation boundary |

No frontend control was found to call a nonexistent route. No audited Preview,
Review, diagnostic, Source-list, Product-list, or Order-list action performs a
provider write. The explicit Apply paths were inspected statically and were not
executed.

## Validation Evidence

- Frontend focused permission tests: 109 passed.
- Full frontend suite: 58 files and 416 tests passed.
- Frontend production build: passed.
- i18n validation: 2,067 messages; no missing keys, interpolation mismatches,
  unapproved hardcoded strings, or critical Persian leakage.
- `git diff --check`: passed.
- Backend tests and Python compilation could not run because this Windows
  checkout has no usable Python interpreter, Docker engine, or installed WSL
  distribution. Backend conclusions are static and test-source based.

## Current Assessment

**Authorization adoption:** complete without a migration. Canonical Workspace
permissions are exposed by `/api/auth/me`, enforced at route/action level, and
legacy aliases remain compatible.

**Integration audit:** complete for the current routes and controls. All small
and medium findings were remediated and frontend validation is green.

**Full canonical Workspace convergence:** HOLD. The application still exposes
legacy and unified Workspace workflows, and the unified Apply contract lacks a
separate exact-operation confirmation boundary. These are architecture changes
requiring OD-004 and OD-005 before implementation.
