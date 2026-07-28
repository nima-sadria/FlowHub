# Logging and Event Model

## Log Purposes

- Application logs diagnose runtime behavior.
- Connector events describe lifecycle and operational facts.
- Audit events establish actor accountability.
- Operation attempts establish write execution evidence.

Projection between these models is allowed; replacing one with another is not.

## Common Fields

Structured logs SHOULD include timestamp, severity, category, event name,
message, correlation ID, job/connector identity where relevant, safe error
code, and bounded metadata.

## Redaction

Redaction occurs before persistence and before API projection. Sensitive key
matching is recursive and case-insensitive. Raw request headers, credentials,
secret settings, tokens, and provider payloads MUST NOT be logged.

## Severity

- `debug`: development detail with no operator action.
- `info`: expected lifecycle event.
- `warning`: degraded or recoverable state.
- `error`: failed operation or unavailable capability.
- `critical`: integrity, security, or platform availability risk.

Severity MUST follow outcome and impact, not merely an action-name suffix.

## Correlation

One user action SHOULD carry a stable correlation ID through API handling,
jobs, connector calls, attempts, diagnostics, and audit. Correlation does not
replace stable resource or idempotency IDs.

## Frontend Logging

Frontend diagnostic ingestion, if enabled, MUST be bounded, rate-limited,
authenticated, and redacted. User-visible errors remain localized and
actionable; logs retain safe technical context.

