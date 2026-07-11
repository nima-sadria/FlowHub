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
- Stock writes, Source writes, Scheduler execution, automatic Apply, and additional marketplace writes remain disabled or deferred.
- Maintenance mode and role-based authorization remain enforced for write workflow actions.
- Secrets are write-only in connector settings responses.
- Logs redact secret-like values.
- Backend-only ingestion endpoints require protected access or remain disabled.
