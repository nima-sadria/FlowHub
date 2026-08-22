# ADR-SOURCE-001-A3: Explicit Archive, Permanent Delete, and Workspace Binding

**Status:** Accepted
**Date:** 2026-08-20
**Decider:** FlowHub Owner
**Amends:** `ADR_SOURCE_ARCHITECTURE_V2.md`
**Related:** `SOURCE_ACQUISITION_DESIGN.md`, `ADR_SOURCE_PRODUCT_IDENTITY_AUTHORITY_ADDENDUM.md`, `UNIFIED_MULTI_CHANNEL_WORKSPACE.md`

## Context

The Source lifecycle previously exposed one `DELETE` request whose outcome
depended on whether protected history existed. The UI could therefore present
Delete while the server archived the Source. The legacy Workspace Preview also
used the singleton connector identity `nextcloud:primary`; when that identity
belonged to an archived profile, Preview resolved the wrong Source profile.

Source acquisition runs, observations, identity evidence, schema assessments,
and Workspace snapshots are append-only or immutable and use restrictive
foreign keys. A history-bearing Source cannot be physically removed without
either corrupting those guarantees or rewriting immutable evidence.

## Decision

1. `POST /api/v2/sources/{id}/archive` is the only Archive operation. Archive
   preserves history, disables operational work, and remains visible as a
   read-only historical Source.
2. `DELETE /api/v2/sources/{id}` is permanent deletion only. It requires the
   expected Source version, exact Source-name confirmation, an explicit
   permanent-delete acknowledgement, and acknowledgement of the history
   policy. It never changes the Source to `archived`.
3. A Source without Source-owned history is physically removed after its
   operational children and connector configuration are explicitly deleted in
   one transaction. A Source with immutable history is changed to the
   terminal non-operational `deleted` tombstone state, its connector identity
   and operational projections are removed, and immutable evidence remains
   anchored by restrictive foreign keys. `deleted` rows are excluded from
   Source UI, Diagnostics, active denominators, processing, and Workspace
   resolution; they are not an Archived Source.
4. Active acquisition runs and active Workspace bindings block permanent
   deletion. The Owner must finish, archive, or explicitly rebind the active
   Workspace first. Historical snapshots retain provenance and are not used as
   operational bindings.
5. New source-centric Workspaces persist one explicit mutable
   `uw_workspace_source_bindings` row. Resolver code may select only an active
   Source from that binding. No resolver selects a replacement merely because
   its provider type matches. The legacy Nextcloud Preview path accepts an
   explicit Source binding and otherwise fails with an actionable rebind
   reason whenever Source registry rows exist.

## Dependency policy

Operational connector settings, secret references, connector health/diagnostic
projections, caches, read leases/reservations, refresh projections, and
ephemeral Preview rows are safe to delete with the Source. Acquisition runs,
observations, observation datasets, identity assessments and bindings,
mapping/schema evidence, Workspace snapshots, business events, currency
history, and audit evidence are retained when their immutability or history
contract requires them. The deletion audit event is a detached immutable fact
of the destructive operation.

The service deletes children by named dependency class inside the Source row
lock and transaction. It does not rely on broad database cascades. Any failure
rolls back the connector/configuration changes, tombstone transition, and
audit append together.

## Consequences

Owners can distinguish reversible historical retirement from irreversible
operational deletion. A history-bearing deletion leaves no usable Source and
cannot be selected by a new Workspace, while immutable evidence remains
referentially valid. Physical deletion is available for genuinely unused
Sources. Existing archived Sources remain visible and read-only until the
Owner explicitly chooses permanent deletion.

## References

- `app/flowhub/source_workspace/service.py`
- `app/flowhub/workspace/price_workflow.py`
- `alembic_flowhub/versions/flowhub_041_source_delete_bindings.py`
- `tests/flowhub/source_workspace/test_source_lifecycle.py`
- `tests/flowhub/source_workspace/test_source_lifecycle_postgres.py`
