# Security

Please report security issues privately. Do not open a public issue with secrets,
credentials, exploit details, or customer data.

## Supported Version

The first public release branch is `main`.

## Reporting

Send a private report to the repository owner with:

- affected version or commit
- clear reproduction steps
- impact
- any logs with secrets redacted

## Security Expectations

- Manual WooCommerce price execution supports simple products and variations through the protected workflow: Preview, Row Selection, Dry Run, Approval, Manual Execute, Read-back Verification, and Audit.
- The Write Pipeline is the only external WooCommerce write path; price writes require Dry Run and Approval.
- SnappShop and TapsiShop product writes are implemented through capability-gated
  channel adapters. Protected multi-channel writes require Preview, Dry Run,
  explicit Apply approval, and per-channel result handling.
- Source writes and automatic Apply remain disabled. Marketplace order polling,
  reconciliation, and pending webhook processing run in the separate
  `order-sync-runner` process under atomic per-channel leases.
- A webhook receipt or reconciliation page commits normalized domain state,
  checkpoint state, and the final active-lease guard as one transaction.
- Maintenance mode and role-based authorization remain enforced for write workflow actions.
- Secrets are write-only in connector settings responses.
- Logs redact secret-like values.
- Backend-only ingestion endpoints require protected access or remain disabled.
