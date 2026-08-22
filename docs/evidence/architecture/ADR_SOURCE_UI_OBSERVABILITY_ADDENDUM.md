# ADR-SOURCE-001-A1: Distinguish Unexecuted Diagnostics from Failures

**Status:** Proposed
**Date:** 2026-08-05
**Decider:** FlowHub Owner
**Amends upon acceptance:** `ADR-SOURCE-001`
**Related:** `SOURCE_ACQUISITION_DESIGN.md`, `PRICING_UI_CONTRACT.md`

## Context

`ADR-SOURCE-001` requires shared typed Stages and observable fail-closed
behavior, but it does not explicitly distinguish a failed check from a check
that did not run. Treating both as a failure gives the operator a false cause;
for example, a file check skipped after a TLS failure is not evidence that the
file is missing.

Freshness is also time-dependent. Storing `stale` as a historical Stage outcome
would mutate the meaning of immutable execution evidence as time passes.

## Decision

Upon acceptance, add this Core Invariant to `ADR-SOURCE-001`:

> **15.** A check that has not run is presented distinctly from a check that
> failed. Absence of evidence is never rendered as evidence of failure or
> success.

Every Stage exposes two independent values:

```text
execution_status:
  not_run | pending | running | passed | failed | skipped | not_applicable

freshness:
  current | stale | unknown
```

Historical execution outcomes are immutable. Freshness is a projection derived
from the result timestamp, current comparison cohort, and freshness policy.

## Consequences

- A gated chain identifies the first actual failure and does not manufacture
  downstream failures.
- Provider-inapplicable checks are explicit and do not look incomplete.
- A previously passing check may become stale without becoming failed.
- Config, Binding, or Execution Policy changes invalidate the current evidence
  projection without rewriting prior Stage results.
- API and UI fixtures must cover every execution and freshness value.

## Acceptance Criteria

- When one required Stage fails, every later applicable Stage prevented by that
  gate is `skipped`.
- A Stage excluded by provider capability or plan is `not_applicable`.
- A new Config, Binding, or Execution Policy cohort initially projects
  `not_run` and `unknown` freshness while preserving prior evidence.
- Old passing evidence may project `stale`, but its stored execution result
  remains `passed`.
- The API and interface render `failed`, `skipped`, `not_run`, and
  `not_applicable` as different operational states.
