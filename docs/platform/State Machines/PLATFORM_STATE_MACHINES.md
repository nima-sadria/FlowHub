# Platform State Machines

## Connector

```text
absent -> candidate_configured -> verification_running
verification_running -> verified_candidate | verification_failed
verified_candidate -> active
active -> healthy | degraded | stale | failed | disabled | replaced
```

Verification failure cannot replace active configuration.

## Workspace

```text
empty -> snapshot_ready -> drafting -> review_ready -> selection_ready
selection_ready -> awaiting_confirmation -> applying
applying -> completed | partially_completed | reconciliation_required | failed
```

Any upstream identity or checksum change invalidates downstream states.

## Apply Job

```text
created -> queued -> running
running -> completed | partially_completed | reconciliation_required
running -> failed | cancelled
```

Cancellation stops undispatched work. It does not reclassify already-dispatched
uncertain operations.

## Write Operation

```text
requested -> started
started -> confirmed | failed | outcome_unknown
outcome_unknown -> reconciling
reconciling -> confirmed | failed | outcome_unknown
requested -> not_attempted
```

Only `confirmed` updates authoritative cache and confirmed history.

## Health

```text
never_checked -> healthy | degraded | failed
healthy | degraded | failed -> stale
stale -> healthy | degraded | failed
```

Health state records evidence age and source. A read does not itself change
state.

## Diagnostics

```text
idle -> running -> completed | completed_with_warnings | failed
```

Skipped and unsupported checks are not failures. Explicit external checks are
distinguished from local recorded-fact checks.

## Alert

```text
detected -> classified -> surfaced -> acknowledged_or_cleared
```

FlowHub currently derives alert-like states from facts. A durable alert entity
or external notification transport requires an Owner decision.

