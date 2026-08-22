# ADR-CHANNEL-READ-001: Canonical Channel Read Architecture

**Status:** Accepted
**Date:** 2026-08-19
**Decider:** FlowHub Owner
**Related:** `ADR_SOURCE_ARCHITECTURE_V2.md`, `ADR_WOOCOMMERCE_WEBHOOKS.md`,
`ADR_DIAGNOSTICS_STATE_MODEL.md`, `STALE_JOB_RECOVERY.md`

## Context

FlowHub's persisted Channel state (`DlProductCache`) is an *observation* of
external Channel state, never guaranteed to equal current external reality.
External changes can come from a human administrator, a plugin, another
integration, or FlowHub's own write path. Webhooks are the fastest
observation signal FlowHub has, but they are an optimization, not a
correctness guarantee: they can be delayed, disabled, or lost.

`ADR_WOOCOMMERCE_WEBHOOKS.md` deliberately shipped Phase 1 with every
WooCommerce product webhook triggering the *same* full-channel
`CommerceHubService.refresh_channel_cache` job the scheduled/manual poll
uses, explicitly flagging this as a temporary tradeoff: "it can be narrowed
to a per-product REST fetch in a later phase without changing the
receipt/idempotency contract." That full-channel job is owned by a single
`DlRefreshJob` lease scoped to `(connector_id, entity_type)` --
channel-wide, with no per-product concept. On 2026-08-18, that coupling
caused 13 healthy `product.updated` deliveries to dead-letter while a
full-catalog job held the only lease for the channel; that day's amendment
(below, and in `ADR_WOOCOMMERCE_WEBHOOKS.md`) fixed the symptom (honest
failure attribution, no attempt burned on deferred work). This ADR fixes the
underlying cause: webhook-driven observation must never compete with
full-catalog work for the same execution lease.

The goal is `External change -> FlowHub observes it as quickly as the
connector allows`, without achieving that through continuous full-catalog
scanning. This must be provider-neutral: WooCommerce is the only connector
migrated to this architecture in this phase, but nothing in the contract,
lease model, or confidence model may be WooCommerce-specific.

## Decision

### Strategy, Scope, and Reason are independent axes

Three provider-neutral read strategies, never exposed to Workspace by name:

- **LIGHT** -- incremental or targeted observation. `O(changed)` where the
  connector allows it. Never a complete catalog scan.
- **FULL** -- builds/rebuilds the complete Channel snapshot. Resumable. Not
  an integrity-repair operation.
- **DEEP** -- exceptional recovery: a FULL snapshot plus bounded,
  sampled live verification. Owner/resolver-triggered only, never routine.

Strategy is independent of **Scope** (`CHANNEL` or `PRODUCT`) and **Reason**
(why the read is happening -- `WEBHOOK_PRODUCT_UPDATED`,
`PERIODIC_RECONCILIATION`, `OWNER_REQUESTED`, `VERIFICATION`,
`INITIAL_BACKFILL`, `RECOVERY`). Workspace expresses intent as a
`ChannelReadRequest` (`app/flowhub/read_engine/contracts.py`); the
**Connector Strategy Resolver** (`app/flowhub/read_engine/strategy_resolver.py`)
decides the concrete execution mechanism from capabilities, scope, and cache
state -- Workspace never says "light refresh WooCommerce."

`resolve()` is a pure function (no I/O). It maps onto
`IncrementalReadEngine`'s existing internal mechanism names
(`initial_full_read` / `modified_since` / `metadata_filter`) for
`CHANNEL` scope -- these are **not replaced**, only reframed as LIGHT/FULL
sub-mechanisms -- and adds `entity_read` for `PRODUCT` scope and
`deep_reconciliation` for DEEP. `IncrementalReadEngine.determine_strategy()`
keeps serving every existing manual/scheduled call site unchanged; the
resolver is a new, additive entrypoint used only by PRODUCT-scope and DEEP
callers.

### Connector Read Capabilities

`ConnectorReadCapabilities` (`read_engine/contracts.py`) is extended, not
replaced, with the fields this architecture's decisions require:
`supports_entity_read` (canonical "supports_targeted_read"), `supports_cursor`,
`supports_change_feed`, `supports_full_snapshot`, `supports_deep_recovery`,
`supports_variation_embedding`, `max_page_size`, `recommended_concurrency`,
`rate_limit_characteristics`. The existing `supports_batch_read` already
*is* the canonical "supports_bulk_read" capability -- no duplicate field was
added for it. No connector is required to implement every capability; the
resolver fails closed (`IncrementalReadUnsupported`) rather than silently
falling back to a more expensive mechanism. This is a distinct, technical,
per-connector contract from `docs/evidence/architecture/CAPABILITY_REGISTRY.md`,
which is an explicitly draft, documentation-only business/domain-maturity
registry not wired to any code.

### Entity work: a second, independent lease scope

`dl_refresh_jobs` (`DlRefreshJob`, owned by `RefreshJobLifecycle`) keeps its
exact current meaning: one lease per `(connector_id, entity_type)`, for
FULL/DEEP channel-wide work. A new table, `dl_channel_entity_work`, owns a
second, fully independent lease scoped to
`(connector_id, entity_type, entity_id)`, claimed by workers via
`SELECT ... FOR UPDATE SKIP LOCKED`, for LIGHT/PRODUCT-scope targeted work.
**A running FULL job never blocks, and is never blocked by, a targeted
entity-work claim for the same connector.** This is the structural fix for
the 2026-08-18 incident: the two lease scopes cannot contend for the same
row.

The design is modeled structurally on Source Acquisition's `saq_runs`
(worker id, lease, partial-unique-index-per-active-scope, bounded retry
chain) -- imitated, not merged into; Channel and Source remain separate
bounded contexts per `ADR_SOURCE_ARCHITECTURE_V2.md`.

**Coalescing.** Webhook receipts (`webhook_receipts`) are never the
claimable unit -- they have no in-flight state today, and adding one would
fragment an already-correct, working state machine. Instead, a join table
(`dl_channel_entity_work_receipts`) links receipts to whichever
`dl_channel_entity_work` execution covers them. New evidence for an entity
already `pending` coalesces into that row (`latest_event_at` advances,
`latest_provider_event_id` is retained); new evidence for an entity already
`running` sets `superseded_at`, which requeues the row to `pending` on
completion instead of finishing it -- the newest external observation always
wins, and no event is silently dropped. On terminal completion, every
linked receipt transitions atomically through the *existing*
`WebhookIngestionService.mark_woocommerce_receipt_processed` /
`mark_woocommerce_receipt_failed` methods -- no second receipt state machine
was created. A receipt whose payload carries no resolvable product id is
dead-lettered immediately rather than left orphaned.

Retries are bounded per work item (`attempt_count` / `max_attempts`) with
the same backoff shape `webhooks/service.py` already uses. A crashed claim
is recovered by a bounded `recover_expired_entity_work()` scan, mirroring
`RefreshJobLifecycle.recover_expired()` for this table -- recovery clears
only the expired lease and never replays provider I/O twice for one
logical mutation beyond what an at-least-once retry already implies (see
concurrency tests, `PostgreSQL Concurrency Results` in the implementation
report).

### FULL-vs-LIGHT fencing

`dl_product_cache` gains a typed `provider_observed_at` (DateTime) column.
The existing `last_modified` (`String(100)`) only sorts correctly today
because WooCommerce happens to emit zero-padded GMT ISO-8601; it is too
fragile to fence on in a provider-neutral design (a future connector's
timestamp format is not guaranteed to share that property). Every write
path -- FULL's batch upsert and LIGHT's targeted upsert alike -- writes
through one conditional UPSERT:

```
INSERT ... ON CONFLICT (connector_id, product_id) DO UPDATE ...
WHERE dl_product_cache.provider_observed_at IS NULL
   OR excluded.provider_observed_at >= dl_product_cache.provider_observed_at
```

A slow FULL page can never overwrite a newer targeted (LIGHT) observation.
`last_modified` and its one existing reader are untouched.

FULL's existing "unseen sweep" (rows not seen this run get
`exists=False`) is re-keyed off `last_fetched_at < job.started_at` instead
of the unbounded, ever-growing `seen_product_ids` list previously
serialized into `DlRefreshJob.meta` on every page. This closes a race this
architecture would otherwise introduce: once LIGHT can run concurrently
with FULL, a product touched by a concurrent LIGHT read mid-FULL-scan must
never be swept just because that page's `seen_product_ids` didn't include
it. Keying off `last_fetched_at` (which a concurrent LIGHT write naturally
bumps to "now") closes that gap for free.

### Observation Confidence

A new, purely additive concept, deliberately distinct from cache
freshness: `ObservationConfidence` (`CONFIRMED` / `LIKELY_FRESH` / `STALE`
/ `UNKNOWN` / `RECOVERY_REQUIRED`), computed from real evidence (last read
mechanism, entity-work status and attempt count, TTL) rather than stored as
one arbitrary boolean. `RECOVERY_REQUIRED` fires when entity work exhausts
its retry budget -- the concrete signal that FlowHub tried and failed to
observe a real external change. New, additive columns on
`dl_product_cache` (`observation_confidence`, `_reason`, `_computed_at`).
The existing `freshness` column (`fresh|stale|error`) and all of its
existing readers are **left completely untouched** -- this is a new axis
that sits alongside freshness, not a replacement for it, and no repo-wide
migration of `freshness` call sites is in scope. Confidence decay with no
new event (e.g. `LIKELY_FRESH` aging into `STALE`) is handled by recomputing
from raw evidence at read time rather than a periodic sweep job; the stored
column is a write-time cache for fast row display, not the source of truth.

Diagnostics rolls per-row confidence up to a new, distinct Channel-level
axis (`diagnostics/state_model.py`), following the existing
`CapabilityPolicy`/TTL-policy pattern -- **not** merged into the existing
Freshness axis, which answers a different, coarser question ("has any read
completed recently").

### Scheduling

No new process or infrastructure. `orders/runner.py`'s existing
PostgreSQL-backed loop gains a sibling `ChannelEntityWorkRunner`, ticking
independently and faster (default 5s, env-configurable) than the existing
~30s full-channel-due check, claiming and processing pending entity work.
`app/flowhub/api/v2/scheduler.py` remains unmounted and routeless, per
`tests/flowhub/test_planned_routers_unmounted.py` -- this architecture does
not touch it. The webhook-to-full-refresh wiring in
`diagnostics/scheduling.py` moves behind an explicit rollout flag
(`FLOWHUB_CHANNEL_READ_TARGETED_LIGHT_ENABLED`, default off); the
pre-existing behavior is fully preserved when the flag is off.

### Verification stays a separate correctness boundary

Preview/Dry Run/Apply verification is not FULL refresh and this
architecture does not change it. WooCommerce Apply already live-verifies
only the operation's own batch (`CurrentStateStrategy.BATCH_BY_ID` via
`CurrentStateRequest(purpose="post_apply_verification", max_staleness_seconds=0)`,
`app/connectors/destinations/woocommerce/connector.py`) -- correctly scoped
already, confirmed by direct code reading, not assumed. Channel Read
strategy selection must never bypass this boundary.

## Invariants

1. **A channel-wide FULL/DEEP lease and a per-entity LIGHT lease are always
   independent scopes.** Neither blocks the other for the same connector.
2. **Newest external observation wins.** No write path may let an older
   `provider_observed_at` overwrite a newer one, regardless of which job
   (FULL or targeted) performed the write or which one committed last.
3. **Coalescing preserves every webhook receipt.** Collapsing repeated
   entity events into one work execution never discards a receipt or its
   audit evidence; every covered receipt transitions deterministically
   through the existing receipt state machine.
4. **Confidence is evidence-derived, never a sticky flag.** A prior
   `RECOVERY_REQUIRED` or `STALE` value must not poison Observation
   Confidence after a subsequent successful observation; confidence is
   recomputed from current evidence, not carried forward.
5. **Freshness and Observation Confidence are independent axes.** Neither
   subsumes the other; existing `freshness` semantics and callers are
   unmodified by this architecture.
6. **DEEP is exceptional.** No scheduler path or resolver escalation
   triggers DEEP merely because confidence is not `CONFIRMED`; DEEP requires
   `RECOVERY_REQUIRED` evidence or an explicit Owner request.
7. **Verification scope is never widened by Channel Read strategy
   selection.** Preview/Dry Run/Apply verification reads exactly the
   operation's scope, never more, independent of which read strategy last
   touched the cache.
8. **No parallel receipt or cache subsystem.** Targeted reads write through
   the same `DlProductCache` and the same webhook receipt state machine
   every other read path already uses.

## Known limitations

- **SnappShop** Apply verification (`channels/snappshop.py`) uses
  `CurrentStateStrategy.COLLECTION_SCAN` -- it paginates the vendor's entire
  product list looking for the requested batch, a pre-existing full-scan
  that predates this architecture. **TapsiShop** Apply verification is
  `CurrentStateStrategy.UNSUPPORTED` -- there is no live read-back path at
  all, so `verify_updates` always reports `RECONCILIATION_REQUIRED`. Both
  are out of scope for this phase; fixing either needs new upstream
  connector read capabilities this phase does not build.
- **DEEP is contract-complete but has no automated or Owner-facing trigger
  in this phase.** `strategy_resolver.resolve()` correctly resolves or
  rejects a `ReadStrategy.DEEP` request, but nothing in the scheduler or API
  surface issues one yet. Wiring an explicit Owner-triggered DEEP recovery
  endpoint is a near-term follow-up, deliberately not built now given DEEP's
  "repair where allowed" semantics were left open by design.
- **`dl_product_cache.freshness` (22 existing call sites) is not migrated**
  to Observation Confidence in this phase.

## Explicitly out of scope this phase

Any change to SnappShop's or TapsiShop's write/verification connectors;
automated DEEP repair beyond bounded sampled verification; enabling
`FLOWHUB_CHANNEL_READ_TARGETED_LIGHT_ENABLED` in any environment (this
phase builds and tests the capability; enabling it live is a separate,
later operational decision); any connector besides WooCommerce.
