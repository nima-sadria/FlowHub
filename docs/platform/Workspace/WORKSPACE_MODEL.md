# Workspace Model

## Purpose

A Workspace is the controlled path from Source data to reviewed Channel
changes. It is not a spreadsheet editor, a Channel cache, or a background sync
shortcut.

## Canonical Entities

- **Workspace:** owner-scoped configuration and lifecycle root.
- **Snapshot:** immutable Source and Channel comparison input.
- **Draft Revision:** explicit user changes based on one Snapshot.
- **Review:** deterministic proposed operations and explanations.
- **Selection:** explicit approved Review item identities plus checksum.
- **Apply Job:** durable execution container for the approved selection.
- **Write Intent:** provider-neutral intended mutation.
- **Attempt:** one dispatch and its transport outcome.
- **Reconciliation:** authoritative read that resolves uncertain state.

## Lifecycle

```text
empty -> snapshot_ready -> drafting -> review_ready -> selection_ready
      -> awaiting_confirmation -> applying
      -> completed | partially_completed | reconciliation_required | failed
```

Any change to Source version, Channel snapshot, Draft revision, Review
identity, selection, scope, or checksum invalidates later approval artifacts.

## Scope Rules

- Review inclusion is derived only from the persisted Snapshot and Draft.
- Selection MUST use stable Review item or Listing identities.
- Apply MUST use persisted selection and checksum.
- Sorting, pagination, filters, localization, and visible grid rows MUST NOT
  expand or shrink Apply scope.
- An empty selection MUST never be interpreted as "all".
- A stale or invalid Review MUST require regeneration.

## Write Rules

- Review and selection persistence perform no provider write.
- Opening or cancelling confirmation performs no provider write.
- Confirm performs one Apply submission for the exact approved identity.
- Duplicate submission MUST resolve through idempotency and ownership guards.
- Verified writes update Channel cache and confirmed history.
- Failed writes remain failed with actionable evidence.
- Ambiguous writes become reconciliation-required and are not retried blindly.

## Recovery

- Cancelled read/review work is recoverable without corrupting the Snapshot.
- A failed operation does not erase successful sibling outcomes.
- Reconciliation reads Channel state and classifies confirmed, failed, or still
  uncertain without repeating the original mutation.
- Apply remains unavailable without a valid approved selection.

## Current Compatibility Boundary

FlowHub currently exposes legacy `/workspace` and unified
`/workspace/:workspaceId` flows. Route convergence and the final exact-operation
confirmation object require Owner decisions OD-004 and OD-005.

