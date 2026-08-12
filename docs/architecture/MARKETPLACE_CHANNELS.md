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

## Channel Gateway

`app/flowhub/channels/gateway.py` (`WorkspaceConnectorFactory`) is the single
channel-resolution boundary between the Write Pipeline and the per-channel
provider connectors implemented in `app/flowhub/unified_workspace/connectors.py`.
`WritePipelineService.execute_workspace`, the sole provider-dispatch authority,
resolves every channel_id through this gateway. It holds no provider logic of
its own; an unresolvable channel_id fails closed with `WorkspaceDomainError`
rather than falling back to a default channel.

## Digikala Channel

**Status: `IMPLEMENTED_UNVERIFIED`.** The Digikala implementation is based
only on the repository-supplied
[`digikala-api.md`](../api/channel/digikala-api.md) contract and its static
contract/regression tests. It has not been exercised with Owner credentials,
so it must not be represented as operational or verified. A successful live,
read-only probe is evidence for Owner and Diagram Keeper review; it is not an
automatic architecture-maturity promotion.

### Implemented boundary

- Canonical provider identifier: `digikala`; display name: `Digikala`.
- It uses the existing Channel configuration surface, enabled/disabled state,
  canonical local brand registry, Diagnostics, and ordinary Activity/audit
  flow; it does not introduce a standalone Digikala UI or persistence model.
- The connector restricts its base URL to the documented HTTPS API root,
  `https://seller.digikala.com/open-api/v1`, and sends the documented
  `Authorization: Bearer <access token>` and `Content-Type: application/json`
  headers on protected requests.
- `access_token` is a required write-only secret and `refresh_token` is an
  optional write-only secret. Sanitized configuration and diagnostics report
  only whether a credential is configured. A blank secret field preserves the
  existing stored value.
- The documented `POST /auth/token` and `POST /auth/refresh-token` operations
  support token acquisition/rotation. FlowHub does not invent a fixed token
  lifetime: it replaces both tokens only from a successful provider response.
- Test Connection is the real, read-only `GET /orders` request documented by
  the provider. Its sanitized outcome, latency, and error category are stored
  as normal connector-health evidence and are surfaced through the shared
  Diagnostics and Commerce Hub configuration flows. A connection test never
  mutates an order or attempts a token refresh.
- The connector exposes only contract-safe raw reads: `GET /auth/scopes`,
  `GET /auth/scopes/{client_code}`, `GET /categories/tree`, `GET
  /products/seller`, `GET /inventories/{product_variant_id}`, `GET /orders`,
  and `GET /orders/{order_item_id}`. Authenticated transport is GET-only and
  endpoint-allowlisted; the only permitted POSTs are the two documented token
  acquisition/refresh routes. It cannot issue a provider order, product,
  inventory, promotion, webhook, or token-revoke write.

### Deliberately unsupported normalization

The supplied document gives a generic list envelope (`data.pager` and
`items`), but does not provide endpoint-specific request parameters or field
schemas for product identifiers/SKUs, categories, price, inventory, listing
status, order status, dates, line items, quantities, or totals. It says that
the allowed pagination parameters must be checked in Swagger; that Swagger
schema is not part of this repository contract.

FlowHub therefore does **not** infer pagination queries, product mappings, or
order mappings from the generic envelope. `products.read` and `orders.read`
are not declared as normalized FlowHub capabilities for Digikala, no Digikala
rows are written to the normalized product/inventory cache, and no Digikala
orders are put into the order-sync/reconciliation pipeline. This is a
capability boundary, not a claim that the provider lacks read endpoints. It
also means there is no Digikala incremental cursor, date/status filtering, or
duplicate/idempotency record until the missing order contract is supplied.

### Write authority and documented-but-not-implemented operations

Digikala is intentionally absent from `WorkspaceConnectorFactory` and the
Write Pipeline. That gateway is the shared execution authority, so its
fail-closed behavior remains in force for every Digikala write. The following
provider-documented groups are `DOCUMENTED_NOT_IMPLEMENTED`:

- Product creation and drafts (`/product-creation/*`, `/draft-products/*`),
  variant/price/activation operations (`/variants/*`), and inventory updates
  (`/inventories/*`).
- Packages and shipments (`/packages/*`, `/shipments/*`), promotions and
  lightning deals (`/promotions/*`, `/lightening-deal/*`), and webhooks
  (`/webhook/*`).
- `POST /auth/revoke`.

The supplied document does not define the exact methods, request bodies,
response schemas, idempotency behavior, or shared FlowHub write-pipeline
mapping for those groups. They remain disabled pending an Owner decision after
the missing contract and authority mapping are available. In particular,
accepting, fulfilling, cancelling, rejecting, or otherwise changing a Digikala
order is not implemented or authorized.

## Multi-Channel Product Pricing

The legacy Product Pricing compatibility API exposes a protected
single-product channel price workflow through FlowHub backend APIs only. The
current operator workflow is `Products.tsx` through catalog Unified Workspace
and `DensePricingWorkspace`, which supports editable per-Listing channel price
cells followed by Draft, Review, and selected Apply. The frontend never calls
WooCommerce, SnappShop, or TapsiShop APIs directly.

The compatibility API loads canonical/business price data separately from
channel values.
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

Commerce Hub provides admin-only configuration for implemented channels. Its
sanitized configuration response contains non-secret settings and credential
state only. SnappShop connection tests return authorized vendor choices for
selection. TapsiShop reports outbound and webhook credential state separately
and displays a webhook URL that contains no secret. Leaving a secret input blank
while editing preserves the stored credential.

SnappShop and TapsiShop configuration updates are atomic. Credential values,
non-secret connector settings, selected vendor or store, channel state, access
mode, and the sanitized actor audit event share one database transaction. A
failed settings or audit operation rolls back the complete update and preserves
the previously committed configuration. TapsiShop refresh-policy values use
explicit boolean parsing; supported true and false strings are never interpreted
by Python string truthiness.

SnappShop's normal setup asks only for the bearer token and agent identifier.
FlowHub supplies the documented base URL, `User-Agent` header name, and a
30-second integer timeout; operators may override those values under Advanced
Settings. `GET /vendors` must succeed before save, and the selected active
vendor is validated before the atomic configuration transaction begins. A
token and agent identifier without a selected vendor are not a complete channel
configuration.

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
  response. Full synchronization follows both `meta.pagination.total_pages` and
  `meta.pagination.links.next`, with an upper page bound.
- Manual `Refresh product cache` reads every page before changing local state.
  A successful run atomically replaces only the `snappshop:main` rows in
  `dl_product_cache` and `dl_inventory_cache`; a page failure preserves the
  previous complete cache. Products pages read this local cache and never call
  SnappShop directly.
- Product-read retries are bounded and apply only to safe timeout, rate-limit,
  and upstream-unavailable failures. Authentication, authorization, and
  validation failures are not retried.
- `FLOWHUB_SNAPPSHOP_PRODUCT_SYNC_MAX_PAGES` defaults to `250` and
  `FLOWHUB_SNAPPSHOP_PRODUCT_SYNC_RETRIES` defaults to `2`.
- Page reads are paced by `FLOWHUB_SNAPPSHOP_PRODUCT_SYNC_PAGE_DELAY_SECONDS`
  (1.1 seconds by default). A 429 response uses `Retry-After` when supplied or
  the bounded `FLOWHUB_SNAPPSHOP_PRODUCT_SYNC_RATE_LIMIT_BACKOFF_SECONDS`
  fallback (30 seconds by default).
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
`app/flowhub/channels/tapsishop.py` from the Owner-supplied
`webhook-v0.2-api-reference.md`, a page-by-page transcription of the official
v0.2 reference.

### Documented contract

- Base URL: `https://vendorgw.tapsi.shop/Web/Hub/vendors/v1`.
- Outbound authentication:
  `TapsiShop.Hub.Authorization: {token}`. The vendor-panel token is stored only
  through FlowHub's secret-setting mechanism.
- Webhook authentication:
  `TapsiShop.Hub.Webhook-Authorization: {webhook_token}`. It is a separate
  write-only secret and is compared in constant time.
- The samples include `accept: text/plain`, `client-name`, and
  `client-version`, but do not state whether the client identity headers are
  required or whether third-party values must be registered. FlowHub sends the
  documented Accept header and omits the ambiguous client identity headers.
- `GET /vendor-information` is the connection and vendor-identity probe.
- `GET /products/{page}/{pageSize}` is page-number based. Provider `id`,
  `hsin`, and seller `sku` are stored as distinct identifiers. The document
  provides no parent or variation identity.
- The update sample uses the exact lowercase URL
  `PUT https://vendorgw.tapsi.shop/web/hub/vendors/v1/products`; FlowHub keeps
  that operation URL fixed and uses seller SKU as `id`, stock, rial price, and
  its operation idempotency key as `referenceCode`.
- `POST /orders` lists orders from page zero using only documented filters.
  `GET /orders/{orderId}` reads order details.
- `GET /courier/{pickupCode}` reads courier details.
- `POST /refresh-token` refreshes credentials. FlowHub omits custom expiry
  because the document conflicts between `expireAt` and `expiredAt`.

### FlowHub behavior

- The Base URL is restricted to the official HTTPS gateway, port 443, and API
  root. Arbitrary URLs, URL credentials, query strings, localhost, private
  networks, and non-HTTPS schemes are rejected.
- Manual product-cache refresh reads every page centrally. Safe transient read
  failures use bounded retries; authentication, validation, and write failures
  are not retried. A complete successful read atomically replaces only
  TapsiShop cache rows. Any page failure preserves the last-known-good cache.
- TapsiShop publishes no numeric rate limit. FlowHub therefore does not claim a
  provider quota. It applies a conservative local page delay, maximum page
  count, bounded retry count, and bounded rate-limit backoff. Product reads
  default to the sample's page size of 10; operators can tune the local page
  size without changing provider semantics.
- Read-only mode permits tests and reads. Write-enabled mode only makes the
  channel eligible for the protected Workspace pipeline.
- Every product write originates from Dry Run → Review → Approval → Apply.
  Direct browser/provider writes and automatic Apply are unavailable.
- The documented update body contains both price and stock and does not define
  partial semantics. FlowHub sends an explicit complete state, requires both
  reviewed values, validates integer rial values divisible by 10, and limits
  batches to one until a provider maximum is documented.
- A successful provider write remains `reconciliation_required`; the document
  does not provide an exact single-product read-back endpoint.
- Token refresh occurs only after authentication failure on a safe request or
  through the explicit connector operation. Safe requests retry once after a
  lock-protected refresh. Writes are never automatically retried.

### Documentation gaps and unsupported behavior

FlowHub does not infer behavior for these gaps:

- No listing-creation endpoint: listing creation is unsupported.
- No category or attribute endpoints: their synchronization is unsupported.
- No parent/variation identity: variation reads and writes are unsupported.
- `/web/hub/` in the update example conflicts with `/Web/Hub/` elsewhere:
  FlowHub follows the exact lowercase update URL and never retries a write
  against the alternate case. The provider should confirm this in a sandbox.
- Order-detail fields conflict in places and no order mutation is documented:
  orders are read-only. The documented order-detail item shape has no quantity,
  so FlowHub preserves those provider rows in the raw order reference but does
  not fabricate normalized line quantities.

### Owner/provider decision table

The following questions remain unresolved in the supplied v0.2 reference.
FlowHub deliberately keeps the affected capability disabled or conservative
until the Owner supplies provider confirmation. A sample alone is not treated
as a normative requirement.

| Question | Documentation evidence | Current FlowHub decision | Confirmation needed |
| --- | --- | --- | --- |
| Are `client-name` and `client-version` required? | They appear in request samples, but the reference does not define whether they are mandatory, how values are registered, or which values third-party clients may send. | Send the documented authorization and Accept headers only. Do not invent client identity values. | TapsiShop must confirm whether both headers are required and issue or approve exact values for FlowHub. |
| Is the discount field `specialprice` or `specialPrice`? | The JSON example uses `specialprice`; prose uses `specialPrice`. | Discount writes are disabled. Price and stock writes do not include either field. | TapsiShop must confirm the exact case-sensitive field name, null/clear semantics, validation, and currency unit. |
| Is refresh expiry `expireAt` or `expiredAt`? | The field table uses `expireAt`; the JSON example uses `expiredAt`. | Token refresh does not send a custom expiry and the UI does not expose one. | TapsiShop must confirm the exact field name, format, timezone, and whether the field is optional. |
| Is courier review `POST` or `PUT`? | The courier-review operation is described with conflicting HTTP methods. | Courier lookup remains read-only; courier review is unsupported. | TapsiShop must confirm the method, endpoint, request schema, idempotency behavior, and retry safety. |
| Which rate-limit headers and quotas apply? | No numeric quota, reset window, or response-header contract is defined. | Do not claim a provider quota. Use conservative local pacing and bounded retries; never infer quota state from undocumented headers. | TapsiShop must document quota scope, limits, response headers, reset semantics, and whether retries consume quota. |
| What is the canonical error schema? | Success envelopes are shown, but HTTP error bodies, stable error codes, retryability, and validation-detail structure are not defined. | Categorize only by HTTP status and transport outcome, return redacted FlowHub errors, and retry only safe reads on timeout, 429, or 5xx within bounded limits. Writes are not retried automatically. | TapsiShop must document error envelopes/codes and which failures are safe to retry. |

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

The official payload places `requestId` on every item, not at the top level.
Idempotency is enforced durably for every `(channel_id, item.requestId)` through
`webhook_provider_event_identities`. A repeated batch is recognized even when
its item order changes. A partially duplicated batch is rejected rather than
silently dropping new items or reprocessing old ones. The same request ID can be
accepted independently for another channel.

The HTTP handler does not mutate canonical inventory, orders, or products. It
creates an immutable receipt, stores a normalized channel event, and leaves
business effects to the processing layer. Current normalized `changeType` and
quantity mapping:

- `1`: deducted due to purchase; item quantity must be `-1`
- `2`: added due to cancellation; item quantity must be `+1`

Item `tapsiShopProductId` is the external TapsiShop product identity.
Item `productId` is the seller SKU. They are never merged.

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
days after receipt. Cleanup must retain item identity rows for as long as their
receipt remains replayable; automated cleanup is not yet implemented.
