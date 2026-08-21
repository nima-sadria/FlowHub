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

### OD-005: Unified Apply confirmation and operation evidence

The unified UI currently saves selected Review items and immediately submits
Apply with `confirmed: true`. The reference model requires a separate user
confirmation bound to exact approved operations.

**Decision:** Approved. Build an immutable, checksummed pre-Apply operation
manifest now (tracked as the Apply Manifest feature; see
`WORKSPACE_IMPLEMENTATION_PHASES.md` Phase 3).

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
resolved. OD-004, OD-005, and OD-007 are approved; implementation of the
Apply Manifest feature (OD-005) is now in progress against the canonical
Unified Workspace surface identified under OD-004. Until OD-006 is decided:

- keep legacy permission aliases in `/api/auth/me`;
- do not remove `can_fetch`/`can_apply`/related aliases.

Regardless of OD-006's outcome, provider writes remain gated by existing
Apply safety checks; do not release, deploy, or execute provider writes
outside those checks before owner approval of the specific change.
