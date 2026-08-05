# Pricing Matrix Backend Contract

**Version:** `v1-draft`
**Base path:** `/api/v2/pricing-matrix`
**Owner:** FlowHub backend
**Consumer:** Pricing Matrix frontend

This document describes endpoints implemented by the backend in the current
worktree. It is intentionally narrower than
`docs/architecture/PRICING_UI_CONTRACT.md`: that document defines the future
UI evidence model; this document is the callable configuration API.

All requests require a bearer token. Read endpoints require `workspace.read`.
Mutations require `workspace.admin`.

## Response and Error Shape

Successful responses are JSON objects. Datetimes are ISO-8601 strings.

Domain errors have this shape:

```json
{"detail":{"code":"pricing_policy_not_activated","message":"pricing_policy_not_activated"}}
```

- `401`: no or invalid session
- `403`: caller lacks the required permission
- `404`: referenced immutable record or channel does not exist
- `409`: lifecycle head conflict (`pricing_policy_head_conflict`)
- `422`: semantic validation or lifecycle precondition failure

Pydantic request validation also returns HTTP `422`. Request objects reject
unknown fields.

## Policy Revisions

Policies are immutable revisions. There is no PATCH, DELETE, archive, or
in-place update endpoint. Creating with an existing `policy_id` creates the
next immutable revision.

### `GET /policies`

Returns `{"items": PolicySummary[]}`. Summaries omit `rules`.

### `GET /policies/{revisionId}`

Returns a complete `PolicyRevision` or `404 policy_revision_not_found`.

### `POST /policies`

Creates a Policy Revision. Request:

```json
{
  "policy_id": "optional UUID-like stable policy identity",
  "name": "Retail EUR v1",
  "computation_currency": "EUR",
  "round_order": "surcharge_then_round",
  "max_quote_age_days": 30,
  "min_quote_count": 1,
  "evaluation_timezone": "UTC",
  "rules": [
    {
      "channel_id": "woocommerce:primary",
      "product_ref": null,
      "product_group_revision_id": null,
      "rate_mode": "percent_bp",
      "rate_value": 1000,
      "fixed_addend_minor": 0,
      "round_mode": "floor",
      "round_step_minor": 100,
      "surcharge_minor": 0,
      "guards": {}
    }
  ]
}
```

`rate_mode`: `percent_bp | multiplier_ppm`
`round_order`: `round_then_surcharge | surcharge_then_round`
`round_mode`: `floor | ceil | nearest`

A rule can target either `product_ref` or `product_group_revision_id`, never
both. Duplicate `(channel_id, product_ref, product_group_revision_id)` scopes
are rejected. Referenced Channels and Product Group Revisions must already
exist.

`PolicyRevision` response:

```text
id, policyId, revisionNumber, name, computationCurrency, basisStrategy,
roundOrder, maxQuoteAgeDays, minQuoteCount, evaluationTimezone,
arithmeticVersion, unitRegistryVersion, checksum, createdAt, rules[]
```

`basisStrategy` is currently always `min`.

## Product Group Revisions

Product groups are immutable revisioned member sets. There is no in-place
member edit or delete. Create another revision of the same `product_group_id`
to change membership.

### `GET /product-groups`

Returns `{"items": ProductGroupRevision[]}`.

### `GET /product-groups/{revisionId}`

Returns one revision or `404 product_group_revision_not_found`.

### `POST /product-groups`

```json
{
  "product_group_id": "optional stable group identity",
  "name": "Mobile accessories",
  "canonical_product_ids": ["canonical-product-uuid"]
}
```

Every supplied canonical product must exist. Duplicate members are rejected.

`ProductGroupRevision` response:

```text
id, productGroupId, revisionNumber, name, canonicalProductIds[], checksum,
createdAt
```

## Currency Unit Declarations

### `GET /units/{scope}/{scopeReference}`

`scope`: `global | source | channel`.

Returns either:

```json
{"scope":"channel","scopeReference":"woocommerce:primary","status":"unresolved","currency":null,"unit":null}
```

or a resolved declaration with `canonicalCurrency`, `canonicalUnit`,
`canonicalFactor`, `currencyProfileId`, and `version`.

### `PUT /units/{scope}/{scopeReference}`

```json
{
  "currency": "IRR",
  "unit": "RIAL",
  "connector_config_version": "connector-config-v1"
}
```

For `IRR`, `unit` is explicitly `RIAL` or `TOMAN`; the backend never infers it
from a value. Currently supported non-IRR currency/unit pairs are `USD/USD`,
`EUR/EUR`, `AED/AED`, and `JPY/JPY`.

For Channel scope, a successful mutation returns an additional
`channelConfigRevisionId`. A changed declaration creates a new immutable
Channel Configuration Revision.

## Channel Policy Lifecycle

The lifecycle is append-only. The mutable head is the current projection and
contains the authoritative `headVersion` concurrency value.

Heads are seeded by the Pricing Matrix migration and when a Channel receives a
unit declaration. A lifecycle mutation never creates a Head implicitly. A
missing Head is a fail-closed backend consistency error
(`pricing_policy_head_missing`), not a version-zero lifecycle state.

### `GET /channels/{channelId}/head`

```text
channelId, headVersion, currentEventId, effectiveActivationId, status,
policyRevisionId, channelConfigRevisionId, updatedAt
```

`status`: `active | inactive`.

### `GET /channels/{channelId}/lifecycle-events`

Returns `{"items": LifecycleEvent[]}` ordered oldest first.

```text
id, channelId, eventKind, predecessorEventId, effectiveActivationId,
policyRevisionId, channelConfigRevisionId, supersedesActivationId, actorUserId,
reason, occurredAt
```

`eventKind`: `activate | deactivate`.

### `POST /channels/{channelId}/activate`

```json
{
  "policy_revision_id": "policy-revision-uuid",
  "expected_head_version": 0,
  "reason": "Approved for this channel"
}
```

Activation requires a resolved Channel unit, matching policy computation
currency, a valid Channel rule, and channel-compatible round/surcharge values.
It returns the updated `ChannelPolicyHead`.

### `POST /channels/{channelId}/deactivate`

```json
{"expected_head_version":1,"reason":"Pause pricing"}
```

Only an active Channel can be deactivated. It returns the updated inactive
`ChannelPolicyHead`.

## Important Frontend Rules

- Keep and send `headVersion` unchanged from the last Head response. A `409`
  means refetch the Head and Lifecycle Events before asking for a new action.
- Treat all IDs, checksums, versions, and monetary integer values as strings
  where JavaScript precision could be affected. Do not derive currency-unit
  conversions in the frontend.
- Preserve all response status/error codes verbatim for the shared domain
  status mapping. Do not collapse `policy_not_activated`,
  `channel_unit_unresolved`, and `pricing_policy_head_conflict` into one UI
  state.
- The Workspace pricing preview and apply-result APIs described in
  `docs/architecture/PRICING_UI_CONTRACT.md` are not delivered by this
  configuration API phase. Do not depend on undocumented routes.

## Contract Change Process

Do not change a field name, enum, error code, or route consumed by the
frontend without updating this file and `RESUME.md` in the same backend commit.
Additive fields are allowed when documented here.
