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

The service exposes explicit sync entrypoints and stores non-overlap locks in
`channel_order_sync_checkpoints`. No background worker is started by importing
the application.
