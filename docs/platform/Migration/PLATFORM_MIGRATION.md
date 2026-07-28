# Platform Migration

## Adoption Order

1. Establish canonical contracts and named capabilities.
2. Preserve current API compatibility while migrating consumers.
3. Separate Source, Channel, Snapshot, and Workspace identities.
4. Make Review and selected scope immutable and checksummed.
5. Route writes through durable intent, attempt, verification, and
   reconciliation records.
6. Align health, diagnostics, audit, metrics, and analytics projections.
7. Retire compatibility aliases only after measured consumer migration.

## Compatibility Rules

- No destructive schema or route change without an Owner decision.
- Existing saved links and clients receive a documented compatibility period.
- Backfills are deterministic, restartable, and auditable.
- Migrations MUST NOT infer confirmed provider success from an old attempted
  request.
- Legacy unknown states remain unknown until authoritative evidence exists.

## Current Phases

- Authorization contract: complete.
- Page integration audit and minor recovery fixes: complete.
- Canonical Workspace route: blocked on OD-004.
- Exact-operation confirmation boundary: blocked on OD-005.
- Legacy permission alias retirement: blocked on OD-006.
- Operational retention and report/alert persistence: pending Owner decisions.

## Release Gate

No convergence release proceeds until compatibility, rollback, data migration,
backend/frontend tests, and provider-write safety tests are approved. This
adoption work does not merge, release, deploy, or access Production.

