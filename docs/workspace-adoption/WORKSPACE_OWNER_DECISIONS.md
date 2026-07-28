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

## Decisions Required

### OD-004: Canonical Workspace entry point

FlowHub currently has:

- `/workspace`, the legacy Preview/Dry Run/Approval workflow; and
- `/workspace/:workspaceId`, the immutable Snapshot/Draft/Review unified flow.

**Decision needed:** Choose the canonical navigation entry, compatibility
period, redirect behavior, and deprecation plan. This affects routes, user
education, saved links, and test ownership.

**Safe interim:** Keep both routes, apply the same capability contract, and do
not merge their business logic.

### OD-005: Unified Apply confirmation and operation evidence

The unified UI currently saves selected Review items and immediately submits
Apply with `confirmed: true`. The reference model requires a separate user
confirmation bound to exact approved operations.

**Decision needed:** Approve an API/persistence evolution that exposes an exact
pre-Apply operation manifest or formally designate immutable Review items plus
selection checksum as FlowHub's equivalent confirmation object.

**Required acceptance criteria:**

- Opening confirmation performs no write.
- Cancel and Escape send no Apply request.
- Confirm sends exactly once.
- Scope/checksum changes invalidate the dialog.
- The dialog shows exact selected operations and affected Channels.
- No visible-grid recomputation can add or remove operations.

### OD-006: Legacy permission alias retirement

**Decision needed:** Select a release for removing `can_fetch`, `can_apply`,
and other Workspace-related aliases after all consumers use canonical
permissions.

**Safe interim:** Keep aliases in `/api/auth/me` and test that their existing
values do not regress.

### OD-007: Reference specification publication

The reference files were available as untracked Owner-provided documents in a
separate checkout during this audit.

**Decision needed:** Confirm whether those source documents should be committed
to FlowHub. This audit will not copy or modify the Owner's untracked files.

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
resolved. Implementation must now stop at OD-004 and OD-005. Until those
decisions are approved:

- keep both Workspace routes;
- do not alter Apply payloads or persistence;
- do not represent the current immediate unified Apply action as canonical;
- do not merge, release, deploy, or execute provider writes from this audit.
