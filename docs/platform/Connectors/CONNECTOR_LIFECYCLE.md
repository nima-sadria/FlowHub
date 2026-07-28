# Connector Lifecycle

## Model

A Connector Definition describes an adapter type. A Connector Instance binds
that definition to owner-scoped configuration. Candidate, active, and recorded
health state are separate concepts.

## Lifecycle

```text
absent
  -> candidate_configured
  -> verification_running
  -> verified_candidate | verification_failed
  -> active
  -> healthy | degraded | stale | failed | disabled | replaced
```

## Verification and Activation

1. Normalize and validate candidate settings.
2. Store secrets only in the approved secret boundary.
3. Perform one bounded explicit verification.
4. Sanitize and durably record verification facts.
5. On failure, preserve active runtime configuration.
6. On success, atomically activate the verified candidate.
7. Invalidate dependent caches and record actor audit.

Local Integration Platform metadata MAY be created without an external probe
only when it remains inactive/read-only and is clearly presented as
unverified. Enabling scheduler or write capability requires verified runtime
configuration.

## Adapter Requirements

- normalized authentication and timeout behavior;
- typed capabilities;
- stable provider and instance identity;
- explicit read/write classification;
- rate-limit and retry metadata;
- sanitized errors;
- correlation identity;
- bounded cancellation;
- no business-layer direct HTTP access.

## Source and Channel Separation

Source connectors acquire proposed data. Channel connectors expose observed
external state and optional writes. One instance MUST NOT silently serve both
roles. Mappings connect identities without collapsing lifecycles.

## Health

Normal Connector health reads summarize persisted verification and operation
facts. Explicit refresh/test actions MAY make one bounded provider call and
MUST disclose and record that call. Capability support and health are separate.

## Replacement and Deletion

Replacement preserves the prior active configuration until candidate
activation succeeds. Deletion removes FlowHub configuration only unless an
explicit provider-side delete operation is separately specified and approved.
Historical events, attempts, and audit evidence MUST retain stable connector
identity after deletion.

