# API Contracts

## General Rules

- Active product APIs use `/api/v2` except public liveness and authentication
  endpoints with established compatibility contracts.
- Requests and responses MUST use stable identifiers, not display labels.
- Mutations MUST validate authentication, capability, resource scope, and
  stale/concurrency guards.
- Errors MUST use an HTTP status plus a safe actionable message; stable error
  codes SHOULD be added where clients need branching behavior.
- Secrets MUST never be returned after configuration.
- List endpoints MUST define pagination, ordering, and partial-data behavior.
- Long-running work MUST expose durable job identity and terminal state.

## Health and Diagnostics

- `GET /api/health` is public minimal liveness only.
- Authenticated diagnostics and health reads return recorded facts without
  external probes.
- External verification occurs only through an explicit action endpoint,
  subject to authorization, timeout, and sanitized persistence.
- A response MUST disclose whether an external call was performed when the
  distinction affects operator interpretation.

## Workspace

Workspace contracts MUST bind:

- Workspace and owner identity;
- Snapshot and Draft revision identity;
- Review identity;
- selected item identities;
- checksum;
- Apply job and idempotency identity;
- per-operation outcome.

The API MUST reject stale, missing, unauthorized, empty, or checksum-mismatched
scope. Current legacy and unified route details are documented in
`docs/api/`; those documents are implementation evidence.

## Connector Configuration

Connector settings are split into public values and write-only secrets.
Candidate configuration MAY be stored as inactive local metadata, but it MUST
NOT replace active runtime configuration until verification succeeds. Test and
activation semantics MUST be explicit rather than inferred from a generic
successful HTTP response.

## Error Families

| Family | Client behavior |
| --- | --- |
| validation | Correct input; do not retry unchanged |
| unauthorized | Re-authenticate only when identity is invalid |
| forbidden | Keep session; explain missing capability |
| not found | Remove stale navigation or refresh authoritative list |
| conflict/stale | Refresh or regenerate the dependent artifact |
| rate limited | Respect retry guidance |
| dependency unavailable | Preserve local state and allow explicit retry |
| outcome uncertain | Reconcile; never repeat a write blindly |

## Compatibility

API evolution MUST document compatibility, deprecation, migration, and test
gates. Provider-specific fields MAY exist in adapter contracts but MUST NOT
leak into platform-generic entities without a typed extension boundary.

