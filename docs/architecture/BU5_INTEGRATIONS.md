# Legacy Compatibility: BU5 Integration Notes

This file is retained so historical links do not break.

The current first-release connector architecture is documented in:

- `docs/architecture/CURRENT_ARCHITECTURE.md`
- `docs/architecture/INTEGRATION_PLATFORM.md`
- `docs/architecture/DATA_LAYER_ARCHITECTURE.md`

Current behavior:

- Connector configuration belongs in Settings.
- Commerce Hub separates Sources from Channels in product terminology.
- Channels are implemented internally by destination connectors.
- WooCommerce, SnappShop, and TapsiShop are implemented Channels.
- SnappShop and TapsiShop product writes are implemented behind declared
  connector capabilities. FlowHub backend APIs remain the only UI boundary,
  and external writes still require the protected Preview/Dry Run/explicit
  Apply workflow.
- Setup does not configure connectors.
- Integration Platform is the permanent connector boundary.
- Data Layer is canonical for read models and snapshots.
- Manual WooCommerce price execution for simple products and variations is available only through Preview, Row Selection, Dry Run, Approval, Manual Execute, Read-back Verification, and Audit.
- The Write Pipeline remains the only external WooCommerce write path. Source
  writes and automatic Apply remain disabled. SnappShop and TapsiShop product
  writes execute only through their capability-gated channel adapters after
  explicit approval; they do not make Channel data canonical.
- Marketplace order synchronization runs in the separate
  `order-sync-runner` process. It polls SnappShop events, reconciles readable
  channel orders, and processes pending TapsiShop webhook receipts.
- The runner uses one atomic database lease per channel. Heartbeat and cursor
  commits require the current owner and a strictly unexpired lease. Cursor
  progress is rolled back when ownership is lost or the lease expires.
