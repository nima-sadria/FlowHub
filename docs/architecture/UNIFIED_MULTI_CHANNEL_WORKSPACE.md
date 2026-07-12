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
  -> explicit ReviewSelection
  -> idempotent ApplyJob with per-change ApplyJobItems
  -> independent Channel connector batches
  -> verified ChannelCache patch or verification-required state
  -> append-only UnifiedAuditEntries
```

Source Workspace creation delegates the single external read to the existing protected Nextcloud Workspace preview workflow and then materializes its immutable result. Editing, Draft saves, Review, Apply, retries, and audit reads never read the original source. Manual Workspace creation reads only FlowHub cache records.

## Identity and channel isolation

`CanonicalProduct -> Listing -> WorkspaceChannel` is the only supported relationship. A Listing uses a connector-declared primary identity. SKU and name are secondary evidence and are never silently promoted to permanent mappings. Multiple Listings in the same marketplace Channel are stored as separate rows and remain independently selectable.

Global processing never reads Channel caches. Channel Review reads one Listing cache and its matching capability strategy only. No service compares one Channel with another or derives a target from another Channel's Current value.

Variable parents are grouping-only. Simple products and variations may be edited when the effective Channel capability permits the field.

## Immutability and concurrency

Snapshot content, Snapshot rows, Mapping revisions, Draft revisions and changes, Review items/cache captures, and audit entries reject ORM update and delete operations. The additive migration does not provide a destructive downgrade. Business-history retention is indefinite.

Draft saves require the current Draft version and return `409 DRAFT_VERSION_CONFLICT` on obsolete writes. Every save creates a content-checksummed revision; restoring creates a new revision. Apply verifies the current Snapshot, current Draft revision, Review state, captured cache versions/checksums, mapping versions, capability versions, currency configuration, explicit selection, confirmation, permission, and idempotency key. Apply locks only selected Listings in the Workspace.

## Currency

Currency and pricing unit are separate. Configuration precedence is Channel capability override, Source override, then global default. IRR requires an explicit `RIAL` or `TOMAN` unit. Toman is never represented as an ISO currency. Review records raw, original, normalized, conversion-factor, rule, context, and configuration-reference values.

Administrators configure the global unit with `server.currency_unit` through Settings. Existing IRR installations without an explicit unit receive a validation error instead of inferred conversion.

## Cache and Apply safety

Current values are mutable `ChannelCache` state with explicit version/checksum metadata. Draft targets never mutate Current. A Review captures each participating Listing cache version and Mapping/capability versions. Any relevant change makes Apply stale and requires Review regeneration without source reread.

WooCommerce Apply uses the existing price-write adapter and read-back verification. SnappShop batches at most 50 Listing updates and performs targeted read-back. Cache values are patched only when verification proves the resulting values. External partial success is recorded per Listing/change and is never represented as cross-channel atomicity.

## Handsontable

The Workspace route is code-split and uses Handsontable row/column virtualization, nested Channel headers, keyboard navigation, filtering, multi-column sorting, safe copy/paste, and inline editing. Current, identity, SKU, Mapping, and unsupported cells are read-only. Cell status includes a code, textual tooltip, and shape indicator.

Handsontable is dual-licensed. The repository uses the vendor's non-commercial/evaluation key for non-production development. A deployment whose use is commercial must supply and comply with an applicable Handsontable commercial license before production deployment.

## Compatibility

Existing `/api/v2/workspace`, Preview, legacy Dry Run, Write Pipeline, Products price editor, maintenance protections, WooCommerce behavior, and audit behavior remain available. The new API is additive under `/api/v2/unified-workspaces`. Existing source behavior is not silently changed.
