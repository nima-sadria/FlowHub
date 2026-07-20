# FlowHub v1.2 Stable Release Notes

The official stable release registration is documented in
[docs/releases/FLOWHUB_V1.2_STABLE.md](docs/releases/FLOWHUB_V1.2_STABLE.md).

- **Status:** Stable
- **Approved commit:** `4a02fbbcf25f0d82d05f7dc5f0f1dd3efa322a0c`
- **Production use:** Personal/Internal approved
- **Commercial deployment:** Requires a Handsontable commercial license

The capability notes below include the original 1.0 baseline and remain part of
the historical release record.

## Included capabilities

- Nextcloud/OnlyOffice spreadsheet Sources through authenticated WebDAV.
- Source test, file browse, worksheet selection, column mapping, manual read,
  source read quota, and validation.
- WooCommerce Channel test and manual cache refresh for simple products, variable
  parents, and variations.
- Immutable Preview, row selection, Dry Run, Approval, manual price Apply,
  read-back verification, and audit.
- Protected single-product multi-channel price editor with side-by-side
  WooCommerce, SnappShop, and TapsiShop price review, no-write Dry Run,
  explicit Approval/Apply, per-channel results, stale-state conflict checks,
  and audit records.
- Durable TapsiShop webhook ingestion with channel-specific webhook token
  authentication, requestId idempotency, minimized payload storage, retry and
  dead-letter processing state, and TapsiShop-compatible success responses.
- Production order synchronization runner for enabled marketplace channels:
  SnappShop order event polling, order reconciliation, and pending TapsiShop
  webhook receipt processing run in a separate worker process with
  channel-scoped leases and sanitized health visibility.
- Database-backed login throttling with explicit trusted-proxy configuration.
- PostgreSQL-inclusive backups, manifest validation, explicit restore, and
  rollback documentation.

## Safety model

Only the Write Pipeline may update WooCommerce, and only after Dry Run and
Approval. Multi-channel marketplace price writes are protected by the Products
Dry Run, Approval, and explicit Apply workflow. Sources remain read-only. Stock
writes and automatic Apply are not included.

## Upgrade and rollback

The migration head is `FLOWHUB_019`. Create `flowhub backup` before upgrading;
use [docs/release/ROLLBACK.md](docs/release/ROLLBACK.md) for a failed upgrade.

The current UI release covers Application Shell, Dashboard, Products, Orders,
Sources, Channels, Activity, Data Quality, Diagnostics, Settings, User
Management, Rate Limits, Setup Wizard, and Login. Setup progresses through
Workspace, Database, Owner, and Review.

## Deferred after 1.0.0

- CSV and Google Sheets Sources
- WooCommerce stock updates
- Additional marketplace Channels beyond WooCommerce, SnappShop, and TapsiShop
