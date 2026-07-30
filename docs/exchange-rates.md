# FlowHub exchange rates

FlowHub treats exchange rates as a provider-independent platform capability.
The header, user preferences, scheduler, persisted snapshots, and future pricing
consumers use normalized models rather than Navasan response objects.

## Navasan contract

The implementation is based on the official
[Navasan Web Service Guide](https://www.navasan.tech/webserviceguide/).
The guide documents `http://api.navasan.tech`; the same host was verified to
serve HTTPS and FlowHub accepts only `https://api.navasan.tech`.

FlowHub uses:

- `GET /latest/?api_key=...` for one all-items refresh.
- `GET /usage/?api_key=...` for centrally budgeted usage reconciliation.
- `value`, `change`, Unix `timestamp`, and Persian `date`.
- HTTP 400, 401, 422, 429, and 503 normalized into safe internal errors.

Decimal strings are parsed with Python `Decimal`. Raw response objects, error
bodies, URLs containing query strings, and the API key never leave the provider
adapter.

## Provider abstraction and normalized identity

Adapters implement `ExchangeRateProvider`. `ExchangeRateProviderRegistry`
constructs the active adapter from an allowlisted provider type. Adding another
provider requires an adapter, registration, and canonical mappings; it does not
require changes to the header, preferences, scheduler, or snapshot consumers.

Definitions preserve:

- provider item identifier, such as `usd_sell`;
- canonical identity, such as `USD_TEHRAN_SELL`;
- localized names;
- market classification and buy/sell side;
- returned unit.

Selections also retain the canonical identity so a future provider can satisfy
an existing preference where an equivalent mapping exists.

## Persistence and future pricing

`FLOWHUB_021` creates provider configuration, definitions, immutable snapshots,
ordered per-user selections, and fetch-run diagnostics. `FLOWHUB_022` adds
scheduler state, atomic lock ownership, authoritative budget counters, provider
usage reconciliation, canonical selection identity, and immutable snapshot
classification/fingerprints.

Snapshots have stable UUIDs, Decimal values, external and canonical identities,
provider and fetch timestamps, classification, side, unit, and source status.
Refreshes append snapshots; they do not overwrite current or historical rows.
Malformed and partial responses never erase last-known-good values.

Historical snapshots are retained. No automatic cleanup is enabled. A future
retention job must exclude snapshots referenced by pricing calculations, dry
runs, approvals, or audit records before deletion is allowed.

Future pricing rules must reference `ExchangeRateSnapshot.id`. Pricing must read
persisted snapshots and must not contact a provider. Dry Run → Review → Approval
→ Apply governance remains unchanged; this subsystem does not modify products
or channel prices.

## Scheduler ownership and restart behavior

Scheduled refresh is owned only by the dedicated process:

```text
python -m app.flowhub.exchange_rates.runner
```

Docker Compose runs it as `exchange-rate-runner`. The API process never starts
the loop. The runner polls persisted policy and records its ID, state, and
heartbeat.

`refreshes_per_day` is converted to `86400 / refreshes_per_day`. The next UTC
run is persisted. After downtime, one due refresh may run and the next time is
calculated from the current completion time; missed intervals are not replayed,
so restarts cannot create a catch-up storm.

Manual and scheduled refreshes use the same atomic conditional database update
on `refresh_lock_until` and `refresh_lock_token`. Only the lock owner can release
the lease. This is safe across separate application workers and runner
processes. Authentication failure blocks further scheduled attempts until
credentials are changed. Other failures use bounded 5/10/20-minute backoff and
then return to the configured interval.

## Authoritative request budget

Every provider request—scheduled refresh, manual refresh, Test Connection,
usage synchronization, and any retry—must reserve budget before external I/O.
The default policy is:

```text
configured daily limit = 120
safety reserve = 10
safe routine budget = 110
usage reconciliation allowance = 1
maximum configured refreshes per day = 109
```

The persisted counter records attempts before I/O and completions after a
provider response. Day boundaries use FlowHub’s configured IANA timezone.

```text
effective usage = max(internal attempts, provider-reported daily usage)
safe remaining = max(0, configured limit - reserve - effective usage)
```

The higher value is always authoritative. Usage checks are themselves budgeted.
`/usage/` is cached for 24 hours; the settings page reads persisted diagnostics
and does not call Navasan. A failed usage check preserves the last successful
provider counters and marks reconciliation stale or failed.

## Secrets and transport security

The preferred credential is the environment secret:

```text
FLOWHUB_NAVASAN_API_KEY=
```

The existing Super Admin connector-settings workflow can store the same secret
under `exchange_rates.navasan.api_key`; environment configuration takes
precedence. Administrative responses expose only configured/not-configured and
`********`. The value is excluded from audit events, snapshots, fetch
diagnostics, frontend state, logs, traces, and exception messages.

Only the fixed provider registry URL is accepted. Arbitrary schemes, hosts,
localhost, private networks, metadata services, and HTTP downgrades cannot be
configured.

## User and administrator behavior

Users select exactly three ordered, distinct active rates at
`/settings/exchange-rates`. The header reads authenticated FlowHub cache APIs
only. Fresh, stale, unavailable, and disabled states retain layout and expose
freshness in accessible labels/tooltips. Narrow layouts use a compact three-rate
menu rather than silently removing the feature.

Only Owner/Super Admin users can configure credentials and provider policy,
test the connection, reconcile usage, inspect diagnostics, or request a manual
refresh. Backend authorization is independent of UI visibility. Configuration,
connection tests, usage synchronization, and manual refresh create audit
events; ordinary cached header reads do not.

## Local verification

1. Configure `FLOWHUB_DATABASE_URL`, `FLOWHUB_JWT_SECRET`, and optionally
   `FLOWHUB_NAVASAN_API_KEY`.
2. Run `alembic -c alembic_flowhub.ini upgrade head`.
3. Start the API, frontend, and the dedicated exchange-rate runner.
4. Verify `/settings/exchange-rates` with Owner and normal-user accounts.
5. Confirm browser traffic stays under `/api/v2/exchange-rates/*` and never
   targets `api.navasan.tech`.
6. Run backend tests, migration tests, frontend tests, and `npm run build`.

Automated tests use fake adapters and consume no real Navasan quota.
