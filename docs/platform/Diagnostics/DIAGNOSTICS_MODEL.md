# Diagnostics Model

## Purpose

Diagnostics explain configuration, capability, freshness, dependency, and
operational failures. They are read-first and repair-guided.

## Check Contract

Each check records:

- check name, target, category, and evidence source;
- status and failure class;
- severity;
- safe message and recommended action;
- start/completion time and duration;
- whether an external call occurred;
- bounded details and skipped reason.

Unsupported or not-configured checks are explicit, not generic failures.

## Execution Rules

- Normal diagnostics status reads use local persisted facts.
- Explicit refresh/test actions MAY perform a bounded external probe.
- External probes require authorization, timeout, cancellation, sanitized
  errors, and durable result recording.
- A diagnostic probe MUST NOT mutate business data.
- Failure of one check SHOULD preserve other completed results.

## History

The active API currently exposes an empty diagnostic history projection rather
than durable run history. Adding durable retention is an Owner-level data and
retention decision.

## Repair

Repair guidance distinguishes safe read-only verification from a mutating
repair. Mutating repair requires a separately authorized action and MUST NOT be
executed as a side effect of diagnostics.

