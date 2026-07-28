# Platform Data Contracts

## Identity Rules

- IDs are opaque, stable, and never derived from localized labels.
- Source row identity includes Source, source version, worksheet/table, and row
  key where applicable.
- Channel Listing identity includes Channel instance and provider object ID.
- Parent and child Listings remain distinct.
- Correlation, job, Review, selection, intent, and attempt IDs are separate.

## Core Contracts

### SourceRecord

Contains Source identity, source version, row provenance, canonical product
identity candidates, proposed values, validation, and raw extension metadata.

### ChannelListingSnapshot

Contains Channel and Listing identity, observed values, provider version or
timestamp, freshness, trust state, and adapter extension metadata.

### WorkspaceSnapshot

Immutable set of normalized Source records, Channel Listing snapshots,
mappings, acquisition accounting, and content checksum.

### DraftRevision

Immutable user-authored changes tied to one Workspace Snapshot and actor.

### ReviewItem

Deterministic proposed operation with old and desired values, explanations,
warnings, blocking errors, Source provenance, and Channel target identity.

### ReviewSelection

Explicit Review item identities, selected count, checksum, actor, and creation
time. Empty is not "all".

### WriteIntent and Attempt

WriteIntent records exact desired mutation and approval identity. Attempt
records one dispatch, transport evidence, response classification, and
verification state.

### ConfirmedChange

Append-only before/after business outcome created only after authoritative
verification. It is not derived from request acceptance alone.

### AuditEvent

Actor, effective scope, action, target, outcome, correlation ID, safe detail,
and timestamp.

## Common Metadata

All externally influenced records SHOULD include:

- `created_at` and relevant observed/verified timestamps;
- owner or tenant scope;
- source/connector identity;
- correlation ID;
- freshness and trust state;
- safe error code and message where applicable.

## Immutability

Snapshots, Review results, approved selections, confirmed changes, and audit
events are immutable. Corrections are new records linked to predecessors.
Rendering, localization, enrichment, and analytics MUST NOT mutate raw
contracts.

## Secret and Extension Data

Secrets are never part of public contracts. Provider-specific fields belong in
typed adapter extension data and MUST be sanitized before logging or audit.

