# ADR-SOURCE-001: Source Runs, Immutable Observations, and Workspace Binding

**Status:** Accepted, implementation pending
**Date:** 2026-08-05
**Decider:** FlowHub Owner
**Detailed design:** `SOURCE_ACQUISITION_DESIGN.md`

## Context

FlowHub treats Sources as desired-state inputs and Channels as external commerce
destinations. Its existing Workspace pipeline relies on immutable Mapping and
Workspace revisions, deterministic Review and Dry Run, explicit Approval,
protected Apply, and append-only audit.

External Source acquisition does not yet provide an equally strong boundary:

- Nextcloud still depends on a singleton identity and global settings.
- The Data Layer Source snapshot is mutable latest-state metadata rather than
  immutable acquisition history.
- Some query paths may perform remote I/O and persistence side effects.
- Diagnostics and acquisition do not yet share one staged execution contract.
- Workspace decisions do not reference one explicit immutable external Source
  observation.
- Workbook schema changes are not a first-class fail-closed condition.

Production experience established two general rules:

1. Business verification requests provider-neutral current state and must not
   evolve into one remote request per entity.
2. Every decision is bound to exact Source and destination observations. A
   refresh never silently changes a previously created decision.

## Decision

FlowHub will introduce explicit Source Runs that produce append-only immutable
Source Observations. Every new Workspace created from an external Source will
reference one Source Observation and one Mapping revision.

Each Source will own or reference an independent Integration Platform Connector
Instance and a versioned logical Resource Binding. Settings, secret references,
health, quotas, Runs, Observations, and current-state projections are scoped to
those identities. New behavior cannot depend on `nextcloud:primary`.

The design remains inside the existing modular monolith. A separate acquisition
microservice, mandatory broker, and full event sourcing are not required.

## Core Invariants

1. Source adapters are read-only.
2. Existing Source Observations and Mapping revisions are never mutated.
3. A Run captures exact Config, Resource Binding, and Execution Policy revisions
   before remote I/O.
4. Observation reuse requires both content equality and an identical parse
   contract. Parser, schema, resource identity, header-row, or parse-policy
   changes create a new Observation even when captured content is unchanged.
5. Mapping revisions store the expected worksheet schema fingerprint. Schema
   drift is derived for an immutable Worksheet Observation and Mapping Revision
   pair; it never mutates either record. Drift blocks normal Preview and Apply
   until an operator saves a reviewed Mapping revision.
6. Workspace, Review, Dry Run, Approval, and Apply never switch to newer Source
   or destination observations. Newer relevant observations make the decision
   outdated and require Preview.
7. Mapping, normalization, validation, and Workspace business logic never issue
   provider or transport requests.
8. One acquisition creates at most one complete capture for its parse contract,
   regardless of transport, worksheet count, or enabled Channel count.
9. Every new query endpoint is side-effect free. Live probes, resource
   inspection, acquisition, and Diagnostics use explicit commands.
10. Observation state required by a Workspace, nonterminal decision, retained
    Run, or retained audit record is protected by a retention hold.
11. Latest-successful and latest-Observation projections are scoped to the
    Source's current logical Resource Binding. Repointing to a different logical
    resource resets acquisition readiness and requires Mapping review. Replacing
    content within the same Upload binding does not change binding identity.
12. Outbound Source requests pass through one provider-declared, SSRF-aware
    egress policy before a provider adapter connects. Fixed-host providers use
    adapter-owned destinations rather than user-editable targets.
13. Secrets, unrestricted content hashes, storage keys, and cross-Source
    deduplication state are not exposed through normal APIs.
14. Fail-closed conditions are observable. Schema drift degrades Source
    readiness and emits a durable, deduplicated attention signal even when the
    acquisition itself succeeds.

## Run Semantics

Execution state and business result are separate:

```text
status: queued | running | succeeded | failed | cancelled | abandoned
result: observed | not_modified | content_unchanged_reparse | none
```

`abandoned` represents lease expiry or worker loss, not provider failure.

Idempotency identifies repeated caller intent through a Source-scoped key.
Concurrency is enforced separately through a Source-read lease. Every operation
that executes `resource_read`, including deep Diagnostics, uses the same lease
and provider budget. Same-contract work may return the active Run; conflicting
Config, Binding, or Policy revisions do not silently coalesce.

## Schema Assessment

Schema compatibility is a deterministic assessment over two immutable inputs:

```text
(worksheet_observation_id, mapping_revision_id, assessment_algorithm_version)
```

It is evaluated lazily for the current Mapping or when Preview, Workspace
creation, or Diagnostics needs it, then cached as an immutable assessment.
Changing the assessment algorithm creates a new assessment record and never
rewrites an old result.

An Observation records captured reality even when headers drift or canonical
headers collide. Schema assessment then reports `match`, `drift`, `ambiguous`,
or `no_mapping`. `drift` and `ambiguous` degrade readiness and block decision
creation; they do not turn a successful acquisition into a provider failure.

## Shared Provider Execution

Providers register typed stages once in a canonical Stage Registry. Acquisition,
connection testing, and deep Diagnostics build different plans from those same
stage implementations.

Shared stages receive the same persisted Execution Policy Snapshot when proving
acquisition readiness. With identical Stage Context and provider response, they
must produce identical typed results and reason codes. Contract tests enforce
behavioral equivalence, not only implementation identity.

Diagnostics may add supplemental read-only stages such as root discovery,
certificate-expiry reporting, or health-history analysis. Supplemental stages
are not presented as proof that the acquisition critical path succeeds.

## Security Decision

Testing an unsaved URL is treated as an SSRF-sensitive operation.

- HTTPS is the production default.
- HTTP and private-network destinations require deployment-admin allow-listing
  so legitimate self-hosted LAN Sources remain possible.
- The allow-list is deployment configuration and cannot be modified from Source
  settings.
- Loopback, link-local, metadata, multicast, unspecified, and reserved targets
  remain blocked in production.
- DNS answers and redirect destinations are revalidated, and approved addresses
  are pinned for the request attempt.
- Probe endpoints are authorized and rate-limited by user, Source, and target.
- Precise network diagnostics are hidden from lower-privilege users.

Fixed-host providers use an adapter-owned allow-list. Detailed IPv4, IPv6, DNS
rebinding, redirect, and development-profile rules are defined in the design
specification.

## Retention and Rollback Decision

Raw artifacts may expire only when retained normalized data and hashes preserve
all referenced Workspace guarantees. Normalized Observation state protected by
a retention hold cannot be removed.

Source rollback never mutates an external file or silently restores Channel
state. The supported operation is `Create Workspace from this Observation`,
which creates a new Preview and passes through Review, Dry Run, Approval, and
Apply. Reversing a completed Channel write is a separate capability-gated
compensating-change workflow.

## Options Considered

### Extend the Singleton and Mutable Snapshot

Rejected. It cannot provide trustworthy decision identity, independent Sources,
safe schema evolution, or durable diagnostics.

### Connector Instances, Runs, and Immutable Observations

Accepted. It adds moderate storage and migration complexity while preserving
the modular monolith, provider-neutral business logic, and safety model.

### Full Event Sourcing and a Separate Acquisition Service

Rejected for the current phase. Run and Observation contracts preserve the
option to add durable workers later without distributed-system overhead now.

## Consequences

Positive consequences:

- multiple independent Sources become first-class
- decisions have reproducible Source provenance
- schema drift fails closed and cannot stall silently
- refresh cannot silently alter Preview, Dry Run, or Apply inputs
- Diagnostics can identify root stage, TLS expiry, and intermittent health
- conditional capture and parse-aware reuse reduce remote work
- provider batching and collection strategies do not leak into business rules

Costs and trade-offs:

- forward-only migrations, new indexes, and retention policy are required
- legacy global Nextcloud settings require compatibility migration
- immutable Observations consume more storage than latest-state upserts
- parser upgrades may cause lazy re-capture or re-parse on later Runs
- old Workspaces retain legacy provenance
- Source UI must distinguish saved, verified, bound, observed, mapped, drifted,
  degraded, disabled, unsupported, and ready states

## Compatibility

The invariants apply to every new command/query contract from its first release.
Legacy side-effecting `GET` paths may exist temporarily only behind an explicit
compatibility flag, with deprecation metadata, usage telemetry, no new frontend
consumer, a defined removal release, and regression tests.

The mutable `dl_source_snapshots` record becomes a current-binding latest-state
projection pointing to an immutable Observation. It is not decision identity or
history.

No migration rewrites historical Workspace rows, Mapping revisions, Approvals,
execution attempts, or audit records.

## Scope Boundary

This ADR covers Source acquisition and Source Diagnostics. Channel diagnostic
internals remain governed by `INTEGRATION_PLATFORM.md` and
`MARKETPLACE_CHANNELS.md`.

Scheduling may trigger Source inspection or acquisition only after the shared
scheduler is approved. It cannot trigger Approval or Apply.

## Implementation Governance

The domain model, canonicalization rules, reason-code catalog, Provider model,
API semantics, stage plans, SSRF policy, retention holds, Source UI, migration,
and required tests are defined in `SOURCE_ACQUISITION_DESIGN.md`.

Those details may be refined during implementation without changing this
Accepted ADR while every Core Invariant continues to hold. Reversing the Run and
Observation split, allowing mutable decision identity, weakening fail-closed
schema behavior, permitting silent operational stalls, or bypassing Workspace
safety requires a new superseding ADR.
