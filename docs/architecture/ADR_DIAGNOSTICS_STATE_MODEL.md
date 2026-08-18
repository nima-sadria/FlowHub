# ADR-DIAGNOSTICS-001: Canonical Diagnostics State and Scheduled Evidence

**Status:** Accepted
**Date:** 2026-08-15
**Decider:** FlowHub Owner
**Supersedes:** The single-axis Channel health derivation in
`CURRENT_ARCHITECTURE.md` and `app/flowhub/diagnostics/semantics.py`

## Context

FlowHub currently projects connector configuration, connection health, product
and order synchronization, webhook processing, cache state, and runner state
through one `DiagnosticState` value. Dashboard, Diagnostics, Source summaries,
and the Sidebar then apply additional client-side severity rules. This makes a
successful connection look like complete operational readiness, lets an order
timestamp mask missing product evidence, counts Coming Soon and archived
resources as operational, and permits one surface to say "Operational" while
another says "Needs attention."

Normal Diagnostics reads are record-backed and safe, but connection evidence is
normally refreshed only by an operator. Product and order work already has
provider-specific execution and quota boundaries. Creating a second scheduler
or turning every Diagnostics read into provider I/O would violate those
boundaries.

Source lifecycle, immutable observation, zero-I/O configuration, Source Product
Key, Channel capability, marketplace write-safety, and Business Observability
contracts remain authoritative. This decision changes their Diagnostics
projection; it does not replace them.

## Decision

FlowHub will publish one backend-owned canonical Diagnostics State Model. The
model is a record-backed projection consumed by Diagnostics, Dashboard, Recent
Checks, Source and Channel summaries, and the global status indicator. Frontend
code localizes and renders the projection but does not derive readiness,
freshness, denominator eligibility, overall severity, or recommended action.

The model keeps these axes independent:

1. **Connectivity** — `UNKNOWN`, `HEALTHY`, `DEGRADED`, `UNHEALTHY`, or
   `NOT_APPLICABLE`.
2. **Operational readiness** — `READY`, `NEEDS_ATTENTION`, `BLOCKED`,
   `DISABLED`, `ARCHIVED`, `COMING_SOON`, or `NOT_APPLICABLE`.
3. **Freshness** — `FRESH`, `STALE`, `NEVER_RUN`, `NOT_SCHEDULED`,
   `NOT_ENABLED`, or `NOT_APPLICABLE`.
4. **Capability availability** — `SUPPORTED_ENABLED`, `SUPPORTED_DISABLED`,
   `NOT_SUPPORTED`, `NOT_CONFIGURED`, or `COMING_SOON`.
5. **Background job state** — `RUNNING`, `IDLE`, `PENDING`, `DEGRADED`,
   `FAILED`, or `UNKNOWN`.

Capability evidence is kept separately for connection verification, product
synchronization, order synchronization, webhook processing, product cache,
provider acquisition/read, and background processing. Every capability records
support, schedule mode, last attempt, last success, last outcome, next expected
run when meaningful, freshness, and safe evidence references.

## Overall-State Derivation

The canonical overall state is deterministic:

1. `ERROR` when the platform projection cannot be generated or current
   operational connectivity is unhealthy.
2. `BLOCKED` when an operational resource cannot perform a required operation
   because configuration or another explicit prerequisite blocks it.
3. `NEEDS_ATTENTION` when required evidence is stale, has never run, is
   degraded, or a required runner is not current.
4. `HEALTHY` when every denominator-eligible resource is ready and every
   required capability has acceptable current evidence.

Coming Soon, archived, and intentionally disabled resources never lower the
overall state. Informational technical checks do not lower it either. The same
projected `overallState` value is returned to every consumer.

## Denominator Semantics

The Channel denominator contains available, enabled operational Channels.
Disabled and Coming Soon counts are reported separately. Coming Soon
capabilities are not evaluated as provider failures.

The Source denominator contains active Sources. Disabled and archived counts
are reported separately. Archived Sources retain historical evidence and their
persisted display identity, but are never evaluated as current operational
failures.

Resource identity comes from the canonical persisted display name and lifecycle
record. Provider type is a separate field. Two Nextcloud Sources therefore keep
distinct names without hard-coded aliases.

## Freshness and Scheduling Policy

Freshness is derived from a backend policy catalog plus persisted evidence, not
from UI constants. Each capability has its own accepted evidence window.
Provider-specific environment overrides may make a policy explicit without
changing connector credentials or executing I/O during Save.

Connection verification is scheduled conservatively for configured,
operational connectors. The existing order-sync runner process evaluates due
work and invokes existing bounded connection-test primitives. The API process
does not start a loop. The evaluator performs no I/O for disabled, archived,
Coming Soon, unsupported, or incomplete resources.

Product synchronization is scheduled only when its explicit connector policy
is enabled and has an interval. A missing legacy policy is `NOT_SCHEDULED`; it
is never guessed. The existing runner process may execute a due product sync by
calling the same capability-aware, rate-limited refresh service used manually.
The refresh job records `scheduled` rather than fabricating manual history.
Diagnostics evaluation itself never triggers synchronization.

The effective product-synchronization schedule mode is **composed** from all
available evidence, not read from the polling policy alone. A connector's
`product_sync` environment policy describes only a *poll*. For a provider that
pushes product changes over webhooks, the absence of that poll is not "no
schedule" — delivery is event-driven, and the poll, when configured, is a
reconciliation safety net layered on top. Reporting only the polling axis
produced the contradiction where one channel published
`Webhook: EVENT_DRIVEN` and `Product synchronization: NOT_SCHEDULED`
simultaneously.

Composition is evidence-gated, per provider and per instance:

- The provider's webhook policy must be `EVENT_DRIVEN`, the instance's webhook
  secret must be configured, **and** at least one durably accepted
  (non-dead-letter) receipt must exist. Configuration alone is a claim, not
  evidence; a configured-but-never-delivering webhook does not change the mode.
- When all three hold and the connector's own polling policy is also
  `SCHEDULED`, the mode is `EVENT_DRIVEN_WITH_RECONCILIATION`.
- When all three hold and no poll is configured, the mode is `EVENT_DRIVEN`.
- Otherwise the declared polling policy applies unchanged
  (`SCHEDULED` / `MANUAL` / `NOT_SCHEDULED`).

Schedule mode and capability availability remain separate axes. Composition
never writes a support value into the mode, and never writes a mode into
support: a channel that is unsupported, disabled, unconfigured, or Coming Soon
keeps its declared policy and reports that fact through
**Capability availability**.

Freshness for `EVENT_DRIVEN` and `EVENT_DRIVEN_WITH_RECONCILIATION` is derived
from real product evidence — the last successful product synchronization —
against the capability's own accepted evidence window, not from whether a
polling interval exists. Answering `NOT_SCHEDULED` for freshness on an
event-driven channel made the tile unusable for exactly the channels that were
working. Event-driven product synchronization also participates in readiness:
stale product data on a channel the provider is actively pushing to is a real
operational problem and must be able to surface `NEEDS_ATTENTION`.

Reconciliation is published as its own sub-fact of the product-synchronization
capability, never overloaded onto `nextExpectedAt`. Its mode is `SCHEDULED`
(with a next-reconciliation timestamp), `MANUAL` (event-driven or
manual-by-design, with manual refresh available), or `DISABLED` (neither event
delivery nor any schedule reconciles this channel).

No new scheduler, cron, interval, or polling cadence is introduced by any of
this. Composition is a projection over evidence that already exists.

Order scheduling continues to use the existing order runner, connector
capabilities, connector settings, leases, checkpoints, and provider-specific
intervals. Product timestamps never satisfy order freshness and order
timestamps never satisfy product freshness.

Source acquisition remains governed by the accepted Source ADR. A missing
Source acquisition schedule is shown as `NOT_SCHEDULED`; Diagnostics does not
invent one and cannot trigger Approval or Apply.

## Cache Semantics

Product cache outcome and freshness are different fields. A completed refresh
remains `SUCCESSFUL` historical evidence while its data may independently be
`STALE`. Cache row count is content evidence, not proof of current readiness.
No migration fabricates historical success.

## Recommended Actions

The backend selects exactly one resource-level action from the controlling
state. Scheduled stale work reports the next scheduled run. Manual-only stale
work may offer a manual refresh. Unsupported, intentionally disabled,
not-scheduled-but-not-required, archived, and Coming Soon capabilities do not
produce impossible actions. A resource cannot simultaneously publish "No
action required" and an actionable refresh recommendation.

The action must reflect the *composed* mode, not the polling policy alone. On
an event-driven channel whose most recent reconciliation or refresh attempt
failed, the action is `RETRY_RECONCILIATION` — investigate and retry that
specific failed attempt — not `REFRESH_PRODUCTS`, which wrongly implies nothing
has ever run and that a full manual refresh is the remedy. An event-driven
channel with a configured reconciliation poll reports its next reconciliation
run instead. A healthy event-driven channel with fresh product data, no dead
letters, and no queue backlog reports `NO_ACTION_REQUIRED`, and must never
publish a false `REFRESH_PRODUCTS`.

## Background Jobs

The existing runner heartbeat is projected as a current state snapshot. A live
runner with no due work is `IDLE` and healthy. Heartbeat age is evaluated by a
backend TTL. The projection also exposes last successful job, queue depth, and
last failure when available. Routine heartbeat persistence is coalesced so it
does not flood Activity or connector event history.

Runner state and queue depth must agree. A live, healthy runner that has real
executable work waiting is `PENDING`, never `IDLE`: publishing "Idle" beside a
non-zero queue depth is a contradiction the Owner cannot act on. `IDLE` means
live with a queue depth of zero; `RUNNING` means currently executing.

Queue depth counts only work a live runner will genuinely pick up. Refresh jobs
whose execution lease has already expired, and webhook receipts already past
their retention window, are abandoned records, not backlog, and are excluded.
The expiry definition is shared with the existing stale-job recovery path so
"abandoned" means the same thing to recovery and to the projection. Excluded
records are **not** hidden: they remain visible as a distinct stale-queue count
under **Advanced evidence**, because they are real operational history. Queue
depth is never suppressed or cosmetically zeroed.

## Observability

Existing Integration Platform event names and refresh-job records remain the
technical evidence source. Scheduled connection checks emit a sanitized event
only on a meaningful state transition; product and order services retain their
existing started/completed/failed conventions. Business Observability remains
the durable owner-facing channel for business-impacting facts. Routine healthy
polls and heartbeats are not Business Events.

## Owner and Advanced Views

The normal Owner view uses human-readable capability labels and the canonical
state axes. Internal evidence keys, correlation IDs, reason codes, evidence
source IDs, and raw safe timestamps remain available under a collapsed
**Advanced evidence** section. Actionable resources are prioritized and
expanded. Healthy resources are collapsed by default. Archived and Coming Soon
resources use compact, separate sections.

## Alternatives Considered

### Keep per-page derivation

Rejected because identical persisted evidence can produce contradictory
overall states and denominators.

### Run provider checks during every Diagnostics request

Rejected because it couples page traffic to provider I/O, ignores quotas, and
turns a read endpoint into an operational command.

### Add a second Diagnostics scheduler

Rejected because FlowHub already has a database-backed runner architecture and
would gain overlapping leases, heartbeats, and failure semantics.

### Treat missing sync evidence as a connection failure

Rejected because authentication/connectivity and operational data readiness are
different facts.

## Consequences

- Existing response fields may remain as compatibility aliases, but the
  canonical projection is authoritative.
- Dashboard and Sidebar must consume the projection or use explicitly named
  platform-liveness wording; they cannot infer system health independently.
- Frontend tests assert rendering and localization, while backend/domain tests
  own state derivation.
- Policy or evidence persistence changes, if later required, must be additive
  and forward-only from the current Alembic head.
- The task is intentionally deployment-neutral. Source changes are committed
  and verified, but deployment is a separate Owner action.

## Amendments

### 2026-08-18 — Composed product-sync scheduling and runner queue semantics

Accepted, amending this ADR in place rather than superseding it: the change
extends axes this ADR already owns and contradicts none of its decisions.

- Added `EVENT_DRIVEN_WITH_RECONCILIATION` to the schedule-mode vocabulary and
  made the effective product-synchronization mode a composition of webhook
  capability, per-instance webhook configuration, accepted delivery evidence,
  and the declared polling policy (see *Freshness and Scheduling Policy*).
- Added the `reconciliation` sub-fact (`SCHEDULED` / `MANUAL` / `DISABLED`,
  with `nextReconciliationAt`) to the product-synchronization capability shape.
- Added the `RETRY_RECONCILIATION` recommended action for event-driven channels
  whose latest reconciliation attempt failed (see *Recommended Actions*).
- Added `PENDING` to the background-job state vocabulary and excluded
  lease-expired jobs and retention-expired receipts from queue depth, keeping
  them visible as a separate stale count (see *Background Jobs*).

No schema change, no migration, and no new scheduler or polling interval was
introduced. `ScheduledDiagnosticsEvaluator` is unchanged; its existing
treatment of webhook receipts as due work independent of the polling interval
was already correct.
