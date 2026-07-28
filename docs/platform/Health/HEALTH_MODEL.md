# Health Model

## Endpoint Classes

`GET /api/health` is minimal public liveness: process status, environment, and
version only. It performs no dependency probe.

Authenticated health and diagnostics surfaces summarize recorded Connector,
cache, queue, and operation facts. Explicit refresh endpoints are separate.

## Dimensions

Health is multidimensional:

- configuration completeness;
- credential verification;
- external API evidence;
- read and write capability;
- last successful Source/Channel operation;
- cache freshness and trust;
- webhook/polling/queue state;
- unresolved reconciliation work.

Capability support is not health. A Connector can be healthy while a
capability is unsupported.

## States

Canonical presentation states are `unknown`, `healthy`, `degraded`, `failed`,
and `stale`. Exact domain states MAY be retained internally with an explicit
mapping.

Every state includes evidence time, evidence source, reason code, actionability,
and recommended next action where relevant.

## Probe Boundary

GET health reads MUST NOT call external providers. A user-triggered refresh MAY
make one bounded call per requested Connector, cache the sanitized result, and
disclose `external_call_performed`.

