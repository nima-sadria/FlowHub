# Operational Model

## Purpose

Operational intelligence explains what FlowHub knows, how recently it knows
it, what work was attempted, and what an operator can safely do next.

## Record Families

| Record | Purpose | Authority |
| --- | --- | --- |
| Connector fact | Last verification or operation evidence | Operational status |
| Health projection | Current interpretation of recorded facts | Read model only |
| Diagnostic run | Explicit checks and repair guidance | Point-in-time evidence |
| Audit event | Who did what and with which outcome | Actor accountability |
| Operation attempt | Exact dispatch and transport result | Execution evidence |
| Confirmed change | Verified business before/after state | Business history |
| Metric sample | Bounded counter or aggregate | Performance analysis |
| Analytics projection | Scoped derived interpretation | Reporting only |

These records MUST NOT be collapsed into a single generic log.

## Failure Semantics

- Validation failure: no external call.
- Authentication/authorization failure: no unauthorized work.
- Dependency failure: preserve active local state.
- Confirmed provider rejection: operation failed.
- Ambiguous provider response: outcome unknown, reconciliation required.
- Local finalization failure after confirmed provider update: provider state
  wins; local state requires reconciliation.

Every operator-facing failure SHOULD state what happened and the safe recovery
action without exposing secrets.

## Background Work

Background jobs require durable identity, ownership/lease, cancellation,
idempotency, progress, one terminal classification, and restart-safe recovery.
Schedulers MUST NOT start merely because local Connector metadata was created.

## Current Limitations

Retention, durable diagnostic-run history, external alert transport, and
auditable report artifacts are not yet canonical runtime capabilities. They
are Owner decisions, not implied features.

