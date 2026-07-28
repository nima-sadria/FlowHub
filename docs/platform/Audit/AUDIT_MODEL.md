# Audit Model

## Separation of Evidence

FlowHub maintains three distinct evidence families:

1. **Actor audit:** authenticated action, scope, target, and outcome.
2. **Operation ledger:** intended write, each attempt, and verification state.
3. **Confirmed history:** immutable verified business before/after values.

A successful HTTP request does not by itself create confirmed business
history.

## Audit Event

An event MUST include actor identity, effective owner scope, action, target,
outcome, timestamp, and correlation ID. Administrative scope expansion also
includes the supplied reason and authorizing policy.

Detail MUST be structured, bounded, and sanitized. Passwords, tokens, API
keys, authorization headers, raw connector settings, and unbounded payloads
MUST NOT be stored.

## Write Reliability

Security- and write-critical audit events SHOULD use a transaction boundary
that does not disappear because a later presentation step fails. Failure to
persist mandatory audit evidence MUST be visible to operators and MUST NOT be
silently represented as a fully audited success.

## Access

Audit reads require `audit.read` and owner scoping. Cross-owner access requires
approved administrative policy, explicit reason, and an audit event for the
override itself.

## Retention

Current retention and archival periods require Owner approval. Until defined,
records MUST NOT be automatically deleted by a newly introduced policy.

