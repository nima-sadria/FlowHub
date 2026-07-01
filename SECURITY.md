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

- Write execution is disabled in the first release.
- Secrets are write-only in connector settings responses.
- Logs redact secret-like values.
- Backend-only ingestion endpoints require protected access or remain disabled.
