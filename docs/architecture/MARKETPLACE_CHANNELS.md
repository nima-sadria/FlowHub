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

SnappShop and TapsiShop are future channel definitions only. This abstraction does not implement their external API calls.
