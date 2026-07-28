# Platform Architecture

## System Shape

FlowHub is a modular monolith with explicit domain boundaries:

- API and authentication boundary;
- Source adapters and Source Workspace;
- Channel adapters and Commerce Hub;
- immutable Workspace snapshots, Drafts, Review, and selection;
- provider-neutral Write Pipeline;
- verified Channel cache;
- connector registry, diagnostics, and health read models;
- audit, operational logs, metrics, and analytics.

The active runtime and exact modules are documented in
`docs/architecture/CURRENT_ARCHITECTURE.md`. Module paths are implementation
details and do not define business behavior.

## Dependency Direction

```text
API/UI
  -> application services
  -> domain contracts
  -> repositories and adapter interfaces
  -> database or external provider adapters
```

Business services MUST NOT depend on provider-specific HTTP clients directly.
External calls MUST be isolated behind Source or Channel adapter boundaries.

## Trust Boundaries

| Boundary | Trusted fact |
| --- | --- |
| Source adapter | acquired bytes/records plus source identity and version |
| Source normalization | canonical Source records and row provenance |
| Workspace Snapshot | immutable comparison input |
| Review | deterministic proposed changes from one Snapshot/Draft revision |
| Selection | explicit selected Review item identities and checksum |
| Write Pipeline | durable intended operation and attempt identity |
| Channel adapter | request transport and authoritative verification read |
| Channel cache | verified external state only |
| Audit/history | actor evidence and confirmed outcomes |

## Consistency Model

- Source acquisition is one logical read per snapshot operation.
- Snapshot, Draft revision, Review, and selection identities are immutable.
- API reads MAY be eventually consistent when explicitly marked with freshness.
- Channel writes require per-operation state and idempotency protection.
- Unknown outcomes are resolved by authoritative read reconciliation.
- Cross-resource writes SHOULD use one transaction where local atomicity is
  required; external calls can never be part of that local transaction.

## Compatibility

Legacy and unified Workspace routes currently coexist. Both MUST preserve the
same authorization and safety invariants until Owner-approved convergence.
Compatibility aliases MAY remain at API boundaries but MUST NOT become the
canonical domain vocabulary.

## Non-Goals

- No provider is privileged as the platform model.
- No health read performs hidden external work.
- No analytics projection is an authority for Apply scope.
- No frontend filter or table model defines persisted business scope.

