# ADR-WOOCOMMERCE-WEBHOOKS-001: Inbound WooCommerce Product Webhooks (Phase 1)

**Status:** Accepted
**Date:** 2026-08-17
**Decider:** FlowHub Owner
**Extends:** The durable-receipt/dedup webhook architecture already proven for
TapsiShop (`app/flowhub/webhooks/`), the canonical Diagnostics State Model
(`ADR_DIAGNOSTICS_STATE_MODEL.md`), and Business Observability v1.

## Context

FlowHub had no inbound WooCommerce webhook endpoint. WooCommerce product
freshness depended entirely on scheduled/manual polling
(`WooCommerceProductReadAdapter`, driven by `CommerceHubService.refresh_channel_cache`).
TapsiShop already has a secure, durable, idempotent webhook ingestion path
(`app/flowhub/webhooks/service.py`, `app/flowhub/api/v2/webhooks.py`) backed
by `webhook_receipts` / `webhook_provider_event_identities`. This phase
extends that exact architecture to WooCommerce `product.created`,
`product.updated`, and `product.deleted` topics, without touching orders,
customers, or any other channel's write path.

## Decision

### Ingress and authentication

- `POST /api/v2/webhooks/woocommerce/{channel_id}` lives in the same router
  as the TapsiShop route, with the same manual `Request.body()` / size-cap /
  content-type discipline (`MAX_WOOCOMMERCE_WEBHOOK_BYTES = 256 KiB`).
- WooCommerce signs webhooks with `base64(HMAC-SHA256(raw_body, secret))` in
  `X-WC-Webhook-Signature` — a different encoding than the hex-digest
  generic webhook verifier in `integration_platform/service.py`. A dedicated
  helper (`woocommerce_signature_matches`) computes and constant-time
  compares this, rejecting missing/malformed/mismatched signatures with 403
  before any durable write.
- `woocommerce.webhook_secret` is a distinct `AppConfigService` key from
  `woocommerce.key` / `woocommerce.secret` (outbound REST consumer
  credentials). It follows the same write-only, masked, blank-save-preserves
  pattern already used for `woocommerce.secret`, resolved through
  `IntegrationConnectorSetting` + `AppConfigService`, exactly mirroring how
  TapsiShop's `webhook_token` is resolved.
- The lifecycle guard (`authenticate_woocommerce`) checks
  `IntegrationConnectorInstance.connector_type == "woocommerce"` and
  `enabled`, before signature verification is even attempted — mirroring
  `authenticate_tapsishop`.

### Topic allowlist

Only `product.created`, `product.updated`, `product.deleted` are accepted in
Phase 1. `X-WC-Webhook-Topic` is read first, falling back to
`X-WC-Webhook-Resource`/`X-WC-Webhook-Event`. Any other topic — including
orders, customers, and `product.restored` (not a WooCommerce core topic) —
is rejected with 400 before a receipt is written. Orders and customers
remain entirely out of scope for this phase.

### Idempotency

`webhook_receipts` / `webhook_provider_event_identities` are reused
verbatim. `provider = "woocommerce"`,
`provider_event_id = f"{X-WC-Webhook-ID}:{X-WC-Webhook-Delivery-ID}"`; both
headers are required (missing either is a 400, no receipt written).
`WebhookIngestionService.accept_woocommerce_event` mirrors
`accept_tapsishop`'s transaction/`IntegrityError`-race handling: a
concurrent duplicate delivery converges on the same receipt row instead of
raising or double-writing. A Postgres-only concurrency test
(`tests/flowhub/webhooks/test_woocommerce_webhooks_postgres.py`) exercises
this race directly, since SQLite's single-connection test pool cannot.
The receipt transition itself is also row-locked: concurrent evaluators
cannot create duplicate processing attempts or duplicate Business Events for
one receipt outcome.

### Processing model: request validates, a background process applies

The request handler only verifies, durably stores the receipt, and returns
2xx. It never upserts into the product cache in-request. This mirrors
`OrderSyncService.process_tapsishop_webhook_receipts` / `orders/runner.py`
in spirit, but the concrete mechanism is different, and that difference was
the single largest discovery point in this phase.

**What already existed:** `app/flowhub/diagnostics/scheduling.py`'s
`ScheduledDiagnosticsEvaluator` is the background process that already owns
product cache refresh for every channel, including WooCommerce — it is
invoked from the order-sync runner's established loop and calls
`CommerceHubService.refresh_channel_cache`, which calls
`IncrementalReadEngine.run_manual` with the same
`WooCommerceProductReadAdapter` the manual "Refresh cache" button uses. That
adapter already writes into `DlProductCache` (the Source Product Key /
Listing resolution layer downstream is unchanged) and already tombstones
products that stop appearing in a full read (`exists = False` in
`read_engine/service.py`), which is exactly the soft-delete semantics
`product.deleted` needs — no new deletion code was required.

**What Phase 1 adds:** `ScheduledDiagnosticsEvaluator.run_once` now also
checks, per WooCommerce channel, whether any `webhook_receipts` rows are
`queued`/`retry_scheduled` for that channel
(`WebhookIngestionService.pending_woocommerce_receipt_ids`). If so, a
refresh is due *right now*, independent of the scheduled/manual polling
interval — this is the event-driven axis, kept independent of the
scheduled-polling axis per the plan's explicit requirement. After the
refresh completes, each pending receipt is marked `processed` (success) or
scheduled for retry / dead-lettered (failure) through the exact same
`WebhookIngestionService.process_receipt` state machine TapsiShop receipts
already use. No parallel identity mapping or new per-product WooCommerce
REST fetch path was invented; the webhook only ever tells the existing,
already-tested poll-and-upsert path "refresh now," and only marks itself
processed after that path actually ran.

This was chosen deliberately over adding a whole new runner process: the
order-sync runner (`orders/runner.py`) already exists and already drives
`ScheduledDiagnosticsEvaluator`, so a second background process would have
been a redundant execution boundary for the same table
(`DlProductCache`). It was also chosen over inventing a narrow per-webhook
upsert function, because that would have required a second, independently
correct mapping from WooCommerce webhook payload fields to `DlProductCache`
columns — precisely the "parallel identity mapping" the plan warns against.
The tradeoff is that a single webhook triggers a full incremental
poll-and-upsert of the channel rather than a single-row write; this is
judged acceptable for Phase 1 given WooCommerce stores are not expected to
emit product webhooks at a rate that makes this costly, and it can be
narrowed to a per-product REST fetch in a later phase without changing the
receipt/idempotency contract.

To keep this change fully outside order-sync code, it was implemented in
`app/flowhub/diagnostics/scheduling.py` (shared diagnostics due-work
evaluation, not order-sync business logic) rather than in
`app/flowhub/orders/service.py` or `app/flowhub/orders/runner.py`, neither
of which were modified.

### Product update scope guard

A `product.updated` webhook only ever refreshes the WooCommerce channel's
own cache/listing evidence. Nothing in this phase calls
`WooCommerceConnector.update_price` or any other channel's write adapter
from the webhook path — cross-channel propagation continues to happen
exclusively through the existing Draft → Review → Dry Run → Apply pipeline.

### Diagnostics

`CanonicalDiagnosticsProjector._webhook_capability` now supports
`provider in {"tapsishop", "woocommerce"}` (previously TapsiShop-only),
reading `WebhookReceipt`/`WebhookDeadLetter` evidence filtered by
`channel_id` **and** `provider` (tightened from channel-only, since a
channel id is provider-specific but the filter is now explicit).
`DiagnosticsPolicyCatalog.webhook(provider)` reports `EVENT_DRIVEN` mode for
both providers, with a per-provider environment-configurable freshness TTL
(`FLOWHUB_WOOCOMMERCE_WEBHOOK_EVIDENCE_TTL_SECONDS`). Product webhook
freshness is projected as `webhookProcessing`, which remains an
independent capability axis from `productSynchronization` (the
scheduled/manual polling safety net) — a channel can show current webhook
evidence while polling evidence is stale, or vice versa.

### Business Observability

Event types `woocommerce_webhook_received`, `woocommerce_webhook_duplicate`,
`woocommerce_webhook_signature_rejected`, `woocommerce_product_event_processed`,
and `woocommerce_webhook_processing_failed` are emitted through
`BusinessObservabilityService.emit_event` under the existing `"channels"`
domain (`BUSINESS_EVENT_DOMAINS` in `business_observability/contracts.py`
was re-read; `"channels"` already covers channel-connectivity-shaped
events, including webhook ingestion, and no other domain fit better — no
new domain was added). Exactly one event is emitted per meaningful outcome
per webhook delivery: acceptance, duplicate, signature rejection, or (once
the background processor runs) processed/failed — never one event per
internal step.

## Invariants

1. **Event-driven ≠ scheduled/manual.** The `webhookProcessing` capability
   and the `productSynchronization` capability are always evaluated and
   reported independently; neither is inferred from the other.
2. **Webhook delivery ≠ cross-channel write.** No webhook handler for any
   channel may call another channel's write adapter. WooCommerce product
   webhooks only ever refresh WooCommerce's own cache evidence.
3. **Webhook receipt ≠ successful processing.** A 200 response means the
   receipt was durably and idempotently stored, nothing more.
   `processing_state` (`queued` → `processed` / `retry_scheduled` →
   `dead_letter`) is the only source of truth for whether the underlying
   product cache was actually refreshed.
4. **Product freshness stays an independent evidence axis** per channel,
   never merged with order freshness, connection health, or any other
   channel's evidence.
5. **Retryability follows the real failure category.** A receipt's
   `error_category` is derived from the normalized classification of the
   failure that actually occurred (`classify_failure` in
   `security/upstream_errors.py`), never hardcoded. Categories in
   `TRANSIENT_ERRORS` retry with backoff up to `MAX_PROCESSING_ATTEMPTS`;
   categories in `PERMANENT_ERRORS` (including `auth_failed`, `not_found`
   and `internal_error`) dead-letter on the first attempt. An unrecognized
   category is treated as permanent, because five identical retries of a
   non-retryable failure tell the Owner nothing.
6. **Work that was never attempted must not consume an attempt.** When a
   refresh is deferred because FlowHub's own single-flight lease is already
   held (`RefreshJobAlreadyRunning` → category `refresh_in_progress`), the
   pending receipts stay `queued` and are retried on a later tick. They are
   not marked failed. Charging an attempt for work that never ran is what
   dead-lettered 13 healthy `product.updated` deliveries on 2026-08-18.
7. **Reconciliation is a distinct read operation.**
   `POST /api/v2/commerce/channels/{channel_id}/reconcile` handles the
   canonical `RETRY_RECONCILIATION` action by running the existing
   WooCommerce product-cache/read path with `job_type="reconciliation"`.
   It reuses `RefreshJobLifecycle` single-flight ownership, never resumes a
   stale pending run, preserves previously successful cache evidence on a
   failed refresh, and never processes or replays webhook receipts.

## Amendment (2026-08-18): honest failure attribution

Production evidence: 13 `product.updated` receipts for `woocommerce:primary`
dead-lettered at `attempt_count = 5`, every attempt recording
`error_category: "temporary"` and a `CHANNEL_UPSTREAM_ERROR` payload, while
the same store served `/wp-json/wc/v3/orders` with HTTP 200 throughout. Two
defects produced that, and both are now closed:

* `ScheduledDiagnosticsEvaluator._sync_products` hardcoded
  `error_category="temporary"` for every refresh failure, so retryability
  never reflected the real cause (invariant 5 above).
* A refresh blocked by an existing lease was reported as a *failed* refresh
  and relabelled `CHANNEL_UPSTREAM_ERROR` by the catch-all in
  `normalize_upstream_error`, even though no provider call had been made
  (invariants 5 and 6, plus `ADR_DIAGNOSTICS_STATE_MODEL.md`).

`normalize_upstream_error` keeps its exact public payload
(`code`/`message`/`source`/`http_status`) for contract compatibility;
`classify_failure` is the internal entry point that additionally returns
`category` and `upstream_attributable`. Those richer values are persisted
only as Advanced Evidence/refresh-job metadata and are consumed in-process by
the evaluator; they are not added to public error objects.

## Amendment (2026-08-19): narrowed to targeted per-product reads

This ADR's Decision section named the exact tradeoff being made and the
exact condition for revisiting it: "a single webhook triggers a full
incremental poll-and-upsert of the channel rather than a single-row
write... it can be narrowed to a per-product REST fetch in a later phase
**without changing the receipt/idempotency contract**." That phase has now
landed; see `ADR_CHANNEL_READ_ARCHITECTURE.md` for the full architecture.

Behind a new rollout flag (`FLOWHUB_CHANNEL_READ_TARGETED_LIGHT_ENABLED`,
**default off** -- this amendment ships the capability, enabling it live is
a separate operational decision this task does not make), the webhook path
changes as follows:

* `ScheduledDiagnosticsEvaluator` no longer treats a pending WooCommerce
  receipt as making the full-channel job due. A new sibling runner,
  `ChannelEntityWorkRunner` (`entity_work_runner.py`), links each pending
  receipt to a `DlChannelEntityWork` row and processes it with
  `WooCommerceProductReadAdapter.fetch_entity()` -- one `GET /products/{id}`
  (plus its variations, if any) instead of a full catalog poll.
* This targeted read owns **no** `DlRefreshJob` row and never contends with
  `RefreshJobLifecycle`'s channel-wide lease -- the structural fix for the
  2026-08-18 incident (Amendment above): a full-catalog job can no longer
  hold the only lease a webhook-driven refresh needs.
* **Invariant 6 still holds, strengthened.** Work that was never attempted
  still must not consume an attempt -- now enforced per targeted read
  (`entity_work.py`'s bounded `attempt_count`/`max_attempts`) rather than by
  detecting a deferred full-channel refresh.
* **The receipt/idempotency contract is exactly as promised: unchanged.**
  `webhook_receipts`, `provider_event_id` dedup, HMAC verification, and the
  `queued` -> `processed`/`retry_scheduled`/`dead_letter` state machine are
  untouched. Receipts are linked to whichever `DlChannelEntityWork`
  execution covers them (`dl_channel_entity_work_receipts`) and transition
  through the exact same `WebhookIngestionService.mark_woocommerce_receipt_processed`
  / `_failed` methods this ADR already specified -- entity_work.py is simply
  a new caller of the same state machine, not a second one.
* When the flag is off, behavior is exactly what this ADR originally
  specified -- unchanged.

## Explicitly out of scope this phase

Orders, customers, remote WooCommerce webhook management via the REST API,
any change to the live `woo.softpple.business` webhook configuration, and
`product.restored` (not a WooCommerce core topic).
