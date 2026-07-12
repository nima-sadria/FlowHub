# FlowHub v1.2 Unified Multi-Channel Workspace

## Runtime architecture

The production flow is:

```text
Source read or Manual Products selection
  -> immutable WorkspaceSnapshot and SnapshotRows
  -> versioned normalization/global validation metadata
  -> canonical product and Listing rows
  -> virtualized Workspace Grid
  -> immutable DraftRevision and DraftRevisionChanges
  -> deterministic Review and per-Listing cache-version captures
  -> versioned canonical ReviewSelection checksum
  -> global `(channel_id, listing_id)` locks in deterministic order
  -> immutable provider-neutral Write Pipeline intents and durable dispatch attempts
  -> shared Write Pipeline limiter and independent provider adapters
  -> exact read-back verification or explicit reconciliation-required outcome
  -> verified-only ChannelCache patch
  -> append-only UnifiedAuditEntries
```

Source Workspace creation delegates the single external read to the existing protected Nextcloud Workspace preview workflow and then materializes its immutable result. Editing, Draft saves, Review, Apply, retries, and audit reads never read the original source. Manual Workspace creation reads only FlowHub cache records.

## Identity and channel isolation

`CanonicalProduct -> Listing -> WorkspaceChannel` is the only supported relationship. A Listing uses a connector-declared primary identity. SKU and name are secondary evidence and are never silently promoted to permanent mappings. Multiple Listings in the same marketplace Channel are stored as separate rows and remain independently selectable.

Global processing never reads Channel caches. Channel Review reads one Listing cache and its matching capability strategy only. No service compares one Channel with another or derives a target from another Channel's Current value.

Variable parents are grouping-only. Simple products and variations may be edited when the effective Channel capability permits the field.

## Immutability and concurrency

Snapshot content, Snapshot rows, Mapping revisions, Draft revisions and changes, Review items/cache captures, and audit entries reject ORM update and delete operations. The additive migration does not provide a destructive downgrade. Business-history retention is indefinite.

Draft saves require the current Draft version and return `409 DRAFT_VERSION_CONFLICT` on obsolete writes. Every save creates a content-checksummed revision; restoring creates a new revision. A confirmed selection is serialized canonically, retained in immutable audit, and SHA-256 bound to Workspace, Snapshot, Draft Revision, Review, Channel, Listing, Review Item, field, and selection version. Apply reloads that scope and returns `409 APPLY_SELECTION_CHECKSUM_MISMATCH` before dispatch if it changed.

Listing locks are global across Workspaces by `(channel_id, listing_id)` and acquired in that stable order. Expired locks are atomically replaced only when their owning job is terminal; an unfinished or reconciliation-required owner remains blocking even after wall-clock expiry. Mapping decisions and cache synchronization use the same lock protocol. After locks are acquired, Apply rechecks Draft, Review ruleset, mapping, cache, capability, currency, and selected-scope dependencies before persisting dispatch intent.

## Currency

Currency and pricing unit are separate. Configuration precedence is Channel capability override, Source override, then global default. IRR requires an explicit `RIAL` or `TOMAN` unit. Toman is never represented as an ISO currency. Review records raw, original, normalized, conversion-factor, rule, context, and configuration-reference values.

Administrators configure the global unit with `server.currency_unit` through Settings. Existing IRR installations without an explicit unit receive a validation error instead of inferred conversion.

## Cache and Apply safety

Current values are mutable `ChannelCache` state with explicit version/checksum metadata. Draft targets never mutate Current. A Review captures each participating Listing cache version and Mapping/capability versions. Any relevant change makes Apply stale and requires Review regeneration without source reread. Apply also rejects a cache older than `workspace.channel_cache_max_age_minutes` (default 60, bounded to 1–10,080 minutes), even when its checksum is unchanged.

Unified Workspace never calls a provider adapter. It creates typed immutable intents for `WritePipelineService`, which is the sole external write authority and owns limiter use, durable pre-dispatch attempts, provider dispatch, and result recording. Provider adapters translate protocol and transport only. WooCommerce uses the existing price adapter; SnappShop batches at most 50 updates.

Only `VERIFIED_APPLIED` means success. HTTP acceptance without an exact Channel, external Listing/variation identity, normalized value, and current-attempt read-back becomes `RECONCILIATION_REQUIRED`; it does not patch cache or emit success audit. Providers without native idempotency use a stable persisted item key plus read-before-retry reconciliation. An uncertain attempt is never blindly redispatched, and its global Listing lock remains until controlled reconciliation verifies the target.

## Handsontable

The Workspace route is code-split and uses Handsontable row/column virtualization, nested Channel headers, keyboard navigation, filtering, multi-column sorting, safe copy/paste, and inline editing. Current, identity, SKU, Mapping, and unsupported cells are read-only. Cell status includes a code, textual tooltip, and shape indicator.

Handsontable is dual-licensed. Development/test may use the vendor's evaluation mode. Production reads a purchased key from `VITE_HANDSONTABLE_LICENSE_KEY`; no key is committed. When the key is absent, the production Grid is disabled with an explicit configuration error. A valid commercial Handsontable license is required before Production.

## Migration guarantees

`FLOWHUB_016` is an additive migration from `FLOWHUB_015`. Its SQLite and PostgreSQL DDL is frozen in a migration-local module and never imports live ORM metadata. Historical snapshots, revisions, review dependencies, currency-profile versions, dispatch attempts/events, and audit entries have database update/delete rejection triggers on both supported databases. Currency configuration changes create new immutable version rows. The downgrade is deliberately non-destructive.

## Compatibility

Existing `/api/v2/workspace`, Preview, legacy Dry Run, Write Pipeline, Products price editor, maintenance protections, WooCommerce behavior, and audit behavior remain available. The new API is additive under `/api/v2/unified-workspaces`. Existing source behavior is not silently changed.
