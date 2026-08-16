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
5. **Background job state** — `RUNNING`, `IDLE`, `DEGRADED`, `FAILED`, or
   `UNKNOWN`.

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

## Background Jobs

The existing runner heartbeat is projected as a current state snapshot. A live
runner with no due work is `IDLE` and healthy. Heartbeat age is evaluated by a
backend TTL. The projection also exposes last successful job, queue depth, and
last failure when available. Routine heartbeat persistence is coalesced so it
does not flood Activity or connector event history.

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
