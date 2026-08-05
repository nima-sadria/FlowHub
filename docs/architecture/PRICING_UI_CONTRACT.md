# FlowHub Source and Pricing Interface Contract

**Status:** Proposed, implementation pending
**Contract version:** `source-pricing-interface-v1`
**Date:** 2026-08-05
**Related:** `ADR-SOURCE-001`, `ADR-SOURCE-001-A1`, `ADR-PRICING-001`,
`SOURCE_ACQUISITION_DESIGN.md`, `PRICING_MATRIX_DESIGN.md`

## Contract Boundary — What Is Callable Today

There are two contracts, with different authority:

- **`FRONTEND_CONTRACT.md` (repository root) is the authoritative, callable
  backend contract. It describes the Pricing Matrix APIs that exist and can be
  called now** — policy revisions, product-group revisions, currency-unit
  declarations, and the channel policy lifecycle.
- **This document (`PRICING_UI_CONTRACT.md`) is a separate, `Proposed`
  architectural contract. It describes future UI and backend exposure that is
  NOT implemented yet.** In particular, the following are design intent only and
  are not callable today:
  - Source Acquisition (runs, observations, resource bindings, schema assessment)
  - Diagnostics (stages, freshness, cohorts, recent checks)
  - Workspace Pricing Preview (preview rows, quotes, guard results)
  - Apply Result (apply projection, write attempts, per-channel status)
  - `allowed_actions` action-gate evidence
  - The `contract_version` response envelope and the contract-revision /
    fail-closed mechanism described under *Contract Authority and Change Control*

No route, shape, enum, or field defined only in this document is callable today.
Any frontend that must call the backend uses `FRONTEND_CONTRACT.md`. Where this
document and `FRONTEND_CONTRACT.md` diverge for a surface that is callable now,
the divergence is recorded under *Open Questions for Codex* at the end of this
file and is **not** resolved unilaterally by the UI in either direction.

## Purpose

This document is the shared contract between FlowHub backend implementation and
interface implementation. The architecture documents define what the system
decides; this contract defines the evidence the backend exposes and the states
the interface must preserve.

It does not replace the domain documents. If a conflict exists, an accepted ADR
wins, then its detailed design, then this interface contract. The conflict must
be corrected before implementation continues.

## Contract Authority and Change Control

Every response governed by this document carries:

```text
contract_version: source-pricing-interface-v1
```

The checked-in Pydantic response models and generated OpenAPI document are the
authoritative transport schema. This Markdown document defines their required
semantics.

- Required fields are always present. Unavailable values are explicitly
  nullable; omission is not used to hide an unimplemented or unknown state.
- Outcomes with different fields use discriminated unions.
- Lists that can grow by product, quote, or write item use cursor pagination.
- Backend fixtures cover every enum value and every safety-relevant edge case.
- Frontend types are generated from OpenAPI, or contract-tested against those
  checked-in fixtures until generation is introduced.
- Additive fields may remain within this contract version. Removing a field,
  adding or removing an enum value, or changing semantics requires a contract
  version change.
- An unknown contract version or enum value fails closed as an unsupported
  contract. It is never coerced into success, ready, applied, or healthy.

## Domain State Vocabulary

Domain enums below are exact. Presentation variants, localized labels, icons,
and tones are not domain states and may be shared where meaning remains clear.
The UI must not invent a new domain state or coerce one domain state into
another.

### Source Run

```text
run_status:
  queued | running | succeeded | failed | cancelled | abandoned

run_result:
  observed | not_modified | content_unchanged_reparse | none

source_operation:
  connection_test | resource_inspection | acquisition | deep_diagnostics

source_trigger:
  manual | scheduled | webhook | system
```

`abandoned` means lease expiry or worker loss, not provider failure.

### Stage Execution and Freshness

```text
execution_status:
  not_run | pending | running | passed | failed | skipped | not_applicable

freshness:
  current | stale | unknown
```

`skipped` means an applicable Stage was gated by an earlier result.
`not_applicable` means the provider capability or operation plan does not use
the Stage. `stale` is a time-derived freshness projection, never an immutable
execution outcome.

The existing FlowHub diagnostic presentation vocabulary remains:

```text
diagnostic_state:
  HEALTHY | INFO | NOT_CHECKED | NOT_APPLICABLE
  | DISABLED | WARNING | ERROR
```

This presentation state is derived from typed Stage evidence; it does not
replace `execution_status` or `freshness` in the API.

### Source Readiness

All seven `ADR-SOURCE-001` readiness dimensions are exposed:

```text
readiness_dimension_state:
  ready | degraded | blocked | unknown | not_applicable

source_aggregate_state:
  draft | ready | degraded | disabled | unsupported

schema_assessment:
  match | drift | ambiguous | no_mapping
```

The dimensions are:

```text
connection
resource_binding
acquisition
schema_compatibility
mapping
validation
operational_health
```

The aggregate is a backend-derived projection. It may be materialized for
efficient reads, but it is never a decision identity and never replaces its
dimensions or immutable evidence.

Pricing readiness is separate and scoped per Channel:

```text
pricing_readiness:
  ready | degraded | unknown

operation_gate:
  allowed | blocked
```

One Channel's pricing fault does not degrade another Channel.

### Schema Difference

```text
schema_change_kind:
  added | removed | moved | renamed | canonical_collision
```

Raw and canonical headers are both returned. Raw text is shown to the operator;
canonical text supports explanation and audit.

### Quote and Rule Resolution

```text
quote_presence:
  quoted | absent | zero

quote_exclusion_reason:
  excluded_stale | excluded_undated | excluded_future_dated
  | excluded_zero | excluded_absent
  | quote_precision_invalid | quote_negative | currency_unresolved
  | null

resolution_specificity:
  channel_product | channel_group | channel_default
  | global_product | global_group | global_default

guard_status:
  passed | rejected | not_applicable
```

The specificity names map in order to the six Scope keys in
`PRICING_MATRIX_DESIGN.md`; no additional tie-break exists.

### Pricing Outcome

```text
cell_outcome:
  priced | product_unmapped | legacy_formula_unmigrated
  | rule_unresolved | rule_ambiguous
  | no_quote | all_quotes_zero
  | currency_unresolved | quote_precision_invalid | insufficient_quotes
  | nonpositive_price | guard_rejected

workspace_precondition:
  unit_unresolved | policy_not_activated
```

Workspace preconditions are evaluated before cells. They are never presented as
missing vendor data.

### Attention Signal

```text
attention_scope_type:
  source | channel
```

`reason_code` comes from the checked-in Source or Pricing reason-code catalog;
it is never free-form provider text. `outcome_code`, when present, is a
`cell_outcome`.

### Apply Projection and Write Attempt

There are eight apply projection states:

```text
apply_status:
  pending | running | applied | partially_applied
  | reconciliation_required | failed | blocked | no_changes

write_attempt_state:
  pending | dispatch_intent_recorded | dispatched | provider_accepted
  | verified_applied | failed | reconciliation_required | recovering
```

`partially_applied` means FlowHub knows exactly what shipped and what did not.
`reconciliation_required` means at least one result is unknown. They are not
adjacent severity levels and must not share one presentation.

## Exact Monetary Values

Financial values cross the API as strings, never JSON floating-point numbers.

Integer strings match `-?(0|[1-9][0-9]*)`. Decimal strings are finite base-10
values without exponent notation. Leading `+`, `NaN`, and infinities are
invalid.

```text
ExactAmount:
  numerator: integer string
  denominator: positive integer string
  currency: ISO 4217 code
  unit: declared unit code
  unit_registry_version: string

ExactDisplay:
  value: exact decimal or fraction string
  currency: ISO 4217 code
  unit: declared unit code
  exact: true
```

`denominator` is `1` for an exact integer. The frontend uses string or BigInt
formatting and must not pass exact financial values through JavaScript `number`.

The interface never silently replaces an exact value with an approximation. If
a rational has no terminating decimal representation, show the exact fraction.
An optional approximation is permitted only when prefixed by `approx.` (or its
localized equivalent) and the exact value remains visible or immediately
reachable.

Examples:

```text
101 RIAL -> 10.1 TOMAN     exact
101 RIAL -> 10 TOMAN       forbidden
```

## Required API Views

The shapes below define required evidence. Concrete routes may add pagination
and links but cannot remove the listed semantics.

### Common Envelope

```text
contract_version
data
```

### Source Detail

```text
source_id
source_readiness:
  dimensions:
    connection
    resource_binding
    acquisition
    schema_compatibility
    mapping
    validation
    operational_health
  aggregate
  schema:
    assessment
    assessment_id                    nullable
    worksheet_observation_id         nullable
    mapping_revision_id              nullable

pricing_readiness_by_channel[]:
  channel_id
  readiness
  operation_gate
  reason_codes[]

resource_binding:
  binding_revision_id                nullable
  display_name                       nullable
  safe_resource_identity             nullable
  last_modified_at                   nullable
  size_bytes                         nullable

last_successful_acquisition_at       nullable
last_schema_compatible_observation_at nullable
last_successful_workspace_created_at nullable
last_successful_apply_by_channel[]:
  channel_id
  applied_at                         nullable

current_run:                         nullable
  run_id
  operation
  trigger
  status
  result
  started_at                         nullable
  finished_at                        nullable

open_signals[]:
  signal_id
  scope_type
  source_id
  channel_id                         nullable
  reason_code
  outcome_code                       nullable
  policy_revision_id                 nullable
  affected_product_count
  first_seen_at
  last_seen_at
  occurrence_count

allowed_actions:
  preview
  dry_run
  apply
  activate_policy
  review_mapping
  run_diagnostics
```

Each allowed action is:

```text
allowed: boolean
reason_codes: string[]
```

The backend computes action gates. The frontend does not reconstruct safety or
authorization policy from badges.

`safe_resource_identity` is a permission-filtered display identifier, never an
unrestricted content hash, storage key, secret, or cross-Source lookup key.

### Diagnostics

```text
diagnostic_run_id
cohort_id
started_at
finished_at                         nullable
aggregate_state

stages[]:
  stage_id
  execution_status
  freshness
  diagnostic_state
  duration_ms                       nullable
  checked_at                        nullable
  reason_code                       nullable
  recommended_action_code           nullable
  message_params                    object
  retryable                         nullable
  is_actionable

supplemental[]:
  stage_id
  label_code
  execution_status
  freshness
  diagnostic_state
  value                             nullable
  reason_code                       nullable
  recommended_action_code           nullable
  message_params                    object

recent_checks[]:                    up to the latest 10 comparable checks
  diagnostic_run_id
  cohort_id
  checked_at
  aggregate_state
```

Config, Binding, or Execution Policy changes create a new `cohort_id`. Checks
from another cohort are historical context and do not satisfy current evidence.

Localized prose is not the primary contract. The backend returns stable reason
and action codes plus sanitized parameters. Raw upstream bodies, secrets,
credentials, internal paths, and unrestricted network details are forbidden.

### Schema Drift

```text
assessment_id
status                              match | drift | ambiguous | no_mapping
fingerprint_algorithm_version
expected_header_hash                nullable
observed_header_hash

headers[]:
  position
  expected_raw                      nullable
  expected_canonical                nullable
  observed_raw                      nullable
  observed_canonical                nullable
  change_kind                       nullable
```

The interface displays the raw forms exactly as captured, including ZWNJ and
Arabic-form letters. Canonical values are detail evidence, not replacements for
the operator's text.

Schema drift has no inline `Accept` action. The action opens Mapping review;
saving the reviewed Mapping creates a new immutable Mapping Revision.

### Workspace Pricing Preview Row

```text
product_ref
channel_id
pricing_policy_activation_id
policy_revision_id
computation_currency
channel_unit
outcome

price:                              nullable; present only for priced
  exact_amount
  display

basis:                              nullable
  vendor_revision_id
  vendor_name
  raw_value
  raw_currency
  raw_unit
  as_of                             nullable
  valued_amount

quotes[]:
  vendor_revision_id
  vendor_name
  raw_value                         nullable
  raw_currency
  raw_unit
  canonical_unit_amount             nullable integer string
  as_of                             nullable
  presence
  exclusion_reason                 nullable
  valued_amount                    nullable

resolved_rule_entry_id             nullable
resolution_specificity             nullable

guard_result:                       nullable
  status
  guard_code
  reference_vendor_revision_id      nullable
  reference_vendor_name             nullable
  reference_value                  nullable ExactAmount
  threshold                        nullable ExactAmount
  reason_code                      nullable
```

Excluded quotes remain in `quotes[]`. A blocked row retains enough evidence to
explain whether the problem is mapping, policy, quote eligibility, valuation,
or a guard.

### Apply Result

```text
workspace_id
workspace_status
expected_item_count
started_at                          nullable
finished_at                         nullable

channels[]:
  channel_id
  status
  expected_item_count
  verified_count
  failed_count
  unknown_count
  blocked_reason_codes[]
  last_verified_applied_at          nullable

items_page:
  items[]:
    apply_item_id
    channel_id
    product_ref
    attempt_state
    reason_code                     nullable
    provider_reference              nullable
    updated_at
  next_cursor                       nullable
```

`provider_reference` is sanitized and capability-filtered. `no_changes` is
valid only when the immutable apply plan records `expected_item_count = 0`.
Absence of attempts is not evidence of a no-op.

## Interface and Design-System Rules

### Shared Components

Implementation reuses the existing FlowHub component language:

- `Alert`, `Badge`, `DiagnosticStateBadge`, and `Icon`
- `.fh-card`, `.fh-table`, `.fh-alert`, and `.fh-badge`
- existing form, focus, light/dark, and responsive tokens

A single `DomainStatusPresentation` mapping owns localized label, semantic tone,
icon, and emphasis for every domain enum. Pages do not hardcode status colors or
create local aliases.

Distinct states need distinct label, icon, and structure; they do not require a
unique color for every enum. Color is never the only carrier of meaning.

### Responsive Layout

- EN/LTR and FA/RTL are mandatory, in light and dark modes.
- Desktop, tablet, and mobile are required surfaces.
- Wide evidence tables become stacked row summaries with an accessible detail
  disclosure or drawer on narrow screens; the page does not rely on horizontal
  overflow for primary actions or status.
- Interactive mobile targets are at least 44 by 44 CSS pixels.
- Dynamic status changes use an appropriate `aria-live` region without
  repeatedly announcing unchanged polling results.
- All actions are keyboard reachable and retain visible focus.

### RTL and Exact Text

- Pipeline and stage order mirror visually in RTL while logical Stage order in
  data remains unchanged.
- IDs, reason codes, stage IDs, currency codes, and numeric values use bidi
  isolation, such as `<bdi dir="ltr">`.
- Header names in schema diff are shown in their captured raw form. The raw text
  is not canonicalized for display.
- Monetary separators and digit glyphs follow locale, but formatting starts
  from exact strings or BigInt, never floating point.

### Safety-Critical Presentation

- An unresolved Source or Channel unit displays no computed Pricing Preview.
  Raw Source Preview and the non-committing Unit Resolution Preview remain
  available.
- Unit Resolution Preview has no approval or submit control and cannot create a
  Workspace.
- Excluded quotes remain visible and de-emphasized with their reason.
- Configuration faults such as `policy_not_activated` and `rule_unresolved` do
  not look like vendor-data faults such as `no_quote`.
- Acknowledgement may enable Policy Activation and is visible in audit. It never
  changes readiness, closes the attention signal, or hides the affected count.
- `partially_applied` and `reconciliation_required` use strongly different
  structure and iconography because one is known and the other is unknown.

## Apply Progress Delivery

Version 1 uses polling. The frontend follows the backend's `Retry-After` when
present, otherwise bounded exponential backoff with jitter. Polling stops on all
terminal apply states and when the view is abandoned. Push delivery or SSE is a
future contract version and does not change domain states.

## Authorization and Privacy

The backend filters evidence by capability. A lower-privilege user may receive
an actionable reason code without precise host, path, certificate, provider
reference, or network detail. The UI never attempts to reconstruct hidden
technical evidence.

No contract response exposes:

- secrets, tokens, passwords, or credential-bearing URLs
- raw upstream response bodies
- internal filesystem or storage paths
- unrestricted content hashes or cross-Source deduplication keys
- product cell values outside the caller's Source and Workspace permissions

## Forbidden

- Collapsing distinct safety-relevant domain states into one domain result.
- Displaying a price derived from an unresolved unit.
- Passing exact monetary values through floating-point arithmetic.
- Hiding excluded quotes or schema differences.
- Rendering `skipped`, `not_run`, or `not_applicable` as failure or success.
- Treating `stale` as an immutable Stage result.
- Adding an approval control to Unit Resolution Preview.
- Accepting schema drift without a new Mapping Revision.
- Clearing readiness or attention evidence because a blocked scope was
  acknowledged.
- Deriving action permission or safety gates solely in the frontend.
- Hardcoded page-level status colors outside the FlowHub design system.
- Displaying raw upstream errors, secrets, internal paths, or unrestricted
  technical identifiers.

## Acceptance Criteria

- OpenAPI and checked-in fixtures represent every enum and nullable branch in
  this contract.
- Unknown contract versions and enum values fail closed.
- A failure at Stage three renders later applicable Stages as `skipped`, while
  provider-inapplicable Stages remain `not_applicable`.
- A stale passing result remains `passed` with freshness `stale`.
- Source detail exposes all seven readiness dimensions and per-Channel pricing
  readiness.
- A Source acquired today and last applied nine days ago shows both facts.
- A drift result includes raw and canonical header evidence and links to Mapping
  review.
- A preview row shows every excluded quote, its exact value, and its reason.
- A guard rejection identifies the guard, reference, threshold, and rule entry.
- An unresolved unit blocks Pricing Preview, Dry Run, and Apply without blocking
  Raw Source Preview or Unit Resolution Preview.
- Apply views distinguish all eight projection states and preserve exact item
  attempt states.
- `no_changes` appears only with an apply plan whose expected item count is zero.
- EN/LTR and FA/RTL pass light/dark desktop, tablet, and mobile verification.
- No diagnostics or apply response leaks protected technical evidence.

## Decisions Closed by This Contract

- Interface support is mandatory for English LTR and Persian RTL.
- Health history uses up to the latest ten comparable checks in one cohort.
- Schema drift is resolved through Mapping review and a new Mapping Revision,
  not inline acceptance.
- Apply progress uses polling in v1; push delivery is deferred.
- Exact monetary formatting is string/BigInt based.
- Raw headers are shown exactly as captured; canonical forms remain evidence.

## Open Questions for Codex

Raised by Claude UI Phase 1 while cross-checking `FRONTEND_CONTRACT.md` (the
callable contract) against this document. These are conflicts or gaps between
the two contracts for the surface that is callable **today**. They are recorded
here for Codex to resolve on the backend; the UI does not resolve them
unilaterally, and it does not invent behavior to paper over them.

- **PM-1 — Response envelope and `contract_version`.** This document mandates a
  common envelope (`{ contract_version, data }`) and that every governed
  response carry `contract_version: source-pricing-interface-v1`.
  `FRONTEND_CONTRACT.md` responses are bare JSON objects (for example
  `{ "items": [...] }` or a `PolicyRevision` object directly) with no
  `contract_version`, and it declares version `v1-draft`. Are the
  currently-callable configuration endpoints "governed" by this document's
  envelope/versioning, and if so on what timeline? Until answered, the UI reads
  the bare shapes from `FRONTEND_CONTRACT.md` and does not assume an envelope.

- **PM-2 — Field-naming convention.** `FRONTEND_CONTRACT.md` uses camelCase in
  responses (`policyId`, `revisionNumber`, `headVersion`, …) and snake_case in
  request bodies (`policy_id`, `computation_currency`, …). The shapes in this
  document are snake_case throughout. Which convention governs the future
  evidence endpoints, and is there a normalization plan so the frontend can use
  one convention across both contracts?

- **PM-3 — List pagination.** `FRONTEND_CONTRACT.md` list endpoints
  (`GET /policies`, `GET /product-groups`, `GET /channels/{id}/lifecycle-events`)
  return `{ "items": [...] }` with no cursor. This document requires cursor
  pagination for lists that can grow by product, quote, or write item. Do the
  callable list endpoints adopt cursor pagination before UI depends on them at
  scale, or are they exempt as bounded configuration lists?

- **PM-4 — Monetary integers: number vs string.** `FRONTEND_CONTRACT.md` shows
  rule fields (`rate_value`, `fixed_addend_minor`, `round_step_minor`,
  `surcharge_minor`) as JSON numbers in the request example, while its
  "Important Frontend Rules" say to treat monetary integers as strings where
  JavaScript precision could be affected. For request bodies, should these be
  sent as numbers (matching the example) or strings (matching the rule)? Phase 1
  types them as numbers to match the documented example and flags the tension
  here.

- **PM-5 — Nullability of lifecycle/head fields.** `FRONTEND_CONTRACT.md` lists
  `ChannelPolicyHead` and `LifecycleEvent` fields (for example
  `effectiveActivationId`, `policyRevisionId`, `channelConfigRevisionId`,
  `predecessorEventId`, `supersedesActivationId`, `reason`, `actorUserId`) but
  does not enumerate which are nullable for an inactive head or a first event.
  Phase 1 types the plausibly-absent ones as `| null`. Please confirm the exact
  nullability per field.

- **PM-6 — Per-rule casing in the `PolicyRevision` response.**
  `FRONTEND_CONTRACT.md` documents `rules[]` on the `PolicyRevision` response but
  does not enumerate the per-rule field names. Phase 1 infers camelCase to match
  the surrounding response envelope. Please confirm the response rule shape (and
  whether rule monetary fields are strings or numbers on the response side).

- **PM-7 — Where workspace preconditions are projected.** This document defines
  `workspace_precondition: unit_unresolved | policy_not_activated` as evidence,
  and `FRONTEND_CONTRACT.md` exposes the primitives (`GET /units/...` returns
  `unresolved`/`resolved`; activation lifecycle exposes `active`/`inactive`).
  Which contract/endpoint owns the composed per-channel precondition projection
  the future preview/apply UI will read, and when does it become callable?
