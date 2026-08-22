# FlowHub Workspace Owner Decisions

## Approved

### OD-001: Canonical business model

**Decision:** The Workspace reference specification is the canonical target
business behavior for FlowHub.

**Implementation consequence:** Reuse FlowHub architecture and terminology,
copy verified behavior only, and preserve Source/Channel separation.

### OD-002: Canonical authorization contract

**Decision:** Granular Workspace permissions are the canonical authorization
model.

**Implementation consequence:** `/api/auth/me` exposes the canonical
capabilities. Legacy `can_*` flags remain temporary compatibility aliases.
Frontend route and action guards use the granular model.

### OD-003: Audit remediation scope

**Decision:** Small and medium fixes discovered during the Integration Audit
may be implemented and committed immediately.

**Implementation consequence:** Contract mismatches, dead controls, missing
loading/error handling, and permission presentation defects can be repaired
when they do not alter the approved architecture.

### OD-004: Canonical Workspace entry point

FlowHub currently has:

- `/workspace`, the legacy Preview/Dry Run/Approval workflow; and
- `/workspace/:workspaceId`, the immutable Snapshot/Draft/Review unified flow.

**Decision:** Unified Workspace is canonical going forward. Legacy `/workspace`
remains available and is deprecated on a timeline to be set separately; it is
not removed or redirected by this decision alone.

**Implementation consequence:** Verified during implementation that the
*reachable* Unified Workspace UI is `/products`
(`frontend/src/features/sourceWorkspace/DensePricingWorkspace.tsx`), which
already calls the Unified Workspace backend
(`POST /api/v2/unified-workspaces/{id}/apply`) — not
`/workspace/:workspaceId` (`frontend/src/pages/UnifiedWorkspace.tsx`), whose
Handsontable grid is dead code: `entryPoint` only ever resolves to `'manual'`
or `'source'`, and both values redirect to `/products` before the grid
renders. New canonical-Workspace work targets `DensePricingWorkspace.tsx`.
Full route consolidation (redirecting or removing `/workspace` and the dead
`/workspace/:id` grid) is a separate future decision, not resolved here.

**Safe interim:** Keep both routes; do not merge their business logic beyond
what an individual approved change requires.

**Update:** The frontend `/workspace` route already redirected to `/products`
(`d49d0e4`) before this update. This change goes further and removes the
now-fully-unreachable legacy surface entirely: the backend router
(`app/flowhub/api/v2/workspace.py`, mounted at `/api/v2/workspace/*`), its
service (`app/flowhub/workspace/price_workflow.py`), the dead frontend page
(`frontend/src/pages/Workspace.tsx`) and its dedicated client
(`ApiWorkspaceService`), and the now-orphaned
`IntegrationPlatformService.workspace_summary()`/`workspace_preview()`
methods the deleted router was the only caller of. `/workspace` still
redirects to `/products` for bookmarked URLs. The *other* dead surface named
above — `/workspace/:workspaceId` (`frontend/src/pages/UnifiedWorkspace.tsx`)
and its Handsontable grid — is untouched by this change and remains a
separate, not-yet-resolved cleanup.

**Superseded by OD-008 (2026-08-22):** the `/workspace` → `/products`
redirect described immediately above was itself later found to conflict
with an explicit, repeated Owner architecture rule and was reverted as
part of OD-008's Products/Workspace product split. `/products` is no
longer "the canonical Unified Workspace UI" — see OD-008 for the current,
final architecture. This entry is kept for its historical record of the
legacy `app/flowhub/api/v2/workspace.py`/`price_workflow.py` removal,
which remains correct and unaffected by OD-008.

### OD-005: Unified Apply confirmation and operation evidence

The unified UI currently saves selected Review items and immediately submits
Apply with `confirmed: true`. The reference model requires a separate user
confirmation bound to exact approved operations.

**Decision:** Approved. Build an immutable, checksummed pre-Apply operation
manifest (tracked as the Apply Manifest feature; see
`WORKSPACE_IMPLEMENTATION_PHASES.md` Phase 3).

**Status:** Implemented and verified present in current `main` (PR #12,
`5277706`).

**Required acceptance criteria:**

- Opening confirmation performs no write.
- Cancel and Escape send no Apply request.
- Confirm sends exactly once.
- Scope/checksum changes invalidate the dialog.
- The dialog shows exact selected operations and affected Channels.
- No visible-grid recomputation can add or remove operations.

**Implementation consequence:** A new persisted, immutable `ApplyManifest` /
`ApplyManifestOperation` pair is generated when a Review selection is saved,
checksummed over the actual write payload (not just which fields were
selected), returned to the frontend for display before any write, and
re-verified fresh by the server both before Apply job creation and again
immediately before dispatch. `POST /{workspace_id}/apply` requires
`manifest_id` and `expected_manifest_checksum` in addition to the existing
`expected_selection_checksum`.

### OD-008: Products/Workspace product split (final architecture)

A 2026-08-22 reconciliation review found that OD-004's "Unified Workspace
is canonical, reachable at `/products`" framing — and the subsequent
`/workspace` → `/products` redirect it led to — directly contradicted an
explicit, repeated Owner instruction: Workspace must remain a first-class,
independent product concept, and must never be reduced to `/products` or
a redirect to it.

**Decision:** `/products` and `/workspace` are two separate product
surfaces with two separate business responsibilities, not one UI reused
two ways:

- **`/products` — Manual Channel Editor.** The Owner directly edits
  supported Channel fields (Price, Stock QTY, Stock Status; Name/SKU/
  Description are not currently supported by any connector's write path,
  and are correctly not exposed rather than presented as working). No Source comparison,
  no auto-selection, no Workspace warnings/blockers, no Dry Run, no Apply
  Manifest. Still gated by full technical/security controls: auth,
  permission, connector capability, provider validation, confirmation,
  safe write, verification, audit.
- **`/workspace` — Automated Source-to-Channel Pricing Reconciliation.**
  The full canonical pipeline: Normalize → Preview → Auto-selection →
  Review → Dry Run → Verified Write Set → Apply Manifest → Apply →
  Verify → Audit/Reconcile. This is where every Workspace business rule
  (identity matching, Change Badge classification, Price/Quantity/Status
  precedence, warnings/blockers, eligibility/actionability) applies. None
  of it applies to `/products`.
- **Shared infrastructure, not shared UI or business logic**: Channel
  Listings, Channel cache/current-state data, connectors, identity
  resolution, permissions, write pipeline primitives, verification, and
  audit/reconciliation infrastructure may be reused by both surfaces.
  There is exactly one canonical Workspace business engine
  (`app/flowhub/unified_workspace/`); it is not duplicated.

**Implementation consequence:**
- Phase 1 (PR #22): `/workspace` renders a real page
  (`frontend/src/pages/Workspace.tsx`) mounting the existing canonical
  automation engine (`DensePricingWorkspace.tsx` + the
  `unified_workspace` backend) — no redirect.
- Phase 2 (PR #23): `/products` (`frontend/src/pages/Products.tsx`)
  rebuilt as the Manual Channel Editor against the pre-existing,
  previously-orphaned `ProductPricingService`/`ApiProductService`
  backend, fully detached from `unified_workspace`.
- P1-1 (PR #24): `ProductPricingService` generalized from a
  Price-only/3-hardcoded-channel service to real channel enumeration
  (via the marketplace capability registry) and Price/Stock QTY/Stock
  Status, with field/channel capability accuracy verified against each
  connector's actual write method, not assumed.
- Phase 3: the dead Handsontable `/workspace/:workspaceId` grid
  (`frontend/src/pages/UnifiedWorkspace.tsx` and its page-only supporting
  modules) removed — see `WORKSPACE_GAP_ANALYSIS.md` CLS-015/WS-001 and
  `WORKSPACE_IMPLEMENTATION_PHASES.md` Phase 3 for the disposition.

**Migration requirement:** None — this is a routing/UI-composition change
plus the additive `FLOWHUB_045` migration already covered under P1-1;
no schema change was required for the route split itself.

**Test and rollout gate:** Existing PR-level CI (`architecture-guard`,
`frontend`, `postgres-safety`) for each phase; full detail and evidence
in `docs/evidence/workspace-adoption/WORKSPACE_CANONICAL_OWNER_SPEC_2026-08-22.md`,
`WORKSPACE_RECONCILIATION_AUDIT_2026-08-22.md`, and
`WORKSPACE_CORRECTION_PLAN_2026-08-22.md`.

**Provider writes:** Unaffected — remain gated by existing Apply safety
checks in both `/products` and `/workspace`; this decision is routing/UI
architecture only, not a change to write safety.

### OD-007: Reference specification publication

The reference files were available as untracked Owner-provided documents in a
separate checkout during this audit.

**Decision:** The reference specification documents are not committed to
FlowHub. They remain Owner-controlled and outside the repository; FlowHub's
own architecture documents describe adopted behavior in FlowHub's terms.

## Decisions Required

### OD-006: Legacy permission alias retirement

**Decision needed:** Select a release for removing `can_fetch`, `can_apply`,
and other Workspace-related aliases after all consumers use canonical
permissions.

**Safe interim:** Keep aliases in `/api/auth/me` and test that their existing
values do not regress.

## Decision Log Rules

New decisions must identify:

- the affected invariant;
- API and persistence impact;
- compatibility behavior;
- migration requirement;
- test and rollout gate; and
- whether provider writes remain disabled until acceptance.

## Audit Disposition

The authorization contract and all small/medium integration findings are
resolved. OD-004, OD-005, OD-007, and OD-008 are approved. OD-004's
original "Unified Workspace canonical at `/products`" framing is
superseded by OD-008's Products/Workspace split (see OD-004's "Superseded
by OD-008" note); the Apply Manifest feature (OD-005) is unaffected by
that split and remains implemented against the one canonical Workspace
engine. The legacy `/workspace` backend/frontend surface OD-004 removed is
still correctly removed; the `/workspace/:workspaceId` dead Handsontable
grid — OD-004's other named leftover — is now also removed under OD-008
Phase 3. Until OD-006 is decided:

- keep legacy permission aliases in `/api/auth/me`;
- do not remove `can_fetch`/`can_apply`/related aliases.

Regardless of OD-006's outcome, provider writes remain gated by existing
Apply safety checks; do not release, deploy, or execute provider writes
outside those checks before owner approval of the specific change.
