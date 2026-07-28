# Platform Test Matrix

## Required Contract Tests

| Domain | Required scenarios |
| --- | --- |
| Authentication | valid, invalid, expired, revoked, rate-limited |
| Authorization | each canonical capability; read-only UI; local 403 handling; cross-owner reason |
| Connector | candidate validation; failed verification preserves active config; secret masking |
| Health | never checked, healthy, degraded, failed, stale; GET performs no external call |
| Diagnostics | local run, explicit bounded probe, partial checks, sanitized failure |
| Source | one acquisition, provenance, malformed input, stale source, cancellation |
| Workspace | immutable Snapshot, deterministic Review, explicit selection, checksum invalidation |
| Apply | no write before confirm, exactly-once submit, stale rejection, per-operation outcomes |
| Reconciliation | unknown outcome resolved by read; no blind write retry |
| Cache | verified-only mutation; freshness and trust state |
| Audit/logging | actor/scope/correlation; secret redaction; evidence separation |
| Metrics/analytics | scope, windows, reset semantics, unknown/partial outcomes |
| Frontend | loading, empty, error, retry, disabled reason, localization, accessibility |

## Validation Gates

Every implementation commit runs:

1. focused tests for changed behavior;
2. relevant backend or frontend suite;
3. frontend production build when frontend contracts change;
4. i18n validation when user-visible copy changes;
5. migration validation when persistence changes;
6. `git diff --check`.

Provider-write tests use test doubles or disposable environments. They MUST NOT target
Production.

## Traceability

Tests SHOULD cite the canonical rule or decision ID they protect. Historical
WooPrice test names are reference evidence only and are not FlowHub acceptance
criteria.
