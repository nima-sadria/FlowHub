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

## Current Assessment

**Authorization adoption:** approved and implementable without a migration.

**Full canonical Workspace convergence:** partially implemented. The unified
engine has strong persistence and write-safety foundations, but the application
still exposes both a legacy `/workspace` workflow and the unified
`/workspace/:workspaceId` workflow. The unified frontend also submits Apply
directly from its action button without a separate manifest-bound confirmation
dialog. Resolving those boundaries changes user workflow and requires the
Owner decisions recorded in `WORKSPACE_OWNER_DECISIONS.md`.
