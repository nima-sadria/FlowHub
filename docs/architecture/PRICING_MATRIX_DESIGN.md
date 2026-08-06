# FlowHub Pricing Matrix Design

**Status:** Proposed baseline, implementation pending
**Related:** `ADR-SOURCE-001`, `SOURCE_ACQUISITION_DESIGN.md`,
`PRICING_UI_CONTRACT.md`, `UNIFIED_MULTI_CHANNEL_WORKSPACE.md`
**Supersession:** pending `ADR-PRICING-001`
**Date:** 2026-08-05
**Revision:** 13

## Purpose

This specification defines how FlowHub converts vendor quotes into per-Channel
price targets. It replaces spreadsheet formulas with a declarative, versioned,
exactly-computed rule model.

It is derived from an audit of a real production price workbook: 22 worksheets,
5,997 formula cells, 13 distinct formula shapes, 255 silently broken `#REF!`
formulas, and two mutually incompatible unit conventions in the same file.

## Core Decisions

These are decided, not open:

1. **No formula evaluation in the runtime pricing path.** Pricing is declarative
   parameters only. See the migration exception below.
2. **Pricing never changes stock.** A pricing failure blocks a price target. It
   never marks a product out of stock and never writes availability.
3. **Valuation precedes comparison.** Every quote is valued into the Policy's
   computation currency before any selection, spread check, or guard runs.
4. **Unit conversion and currency conversion are different mechanisms.**
   RIAL↔TOMAN is an exact integer factor of 10 and never an exchange rate.
   Cross-currency valuation uses an FX snapshot and exact rationals.
5. **Exactly one rounding.** A Policy binds only to Channels sharing its
   `computation_currency`. Unit differences are permitted because they convert
   exactly; the round step is constrained so the conversion is always integral.
6. **One immutable Policy Revision owns one matrix.** A Workspace may bind
   several Channels, each to exactly one Policy Revision.
7. **Unit and currency belong to the Source, Vendor, and Channel — never to a
   rule.** Display unit is presentation only and never affects computation.
8. **Exactly one rule entry resolves per cell.** Ambiguity, including product
   group overlap, is rejected when the Policy Revision is saved.
9. **No volatile input.** Every time-dependent comparison uses a frozen
   evaluation timestamp, never the wall clock.
10. **Quote-level exclusion and target-level outcome are different things**, with
    a deterministic precedence order between them.
11. **Every non-price outcome is a typed reason code.** No magic strings.

## Superseding the Formula Engine

`SOURCE_CENTRIC_PRICING_WORKSPACE.md` currently permits a Formula Engine. Upon
acceptance, `ADR-PRICING-001` supersedes that section and records the reversal
and the disposition of existing formula data.

### Scope of the prohibition

The prohibition applies to the **runtime pricing path after migration**. It does
not prohibit the migration translator, which must necessarily parse formulas in
order to convert them.

The translator is a bounded, allowlisted migration tool:

- It runs offline, never in the pricing path, and never on user request at
  runtime.
- It accepts only the enumerated formula shapes in Appendix A. Anything else is
  not attempted.
- It emits parameters, never executable state.
- It is removed from the runtime bundle after the migration release.

Any stored formula that does not translate is **quarantined**, not ignored: its
products produce `legacy_formula_unmigrated` and no price target. No formula is
evaluated by the pricing path after the migration release, including quarantined
ones.

## Pipeline

Order is normative:

```
1. Capture        → QuoteSet in source currency, canonical unit  (Observation)
2. Valuation      → exact rational value per quote            (Workspace)
3. Eligibility    → filter against frozen evaluation time     (Workspace)
4. Basis          → select one valued quote                   (Workspace)
5. Rule           → resolve entry, apply rate and addend      (Workspace)
6. Round          → the single rounding                       (Workspace)
7. Guards         → reject or accept                          (Workspace)
```

Steps 2 through 7 occur at Workspace creation and are recorded immutably.

---

## Currency and Unit Model

Iranian pricing uses one currency with two units. FlowHub treats these as
fundamentally different from cross-currency conversion.

|                    | Unit conversion         | Currency conversion        |
| ------------------ | ----------------------- | -------------------------- |
| Example            | TOMAN → RIAL            | USD → IRR                  |
| Factor             | exact integer, `10`     | rational, from FX snapshot |
| Source of truth    | versioned Unit Registry | `ExchangeRateSnapshot`     |
| Can lose precision | only when dividing      | no, carried as a fraction  |
| User-editable      | no                      | no                         |

Conflating them was the defect in revision 5, which forced a separate Policy per
Channel unit. A unit factor is exact and needs no separate Policy.

### Unit Registry

The registry is system-owned and versioned. Users never enter a factor.

```text
currency_unit_registry_v1
  IRR:
    RIAL   → factor_to_canonical = 1        (canonical)
    TOMAN  → factor_to_canonical = 10
```

`RIAL` is the canonical computation unit: it is the smallest, so every inbound
conversion is an exact multiplication and can never lose precision.

A user selects a unit from a closed enum. Storing `TOMAN` with an inconsistent
factor is not representable.

The Rial/Toman choice is presented **only when `currency == IRR`**. Every other
currency normalizes to its ISO 4217 minor unit, and its factor is a registry
fact the user never sees or enters:

```text
USD  → minor unit = cent,  factor_to_canonical = 100
EUR  → minor unit = cent,  factor_to_canonical = 100
JPY  → no minor unit,      factor_to_canonical = 1
```

```text
factor_to_canonical = 10 ^ (ISO 4217 minor-unit exponent)
```

The exponent itself is not the factor: USD has exponent `2`, and its factor is
`10² = 100`.

A factor of 1 for every non-IRR currency would be wrong: `100.50 USD` would fail
normalization with `quote_precision_invalid` even though it is an ordinary,
perfectly representable price.

Offering a unit _choice_ for USD would still be meaningless — the user selects a
currency, and the registry supplies the rest.

### Three declarations, one canonical unit

| Declaration             | Asked when         | Purpose                                |
| ----------------------- | ------------------ | -------------------------------------- |
| `Source.currency_unit`  | Source is created  | How this Source's numbers are written. |
| `Channel.currency_unit` | Channel is created | How prices are written out.            |
| `display_unit`          | Once, system-wide  | What operators see.                    |

FlowHub performs every conversion between them. An operator never converts
manually and never sees two units side by side.

### Vendor inheritance

```text
Vendor.currency_unit = Source.currency_unit      (v1: no override)
```

The unit is declared once, when the Source is created. A per-vendor override is
**not** implemented in v1: it would reintroduce mixed Rial and Toman inside one
Source, which is exactly the ambiguity the single declaration removes.

`quote_scale` remains Vendor-specific and is a separate axis: unit answers "Rial
or Toman", scale answers "does this vendor write thousands".

If a real workbook is later found to mix units within one Source, per-vendor
units are added by an explicit decision, not assumed now.

### Inbound conversion

```
canonical_minor = raw_value × quote_scale × factor_to_canonical(vendor_unit)
```

Always exact. Non-integral results yield `quote_precision_invalid` as before.

### Outbound conversion and the round-step constraint

Writing to a Channel whose unit is not canonical requires division:

```
channel_value = final_canonical / factor_to_canonical(channel_unit)
```

Division can lose precision. FlowHub does not round here — that would be a
second rounding. Instead the condition is made impossible by construction:

```text
for every Rule Entry applicable to a bound Channel:

    round_step_minor % channel_factor == 0

    if round_order == round_then_surcharge:
        surcharge_minor % channel_factor == 0
```

The second condition is required and easy to miss. Under
`round_then_surcharge` the surcharge is added **after** rounding, so it escapes
the round-step constraint entirely:

```text
round_step = 50,000        → divisible by 10 ✓
surcharge  = 5             → not divisible by 10 ✗
final      = 1,000,005     → 100,000.5 TOMAN ✗
```

Under `surcharge_then_round` the surcharge is inside the rounding, so only the
round-step condition applies.

Validation runs per `(rule_entry, bound_channel)` pair at bind time, not once per
Policy: `round_order` is Policy-wide but `round_step_minor` and
`surcharge_minor` are per entry, so a single non-conforming entry must block the
binding.

Because `final` is then always an exact multiple of the Channel factor, the
outbound conversion is exact and no rounding occurs.

The audited workbook uses steps of 50,000 and 100,000 and a surcharge of
500,000 — all divisible by 10 — so this constraint costs nothing in practice
while removing the failure mode entirely.

### Display unit

`display_unit` affects presentation only. Changing it:

- does **not** create a Policy Revision
- does **not** make any decision outdated
- does **not** alter any stored value

`display_unit` resolves the Rial/Toman question only. It is **not** a currency
conversion and does not make a foreign-currency value presentable in IRR.

For multi-currency reporting, v1 takes the narrow position:

> Global reporting aggregates only Workspaces whose `computation_currency` is
> IRR. A Workspace computed in another currency is excluded from the global
> figures rather than converted into them.
>
> A foreign-currency quote appears only in drill-down, labelled in its own
> currency, and shown as the vendor's `raw_value` so it can be compared directly
> against the vendor's own sheet. It is never rolled into a global total and
> never silently converted for display.
>
> **Every global report states how many Workspaces were excluded** and why. An
> incomplete total that looks complete is worse than no total: the operator makes
> decisions on a figure whose scope they cannot see.

The distinction matters because a quote and a price are different things. The
quote is evidence and must stay recognisable against the vendor's own sheet, so
drill-down shows `raw_value` as written — not the canonical amount in cents or
Rial, which the vendor never wrote and would not recognise. The price is already
valued into `computation_currency` and is what aggregates.

A `display_currency` setting is deferred. When it arrives it must obey one rule:
**a historical report is converted with the exchange-rate snapshot the decision
was made under, never with a live rate.** Re-converting last quarter's approved
prices at today's rate produces numbers that were never approved and cannot be
reconciled against what was actually written to a Channel.

Stored values are always canonical. Display conversion happens at render time
and is never persisted. This is why display unit is safe to change at any moment
while `Source.currency_unit` and `Channel.currency_unit` are not.

**Display conversion must be exact.** Dividing a canonical value by the unit
factor can produce a fractional result, and the UI must show it:

```text
101 RIAL  →  10.1 TOMAN        ✓
101 RIAL  →  10 TOMAN          ✗ cosmetic rounding
```

Final prices are always multiples of `round_step_minor` and therefore integral in
any bound Channel unit, but quotes, bases, and intermediate values are not. An
operator comparing a displayed basis against the vendor's own sheet must see the
same number.

---

## Layer 1: Quote Set

A `QuoteSet` is the vendor-facing input for one product, derived from a Source
Observation. It is immutable and carries provenance.

**No currency conversion happens at this layer.** Converting during capture would
make an Observation depend on an exchange rate that is not part of source
reality, and would break the parse-aware reuse key in
`SOURCE_ACQUISITION_DESIGN.md`: identical bytes captured under two different
rates would produce two different Observations.

### Vendor Revision

| Field                   | Type     | Constraint                                    |
| ----------------------- | -------- | --------------------------------------------- |
| `vendor_revision_id`    | uuid     | Immutable.                                    |
| `vendor_id`             | uuid     | Stable identity, never a column letter.       |
| `currency`              | ISO 4217 | Declared, never inferred.                     |
| `currency_unit`         | enum     | Inherited from Source. Not overridable in v1. |
| `unit_registry_version` | string   | Pins the factor. Not user-editable.           |
| `quote_scale`           | integer  | `>= 1`. Typically `1`, `1000`, `1000000`.     |

The conversion factor is resolved from the Unit Registry at the pinned version.
It is never stored as a free integer on the vendor, so a `TOMAN` vendor with an
inconsistent factor is not representable.

`quote_scale` is the fix for the `×1000` versus `×1000000` split found in the
audited file. A vendor who writes thousands declares it once. No rule ever
compensates for a vendor's writing convention.

`currency_unit` separated from `currency` is what makes Rial and Toman
expressible; a `major/minor` axis alone cannot represent a 10× convention inside
one currency.

`quote_scale` must be a positive integer; zero and negative values are rejected
when the Vendor Revision is saved.

### Quote

| Field                   | Type         | Notes                                            |
| ----------------------- | ------------ | ------------------------------------------------ |
| `product_ref`           | string       | Mapped product identity, never a row index.      |
| `vendor_revision_id`    | uuid         | Carries unit and currency semantics.             |
| `raw_value`             | decimal      | Exactly as captured.                             |
| `canonical_unit_amount` | integer      | See normalization. Always in the canonical unit. |
| `as_of`                 | date \| null | From the vendor column header when present.      |
| `presence`              | enum         | `quoted`, `absent`, `zero`.                      |

`presence` is explicit. The audited workbook conflates an empty cell with a zero
cell through `<>0` filtering. FlowHub does not: `absent` means no quote was
given, `zero` means a quote of zero was given, which is nearly always a data
error and is reported as one.

### Normalization to canonical units

`raw_value` is converted to an **exact rational**, never a float:

```
canonical = raw_value × quote_scale × factor_to_canonical(currency_unit)
```

- If `canonical` is not an exact integer → `quote_precision_invalid`.
- If `raw_value < 0` → `quote_negative`.

FlowHub never silently rounds a captured value. A vendor quoting more precision
than the canonical unit supports is a data problem to surface, not to absorb.

---

## Layer 2: Valuation

Valuation converts every quote into `computation_currency` **before any
comparison occurs**. Selecting a minimum across `100 USD` and `8,000,000 IRR` in
native units is meaningless, so no selection, spread check, or guard may run on
native values.

Each quote is valued using the Workspace's `ExchangeRateSnapshot` and stored as
an exact rational:

```text
valuation_numerator / valuation_denominator
```

The FX ratio is **never rounded into an integer**. It is carried as a fraction
and later composed with the rate fraction, so the only rounding in the entire
computation remains the round step.

A quote whose currency has no rate in the snapshot is excluded with
`currency_unresolved`. This is a quote-level exclusion, not automatically a
target-level failure — see Outcome Precedence.

A newer exchange-rate snapshot makes an existing decision **outdated** under the
normal `ADR-SOURCE-001` consistency rule. It never silently re-prices.

### Channel binding

A Policy Revision may bind only to Channels whose **currency** equals
`computation_currency`. A different currency would require a second FX
conversion after rounding, defeating the single-rounding guarantee.

A different **unit** is permitted, because unit conversion is exact and the
round-step constraint guarantees integrality.

`ChannelConfigRevision` records `currency`, `currency_unit`, and
`unit_registry_version`. Pinning the registry version on the Channel matters as
much as on the Vendor: if a future registry version changed a factor, an unpinned
Channel would silently reinterpret every outbound price.

Both currency and unit are validated at bind time and re-verified at Dry Run and
Apply.

`previous_applied` is stored in canonical units, so the delta guard compares
like with like regardless of the Channel's unit.

---

## Layer 3: Eligibility and Basis Selection

Both operate on valued rationals from Layer 2.

### Frozen evaluation time

The Workspace Snapshot records `workspace_pricing_evaluated_at`. The Policy
Revision records `evaluation_timezone`. Every age comparison uses these, never
the wall clock and never the server's local zone.

Using current time would make pricing volatile and contradict the
reproducibility guarantee in `ADR-SOURCE-001`: replaying the same Observation
and revisions must yield the same prices, and it would not if staleness depended
on when the replay happened.

### Age semantics

`as_of` is a calendar date. Age is a whole-day difference computed in
`evaluation_timezone`:

```
age_days = date_in_tz(workspace_pricing_evaluated_at) - as_of
```

- `max_quote_age_days` is **inclusive**: `age_days <= max_quote_age_days` is
  eligible. A threshold of `7` accepts a quote exactly seven days old.
- `age_days < 0` means the quote is dated in the future → `excluded_future_dated`.
  A future date is a data-entry error, not extra freshness, and must never be
  treated as the freshest quote available.
- `as_of == null` → `excluded_undated`.

### Eligibility

| Field                | Type    | Constraint                                |
| -------------------- | ------- | ----------------------------------------- |
| `exclude_zero`       | boolean | Default `true`.                           |
| `max_quote_age_days` | integer | **Mandatory**, `>= 0`. No hidden default. |
| `min_quote_count`    | integer | `>= 1`. Default `1`.                      |

A quote is eligible when all hold:

```
presence == quoted
AND canonical_unit_amount valid           (not quote_precision_invalid/negative)
AND currency resolved in the FX snapshot
AND (raw_value != 0 OR exclude_zero == false)
AND as_of is not null
AND 0 <= age_days <= max_quote_age_days
```

### Exclusion is evidence, not an outcome

Excluded quotes are **never discarded**. They remain in the QuoteSet with an
explicit reason so the UI and audit can show that a vendor did quote and why it
did not count.

```text
exclusion_reason:
  excluded_stale | excluded_undated | excluded_future_dated
  | excluded_zero | excluded_absent
  | quote_precision_invalid | quote_negative | currency_unresolved
  | null
```

### Basis selection

| Field      | Type | v1              |
| ---------- | ---- | --------------- |
| `strategy` | enum | **`min` only.** |

`max`, `preferred_vendor`, `manual`, and `median` are reserved enum values, not
implemented in v1. `manual` in particular has no provenance model yet: a
manually chosen basis needs an author, a justification, and an immutable record,
and shipping it without those would create prices nobody can explain.

There is no `use_last_applied`: insufficient data produces no price target and
never silently reuses an old number.

Comparison between two valued rationals uses cross-multiplication on
arbitrary-precision integers. No quote is converted to a decimal or float in
order to be compared.

Selection outputs the valued rational plus `basis_vendor_revision_id` and
`basis_quote_as_of`. A price whose provenance cannot be named is not shippable.

---

## Layer 4: Pricing Policy Revision

A `PricingPolicyRevision` is a single immutable record containing one matrix.

### A Workspace binds one Policy per Channel

A Workspace analyses several Channels at once, so a single Policy reference is
insufficient. The Workspace Snapshot records one binding per Channel:

```text
WorkspaceSnapshot
  pricing_policy_bindings:
    - channel_id
      channel_config_revision_id
      pricing_policy_revision_id
      pricing_policy_activation_id
```

Each Channel resolves to **exactly one** Policy Revision. Two Channels may share
a Policy Revision or use different ones; nothing is implicit.

### Channel configuration is pinned, not just validated

`channel_config_revision_id` is recorded in the binding, and both Dry Run and
Apply re-verify that the Channel's current configuration revision still matches.

Validating currency and unit only at bind time is not enough: a Channel's unit
or currency can change afterwards, and the binding would silently become wrong.

If the Channel configuration revision has changed, the decision becomes
**outdated** and requires a new Preview. FlowHub does **not** re-convert the
price to fit the new configuration. A currency or unit change is a change to the
meaning of the output, and meaning changes require review.

Independently versioned per-scope rules were rejected: resolution would have to
select "the latest revision for this scope", which reintroduces mutable
selection state and makes the matrix non-atomic and non-reproducible.

| Field                  | Type                 | Notes                                                          |
| ---------------------- | -------------------- | -------------------------------------------------------------- |
| `policy_revision_id`   | uuid                 | Immutable. Bound into the Workspace Snapshot.                  |
| `computation_currency` | ISO 4217             | Must equal every bound Channel's currency.                     |
| `evaluation_timezone`  | IANA zone            | For age computation.                                           |
| `round_order`          | enum                 | `round_then_surcharge` (v1 default) or `surcharge_then_round`. |
| `arithmetic_version`   | string               | `pricing-arithmetic-v1`.                                       |
| `basis_policy`         | BasisSelectionPolicy | Policy-wide. Not overridable in v1.                            |
| `entries`              | RuleEntry[]          | The matrix.                                                    |

### Rule Entry

| Field                | Type     | Constraint                                            |
| -------------------- | -------- | ----------------------------------------------------- |
| `rule_entry_id`      | uuid     | **Immutable identity.**                               |
| `display_order`      | integer  | Presentation only. Never identity.                    |
| `scope`              | ScopeKey | See Scope Resolution.                                 |
| `rate_mode`          | enum     | `percent_bp` or `multiplier_ppm`.                     |
| `rate`               | integer  | `percent_bp`: `>= -10_000`. `multiplier_ppm`: `>= 0`. |
| `fixed_addend_minor` | integer  | May be negative.                                      |
| `round_mode`         | enum     | `floor`, `ceil`, `nearest`.                           |
| `round_step_minor`   | integer  | `>= 1`.                                               |
| `surcharge_minor`    | integer  | May be negative.                                      |
| `guards`             | GuardSet | See Layer 6.                                          |

A Rule Entry **cannot** override `basis_policy` in v1. Basis selection happens at
step 4 and rule resolution at step 5, so a per-entry basis policy would make step
4 depend on step 5 — a circular dependency in a pipeline whose determinism is
the whole point. Per-entry basis selection is reserved for a future revision that
resolves the ordering explicitly.

`rate >= -10_000` for `percent_bp` prevents a rate below −100%, which would
invert the sign of every price.

Workspace Snapshots and audit records store `rule_entry_id`, never a positional
index. An index shifts when entries are reordered, which would silently rewrite
the meaning of historical records.

All monetary fields are integers in `computation_currency` minor units.

### Why integers throughout

`10%` is `1000` bp. A `1.28` multiplier is `1_280_000` ppm. No parameter is ever
a float. This removes an entire class of divergence between browser preview and
server Apply, which invariant 6 of `ADR-SOURCE-001` requires.

---

## Layer 5: Arithmetic

`pricing-arithmetic-v1` owns **how numbers are computed exactly**. It does not
own which business steps run in which order; that is a Policy field.

### One rounding, and only one

The valued basis, the FX ratio, the rate ratio, and the fixed addend are all
carried as exact rationals with arbitrary-precision integers. Fractions compose;
they are never collapsed early.

```
basis_rational  = valuation_numerator / valuation_denominator
percent_bp:       × (10_000 + rate) / 10_000
multiplier_ppm:   × rate / 1_000_000
then:             + fixed_addend_minor
```

Rounding occurs exactly once, at the round step. Any implementation that
materializes an integer before that point is incorrect, regardless of how small
the apparent error is.

### Not a goal: bit-matching Excel

Excel computes in binary floating point and is itself inconsistent at
boundaries. Where exact rational arithmetic and Excel disagree, Excel is wrong.
The migration report flags any product whose recomputed price differs from the
workbook so the difference is reviewed rather than discovered in production.

### Evaluation order

```
1. basis_rational                                    (Layers 2–3)
2. rational = apply_rate(basis_rational, mode, rate) + fixed_addend_minor
3. final    = apply_round_order(rational, surcharge_minor, policy)   ← integer
4. guards(final, quote_set, previous_applied)
```

Step 3 follows the Policy's `round_order`:

```
round_then_surcharge:   round(rational, mode, step) + surcharge
surcharge_then_round:   round(rational + surcharge, mode, step)
```

`round_then_surcharge` is the v1 default because it reproduces the audited
workbook (`FLOOR(...)+500000`) and treats the surcharge as a flat fee rather
than a component absorbed by the rounding step.

`round_order` is a **closed enum with exactly two members**. It is not a
composable pipeline, not an ordered step list, and not user-extensible.

**Order is a Policy field, not part of `arithmetic_version`.** Changing it is a
business decision, not an arithmetic correctness fix. As a Policy field, changing
it produces a new Policy Revision; activating that revision on a Channel marks
that Channel's decisions outdated and requires a new Preview. The historical
order remains reproducible, and no code release is involved. Implementations must not collapse the two branches into one code path
when the surcharge happens to be zero.

### Rounding contract

`round(x, mode, step)` where `x` is an exact rational `n/d` with `d > 0` and
`step` is a positive integer. Semantics are fixed and identical on every
platform:

```
floor    → toward negative infinity
ceil     → toward positive infinity
nearest  → half away from zero
```

Implemented with quotient and remainder on arbitrary-precision integers, never
with a floating-point library function:

```
let  N = n,  D = d × step

floor:    q = N ÷ D, remainder r
          if r != 0 and sign(N) != sign(D) then q = q − 1
          result = q × step

ceil:     q = N ÷ D, remainder r
          if r != 0 and sign(N) == sign(D) then q = q + 1
          result = q × step

nearest:  q = N ÷ D, remainder r          (truncated quotient)
          if 2 × |r| >= |D| then q = q + sign(N) × sign(D)
          result = q × step
```

Two clarifications that cause divergence when left implicit:

- **`floor` is mathematical floor, not truncation.** Most languages truncate
  toward zero on integer division. For negative values, truncation and floor
  differ by one step, and a negative `fixed_addend_minor` or `surcharge_minor`
  can produce a negative intermediate.
- **`nearest` breaks ties away from zero**, not banker's rounding. Half-to-even
  is defensible statistically but surprises operators who expect a price ending
  in exactly half a step to round up.

Contract tests must cover the exact half case, the negative intermediate case,
and a remainder of zero, for all three modes.

### Final value constraint

`final` must be `> 0`. A non-positive computed price yields `nonpositive_price`
and no price target. This is checked before guards, because a non-positive price
makes every ratio guard meaningless.

---

### Operational bounds

Arbitrary-precision integers are required for correctness but must not become an
unbounded performance surface. The following limits are enforced at save or
capture time, not at evaluation time:

| Value                                   | Limit                                               |
| --------------------------------------- | --------------------------------------------------- |
| `raw_value` total significant digits    | 18                                                  |
| `raw_value` decimal places              | 6                                                   |
| `raw_value` source string length        | 32 characters                                       |
| `quote_scale`                           | `<= 10^9`                                           |
| `rate`                                  | `percent_bp` `<= 10^7`; `multiplier_ppm` `<= 10^12` |
| `fixed_addend_minor`, `surcharge_minor` | `<= 10^18` absolute                                 |
| `round_step_minor`                      | `<= 10^15`                                          |
| FX numerator and denominator            | `<= 10^18` each                                     |

Bounding significant digits alone is insufficient: a value with many decimal
places produces a large denominator during exact-rational normalization even when
the digit count looks modest. Decimal places and raw input length are therefore
bounded independently.

Every rational is **reduced to lowest terms after each composition**. Without
reduction, denominators grow multiplicatively across valuation, rate, and addend,
and a long-running Workspace accumulates arbitrarily large integers for no
benefit.

Exceeding a limit is a save-time or capture-time error with a named reason, never
a silent truncation and never a runtime failure partway through a Workspace.

---

## Scope Resolution

```text
ScopeKey = (channel_id | null, product_group_revision_id | product_ref | null)
```

### Complete specificity chain

Both axes are independent, so all six combinations exist. Channel specificity
outranks product specificity:

```
1. (channel,  product_ref)
2. (channel,  group)
3. (channel,  null)
4. (null,     product_ref)
5. (null,     group)
6. (null,     null)
```

The earlier revision omitted `(null, product_ref)`, leaving a saveable scope with
no defined precedence. All six are now resolvable and the chain is exhaustive.

Most specific match wins. Evaluation stops at the first level with a match.

### Product Group

A Product Group is a user-defined entity with an immutable revision. It is not
derived from a catalog taxonomy in v1. A group has a name and an explicit
membership list; it is never a row range.

A Rule Entry references a `product_group_revision_id`. **Publishing a new group
revision does not by itself make any decision outdated.** An existing Policy
Revision continues to reference the group revision it was published against, and
that pairing remains valid and reproducible indefinitely.

Only publishing a new **Policy Revision** that references the newer group
revision changes the inputs to new decisions. Group membership can therefore
never drift underneath an approved decision, and editing a group does not
invalidate work in progress elsewhere.

### Overlap is a save-time error

A product may belong to more than one group. If two entries at the same channel
level reference groups whose membership intersects, those products would match
two entries at equal specificity.

FlowHub does not resolve this by group priority, creation order, or entry order.
Any implicit tiebreak is a silent pricing decision, which this design forbids.

**Save-time validation:** entries are partitioned by **exact `channel_id`
value**, with `null` treated as its own distinct partition rather than a
wildcard that overlaps every Channel. Within each partition, compute the
pairwise membership intersection of every referenced group revision.
A non-empty intersection prevents the Policy Revision from being saved. The
error names both `rule_entry_id` values, both group revisions, and a sample of
the overlapping products.

This is computable at save time because group revisions are immutable and
membership is explicit. The same check covers duplicate `(channel, product_ref)`
and duplicate `(channel, null)` entries.

`rule_ambiguous` remains a runtime outcome for defensive purposes, but a
well-formed Policy Revision can never produce it.

Every priced cell records `resolved_rule_entry_id` and `resolution_specificity`,
so an operator can answer "why this price" without reading configuration.

---

## Layer 6: Guards

Guards run after computation and can only reject, never adjust.

| Guard                     | Field                                | Compares             |
| ------------------------- | ------------------------------------ | -------------------- |
| Absolute floor            | `min_price_minor`                    | integer vs integer   |
| Absolute ceiling          | `max_price_minor`                    | integer vs integer   |
| Delta limit               | `max_increase_bp`, `max_decrease_bp` | integer vs integer   |
| Markup floor              | `min_markup_bp`                      | integer vs rational  |
| Conservative markup floor | `min_markup_worst_case_bp`           | integer vs rational  |
| Basis spread              | `max_basis_spread_bp`                | rational vs rational |

### Numeric contract

`final` is an integer. `basis` and every valued quote are **rationals**, not
integers. No guard may round a rational in order to compare it.

Every ratio comparison is performed by cross-multiplication on
arbitrary-precision integers. For a rational `n/d` with `d > 0`:

```
min_markup_bp:
    reject when   (final × d − n) × 10_000  <  min_markup_bp × n
    where n/d = basis_rational

min_markup_worst_case_bp:
    same form, with n/d = highest eligible valued quote

max_basis_spread_bp:
    let  lo = n_lo/d_lo  (lowest eligible),  hi = n_hi/d_hi  (highest eligible)
    reject when   (n_hi × d_lo − n_lo × d_hi) × 10_000  >  max_basis_spread_bp × (n_lo × d_hi)
```

A single eligible quote makes the spread guard trivially pass; it is not an
error.

### Zero basis

If `exclude_zero == false`, a zero quote can become the basis, and every markup
and spread guard would divide by zero.

FlowHub does not skip the guard and does not treat the result as infinite
markup. A zero basis with any markup or spread guard configured yields
`guard_rejected` with guard reason `basis_zero`. Pricing from a zero cost is a
data error, and the guard exists precisely to stop it.

### `previous_applied`

Because `computation_currency` equals the Channel currency, `previous_applied`
is already in the same currency and minor unit. No re-valuation occurs, so
exchange-rate movement is never mistaken for a price change.

If no previous applied price exists, the delta guard does not run and is
recorded as `not_applicable`.

### Markup reference

FlowHub does **not** model procurement cost as an independent entity. No such
data exists in the audited workbook, and making it mandatory would produce
`cost_unavailable` for essentially the entire catalog on day one.

The markup reference is the **selected basis** — the best price, which the
business already treats as cost.

`min_markup_worst_case_bp` measures against the highest eligible valued quote
instead. It answers a different question: whether the price still clears a
minimum markup when measured against the most expensive quote in the eligible
set, rather than the cheapest. It is off by default and enabled per Policy.

Eligible quotes for all guards are exactly the population Layer 3 used. Guards
and basis selection never see different data.

A markup rejection names the reference vendor and quote. An operator must see
which vendor caused the rejection, not an opaque threshold failure.

---

## Outcome Precedence

**No pricing outcome ever writes stock or availability.** Every failure blocks a
price target and leaves existing Channel state untouched.

### Two levels

- **Quote-level exclusion** removes one quote from the eligible set. It is
  recorded as evidence and does not by itself fail the target.
- **Target-level outcome** is the single result for the product-Channel cell.

One quote missing an FX rate while two others remain eligible produces a normal
`priced` result. The excluded quote is visible as evidence. The target fails only
when the eligible set cannot support a price.

### Deterministic order

The first matching condition wins. Configuration faults precede data faults,
because a configuration fault blocks the cell regardless of data quality and is
the actionable cause.

#### Preconditions and their scope

Preconditions are evaluated **before any cell is examined**. Their blast radius
matches where the fault actually lives, consistent with per-Channel readiness.

| Precondition                            | Outcome                | Scope                            |
| --------------------------------------- | ---------------------- | -------------------------------- |
| `Source.currency_unit` is `unresolved`  | `unit_unresolved`      | All Channels fed by that Source. |
| `Channel.currency_unit` is `unresolved` | `unit_unresolved`      | That Channel only.               |
| No activation for the Channel           | `policy_not_activated` | That Channel only.               |

A Source without a declared unit invalidates every number that originates from
it, so nothing downstream can be priced. A Channel without a declared unit
invalidates only its own output; other Channels reading the same Source are
unaffected and remain fully previewable, dry-runnable, and appliable.

These are not per-cell outcomes. Evaluating cells under an unresolved unit and
reporting `no_quote` for an empty one would name the wrong problem: the operator
would go looking for missing vendor data when the actual fault is a single
undeclared setting.

#### Partial application is explicit

Apply is **per Channel**, not all-or-nothing. A blocked Channel does not prevent
healthy Channels from being applied.

Blocking every Channel because one is misconfigured is collateral damage, and in
a pricing system it means shipping nothing for days over an unrelated setting.

But partial application is never silent, and it introduces **no new write path**.

#### `partially_applied` is a projection, not a mechanism

All writing goes through the existing `WritePipelineService` defined in
`UNIFIED_MULTI_CHANNEL_WORKSPACE.md`. This specification adds no alternative
route and no pricing-specific write logic.

That model already provides what safe partial application requires:

- every item has a `ProviderWriteAttempt` with durable idempotency
- only `VERIFIED_APPLIED` counts as success
- an indeterminate result becomes `RECONCILIATION_REQUIRED` and is never blindly
  retried
- retry never re-sends an item already `VERIFIED_APPLIED`

`partially_applied` is **computed**, never recorded independently. Deriving it
independently would let the summary drift from the attempts, and the attempts are
the only record the provider can actually be reconciled against.

The projection is built from four inputs, not from attempts alone:

```text
immutable apply plan            → expected_item_count, expected items
channel precondition result     → blocked, with reason
write job state                 → pending | running | finished
latest ProviderWriteAttempt     → per expected item
```

Attempts alone are insufficient: a blocked Channel has no attempts, and neither
does a run that has not started. Zero attempts is ambiguous on its own.

#### Indeterminate is not partial success

A Workspace containing any indeterminate item is **not** `partially_applied`. It
is `reconciliation_required`, a distinct and more serious state.

#### Two explicit folds

There is no single fold reused at both levels. The two levels consume different
inputs — one reads item attempts, the other reads Channel statuses — and
`partially_applied` at Channel level has no representation among the item
counters. Both folds are total and ordered.

**Channel fold.** Counters over the expected items in the apply plan:
`unknown`, `verified`, `failed`, with `accounted = unknown + verified + failed`.

```text
if channel precondition blocked             → blocked
else if expected_item_count = 0             → no_changes
else if write job not started               → pending
else if write job running                   → running
else if accounted != expected_item_count    → failed (apply_projection_incomplete)
else if unknown > 0                         → reconciliation_required
else if verified > 0 and failed > 0         → partially_applied
else if verified > 0                        → applied
else                                        → failed
```

**Workspace fold.** Over Channel statuses, most severe first:

```text
if any channel reconciliation_required      → reconciliation_required
else if any channel running                  → running
else if any channel pending                  → pending
else if any channel partially_applied       → partially_applied
else if applied > 0 and (failed > 0
                         or blocked > 0)    → partially_applied
else if applied > 0                         → applied
else if failed > 0                          → failed
else if blocked > 0                         → blocked
else                                        → no_changes
```

Four cases the earlier single fold got wrong:

- **Some verified and some failed** is genuinely partial. Calling it `failed`
  hides that real prices reached the provider, and an operator who believes
  nothing shipped may re-run or roll back on a false premise.
- **Every Channel blocked** satisfied the old `partially_applied` condition
  vacuously — "every attempted item verified" is trivially true when nothing was
  attempted. It is now `blocked`.
- **`no_changes` requires evidence.** It is reported only when the apply plan
  recorded `expected_item_count = 0`, never merely because no attempt exists.
  Absence of attempts is equally consistent with blocked, pending, and crashed.
- **A run that has not started** was previously indistinguishable from a no-op.
  `pending` and `running` are now explicit states, so an unstarted or in-flight
  Apply is never reported as a completed one.
- **A finished job with an unaccounted planned item** is an invariant failure,
  not success. `WritePipelineService` commits dispatch intent before provider I/O,
  so a missing terminal outcome cannot be silently treated as applied. The
  projection reports `failed` with `apply_projection_incomplete` and raises an
  operational alert.

`partially_applied` means "we know exactly what shipped and what did not".
`reconciliation_required` means "we do not know", and presenting the second as a
softer form of the first would let an operator move on from a Workspace whose
real state nobody has established.

The Workspace also records the blocked Channel list with reasons, and Activity
records both, so the precondition failures from the previous section remain
visible alongside the write results.

#### Per-cell precedence

The first matching condition wins.

| #   | Outcome                     | Condition                                   |
| --- | --------------------------- | ------------------------------------------- |
| 1   | `product_unmapped`          | Product not mapped to the Channel.          |
| 2   | `legacy_formula_unmigrated` | Quarantined by migration.                   |
| 3   | `rule_unresolved`           | No entry matches any specificity level.     |
| 4   | `rule_ambiguous`            | Two entries match at equal specificity.     |
| 5   | `no_quote`                  | Every quote has `presence == absent`.       |
| 6   | `all_quotes_zero`           | At least one quote, all quoted values zero. |

| 7 | `currency_unresolved` | Eligible count below `min_quote_count`, **and every** exclusion was `currency_unresolved`. |
| 8 | `quote_precision_invalid` | Same, where every exclusion was `quote_precision_invalid`. |
| 9 | `insufficient_quotes` | Eligible count below `min_quote_count` for any other or mixed reason. |
| 10 | `nonpositive_price` | Computed `final <= 0`. |
| 11 | `guard_rejected` | A guard rejected. Guard is named. |
| 12 | `priced` | Otherwise. |

Rows 7 and 8 exist so a uniform cause is reported specifically. When exclusions
are mixed, the generic `insufficient_quotes` is correct: no single cause
explains the failure, and naming one would mislead.

All values are `retryable: no`. Extend the reason-code catalog in
`SOURCE_ACQUISITION_DESIGN.md` accordingly.

### Blocked price targets must be observable

Because pricing failures no longer delist products, a stale price can persist on
a Channel indefinitely. This is the same silent-stall risk that
`ADR-SOURCE-001` invariant 14 closes for schema drift.

#### Readiness dimensions are independent

| Situation                                       | Acquisition | Schema    | Pricing    | Aggregate  |
| ----------------------------------------------- | ----------- | --------- | ---------- | ---------- |
| Captured, schema matches, rules complete        | `ready`     | `match`   | `ready`    | `ready`    |
| Captured, schema matches, no rule for a Channel | `ready`     | `match`   | `degraded` | `degraded` |
| Captured, headers drifted                       | `ready`     | `blocked` | unchanged  | `degraded` |
| Capture failed, rules complete                  | `degraded`  | unchanged | unchanged  | `degraded` |

Schema drift does not degrade acquisition: the file was read successfully and
the Observation is valid. It blocks the schema dimension, and the aggregate
reflects that.

Conflating dimensions misdirects the operator. A Source that reads perfectly
every night while shipping nothing must not display as an acquisition problem,
and a genuine WebDAV outage must not be masked by healthy pricing.

`pricing_readiness` is scoped per Channel. One Channel missing a rule does not
degrade the others.

#### Attention signal

Durable and deduplicated on a stable key:

```text
(source_id, channel_id, outcome_code, policy_revision_id)
```

One open signal per key, not one per product. Re-running the same blocked
condition updates the existing signal rather than creating a new one.

Each signal carries affected product count, affected Channel count, outcome code,
a representative sample of affected products, first-seen and last-seen
timestamps, and the Policy Revision in force when it opened.

**Activation closes prior signals for that Channel only.** Activating a Policy
Revision on a Channel closes open signals matching:

```text
(source_id, this_channel_id, *, previous_policy_revision_id)
```

with reason `superseded`, recorded in Activity. Signals belonging to other
Channels that still use the previous Policy Revision are **not** touched — their
conditions are still live and closing them would hide real problems.

If the condition persists on the activated Channel, a new signal opens on the new
key. Without this rule, superseded signals accumulate forever and the operator
cannot distinguish a live problem from a resolved one.

A signal otherwise closes only when its condition clears. It is never closed by
a successful acquisition alone.

Overview shows **last successful Apply** separately from **last successful
acquisition**.

---

## Policy Activation

Activation is a per-Channel event, not a property of the Policy. A Policy
Revision is immutable and may be shared by several Channels, so nothing about a
particular activation may be written onto it.

Activation and deactivation share **one append-only lifecycle log**. Separate
activation and deactivation tables break the chain: after a deactivation the head
holds no activation, so the next activation would carry a null predecessor even
though it is not the first. A single log keeps activate, deactivate, and
reactivate on one continuous chain.

```text
PricingPolicyLifecycleEvent
  event_id
  channel_id
  predecessor_event_id             (nullable — null only for the very first event)
  kind                             activate | deactivate
  actor
  reason
  created_at

  -- activation payload, present only when kind = activate
  policy_revision_id
  channel_config_revision_id
  unit_registry_version
  migration_preview_id
  blocked_scope_acknowledgement    (nullable)
  acknowledged_by

ChannelPricingPolicyHead
  channel_id                       (primary key)
  current_event_id
  effective_activation_id          (nullable — null while deactivated)
  head_version
```

`effective_activation_id` is the `event_id` of the activate event currently in
force, or null after a deactivate. The Workspace pins
`effective_activation_id`, exactly as before.

Deactivation carries its own actor and reason. Modelling it as a null head with
no record would erase who stopped pricing on a Channel and why — usually the fact
an operator most needs six months later.

Every activation-scoped fact — the migration preview it was gated on, the
acknowledgement, who acknowledged it — lives here. Two Channels sharing one
Policy Revision have two independent activations and two independent
acknowledgements.

### Activation contract

- **Append-only, with backward links only.** A lifecycle event is never mutated
  after it is written. Each event records `predecessor_event_id` pointing at the
  event it follows; the predecessor is not touched. Writing `superseded_by` onto
  the older record would be a mutation and would break the immutability this
  model depends on.
- **Effective state lives in a separate head pointer**, defined above. The head
  is the only mutable object, it holds no history, and every historical fact
  remains in the append-only lifecycle log.

- **A lifecycle write is one transaction.** The event insert and the head swap
  commit together:

The head row is created when the **Channel** is created, with
`current_event_id = NULL`, `effective_activation_id = NULL`, and
`head_version = 0`. It is never created lazily, so a lifecycle write is always an
update and never has to branch on whether a row exists.

Both kinds use the same transaction shape:

```text
BEGIN
  INSERT lifecycle_event (
      kind                 = 'activate' | 'deactivate',
      predecessor_event_id = head.current_event_id      -- may be NULL
  )
  UPDATE head
     SET current_event_id        = new_event_id,
         effective_activation_id = (kind = 'activate') ? new_event_id : NULL,
         head_version            = head_version + 1
   WHERE channel_id   = ?
     AND head_version = ?                      -- the whole guard, on its own
  IF rows_affected = 0 THEN ROLLBACK
COMMIT
```

**The guard is `head_version` alone.** An earlier draft also compared the
predecessor for equality, which is broken whenever the predecessor is null — the
very first event, and every activation following a deactivation. `= NULL` never
matches in SQL, so those cases would fail forever.

`head_version` is monotonic and covers the same concurrency case without any null
handling. The caller still reads the head first and carries
`predecessor_event_id` into the new event, so the backward chain stays correct —
but the chain is data, not the concurrency guard.

A failed compare-and-swap rolls back the activation insert as well. Writing the
record first and swapping afterwards would leave an immutable activation that
was never effective — a record that can never be corrected, because activations
are never mutated. An orphan in an append-only log is permanent.

A losing writer retries against the new head or fails; it never overwrites. Two
Policies are never simultaneously effective on one Channel, even transiently.

- **Dry Run and Apply re-verify the head.** Both check:

```text
head(channel_id).effective_activation_id == workspace.pricing_policy_activation_id
```

A mismatch makes the decision `outdated` and requires a new Preview. Pinning the
activation in the Workspace is not sufficient on its own: the pin records what
was true at Preview time, and only the head check proves it is still true at
write time.

- **Deactivation is an event in the same log**, appended like any other, with
  `effective_activation_id` set to null under the same compare-and-swap.
  Deactivation is never modelled as the absence of a record, and never as a
  separate table that would break the chain.
- **The Workspace pins `pricing_policy_activation_id`**, not only the Policy
  Revision ID. The acknowledgement, the migration preview it was gated on, and
  the pinned Channel config all hang off the activation. Recording only the
  Policy Revision would make it impossible to prove afterwards which
  acknowledgement a decision was made under, since one Policy Revision may be
  activated on several Channels under different acknowledgements.

## Activation Gate

`excluded_undated` is enforced strictly from day one. Observation time is **not**
used as a substitute for a missing `as_of`: capture time records when FlowHub
read the file, not when the vendor set the price, and substituting one for the
other would make every quote permanently fresh.

Because the audited workbook contains vendor columns with no date, this will
exclude real data on first activation. Activation is therefore gated:

1. A **migration preview** runs before a Policy Revision may be activated.
2. It reports every vendor lacking dates, and every product that falls below
   `min_quote_count` as a result.
3. Activation is blocked until either the vendor data is corrected, or an
   operator explicitly acknowledges the blocked scope.
4. The acknowledgement is recorded on the `PricingPolicyActivation`, names the
   affected product count, and is visible in audit.

An operator may choose to ship with a blocked scope. They may not do so
unknowingly.

**Acknowledgement permits activation and nothing else.** It does not:

- change `pricing_readiness` to `ready`
- close or suppress any attention signal
- mark the affected products as priced or as intentionally unpriced

The blocked scope remains degraded and remains visible until the underlying data
is corrected. An acknowledgement that silenced the signal would convert a known
gap into a forgotten one, which is the failure this gate exists to prevent.

---

## Migrating Existing Sources and Channels

Existing IRR records predate the unit declaration and have no `currency_unit`.

```text
currency_unit     = unresolved
pricing_readiness = degraded
Apply             = blocked
```

**FlowHub never infers the unit from magnitude.** A price of `1,200,000` is a
plausible Rial value and a plausible Toman value, and guessing wrong shifts every
price on that Source by a factor of ten in the same direction — a uniform,
plausible-looking error that no guard would catch because every number moves
together.

`unresolved` is a first-class value, not a null to be defaulted. Every read path
must handle it explicitly.

Resolution is a one-time explicit choice by the owner, per Source and per
Channel, recorded with the actor and timestamp. Until then the Source is
degraded, Apply is blocked, and an attention signal is open.

### What is permitted while unresolved

| Operation               | Permitted | Why                                                  |
| ----------------------- | --------- | ---------------------------------------------------- |
| Raw Source Preview      | yes       | Shows captured values as written, no interpretation. |
| Unit Resolution Preview | yes       | Two-sided, non-approvable. See below.                |
| Pricing Preview         | **no**    | Every number could be wrong by exactly 10×.          |
| Dry Run                 | **no**    | Same.                                                |
| Apply                   | **no**    | Same.                                                |

An earlier revision permitted Pricing Preview here on the reasoning that reading
is safe. That reasoning is wrong: a priced preview computed from an unknown unit
displays plausible numbers that may be off by a factor of ten, and a plausible
wrong number is more dangerous than no number. It invites an operator to
sanity-check prices against a value the system does not actually understand.

### Unit Resolution Preview

A dedicated, explicitly two-sided view that shows the same rows interpreted both
ways, side by side and labelled:

```text
Product        as RIAL            as TOMAN
iPhone 15      1,200,000 RIAL     12,000,000 RIAL
```

It exists so the owner can recognise which interpretation matches reality. It
carries no approval control, produces no Workspace, and cannot be promoted into
a decision. It is a disambiguation aid, not a Preview.

### Distinct reason code

```text
unit_unresolved       ← the Source or Channel unit has never been declared
currency_unresolved   ← the FX snapshot has no rate for this currency
```

These are different failures with different remedies: one is answered by the
owner choosing Rial or Toman once, the other by adding a rate. Reusing
`currency_unresolved` for a missing unit would send the operator to the FX
configuration for a problem that has nothing to do with it.

---

## Integration with ADR-SOURCE-001

- `PricingPolicyRevision` and `ProductGroupRevision` are immutable and
  append-only, like `MappingRevision`.
- The Workspace Snapshot records `pricing_policy_revision_id`,
  `exchange_rate_snapshot_id`, `arithmetic_version`,
  `workspace_pricing_evaluated_at`, and per-cell `resolved_rule_entry_id`.
- **Creating** a Policy Revision has no effect on any existing decision. A
  revision is a draft artifact until it is activated on a Channel.
- **Activating** a Policy Revision on a Channel makes decisions bound to that
  Channel's previous activation **outdated**.
- **Deactivating** a Channel likewise makes that Channel's decisions outdated.
- A newer exchange-rate snapshot makes an existing decision **outdated**.
- A newer group revision does not, until a Policy Revision referencing it is
  activated.
- Pricing evaluation issues no provider requests, satisfying invariant 7.
- Pricing is fully deterministic: no wall clock, no `RAND`, no volatile input.

## Forbidden

- Formula evaluation in the runtime pricing path after migration.
- Floating-point arithmetic in computation or storage.
- Any rounding before the round step, including FX conversion.
- A second currency conversion between the rounded price and the Channel.
- Comparing, aggregating, or guarding on native-currency values.
- Rounding a rational in order to evaluate a guard.
- Currency conversion during capture.
- Wall-clock time or server-local timezone in any pricing comparison.
- Treating capture time as a substitute for a missing `as_of`.
- Any pricing outcome writing stock or availability.
- Positional indexes as rule identity.
- Implicit tiebreaks between overlapping groups.
- Silent fallback when a rule fails to resolve.
- Guards that adjust a price instead of rejecting it.
- Unit or currency compensation inside a rule.
- Inferring a currency unit from the magnitude of a value.
- Cosmetic rounding in display conversion.
- Per-vendor unit overrides in v1.
- Writing activation-scoped facts onto an immutable Policy Revision.
- Closing a signal belonging to a Channel other than the one being activated.
- Pricing Preview, Dry Run, or Apply on an unresolved unit.
- Reusing `currency_unresolved` for a missing unit declaration.
- Converting a historical report with a live exchange rate.
- Two Policy Revisions simultaneously effective on one Channel.
- Translating a formula shape whose meaning is inferred rather than proven.
- A unit factor of 1 for a currency that has a minor unit.
- Mutating an activation record after it is written.
- Aggregating a non-IRR Workspace into a global IRR report, or presenting such a
  report without stating the excluded count.
- Persisting an activation record whose head swap did not commit.
- Treating Policy Revision creation as a decision-affecting event.
- Blocking a healthy Channel because a different Channel is misconfigured.
- Marking a partially applied Workspace as `applied`.
- Any write path for price targets other than `WritePipelineService`.
- Recording Workspace or Channel apply status independently of item attempts.
- Presenting a Workspace containing indeterminate items as `partially_applied`.
- Reporting a fully blocked Workspace as partially applied.
- Reporting a no-op Workspace as applied.
- Inferring `no_changes` from the absence of write attempts.
- Reusing one fold across both levels.
- Separate activation and deactivation tables, which break the lifecycle chain.
- Retrying an item already `VERIFIED_APPLIED`.
- Comparing a nullable predecessor with `=` in the head guard.
- Deactivating a Channel without an append-only event naming actor and reason.

## Acceptance Criteria

- Every formula shape is either fixture-proven and translated, or quarantined
  with a typed outcome. Every translated shape is expressible without runtime
  formula evaluation.
- Basis selection, spread checks, and guards operate only on valued quotes.
- Rounding occurs exactly once, and FX contributes a fraction.
- A Policy cannot bind to a Channel whose currency differs from
  `computation_currency`.
- A quote whose normalization is not an exact integer yields
  `quote_precision_invalid` and is never silently rounded.
- Staleness is computed against `workspace_pricing_evaluated_at` in
  `evaluation_timezone`; replaying a Workspace months later reproduces identical
  eligibility.
- A quote dated exactly `max_quote_age_days` old is eligible.
- A future-dated quote is excluded, never treated as freshest.
- Undated quotes are excluded, and activation is gated on an explicit
  acknowledgement of the resulting blocked scope.
- Excluded quotes remain visible as evidence with an explicit reason.
- One quote missing an FX rate does not fail a target that still has enough
  eligible quotes.
- Target outcomes follow the precedence table exactly, verified by fixtures for
  each row.
- Every one of the six scope levels resolves, including `(null, product_ref)`.
- Overlapping group membership at the same channel level prevents saving the
  Policy Revision and names both entries.
- A zero basis with a markup or spread guard yields `guard_rejected` with reason
  `basis_zero`, never a division error.
- Guard comparisons use cross-multiplication and never round a rational.
- No pricing outcome changes stock or availability in any Channel.
- Acquisition, schema, and pricing readiness move independently.
- Activating a new Policy Revision closes prior signals as `superseded`.
- Publishing a group revision alone leaves existing decisions valid.
- Workspace and audit records reference `rule_entry_id`, and reordering entries
  does not alter historical meaning.
- Replaying a historical Observation with its recorded revisions reproduces the
  original prices exactly.
- A Workspace binds one Policy Revision per Channel, each pinned to a
  `channel_config_revision_id`.
- Changing a Channel's unit or currency makes the decision outdated; it never
  triggers a silent re-conversion.
- `round_step_minor` is rejected at bind time when it is not a multiple of a
  bound Channel's unit factor.
- Outbound conversion to a Channel unit is always exact and performs no rounding.
- Changing `display_unit` alters no stored value and outdates no decision.
- A Rule Entry cannot override `basis_policy` in v1.
- `floor` rounds toward negative infinity and `nearest` breaks ties away from
  zero, verified by fixtures including negative intermediates and exact halves.
- Rationals are reduced to lowest terms after each composition.
- Exceeding an operational bound fails at save or capture time, never mid-run.
- Acknowledging a blocked scope permits activation without clearing readiness or
  closing signals, and is recorded on the activation, not the Policy Revision.
- Binding is rejected when any applicable Rule Entry has a `round_step_minor`, or
  a `surcharge_minor` under `round_then_surcharge`, that is not a multiple of the
  Channel unit factor.
- A vendor cannot declare a unit different from its Source in v1.
- An `unresolved` unit blocks Pricing Preview, Dry Run, and Apply, and permits
  only Raw Source Preview and the two-sided Unit Resolution Preview.
- The Unit Resolution Preview carries no approval control and cannot produce a
  Workspace.
- `unit_unresolved` and `currency_unresolved` are distinct codes with distinct
  remedies.
- Activation records are append-only with backward links only; no record is
  mutated after being written.
- Exactly one effective activation per Channel, enforced by compare-and-swap on
  a separate head pointer, with deactivation modelled as its own event.
- `100.50 USD` normalizes to `10050` and does not yield
  `quote_precision_invalid`.
- An unresolved unit aborts before cell evaluation and never surfaces as
  `no_quote` on an empty cell.
- An unresolved Source unit blocks every Channel fed by it; an unresolved Channel
  unit blocks only that Channel.
- A failed head compare-and-swap rolls back the activation insert, leaving no
  orphan record.
- Dry Run and Apply re-verify the head against the pinned activation and mark the
  decision outdated on mismatch.
- Creating a Policy Revision changes no existing decision; only activation and
  deactivation do.
- Apply proceeds per Channel, and a Workspace with blocked Channels is recorded
  as `partially_applied` with both lists.
- All price-target writes go through `WritePipelineService`; this specification
  adds no write path.
- Channel and Workspace apply status are folds over `ProviderWriteAttempt`
  states, never recorded independently.
- Only `VERIFIED_APPLIED` counts as success; an indeterminate outcome becomes
  `RECONCILIATION_REQUIRED`.
- Retrying an Apply does not re-send any item already `VERIFIED_APPLIED`.
- A Workspace containing any `RECONCILIATION_REQUIRED` item reports
  `reconciliation_required`, never `partially_applied`.
- A mix of verified and failed items reports `partially_applied`, not `failed`.
- A Workspace whose Channels were all blocked reports `blocked`, not
  `partially_applied`.
- A Workspace with nothing to write reports `no_changes`, not `applied`.
- Channel and Workspace statuses use two explicit folds, not one reused fold.
- The Channel projection reads the apply plan, precondition result, write job
  state, and latest attempt per expected item.
- A finished Channel job cannot report `applied` unless `unknown + verified +
  failed == expected_item_count`; a mismatch reports
  `apply_projection_incomplete`.
- `no_changes` is reported only when the apply plan recorded
  `expected_item_count = 0`.
- An unstarted or in-flight Apply reports `pending` or `running`, never
  `no_changes` or `applied`.
- At Workspace level, `running` takes precedence over `pending` when both are
  present.
- Activation following a deactivation carries a non-null `predecessor_event_id`,
  and the lifecycle chain remains unbroken across reactivation.
- The head row exists from Channel creation with `head_version = 0`, and the
  first activation succeeds with a null predecessor.
- The compare-and-swap guard uses `head_version` only and performs no nullable
  equality comparison.
- Deactivation appends a lifecycle event carrying `predecessor_event_id`, actor,
  reason, and timestamp, and nulls `effective_activation_id`.
- `factor_to_canonical` equals `10 ^ minor-unit exponent`, so USD resolves to 100.
- Drill-down shows the vendor's `raw_value`, not the canonical amount.
- The Workspace pins `pricing_policy_activation_id`, and the acknowledgement
  under which any decision was made is recoverable from it.
- A formula shape is translated only when a fixture proves its meaning;
  otherwise it is quarantined.
- Bounds on decimal places and raw input length are enforced independently of
  significant digits.
- No code path infers a unit from a value's magnitude.
- Activating on one Channel does not close signals belonging to another Channel
  still using the previous Policy Revision.
- `ChannelConfigRevision` pins `unit_registry_version`.
- Display conversion of a value that is not a multiple of the unit factor shows
  the fractional result rather than rounding it.

---

## Appendix A: Formula Shape Inventory

The translator allowlist is backed by the cell-level inventory under
`docs/architecture/formula_inventory/`. The source snapshot is `Price
List.xlsx` with SHA-256
`a529c3306d6db3923eb55451562c5a1eb4886861c45b390cddfdfc6f70db6a45`.
It contains 5,997 formula cells across 20 formula-bearing worksheets (22 total),
53 normalized R1C1 formulas, and the 13 verified syntax/semantic shapes below.

Each supported shape still requires a fixture with input values, the workbook's
stored output, and the expected FlowHub output. `Supported` here means the
workbook semantics fit the declared model; it does not waive the fixture gate.

| # | Cells | Workbook shape | Model / disposition |
| --- | ---: | --- | --- |
| A1 | 2,291 | `IF(D="","x",IFERROR(FLOOR((D*(1+rate/100)+IF(ISNUMBER(addend),addend,0))*1000000,50000),"x"))` | `percent_bp`, optional fixed addend, `floor`, step 50,000, scale 1,000,000. |
| A2 | 1,840 | `IFERROR(MIN(FILTER(vendors,vendors<>0)),"❌")` | Layer 3 `min` basis selection with zero exclusion. |
| A3 | 663 | `IFERROR(FLOOR(D*(1+rate/100)*1000,100000),"❌")` | Percentage rule, `floor`, step 100,000, scale 1,000. |
| A4 | 90 | `IFERROR(FLOOR(...,100000)+500000,"❌")` | `surcharge_minor = 500000`, `round_then_surcharge`. |
| A5 | 7 | `IFERROR(ROUNDUP(D*(1+rate/100),-2),"❌")` | `round_mode = ceil`; step derived from `-2`. |
| A6 | 327 | `IF(D="","x",IFERROR(FLOOR($G$2*E,50000)/10,"x"))` | **Quarantined.** Arithmetic proven; `G2` meaning and post-round `/10` semantics unproven. |
| A7 | 319 | `IFERROR(F/E,"x")` | Derived display ratio, **not** a price target. |
| A8 | 25 | `=M2` / `=N2` variants | Manual metadata copy; retained for provenance, not modeled as pricing. |
| A9 | 254 | A1 with broken rate/addend references | **Broken.** Missing Channel pricing parameters; never translated. |
| A10 | 94 | `IFERROR(FLOOR((D*(1+rate/100)*1000),100000),"❌")` | Parenthesized syntax variant of A3 with the same model. |
| A11 | 85 | `IFERROR(FLOOR((D*(1+rate/100)*1000)+500000,100000),"❌")` | Fixed amount before rounding: `surcharge_then_round`. |
| A12 | 1 | `IFNA(MIN(FILTER(E3:I3,E3:I3<>0)),"❌")` at `Surface Acc!I12` | **Broken/anomalous.** Cross-row formula in Link column, cached `#VALUE!`; meaning not inferred. |
| A13 | 1 | A10 with a broken basis reference at `Beats!C34` | **Broken.** Missing price basis; never translated. |

### Note on A6

The `/10` occurs **after** the rounding, so it cannot be a Source input scale —
an input scale applies before any computation. In the audited UGREEN worksheet,
`E` is labelled purchase, `C` is labelled website, and the manually stored
`G2 = 1.28` has no label. The workbook proves the arithmetic and cached result;
it does not prove whether `G2` is markup, an external market value, or another
business input, and it does not prove the business meaning of `/10`.

Until versioned input provenance and an owner-approved fixture establish those
meanings, **A6 is quarantined and not translated**. Products depending on it
produce `legacy_formula_unmigrated`.

An earlier revision mapped the `/10` onto the Source unit. That was inference,
not evidence, and inference in a migration table becomes a silent factor-of-ten
error across a vendor's entire catalogue.

The inventory reconciles all documented totals: 5,997 formula cells, 13 shapes,
and 255 formula cells containing `#REF!` (A9 plus A13). It also discovered the
separate A12 `#VALUE!` anomaly, so the complete broken-formula total is 256.
Any future shape absent from this appendix is quarantined rather than guessed.

`IFERROR(..., "x")` and `IFERROR(..., "❌")` do not map to a single outcome. The
migration report must classify each occurrence against the precedence table
above, because the workbook uses one marker for several distinct causes.

## Open Questions

1. Suggested `max_quote_age_days` at Policy creation. The field is mandatory,
   but the UI needs a sensible starting proposal.
2. Whether `min_markup_worst_case_bp` ships in v1 or after the first production
   cycle.
3. Whether `max_basis_spread_bp` defaults on, given the wide vendor disagreement
   visible in the audited file.
4. Which Channels warrant an immediate alert versus a daily digest.
5. Whether `surcharge_minor` should be constrained non-negative in v1. It is
   currently unconstrained, which permits a flat discount.
6. Whether the owner resolves existing Source and Channel units in one guided
   pass at upgrade, or lazily as each Source is next opened.
7. Whether the Unit Resolution Preview should offer a one-click "this one is
   correct" action, or require the owner to set the unit in Source settings.
8. Whether an operator may opt a Workspace into all-or-nothing Apply, given that
   per-Channel Apply is the default.

Resolved:

- FX applies at Workspace creation, before basis selection, as an exact rational.
- RIAL↔TOMAN is a unit conversion with an exact factor, not an exchange rate.
  `RIAL` is canonical; the Unit Registry is versioned and system-owned.
- Source, Channel, and display units are declared separately; FlowHub converts.
  Display unit is presentation only.
- Policy binds only to Channels sharing `computation_currency`. Differing units
  are permitted because `round_step_minor` must be a multiple of the Channel
  unit factor, making outbound conversion exact.
- A Workspace binds one Policy Revision per Channel, with the Channel config
  revision pinned and re-verified at Dry Run and Apply.
- Rule Entries cannot override basis policy in v1.
- Rounding semantics are fixed: floor toward −∞, ceil toward +∞, nearest half
  away from zero, all by quotient and remainder.
- Outbound integrality requires both `round_step_minor` and, under
  `round_then_surcharge`, `surcharge_minor` to be multiples of the Channel unit
  factor, checked per rule entry.
- Vendors inherit the Source unit; no override in v1.
- Activation is a per-Channel record carrying the acknowledgement and the pinned
  Channel config and registry versions.
- Existing IRR records migrate to `unresolved` and block Apply until the owner
  chooses; the unit is never inferred.
- The Rial/Toman choice appears only for IRR.
- An unresolved unit blocks all pricing operations; only raw and two-sided
  disambiguation views remain. `unit_unresolved` is a distinct reason code.
- Activation is append-only, one effective per Channel, pinned by the Workspace.
- Global reporting is IRR-only in v1; `display_currency` is deferred and must use
  the decision's own rate snapshot when it arrives.
- A6 is quarantined pending a fixture; its `/10` is not assumed to be a Source
  unit.
- Non-IRR currencies normalize to their ISO minor unit; the factor is a registry
  fact, not a constant and not user input.
- Activation immutability is preserved by backward links plus a compare-and-swap
  head pointer.
- `unit_unresolved` and `policy_not_activated` are preconditions, not per-cell
  outcomes. Source-unit faults block all fed Channels; Channel-scoped faults block
  only that Channel.
- Apply is per Channel; partial application is explicit and recorded.
- Activation insert and head swap commit in one transaction, guarded by
  `head_version` alone so the first activation is not blocked by a null
  predecessor.
- Activation and deactivation share one append-only lifecycle log, so the chain
  survives reactivation; the head carries `effective_activation_id`.
- `partially_applied` is a projection over the apply plan, precondition evidence,
  write job state, and `ProviderWriteAttempt` results through the existing
  `WritePipelineService`. Channel and Workspace use two explicit folds, and
  indeterminate items yield `reconciliation_required`.
- Policy Revision creation is inert; activation and deactivation are the events
  that outdate decisions.
- Pricing never writes stock.
- One immutable `PricingPolicyRevision` owns the matrix; entries carry
  `rule_entry_id`.
- Six-level scope chain; group overlap rejected at save time.
- Exact rational arithmetic with a single rounding; guards compare by
  cross-multiplication.
- Zero basis rejects rather than dividing.
- Markup reference is the selected basis. No independent cost entity.
- `round_order` is a closed two-member Policy field.
- Product Groups ship in v1 and do not independently outdate decisions.
- Staleness uses a frozen timestamp and explicit timezone; undated and
  future-dated quotes are excluded; activation is gated on acknowledgement.
- Quote-level exclusion is separate from target-level outcome, with a
  deterministic precedence table.
- v1 basis strategy is `min` only.
- The formula prohibition covers the runtime path; the translator is an
  allowlisted offline tool.
