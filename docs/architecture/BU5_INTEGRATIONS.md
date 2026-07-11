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
- WooCommerce is the first implemented Channel.
- Snapp Shop and Tapsi Shop are planned read-only Channel placeholders.
- Setup does not configure connectors.
- Integration Platform is the permanent connector boundary.
- Data Layer is canonical for read models and snapshots.
- Manual WooCommerce price execution for simple products and variations is available only through Preview, Row Selection, Dry Run, Approval, Manual Execute, Read-back Verification, and Audit.
- The Write Pipeline is the only external WooCommerce write path. Stock writes, Source writes, Scheduler execution, automatic Apply, and additional marketplace writes remain disabled or deferred.
