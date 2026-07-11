# Order Synchronization

FlowHub stores marketplace orders in normalized channel tables while preserving
the raw event lineage separately. The integration layer owns provider
communication; the Data Layer owns normalized order records.

## Providers

- SnappShop: polling order events, order details, and order history are consumed
  through the marketplace connector. Cursor checkpoints are persisted per
  channel and source.
- TapsiShop: accepted webhook receipts are consumed after durable
  acknowledgement. The HTTP webhook handler does not perform business effects.

## Idempotency

Provider event identity is scoped by `channel_id` plus provider event/request
ID. Inventory effects are scoped by channel, source event, provider item, and
effect type. Replayed events do not create duplicate proposed quantity effects.

## Inventory

Task 9 does not mutate canonical inventory. Purchase and cancellation events
create `channel_inventory_effects` rows with `state=proposed` and
`applied_to_canonical_inventory=false` for later policy processing.

## Privacy

Order APIs return normalized order and item details. Customer phone, national
ID, and delivery address are not exposed by default. Stored raw provider
payloads are minimized to hashes and operational summaries; customer references
are hashed when available.

## Scheduling

Order synchronization is production-wired through a separate worker process:

```bash
python -m app.flowhub.orders.runner
```

The Docker Compose service is `order-sync-runner`. The FastAPI application does
not start this loop, so API multi-worker deployments do not create duplicate
schedulers. The runner discovers enabled channels from Integration Platform
connector instances and applies connector capabilities before doing work:

- `orders.events.poll`: SnappShop order-event cursor polling.
- `orders.read`: reconciliation from provider order APIs.
- `orders.webhook.receive`: pending TapsiShop webhook receipt processing.

One channel failure is recorded as an order-sync event and does not stop other
channels. Normal runner logs and Integration Platform events must not include
credentials, authorization headers, customer phone numbers, national IDs, or
delivery addresses.

## Configuration

Global defaults are environment variables. Per-channel connector settings with
the same operational names, such as `order_sync_poll_interval_seconds`, override
the global defaults for that channel.

- `FLOWHUB_ORDER_SYNC_ENABLED`
- `FLOWHUB_ORDER_SYNC_RUNNER_POLL_SECONDS`
- `FLOWHUB_ORDER_SYNC_POLL_INTERVAL_SECONDS`
- `FLOWHUB_ORDER_SYNC_RECONCILE_INTERVAL_SECONDS`
- `FLOWHUB_ORDER_SYNC_LEASE_SECONDS`
- `FLOWHUB_ORDER_SYNC_MAX_PAGES`
- `FLOWHUB_ORDER_SYNC_RECONCILE_PAGE_SIZE`
- `FLOWHUB_ORDER_SYNC_WEBHOOK_BATCH_SIZE`
- `FLOWHUB_ORDER_SYNC_OPERATION_TIMEOUT_SECONDS`

## Leases

The runner uses `channel_order_sync_checkpoints` for both source checkpoints and
channel-scoped leases. The lease row uses `source=__channel_lease__` and stores
`lock_owner`, `locked_at`, `lease_expires_at`, `lease_heartbeat_at`, and
`last_run_id`. Source-specific rows keep cursor, interval, last run, last
success, last failure, and next-run metadata.

Lease acquisition is an atomic conditional database update. It succeeds only
when no active lease exists or the previous lease has expired. Heartbeat and
checkpoint commits use one database predicate requiring the expected lease row,
matching owner, a non-null expiry, and `lease_expires_at` strictly later than
current UTC. A failed predicate rolls back pending normalized records and cursor
progress and records a sanitized `lease_expired` or `lease_lost` failure.

Release verifies ownership with an affected-row check. An expired owner may
clear its own still-unreplaced lease during cleanup. It cannot release a newer
worker's lease because the owner must still match. Polling and reconciliation
share the same channel lease, and a page cursor advances only when the page and
active-lease guard commit in the same transaction.

## PostgreSQL Lease Tests

The concurrency suite uses independent SQLAlchemy sessions against an isolated
schema in a dedicated database whose name must contain `test`. It refuses a URL
that does not meet that guard.

Install test dependencies and start the local test database:

```powershell
python -m pip install -r requirements-test.txt
docker compose -f docker-compose.test.yml up -d --wait postgres-test
$env:FLOWHUB_TEST_POSTGRES_URL = "postgresql+psycopg://flowhub_test:flowhub_test_local_only@localhost:55432/flowhub_lease_test"
```

Run the PostgreSQL-marked tests:

```powershell
python -m pytest tests/flowhub/orders/test_order_sync_postgres.py -m postgres -q
```

Destroy the isolated database and clear the local test URL:

```powershell
docker compose -f docker-compose.test.yml down -v
Remove-Item Env:FLOWHUB_TEST_POSTGRES_URL
```

The credentials above are local test-only defaults in
`docker-compose.test.yml`; no production database URL or credential is used.

## Operations

Check the runner container:

```bash
docker compose -f docker-compose.yml ps order-sync-runner
```

Tail scheduler logs:

```bash
docker compose -f docker-compose.yml logs -f order-sync-runner
```

Check heartbeat and per-channel state through Diagnostics:

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:8085/api/v2/diagnostics/channels/health
```

Manual TapsiShop webhook receipt processing remains available to authorized
administrators through:

```text
POST /api/v2/orders/channels/{channel_id}/process-tapsishop-webhooks
```

The production scheduler itself should run in the separate worker process, not
inside web request handlers.
