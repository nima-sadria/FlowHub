# Marketplace Channel Abstraction

FlowHub keeps Sources and Channels separate.

- Sources provide business data to FlowHub.
- Channels are sales destinations.
- The Data Layer remains canonical.
- Channel connectors must not become the source of truth.
- Marketplace-specific behavior must not be embedded in the shared Rule Engine.
- UI components must not call external marketplace APIs directly.

## Contract Location

The internal marketplace contract lives in `app/flowhub/channels`.

- `contracts.py` defines normalized DTOs and capability names.
- `marketplace.py` defines the connector protocol and capability guardrails.
- `registry.py` registers implemented and future channel definitions without UI-specific code.

Existing WooCommerce write behavior remains in the protected Write Pipeline. The marketplace abstraction does not add a generic write endpoint and does not relax channel access modes.

## Multi-Channel Product Pricing

The Products workflow exposes a protected single-product channel price editor
through FlowHub backend APIs only. The frontend never calls WooCommerce,
SnappShop, or TapsiShop APIs directly.

The editor loads canonical/business price data separately from channel values.
Each channel row reports connection state, read/write capability, current
synchronized value, proposed value, unit, normalized value, freshness, stale
token, validation state, and pending change state. Channel columns are driven by
declared capabilities and connector instance access mode; disabled,
disconnected, or read-only channels cannot be edited and do not block writable
channels.

Protected endpoints:

- `GET /api/v2/products/{product_id}/channel-prices`
- `POST /api/v2/products/{product_id}/channel-prices/validate`
- `POST /api/v2/products/{product_id}/channel-prices/dry-run`
- `GET /api/v2/products/channel-price-operations/{operation_id}`
- `POST /api/v2/products/channel-price-operations/{operation_id}/approve`
- `POST /api/v2/products/channel-price-operations/{operation_id}/apply`

Dry Run stores a no-write operation and audit records. Apply is rejected until a
separate approval call succeeds. Stale tokens prevent accidental overwrite when
channel data changed after the editor opened or after Dry Run. Audit metadata
records actor, product, channel, previous value, proposed value, converted
outbound value, unit, result, upstream reference, and timestamp.

Currency units stay explicit at the channel boundary:

- WooCommerce and canonical values use the configured store currency.
- SnappShop editable/write values are toman and normalize to rial for display.
- TapsiShop editable/write values are rial.

The backend performs validation and connector-boundary conversion. The Rule
Engine must not assume toman or rial.

## Capabilities

Connectors declare capabilities explicitly. Callers must check capabilities before invoking optional behavior.

Required capability names include:

- `products.read`
- `products.write_price`
- `products.write_stock`
- `products.write_discount`
- `products.write_capacity`
- `orders.read`
- `orders.events.poll`
- `orders.webhook.receive`
- `credentials.refresh`
- `courier.read`
- `courier.review`

Unsupported behavior must fail with `unsupported_capability`; it must not be simulated, silently ignored, or routed through provider-specific conditionals in shared business logic.

## DTO Rules

Marketplace connectors normalize provider responses into internal DTOs:

- `ChannelVendor`
- `ChannelProduct`
- `ChannelProductUpdate`
- `ChannelProductUpdateResult`
- `ChannelOrder`
- `ChannelOrderItem`
- `ChannelOrderEvent`
- `ChannelHealth`
- `ConnectorError`

Provider identifiers stay separate from canonical Data Layer IDs:

- `canonical_product_id`
- `external_product_id`
- `sku`
- `product_number`
- `parent_product_number`
- `order_number`
- `channel_reference_code`

Do not overload the canonical product ID with a marketplace identifier.

## Pagination

Connectors must represent both common pagination modes:

- `PageNumberPagination` for page and page-size APIs.
- `CursorPagination` for cursor and continuation-token APIs.

Default limits should be conservative. Channel configs include safe timeout defaults and max page size controls.

## Secrets

Secrets stay in the existing connector configuration and secret-storage flow. Normal APIs may report whether a secret is configured, but must never return raw tokens, API keys, passwords, authorization headers, cookies, or refresh tokens.

## Errors And Retries

Connector errors use normalized categories:

- `authentication`
- `authorization`
- `validation`
- `rate_limit`
- `timeout`
- `upstream_unavailable`
- `not_found`
- `conflict`
- `unsupported_capability`
- `unexpected_response`

Retry metadata must distinguish retryable read failures from unsafe write requests. Implementations must not blindly retry non-idempotent writes; write methods should use provider idempotency keys when the provider supports them.

## Adding A Future Channel

1. Add a marketplace connector implementation outside UI code.
2. Declare capabilities in `MarketplaceConnectorRegistry`.
3. Normalize provider payloads into channel DTOs.
4. Store settings and secrets through the Integration Platform configuration mechanisms.
5. Read provider products into Data Layer snapshots or cache tables; do not treat the provider as canonical during rule evaluation.
6. Add tests with a fake or mocked connector for read normalization, write result normalization, pagination, capability denial, and secret redaction.
7. Wire write behavior only through an approved channel adapter and existing Dry Run, Approval, Apply, audit, limiter, and maintenance protections.

## SnappShop Connector

The SnappShop channel connector is implemented under
`app/flowhub/channels/snappshop.py` from
`snappshop_vendor_automation_API_v2.1.2.pdf`.

Documented defaults and configurable assumptions:

- Base URL default: `https://apix.snappshop.ir/automation/v1`.
- Authentication: `Authorization: Bearer {token}`.
- Unique agent header: the document text describes a user/agent identifier and
  shows `User-Agent: {agent id}`. FlowHub defaults to `User-Agent` but stores
  `agent_header_name` as connector configuration because the wording is
  inconsistent.
- Product list pagination is page-number based and documented as 20 products per
  response. Full synchronization follows `meta.pagination.total_pages` with an
  upper page bound.
- Product writes use `PATCH /vendors/{vendor_id}/products`, up to 50 items per
  request. Outbound items use either `sku` or `id`; FlowHub prefers `sku` when
  both are available because the document says SKU takes precedence.
- SnappShop product write prices are toman. FlowHub requires currency/unit
  metadata at this boundary and converts canonical rial values to toman here,
  never in the Rule Engine.
- Order events and order history use cursor pagination. The cursor is advanced
  only through an explicit acknowledgement path after the caller has durably
  stored the page.
- The companion `webhook.v.0.2.pdf` describes TapsiShop webhook APIs, not
  SnappShop. SnappShop webhook receipt remains unsupported until a SnappShop
  webhook document is supplied.

## TapsiShop Connector

The TapsiShop channel connector is implemented under
`app/flowhub/channels/tapsishop.py` from `webhook.v.0.2.pdf`.

Documented defaults and configurable assumptions:

- Base URL default: `https://vendorgw.tapsi.shop/Web/Hub/vendors/v1`.
- The document shows inconsistent path casing in examples. FlowHub constructs
  every URL through the connector `_url()` helper so path casing can be
  normalized in one place.
- Outbound API authentication uses
  `TapsiShop.Hub.Authorization: {token}`.
- Incoming webhook authentication uses the separate
  `TapsiShop.Hub.Webhook-Authorization: {webhook_token}` credential. FlowHub
  never reuses the outbound token as the webhook token.
- Webhook acknowledgement uses HTTP 200 with a response body containing
  `succeed: true`.
- Health checks call only `GET /vendor-information`; they do not run product or
  order synchronization.
- Product writes use rial values at the channel boundary. FlowHub requires
  explicit `IRR`/`rial` metadata and validates integer multiples of 10 to avoid
  accidental rial/toman conversion.
- Token refresh uses `POST /refresh-token`. The PDF sample contains a spacing
  typo in one rendered path, so the normalized documented task path is isolated
  as `TAPSISHOP_REFRESH_PATH`.
- Token refresh occurs only after an authentication failure on a safe request or
  through the explicit connector refresh method. A per-connector async lock
  prevents concurrent refreshes, the stored token update is delegated to the
  existing configuration service, and the original safe request is retried once.
- Courier lookup is implemented as `GET /courier/{pickupCode}`. Courier review
  remains capability-gated and is not exposed in the UI until the documented
  method inconsistency for `/review-courier` is verified against a real API or
  vendor sandbox. The currently documented method constant is `PUT`.

## TapsiShop Webhook Ingestion

FlowHub exposes a dedicated TapsiShop webhook receiver:

- `POST /api/v2/webhooks/tapsishop/{channel_id}`

Authentication uses the `TapsiShop.Hub.Webhook-Authorization` header and the
stored `webhook_token` for the exact channel. FlowHub uses constant-time
comparison and never logs the supplied or stored token. The outbound API token
and webhook token remain separate credentials.

The receiver validates payload size and `application/json` before parsing. A
successful response is returned only after the receipt is durably stored:

```json
{
  "message": "Webhook accepted.",
  "succeed": true
}
```

Idempotency is enforced by `(channel_id, requestId)`. Repeated delivery of an
already accepted request returns the same TapsiShop-compatible success response
without creating another receipt or processing attempt. The same `requestId` can
be accepted independently for another channel.

The HTTP handler does not mutate canonical inventory, orders, or products. It
creates an immutable receipt, stores a normalized channel event, and leaves
business effects to the processing layer. Current normalized `changeType`
mapping:

- `1`: deducted due to purchase
- `2`: added due to cancellation

Stored payload data is minimized. FlowHub stores request ID, order/item/product
identifiers, SKU, quantity, timestamps, prices, payload hash, and processing
state. Customer name, phone number, national code, and delivery address are not
stored in receipt summaries or normalized events and must not be logged.

Processing uses bounded exponential backoff for transient failures. Permanent
validation failures are not retried. Exhausted failures move to dead-letter
state. Authorized administrators can replay a receipt; replay preserves the
same idempotency identity and does not create a new accepted event. Sanitized
metrics expose received, accepted, duplicate, failed, dead-letter, and processing
latency counts.

Retention: webhook receipt rows include `retention_until`, currently set to 90
days after receipt. A future retention worker should purge or archive rows after
that timestamp according to the deployment's privacy policy.
