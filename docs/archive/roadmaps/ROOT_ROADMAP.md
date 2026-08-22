# Roadmap

## Current

- **FlowHub v1.2 Stable** is the approved stable release at commit
  `4a02fbbcf25f0d82d05f7dc5f0f1dd3efa322a0c`.
- The v1.2 architecture is frozen. Normal feature work follows
  **Feature Design → Implementation → Targeted Feature Audit → Merge → Next
  Feature**. Full architecture audits are reserved for intentional
  architecture-changing releases.

- First public release polish.
- Self-hosted Docker deployment.
- Setup Wizard with server profile, database verification, admin account, and finish.
- Connector configuration under Settings.
- Integration Platform and Unified Logging Platform.
- Read-only external connector behavior.

## Planned

- Additional connectors: Shopify, Magento, ERP, CSV, Google Sheets, custom APIs.
- Advanced Data Layer refresh controls.
- Live Tail for logging.
- Deeper telemetry dashboards.
- Approved write flows and future changes must preserve the v1.2 invariants.
  Architecture changes require explicit Owner approval.

## Not Planned For First Release

- Apply execution.
- Scheduler execution.
- Automatic pricing.
- WooCommerce writes.
- Spreadsheet writes.
