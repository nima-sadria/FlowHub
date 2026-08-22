# Stale Run Recovery Scope

## Decision

FlowHub recovers only durable runs that have an active execution owner. A
recovery never replays provider I/O, deletes business rows, resets a cache, or
changes a successful business result into a fabricated success. It records that
execution ownership was lost before a terminal result was durably recorded.

`DlRefreshJob` is the shared lifecycle only for product-cache refresh and
channel product synchronization. `AcquisitionRun` keeps its existing,
independent lease lifecycle. This is deliberately not a migration of every
persisted record into a new framework.

## Classification

| Subsystem | Class | Reason and action |
| --- | --- | --- |
| WooCommerce product-cache refresh | A. Persisted run with active ownership | `DlRefreshJob`; managed by `RefreshJobLifecycle`. |
| WooCommerce targeted (LIGHT/PRODUCT) entity reads | A. Persisted run with active ownership | `DlChannelEntityWork`; managed by `entity_work.py`, an **independent** lease scope from `DlRefreshJob` -- a channel-wide FULL/DEEP lease and a per-entity LIGHT lease never block each other. See `ADR_CHANNEL_READ_ARCHITECTURE.md`. |
| TapsiShop/Technolife marketplace product sync | A. Persisted run with active ownership | `DlRefreshJob`; managed by `RefreshJobLifecycle`. |
| SnappShop product sync | A. Persisted run with active ownership | `DlRefreshJob`; managed by `RefreshJobLifecycle`. |
| Source acquisition / Read Now | A. Persisted run with active ownership | `AcquisitionRun` already has worker ID, lease, heartbeat (`updated_at`) and `abandon_expired_runs`; it remains its own lifecycle. |
| Worksheet discovery reservations and source-read reservations | B. Persisted event/receipt, not a run | They account for a request or quota decision; they do not own a long-lived execution. No stale-run mutation. |
| Webhook receipts and provider delivery identities | B. Persisted event/receipt, not a run | Their durable receipt/retry/dead-letter state machine is the authority; a refresh watchdog must not modify it. |
| Pricing draft/review/apply records and reconciliation evidence | B. Persisted evidence, not a run | They are immutable or audited business records. They are not execution leases. |
| Order synchronization checkpoint | C. Ephemeral loop/heartbeat | The checkpoint's lease prevents two polling loops; it has no durable RUNNING run identity to recover. Its owner reacquires the existing lease. |
| Diagnostics scheduler | C. Ephemeral loop/heartbeat | Runner liveness is handled by its existing loop/heartbeat, rather than a durable business run. |
| Exchange-rate runner | C. Ephemeral loop/heartbeat | The persisted fetch record is history; provider locking and runner ownership are separate. It is intentionally unchanged. |
| Provider configuration, connector health and static channel/source metadata | D. Not applicable | These are configuration/current-state records, not jobs. |

## `DlRefreshJob` lifecycle

The durable lifecycle is projected as `pending`, `running`, `completed`,
`failed`, or `cancelled`. A recovered run remains stored as `failed` for
compatibility, with `recovery_reason=execution_lease_expired`; API and
Diagnostics project that combination as **stale / recovery required**.

Each running refresh records `started_at`, `heartbeat_at`, and
`lease_expires_at`. Product read engines heartbeat after each durable page
checkpoint. Marketplace channel syncs heartbeat after every successfully read
page. Channel cache replacement and successful terminal status are committed in
the same database transaction.

Policies are per job data rather than one global timeout:

| Entity/strategy | Lease |
| --- | ---: |
| product full read | 30 minutes |
| product modified-since read | 15 minutes |
| product metadata-filter read | 10 minutes |
| marketplace/channel products (default) | 15 minutes |
| source refresh | 30 minutes |
| destination refresh | 30 minutes |
| connector metadata | 10 minutes |

The application startup hook scans only `DlRefreshJob.status=running` and
`AcquisitionRun.status=running`. It is bounded and performs no provider I/O.
For an additive upgrade, a legacy running `DlRefreshJob` that has no lease is
treated as stale only after the policy window measured from its last available
heartbeat, start, or creation timestamp.

## `DlChannelEntityWork` lifecycle

A second, independent lease table for LIGHT/PRODUCT-scoped targeted reads
(webhook-driven and Owner-requested single-entity refreshes). Scoped to
`(connector_id, entity_type, entity_id)` rather than `DlRefreshJob`'s
`(connector_id, entity_type)`, so a long-running FULL/DEEP job never blocks,
and is never blocked by, a targeted read for one product. Workers claim due
rows via `SELECT ... FOR UPDATE SKIP LOCKED` (`entity_work.py`), so multiple
workers process independent entities concurrently without contending on
unrelated rows. The lease defaults to 120 seconds
(`FLOWHUB_CHANNEL_ENTITY_WORK_LEASE_SECONDS`) -- short by design, since a
single-entity read is cheap to simply retry rather than needing the longer
policy windows a full catalog scan requires.

Bounded per-item retry (`attempt_count` / `max_attempts`, default 5) governs
whether an expired lease or a failed read requeues the row (`pending`, with
backoff on failure) or reaches a terminal `failed` state. Terminal outcomes
flip every webhook receipt linked to that execution through the existing
`WebhookIngestionService` state machine -- no second receipt subsystem.
`recover_expired_entity_work()` mirrors `RefreshJobLifecycle.recover_expired()`
for this table: bounded scan, no replayed provider I/O beyond what an
at-least-once retry already implies.

## Recovery and retry

Recovery preserves the existing counters, `meta`, correlation evidence, cache
rows and timestamps. It clears only the expired lease and records a safe error
and recovery reason. A valid active `DlRefreshJob` lease blocks another
full-channel refresh for the same `(connector_id, entity_type)`; it has no
bearing on `DlChannelEntityWork`, which is a fully independent lease scope
(see above). A completed or recovered job no longer owns a lease, so an
explicit Owner retry creates a new `DlRefreshJob` identity; the old record is
not changed back to running.

Diagnostics reports the recovery state, last heartbeat, preserved cache count,
and an explicit retry recommendation. Historical stale records do not by
themselves make the entire platform unhealthy.

Each recovery emits one bounded `job_recovery_marked` connector event with the
job identity and the guarantee that neither provider I/O nor business data was
changed. Normal refresh-start and refresh-complete events remain owned by the
existing provider services; no per-row recovery events are emitted.
