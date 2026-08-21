# Workspace Phase B Change Badges Plan

Status: Owner review draft; planning only

Reviewed branch: `feat/workspace-live-dry-run`

Reviewed commit: `8a7f1f5bee9ec4504b6ba7d7ad649137b36c8b1c`

PR context: PR #16, **feat(workspace): add live-verified Dry Run pricing boundary**

PR #16 merge on `origin/main`: `89a64ed9d4925848ecbf15f533d2e036620eb305`

Classification contract proposed here: `workspace-change-badges-v1`

This document specifies business behavior and an implementation plan. It does not authorize application, test, migration, deployment, or production changes.

## 1. Purpose

Phase B already establishes the safe execution sequence from canonical Source observation through Review, live Channel verification, Reviewed Scope, Verified Write Set, Apply Manifest, and Apply. This plan defines the business-change classification that must explain that sequence to the Owner.

The design has five separate results for each Listing or variation:

1. a Price classification;
2. a Stock Quantity classification;
3. a Stock Status classification;
4. zero or more independent Warnings; and
5. a separate `ELIGIBLE` or `BLOCKED` safety result.

The first four results explain the business state. They never authorize a write. Only selected, live-verified operations in the immutable Apply Manifest are execution authority.

The implementation should extend the existing Source Workspace, Unified Workspace, Review, Dry Run, and Manifest contracts. It must not introduce a generic rules engine, policy DSL, workflow engine, or new provider abstraction.

## 2. Approved Owner rules

The following are approved business decisions and are not implementation choices:

- A Source row matches a Channel Listing only through that Channel's configured Product Identifier.
- A participating Source row still requires the accepted, nonblank, unique Source Product Key for Source identity and canonical binding. That key is not Channel match authority.
- Product names and other display metadata are never match authority, fallback identity, eligibility input, warning input, or Apply input.
- `product_name_mismatch` must be removed from the Pricing Workspace business-validation model.
- Price, Stock Quantity, Stock Status, and Warning are independent badge dimensions. A row may show several simultaneously.
- Eligibility is separate from badges. A warning does not automatically block a row.
- After currency/unit-aware Source normalization, numerically equivalent prices compare equal. Float comparison is prohibited.
- A valid positive value in the mapped Channel Price column produces a valid Price instruction and an `IN_STOCK` availability signal.
- A mapped Channel Price cell that has no usable Price—including blank, canonical zero, `x`, malformed/non-price text such as `hello` or `10O000`, arbitrary text, negative/non-finite input, or disallowed fractional precision—produces no price write and an `OUT_OF_STOCK` availability signal. Price unusability alone is not a blocker.
- RIAL and TOMAN business Price targets are integers. The Owner setting `Fix zero-decimal prices` defaults ON for RIAL/TOMAN: an exact all-zero fraction such as `.00` or `.000` is removed, while a real fraction such as `.50` is never rounded or fixed.
- With `Fix zero-decimal prices` OFF, a positive RIAL/TOMAN Source Price lexeme containing a decimal separator is unusable even when its fractional digits are all zero; it therefore follows the mapped unusable-Price OOS rule. Canonical numeric zero is still the recognized zero/OOS command regardless of this toggle.
- Other currencies permit decimal Price according to their declared currency/unit precision contract. The RIAL/TOMAN fix is not applied to them.
- Every Owner-facing financial value uses thousands separators. Formatting is presentation-only and never changes exact authoritative values.
- Source Stock Status `0` means `OUT_OF_STOCK`; `1` and blank mean `IN_STOCK`.
- Source Quantity `0` implies `OUT_OF_STOCK`.
- Source Quantity blank means no quantity instruction. It must not become zero or create a quantity write. When the quantity field is mapped, its availability signal is `IN_STOCK`.
- A positive integer Source Quantity participates in quantity comparison and write planning.
- Any valid out-of-stock signal wins over any valid in-stock signal.
- A variation is evaluated independently. Badges are not copied to siblings.
- Auto-selection requires at least one actionable business change, an eligible row, and no blocker.
- Warning-only, unchanged, and blocked rows are not auto-selected.
- Owner manual deselection remains authoritative for the life of that Preview.
- Only changed, governed, selected, and live-verified fields enter the Apply Manifest.

### Approved scope boundary

This plan defines Preview/Review classification and its relationship to Phase B safety artifacts. It does not define Phase C parent-dependent operations, new Channel features, sale-price writes, or publication-state workflows.

Owner approval of this plan intentionally supersedes narrower supporting-design clauses: Product Name becomes optional display evidence rather than a participation requirement; every unusable value in the directly mapped Channel Price cell becomes a no-price/OOS business instruction; and a valid positive mapped Price becomes an IN signal. The accepted Source Product Key and Identity Authority ADR remains in force.

This supersession is deliberately narrow. It applies to the Owner-controlled mapped Channel Price cell, whose usability is itself an availability instruction. A Pricing Matrix valuation/rule/guard/calculation failure remains a Price-field-only blocker and contributes no availability signal; independently valid Stock operations may continue. Missing/untrustworthy direct-cell evidence or unresolved direct mapped currency/unit configuration blocks availability classification because the mapped Price signal cannot be known. None of these technical failures may delist a product. Implementation must version and align the affected Source Workspace contract while preserving that Pricing Matrix invariant.

## 3. Product identity rule

### Canonical decision statement

> A Source row matches a Channel Listing only by an exact value from the Source column configured as that Channel's Product Identifier, resolved in the context of that Channel. No other Source or Channel attribute may be used as implicit identity.

This Channel match rule is independent from Source participation. A participating row first requires a nonblank Source Product Key that is unique among participating rows in its Source identity namespace under the pinned normalization version. A blank or duplicate Source Product Key blocks identity validation and canonical binding. It must not be replaced with Product Name, Channel Product Identifier, row number, or another fallback. After Source participation is valid, each Channel Listing is resolved only through that Channel's mapped Product Identifier.

Participation itself is name-independent. Within the configured worksheet/data range, a row participates when at least one raw observed non-display cell is present in any saved identity or pricing role for the scoped Workspace: Source Product Key, a scoped Channel Product Identifier, mapped Price, mapped cost, mapped Quantity, mapped Stock Status, or another explicitly configured non-display Pricing Matrix input. Presence is an explicit null/trimmed-blank check, never truthiness, so numeric `0`, `x`, and `-` are present data. A completely blank row or a row containing only Product Name or other display metadata is ignored as decorative and creates no blocker; category/brand remain display-only unless a versioned pricing contract explicitly consumes them. A row with any participating business/identifier data but a blank Source Product Key is materialized as a blocked Data Quality row. A Source Product Key by itself participates; each scoped Channel then follows its configured missing-identifier/mapping result rather than borrowing the name.

Examples include:

- Source WooCommerce Identifier → WooCommerce Product or Variation ID;
- Source SnappShop Identifier → SnappShop code;
- Source TapsiShop Identifier → TapsiShop code;
- Source Technolife Identifier → Technolife identifier;
- Source Shopify Identifier → Shopify product or variant identifier; and
- Source Magento Identifier → Magento product or child-product identifier.

Different Channels may use different Source columns. A column called SKU may be authoritative only when it is explicitly configured in the Channel Product Identifier role. Its label does not grant authority.

Exact comparison uses only connector-declared canonicalization required by the provider contract, such as parsing a WooCommerce numeric ID into its canonical integer representation. FlowHub must not add generic trimming, case folding, fuzzy matching, leading-zero removal, transliteration, or numeric coercion unless the saved mapping and connector contract explicitly require it.

Price/QTY/Status sentinel rules never apply to an identity-bearing Source Product Key or Channel Product Identifier. Channel identifier values such as literal `x`, `-`, or numeric/string `0` remain present exact identifiers and are passed to connector-owned identifier validation/canonicalization; they are accepted or rejected only by that Channel's identifier contract. FlowHub must not drop identity values through generic value-policy handling or truthiness. Only an actually blank mapped identifier is missing.

The Source Product Key groups Source rows, preserves Source identity across Observations, and participates in the durable canonical-product binding, but it cannot locate a Channel Listing. Product name, SKU label, title, Persian or English text, variation name, image, category, price, stock, status, or sibling identity cannot substitute for the mapped Channel Product Identifier.

Names remain useful display evidence. A missing name uses a neutral label such as `Product <identifier>` and does not block row recognition. A completely different name creates no warning and has no effect on matching, eligibility, auto-selection, Dry Run, Manifest generation, or Apply.

## 4. Four Change Badge dimensions

The backend should return one small, versioned classification object for every participating Source-row/Channel projection. A successfully resolved projection identifies one Listing or variation. A missing, ambiguous, not-found, or invalid projection must still be materialized as a blocked Data Quality row even when no Listing exists.

A blocked Data Quality projection retains Source observation/worksheet/row identity, Source Product Key when available, Channel, raw and normalized Channel Product Identifier, optional resolved Listing identity, all issue codes/evidence, `NOT_EVALUATED` dimensions where comparison is impossible, and `BLOCKED` eligibility. It creates no Draft change, Review operation, selection, Dry Run scope, or Manifest operation. This prevents invalid Source rows from disappearing merely because they cannot produce an executable candidate.

The names below describe the business contract; Terra Medium may choose idiomatic class names and serialization details.

| Dimension | Canonical state | Supporting facts | Owner-facing examples |
|---|---|---|---|
| Price | `UNCHANGED`, `INCREASE`, `DECREASE`, `NO_VALID_PRICE`, or technical `NOT_EVALUATED` | current, target or unusability reason, currency, unit, zero-decimal-fix evidence | `Price unchanged`, `Price ↑ 50,000 · 4.2%`, `Price ↓ 4.93%`, `No usable price` |
| Stock Quantity | `UNMANAGED`, `UNCHANGED`, `INCREASE`, `DECREASE`, or technical `NOT_EVALUATED` | current, desired integer, delta, instruction state, effect | `No quantity instruction`, `Has 8 quantity`, `QTY +3`, `QTY -7`, `QTY not applied while out of stock` |
| Stock Status | `UNCHANGED_IN_STOCK`, `UNCHANGED_OUT_OF_STOCK`, `BECOMES_IN_STOCK`, `BECOMES_OUT_OF_STOCK`, or technical `NOT_EVALUATED` | current, desired, contributing signals | `In stock`, `Out of stock`, `Out of stock → In stock`, `In stock → Out of stock` |
| Warning | zero or more stable warning codes | severity, message key, policy/evidence, suggested action | `Warning · Large price change`, `Warning · Conflicting availability instructions` |

These concepts must also remain distinct:

| Axis | Values | Meaning |
|---|---|---|
| Capability | `SUPPORTED`, `NOT_SUPPORTED` | Whether the Channel contract can read, compare, and/or write the governed field as required. Read and write support should remain independently visible. |
| Mapping | `MAPPED`, `NOT_MAPPED` | Whether the Owner configured a Source column for the Channel field. A configured column that disappeared is schema drift, not `NOT_MAPPED`. |
| Instruction | `SET`, `NO_INSTRUCTION`, `UNAVAILABLE`, `UNUSABLE`, `INVALID` | The normalized meaning of the Source cell. For a direct mapped Price, `UNAVAILABLE` is blank/zero/x and `UNUSABLE` is a present value that cannot be a business Price; both signal OOS. `INVALID` covers blocking schema/configuration/evidence/Matrix failures and invalid Quantity/Status. |
| Verification | `VERIFIED`, `UNVERIFIABLE`, `DRIFTED`, `NOT_REQUIRED` | Whether live evidence can support the proposed operation. |
| Eligibility | `ELIGIBLE`, `BLOCKED` | Whether the row is safe enough to proceed. |
| Actionability | Boolean | Whether at least one supported governed field would produce a Manifest operation if selected and verified. |

`NOT_SUPPORTED`, `NOT_MAPPED`, `NO_INSTRUCTION`, and `UNVERIFIABLE` must never be collapsed into one null value or one generic message.

Neutral presentation composes the independent dimensions rather than inventing another synthetic state. For example:

- `Price unchanged` · `No quantity instruction` · `In stock` · `Eligible`
- `Price unchanged` · `Has 8 quantity` · `In stock` · `Eligible`

### Persistence versus derivation

Persist the raw Source lexeme, normalized Source instruction, exact current and target values, currency/unit, `monetary_precision_contract_version`, zero-decimal applicability/effective `fix_zero_decimal_prices` setting, whether the fix was applied and its reason, Price origin (`DIRECT_MAPPED_PRICE_CELL` or `PRICING_MATRIX`), capability/mapping state, stable warning/blocker codes, classification version, and the evidence references already required by Phase B. Derive these presentation values:

- signed absolute price delta;
- percentage price delta;
- signed quantity delta;
- arrows and localized text;
- grouping and badge order; and
- neutral no-change summaries.

Persisting separately rounded deltas would create redundant state that can disagree with the exact Review/Manifest values. Therefore absolute and percentage price deltas must be derived, not persisted in new columns.

### Global financial display formatting

Every Owner-facing financial value uses digit grouping with thousands separators, including Source/current/target Price, absolute deltas, warning thresholds and reference values, inline editors after commit, badge details, Reviewed Scope, Dry Run evidence, Verified Write Set, Manifest/Apply confirmation, Activity/audit presentation, and any no-change summary. This is one shared presentation contract, not per-screen business logic.

- RIAL/TOMAN integer example: exact `15758858` displays as `15,758,858`.
- With the fix ON, an accepted RIAL/TOMAN Source value `15758858.00` normalizes to exact integer `15758858` and displays as `15,758,858`.
- A currency permitting decimals displays exact `15758858.25` as `15,758,858.25`.
- Redundant trailing fractional zeros are omitted only for display after currency/unit validation; significant allowed fractional digits remain visible.
- Raw or unusable Source evidence is different from normalized financial presentation: preserve its exact lexical meaning, including `.00` when the fix is OFF. It may be grouped as `15,758,858.00` in evidence, but must not be relabeled as normalized `15,758,858`.
- English uses `,`; Persian may use the locale-equivalent grouping glyph/digits, but grouping is mandatory and the numeric run remains directionally isolated/LTR inside RTL layout.

Formatting never participates in parsing, equality, delta calculation, warning thresholds, selection, verification, Manifest hashing, provider serialization, or Apply. Exact Decimal/integer values and explicit currency/unit remain authoritative.

### Presentation scope and lifecycle

Attach the badge group and Eligibility to every `GroupedListing` Channel row, not only to the shared Product cell that appears on the first Channel row. The same immutable classification must be available in the full Reviewed Scope/Review dialog, independent of the currently paginated grid:

- Reviewed Scope shows the business badges, Eligibility, all warnings/blockers, exact identity/evidence, and Owner selection.
- Dry Run shows each selected field's live `write`, `no_op`, or `blocked` outcome and verification evidence; it does not replace the Preview badges.
- Apply confirmation shows the Verified Write Set and operations sourced only from the immutable Review/Dry Run context, never reconstructed from grid cells.

The Review read model must therefore carry enough display data for the complete unpaginated scope: display name fallback, Channel Product Identifier, optional Listing identity, parent identifier/name, variation attributes/label, classification, evidence, and selection references. It must not join Review items only against the currently loaded grid page.

Server classification is authoritative only for its immutable Preview/Review revision. When the Owner makes an unsaved local edit, the UI must clear or visibly mark the old badges as stale until the edited Draft is saved and reclassified; stale server badges must not appear to describe new local values.

## 5. Price rules

### 5.1 Canonical normalization

Price parsing uses canonical finite `Decimal` semantics and explicit currency/unit. A third-party spreadsheet library may expose a native numeric scalar only inside the acquisition adapter. That adapter must emit lossless canonical decimal text, preferably from the original cell lexeme. No binary float may cross into Source normalization, business classification, DTO/Review/Manifest evidence, warning calculation, comparison, or governed write intent.

The mapped Channel Price cell has an availability-bearing contract:

- valid positive direct mapped Price under the declared currency/unit rule → `SET` Price plus `IN_STOCK` signal;
- blank → `UNAVAILABLE / PRICE_UNAVAILABLE_BLANK`, no Price target, `OUT_OF_STOCK` signal;
- canonical numeric zero → `UNAVAILABLE / PRICE_UNAVAILABLE_ZERO`, no Price target, `OUT_OF_STOCK` signal;
- exact token `x`, after surrounding-whitespace removal and case normalization → `UNAVAILABLE / PRICE_UNAVAILABLE_X`, no Price target, `OUT_OF_STOCK` signal;
- any observed but unusable value—including `hello`, `10O000`, arbitrary text, malformed grouping, unsupported notation, negative, NaN/infinity, or disallowed fractional precision → `UNUSABLE` with a typed reason, no Price target, and `OUT_OF_STOCK` signal.

Blank/zero/x are recognized unavailable commands and need no warning. A present unusable value emits the non-blocking, actionable warning `UNUSABLE_MAPPED_PRICE` with bounded raw evidence and the precise reason, such as `malformed`, `negative`, `non_finite`, `fraction_not_allowed`, or `precision_not_allowed`. It is not a blocker merely because the Price cannot be used. Eligibility then depends on whether the resulting OOS outcome is already authoritatively satisfied or can be safely enforced and verified.

#### Versioned numeric lexical grammar

Price and Quantity share a pinned lexical normalization stage before their different business rules:

1. A truly blank cell remains the dimension-specific blank instruction. Reject Boolean values as numeric values.
2. For native spreadsheet numeric cells, the acquisition adapter must retain both the exact numeric value and authoritative raw/formatted cell evidence sufficient to determine whether the observed Price used a decimal separator and fractional scale. A rounded/guessed float or a canonicalized string that erases `.00` is not acceptable lexical evidence. When the RIAL/TOMAN fix is OFF and the adapter cannot prove whether a positive value was integer-form or decimal-form, use `SOURCE_PRICE_LEXEME_UNVERIFIABLE`: block with no availability signal rather than guessing.
3. For text cells, trim surrounding Unicode whitespace and translate Persian digits `۰–۹` and Arabic-Indic digits `٠–٩` to ASCII.
4. Accept `,` or Arabic thousands separator `٬` only as a consistently used grouping separator in groups of exactly three digits after the first one-to-three digits. Remove it after validation.
5. Accept `.` or Arabic decimal separator `٫` as the one decimal separator, but never both. Normalize it to `.`.
6. A numeric candidate must match `[0-9]+(?:\.[0-9]+)?`. A sign, exponent, internal whitespace, underscore, currency symbol, unit label, mixed separator, or any other character is not silently repaired.
7. Parse numeric candidates as finite `Decimal`. Quantity then applies its whole-number rule. Price applies the currency/unit rule below.

For a mapped Price cell, failure at steps 3–7 is a known unusable cell value and therefore OOS, not a row blocker. For Quantity it remains invalid and blocking as specified in Section 6. A missing/corrupt Source Observation, missing mapped header, or adapter inability to produce trustworthy observed cell evidence is not a cell value; it remains blocking schema/acquisition evidence and contributes no availability signal.

#### RIAL/TOMAN integer Price and `Fix zero-decimal prices`

RIAL and TOMAN selling Prices are positive integers in the declared unit. The saved Channel Price mapping/monetary contract contains the Owner setting:

`fix_zero_decimal_prices: boolean`

- Default: `true` whenever the declared business unit is RIAL or TOMAN, including FlowHub's existing IRR/IRT monetary encodings.
- Scope: the directly mapped Source Price and Owner-edited Source target for that Channel; it is pinned in the immutable mapping/contract evidence. Store the explicit effective Boolean under that Channel Price mapping in existing `SourceMappingRevision.value_policy_json`, or the applicable `SourceWorksheetRule.value_policy_json` in per-worksheet mode, include it in the mapping checksum, and copy it to normalized Snapshot, Review, Dry Run, Manifest, and Activity evidence. Never read mutable configuration during Dry Run or Apply.
- When ON, an exact positive numeric value whose fractional digits are all zero is normalized to the same integer. `15758858.00` and `15758858.000` both become exact `15758858`.
- When ON, any nonzero fractional part remains unusable. `15758858.50` must not be rounded, truncated, or fixed; it produces no Price target and contributes OOS.
- After blank and `x`, parse canonical numeric zero before applying the toggle: `0`, `0.0`, and `0.00` all remain `PRICE_UNAVAILABLE_ZERO`, request OOS, and need no unusable-value warning whether the toggle is ON or OFF.
- When OFF, a positive mapped RIAL/TOMAN Source lexeme containing a decimal separator is unusable even when every fractional digit is zero. An integer lexeme such as `15758858` remains valid.
- The setting never changes unit, currency, magnitude, or a real fractional value. It is a zero-fraction lexical normalization, not the Pricing Matrix round step. It does not govern Matrix quotes, FX values, intermediate calculations, percentage deltas, display conversion, or provider readback.
- The setting governs Source/Owner-edit normalization, not a provider's wire-format grammar. The canonical business/Manifest target is integer `15758858`; a connector may serialize the mathematically identical provider-required lexeme `15758858.00`, using exact decimal/string logic rather than float, and must verify the same integral value on readback.
- Changing the setting creates a new pinned mapping/monetary-contract revision and requires a new Preview. It never mutates a historical Snapshot.
- New RIAL/TOMAN mapping revisions materialize explicit `true` unless the Owner turns it OFF. A sealed legacy mapping with no field is never mutated: its deterministic effective default is derived as `true` and pinned into each new Snapshot/Preview; the next Owner-saved Mapping revision materializes it explicitly. Other currencies expose `NOT_APPLICABLE`, not `false`.

Authoritative Channel current/readback values may contain provider formatting such as `.00`. The connector canonicalizes a mathematically integral RIAL/TOMAN provider value to the exact integer before comparison; the Owner setting does not reinterpret provider evidence. A real fractional RIAL/TOMAN current/readback such as `100.50` is `UNVERIFIABLE`: it is never truncated, fixed, or reinterpreted as a Source OOS instruction.

#### Other currencies

For currencies/units other than RIAL/TOMAN, a finite positive Decimal is valid when it is exactly representable under FlowHub's versioned currency/unit monetary precision contract. If the allowed scale is `s`, accept exactly when `value × 10^s` is integral; insignificant trailing lexical zeros do not change representability. For a two-decimal contract, `100.50` and `100.500` are valid while `100.505` is unusable. For a zero-decimal contract, `100.00` is representable while `100.50` is unusable. No value is rounded into compliance. Missing or conflicting currency/unit precision metadata is a configuration blocker with no availability signal.

Provider precision/capability is a later, separate axis. A provider limitation may block or mark unsupported a Price operation, but it must never narrow Source usability, reinterpret a valid Source Price as OOS, or silently round it.

For example, a currency with two fractional digits accepts `15758858.25`. The RIAL/TOMAN zero-decimal fix is hidden/not applicable and must not remove meaningful fractional precision. A value exceeding the allowed precision produces no Price target and contributes OOS only when it is the observed direct mapped Price cell.

#### Blocking boundary

An intentionally unmapped Price field supplies no instruction or availability signal. A mapped header missing from the observed Source schema, unresolved/mismatched currency or unit, untrustworthy observation/current-state evidence, or a Pricing Matrix valuation/rule/guard/calculation failure is a blocker and contributes no availability signal.

This is the architecture boundary: an unusable observed value in the Owner-mapped Channel Price cell is now an availability instruction; a failure to compute or trust a price outside that cell is still a pricing failure and must never change stock. Every normalized Price candidate therefore carries an immutable origin: `DIRECT_MAPPED_PRICE_CELL` or `PRICING_MATRIX`. Direct mapped usable/unusable values contribute the availability signals defined here. A Pricing Matrix target, successful or failed, is availability-neutral; a Matrix valuation/rule/guard/round/calculation failure blocks its Price target without changing stock.

### 5.2 Price comparison

Every comparison is bound to the exact governed Channel field that the operation would write. In the current Pricing Workspace this is normally the regular/base price. Current, target, expected-before, live readback, and Manifest field must all refer to that same regular/base field. An active sale/special/effective price is separate evidence: it may emit `SALE_PRICE_INTERACTION`, but it is never substituted as the comparison baseline and is not written by this plan.

For a valid positive Price target and authoritative Channel current governed price in the same currency and unit, the Price-change comparison is:

- `target == current` → `UNCHANGED`;
- `target > current` → `INCREASE`;
- `target < current` → `DECREASE`.

When the target origin is `DIRECT_MAPPED_PRICE_CELL`, that valid positive target also contributes `IN_STOCK`. A successful `PRICING_MATRIX` target can still classify and write a Price change, but remains availability-neutral under the Pricing Matrix ADR.

Decimal scale is not business meaning after the applicable Source normalization contract accepts the value. Thus provider/current values `100`, `100.0`, and `100.00` compare equal; a RIAL/TOMAN Source `.00` form reaches that comparison only when `Fix zero-decimal prices` is ON, while other currencies follow their allowed precision.

Let `delta = target - current` and `absolute_delta = abs(delta)`. When current price is positive:

`percentage_delta = (delta / current) × 100`

The comparison and policy evaluation use unrounded Decimal values. Presentation rounds the absolute percentage magnitude to two decimal places with Decimal `ROUND_HALF_UP`, trims trailing zeros, and retains the unrounded value in accessible detail. A nonzero change whose displayed magnitude would round to zero is shown as `<0.01%`, never `0%`. Every displayed financial amount uses thousands separators under the global formatting contract; exact current/target/delta remain authoritative. A verified current price of zero can classify a positive target as `INCREASE`, but its percentage is undefined and must display `from 0`, never infinity. A missing, non-finite, negative, differently denominated, or otherwise unauthoritative current value is `UNVERIFIABLE` and blocks the price operation.

No absolute number is suspicious merely because it is large. Price warnings require compatible currency/unit and an explicit policy.

### 5.3 Price badge order and content

For a changed price, the compact label should show direction and preferably both deltas when space permits:

- `Price ↑ 50,000 · 4.2%`
- `Price ↓ 50,000 · 4.93%`
- `Price ↑ 15,758,858` when that is the exact formatted absolute delta

If space is constrained, the badge may show the percentage while its details expose exact current, target, absolute delta, currency, and unit. The absolute amount and percentage describe the same Price dimension; they are not separate changes.

Blank/zero/x shows `No usable price` with its recognized unavailable reason. Malformed/non-price/negative/non-finite/disallowed-fraction input also shows `No usable price`, adds `Warning · Unusable mapped price`, and contributes OOS. It shows `Blocked` only when the OOS result cannot be authoritatively satisfied/enforced or a separate schema/configuration/evidence blocker exists—not merely because the Price value is unusable.

## 6. Stock Quantity rules

Quantity is a non-negative whole-number business value. Decimal formatting such as `5`, `5.0`, and `5.00` is equivalent only when the normalized Decimal is mathematically integral. The stored and compared business target is the canonical integer.

| Source Quantity | Normalized instruction | Desired quantity | Availability signal | Quantity write eligibility |
|---|---|---:|---|---|
| Intentionally not mapped | `NO_INSTRUCTION` | none | none | No write; does not block siblings. |
| Mapped header missing | `INVALID` | none | none | Row blocked for Source schema drift. |
| Blank | `NO_INSTRUCTION` | none | `IN_STOCK` default | Never write quantity and never convert to zero. |
| Canonical zero | `SET` | `0` | `OUT_OF_STOCK` | Compare/write when quantity is supported and managed. |
| Positive integer | `SET` | that integer | `IN_STOCK` | Compare/write when quantity is supported and managed. |
| Negative | `INVALID` | none | none | Row blocked. |
| Non-integer Decimal | `INVALID` | none | none | Row blocked. |
| Malformed, Boolean, NaN, infinite, or unsupported notation | `INVALID` | none | none | Row blocked. |

Blank Quantity means exactly “no quantity instruction.” Its `IN_STOCK` availability signal must not manufacture a quantity target or quantity operation.

If the Listing is not quantity-managed, quantity state is `UNMANAGED`. A supplied positive quantity is suppressed with `CHANNEL_CAPABILITY_LIMITATION`; it creates no quantity operation, while an independent safe Price change may remain eligible. FlowHub must not auto-enable quantity management in this scope. Enabling management would require a separately declared, verified connector capability and a future approved contract.

If the supplied quantity is zero and the Channel cannot enforce the required unavailable outcome through either its verified quantity semantics or Stock Status capability, the row is blocked as `UNAVAILABLE_OUTCOME_NOT_ENFORCEABLE`. Safety-critical unavailability cannot be silently omitted.

### Quantity comparison

For a `SET` Source quantity and authoritative, managed Channel current quantity:

- desired equals current → `UNCHANGED`, label `Has X quantity`;
- desired greater than current → `INCREASE`, label `QTY +X`;
- desired less than current → `DECREASE`, label `QTY -X`.

For Source blank, state is `UNMANAGED` with instruction `NO_INSTRUCTION`, label `No quantity instruction`, even if the Channel happens to expose a current quantity. For a Source `SET` instruction on a Channel Listing whose management is disabled, state is `UNMANAGED` with instruction `SET`, label `Quantity unmanaged by Channel`, and a capability warning. These combinations are distinct; no delta is computed for either.

### Quantity relevance when final status is out of stock

- Source Quantity `0` remains relevant. It caused the unavailable outcome and may create a quantity operation when supported.
- Source positive quantity is suppressed when a price or explicit Stock Status signal makes the final status `OUT_OF_STOCK`. It must not show a directional quantity-change badge or enter the Manifest. Show `QTY not applied while out of stock` in details and issue `SOURCE_AVAILABILITY_CONFLICT` because the explicit inputs disagree.
- Source Quantity blank always remains no instruction and creates no quantity write.
- If a provider requires an unchanged companion quantity in a complete-state payload, that retained value is transport evidence, not a quantity operation or change badge.

### Quantity-derived out-of-stock enforcement

A connector may declare an authoritative invariant that managed Quantity `0` means `OUT_OF_STOCK`, provided both the quantity write and exact quantity readback are supported. Under that declared invariant, an explicit Source QTY `0` can establish and verify the canonical final OOS outcome with a `stock` operation alone. This one-way invariant does not prove that a positive current Quantity means `IN_STOCK`: show `BECOMES_OUT_OF_STOCK` only when current `IN_STOCK` is independently authoritative (or a separately approved stronger invariant proves it). Otherwise Stock Status is `NOT_EVALUATED` with detail `Final out-of-stock outcome via QTY 0`, not a transition claim.

If the connector does not declare that invariant, QTY `0` remains a `stock` candidate when supported and creates an operation only when authoritative current QTY differs. A separate verified `status` operation is required when current status must change to enforce OOS. When both mechanisms exist, use the minimum authoritative operation set: changed `stock=0` alone when the declared zero invariant fully establishes OOS; otherwise changed `stock` plus changed `status`, omitting either field when it is already an authoritative no-op.

`BECOMES_IN_STOCK` requires direct authoritative current status and direct verified status write in v1. Positive QTY alone cannot prove or enforce IN_STOCK unless a future separately approved connector invariant explicitly says so.

An unavailable or unusable direct mapped Price and Source Status `0` never synthesize a QTY `0`. They require a canonical `status` operation backed by direct or connector-declared provider availability read/write semantics, unless authoritative live evidence already proves the Listing is OOS and therefore no write is needed. If no such mechanism exists, use `UNAVAILABLE_OUTCOME_NOT_ENFORCEABLE` and block.

## 7. Stock Status rules

The business engine owns only these provider-neutral values:

- `IN_STOCK`
- `OUT_OF_STOCK`

Connectors translate them to provider values such as WooCommerce `instock` and `outofstock`. Provider publication or visibility states such as `publish`, `draft`, `active`, `inactive`, `hidden`, or `private` are not stock availability and must not enter the business classifier.

For a mapped Source Stock Status column:

- reject native/text Booleans before numeric handling;
- blank after trimming Unicode whitespace → `IN_STOCK`;
- otherwise translate Persian/Arabic-Indic digits and Arabic decimal separator exactly as the pinned numeric normalizer does, but reject all grouping separators, signs, exponent notation, internal whitespace, words, and provider literals;
- require normalized grammar `[0-9]+(?:\.[0-9]+)?` and a finite Decimal value mathematically equal to exactly `0` or `1`;
- numeric `0`, including `0.0`, `00`, `۰`, and exactly equivalent Decimal representations, → `OUT_OF_STOCK`;
- numeric `1`, including `1.00`, `01`, `۱`, and exactly equivalent Decimal representations, → `IN_STOCK`;
- any other number, Boolean, word, provider literal, or malformed value → blocked invalid status.

Status words are not guessed. A future Channel-specific mapping may explicitly transform a Source vocabulary, but its output must be one of the two canonical values before classification.

An intentionally unmapped Stock Status column supplies no instruction. A mapped header missing from the observed Source schema is blocking schema drift.

For an authoritative current status and a desired canonical status:

- `IN_STOCK → IN_STOCK` → `UNCHANGED_IN_STOCK`;
- `OUT_OF_STOCK → OUT_OF_STOCK` → `UNCHANGED_OUT_OF_STOCK`;
- `OUT_OF_STOCK → IN_STOCK` → `BECOMES_IN_STOCK`;
- `IN_STOCK → OUT_OF_STOCK` → `BECOMES_OUT_OF_STOCK`.

If the Channel cannot expose authoritative current Stock Status, FlowHub cannot claim a verified transition. The dimension is `NOT_EVALUATED` with `UNVERIFIABLE`; a requested status operation is blocked. Absence of status support does not block an unrelated price operation unless the requested business outcome depends on status or the Channel's complete-state contract requires it.

## 8. Stock Status precedence rules

### 8.1 Normalized signals

Each field contributes at most one result after normalization:

| Field | Out-of-stock signal | In-stock signal | Neutral/no signal | Blocking result |
|---|---|---|---|---|
| Direct mapped Price cell | blank, canonical zero, exact `x`, or any observed unusable value | valid positive Price accepted by the currency/unit contract | `NOT_MAPPED` | missing mapped header, unresolved/mismatched unit or currency, untrustworthy observation/current evidence |
| Pricing Matrix Price | none | none | every successful target | valuation/rule/guard/round/calculation failure or unusable result; blocks Price only and never changes availability |
| Quantity | canonical zero | blank or positive integer | `NOT_MAPPED` | negative, fractional, malformed, non-finite, missing mapped header |
| Stock Status | canonical zero | blank or canonical one | `NOT_MAPPED` | other value, malformed, missing mapped header |

### 8.2 Deterministic algorithm

For every combination of the three normalized inputs, apply this order:

1. **Availability/row blocker first.** If a blocking identity/shared-schema/direct-Price-configuration/evidence condition exists, Quantity/Status input is invalid, a hard policy applies, or a requested safety outcome cannot be enforced, set the row to `BLOCKED`. These failures contribute no availability signal. A known unusable value in the directly mapped Price cell is explicitly not in this blocker set; it contributes OOS. A Pricing Matrix failure is also excluded: it blocks only its Price field, supplies no availability signal, and leaves independently valid QTY/Status classification eligible.
2. **Out of stock wins.** If there is no blocker and one or more valid out-of-stock signals exist, desired status is `OUT_OF_STOCK`.
3. **Otherwise in stock.** If there is no blocker, no out-of-stock signal, and one or more mapped in-stock signals exist, desired status is `IN_STOCK`.
4. **Otherwise preserve.** If there is no blocker and no availability signal, desired status is `NO_INSTRUCTION`; retain current status and do not create a status operation.

This set-based rule exhaustively covers the Cartesian product: let `B` be availability/row-blocking results, `O` out-of-stock signals, and `I` in-stock signals. A field-scoped Pricing Matrix or provider-Price blocker is not in `B`. The result is `BLOCKED` when `B` is non-empty; otherwise `OUT_OF_STOCK` when `O` is non-empty; otherwise `IN_STOCK` when `I` is non-empty; otherwise `NO_INSTRUCTION`.

When the resulting desired availability differs from authoritative current availability, the Source-to-Draft builder must create one derived canonical `status` candidate with the contributing direct-Price/QTY/Status signal codes in evidence—even when the Source Stock Status column is intentionally unmapped. Today absent/sentinel targets collapse to null and no such candidate is produced; implementation must handle valid direct Price as IN and every unavailable/unusable direct Price as OOS, not stop at a badge. The derived candidate proceeds only when direct status capability can enforce it. The sole exception is explicit QTY `0` on a connector whose declared quantity-zero invariant enforces and verifies OOS; then the `stock` candidate carries the status outcome and no redundant `status` operation is created.

### 8.3 Conflict behavior

When an explicit in-stock signal conflicts with an out-of-stock signal, out of stock wins and the non-blocking warning `SOURCE_AVAILABILITY_CONFLICT` explains which Source fields disagreed. Explicit in-stock signals are valid positive direct mapped Price, positive Quantity, and Stock Status `1`. Blank Quantity and blank Stock Status are default availability signals and lose silently, avoiding noise for ordinary spreadsheets.

A valid positive direct mapped Price contributes `IN_STOCK`; an unavailable/unusable direct mapped Price instead contributes OOS. When QTY zero or Status zero conflicts with a valid Price, OOS still wins. The valid Price may still be written while the Listing becomes/remains OOS, and the explicit disagreement is visible through `SOURCE_AVAILABILITY_CONFLICT`.

### 8.4 Required combinations

In this table, Source Price means the trustworthy direct mapped Channel Price cell; Pricing Matrix targets do not participate in availability precedence.

| Source Price | Source QTY | Source Status | Desired Stock Status | Quantity instruction | Price instruction | Eligibility | Warning | Why |
|---|---|---|---|---|---|---|---|---|
| Valid positive | `5` | `0` | `OUT_OF_STOCK` | Positive QTY suppressed | Set/compare price | `ELIGIBLE` if status is enforceable | `SOURCE_AVAILABILITY_CONFLICT` | Explicit Status `0` wins over the valid Price and positive QTY IN signals. |
| Valid positive | `0` | `1` | `OUT_OF_STOCK` | Set/compare QTY `0` | Set/compare price | `ELIGIBLE` if unavailable outcome is enforceable | `SOURCE_AVAILABILITY_CONFLICT` | QTY zero wins over valid Price and explicit Status `1`. |
| Blank | `5` | `1` | `OUT_OF_STOCK` | Positive QTY suppressed | No price write; unavailable instruction | `ELIGIBLE` if unavailable outcome is enforceable | `SOURCE_AVAILABILITY_CONFLICT` | Deliberate blank price wins; explicit positive QTY/status disagree. |
| Valid positive | Blank | Blank | `IN_STOCK` | No quantity write | Set/compare price | `ELIGIBLE` if status evidence/capability is sufficient | None | Valid Price plus both mapped blank stock fields contribute IN. |
| Malformed text such as `hello` | `5` | `1` | `OUT_OF_STOCK` | Positive QTY suppressed | No Price write; unusable Price instruction | `ELIGIBLE` if OOS is enforceable or already satisfied | `UNUSABLE_MAPPED_PRICE`, `SOURCE_AVAILABILITY_CONFLICT` | Mapped unusable Price contributes OOS and wins over explicit QTY/Status IN signals. |

## 9. Warning and blocker model

### Warning

A warning identifies an actionable, non-fatal condition when FlowHub can still determine and verify the intended safe operations. It is independent from Price, Quantity, and Status badges. Warnings do not change eligibility unless a named Owner policy explicitly promotes that exact condition to a blocker.

Approved warning categories are:

| Code | Emit only when | Owner action |
|---|---|---|
| `LARGE_PRICE_CHANGE` | A configured policy threshold is exceeded using exact percentage basis points and compatible currency/unit. There is no invented default threshold. | Confirm the Source and intended price. |
| `PRICE_OUTSIDE_ADVISORY_BAND` | A configured advisory minimum/maximum exists for the same currency/unit and the target is outside it. | Confirm unit/currency or correct Source. |
| `SALE_PRICE_INTERACTION` | Authoritative Channel evidence shows an active sale/special price and the planned field is the regular/base price, so the effective selling price may differ. | Review the active sale before Apply. |
| `LARGE_QUANTITY_CHANGE` | A configured, unit-aware quantity policy threshold is exceeded. There is no invented default. | Confirm the replenishment/depletion. |
| `CHANNEL_CAPABILITY_LIMITATION` | One supplied field cannot be managed by the Channel but a safe independent sibling change may proceed. | Understand that the omitted field will not be written. |
| `SOURCE_AVAILABILITY_CONFLICT` | Valid explicit Source inputs disagree about availability. | Correct Source if out-of-stock-wins is not intended. |
| `UNUSABLE_MAPPED_PRICE` | A present mapped Price value is not a usable selling Price, so it produces no Price target and requests OOS. Blank/zero/x do not need this warning. | Correct the Source Price if OOS was not intended. |
| `channel_cache_not_fresh` | Existing pinned Channel cache evidence is stale but still within the explicitly allowed non-blocking policy; live verification remains mandatory before Manifest creation. | Review freshness and continue only if the later live check succeeds. |

Product-name differences must never emit a warning.

### Blocker

A blocker means identity, Source meaning, unit/currency, current evidence, requested safety outcome, or executable operation is unsafe or indeterminate. Representative stable codes are:

- `CHANNEL_PRODUCT_IDENTIFIER_MISSING`
- `CHANNEL_PRODUCT_IDENTIFIER_AMBIGUOUS`
- `CHANNEL_LISTING_NOT_FOUND`
- `MAPPED_SOURCE_COLUMN_MISSING`
- `SOURCE_PRICE_LEXEME_UNVERIFIABLE`
- `MONETARY_PRECISION_CONTRACT_MISSING`
- `PROVIDER_PRICE_PRECISION_UNSUPPORTED`
- `PRICING_CALCULATION_FAILED`
- `INVALID_QUANTITY`
- `INVALID_STOCK_STATUS`
- `CURRENCY_OR_UNIT_MISMATCH`
- `AUTHORITATIVE_CURRENT_STATE_UNAVAILABLE`
- `UNAVAILABLE_OUTCOME_NOT_ENFORCEABLE`
- `IN_STOCK_OUTCOME_NOT_ENFORCEABLE`
- `LIVE_STATE_UNVERIFIABLE`
- `LIVE_STATE_DRIFTED`
- an explicitly configured hard-policy blocker

Each blocker occurrence carries one explicit backend-owned scope, not a configurable rules framework: `ROW` for conditions that make the combined outcome unsafe, or `PRICE_FIELD` for a Matrix/provider/current-Price failure that architecture permits FlowHub to omit while independent Stock work continues. The UI never infers scope from message text.

A hard minimum/maximum may be a blocker only when the policy is explicit, currency/unit-aware, attached to the relevant Channel or mapping, and recorded in evidence. Legacy fixed absolute thresholds must not be carried forward as universal suspicious-price rules.

## 10. Eligibility

Eligibility is a row-level safety decision:

`ELIGIBLE` means exact identity is resolved, all row-wide blocking inputs/evidence are trustworthy, the intended outcome is internally deterministic, required capabilities/evidence exist for the independently safe candidate operations, and there is no hard policy or Phase B safety blocker. An unusable direct mapped Price can still be eligible because it deterministically requests OOS; unusability is not itself a blocker.

`BLOCKED` means at least one row-wide business or safety condition prevents a trustworthy outcome. A blocked row produces no Manifest operations, even if another field appears changed.

Pricing Matrix and provider Price-representability failures are field-scoped exceptions required by the existing architecture: they block/omit only the Price candidate. A Matrix failure never enters availability precedence. A valid direct Price retains its classified signal, but a Stock transition that depends solely on a Price operation that cannot be represented is not independent and must not proceed alone. If an independent QTY or Stock Status operation is safe and does not depend on the failed Price write, the row remains `ELIGIBLE` for that operation and the Price blocker stays visible. If no independently actionable safe operation exists, show the row as `BLOCKED`/not actionable so the failed Price cannot be selected. Phase B whole-scope atomicity still applies later to the operations actually selected for Dry Run.

Eligibility does not imply actionability:

- An unchanged row may be `ELIGIBLE` but has no actionable change.
- A warning-only row may be `ELIGIBLE` but has no actionable change.
- A row with an unsupported optional Quantity instruction may remain `ELIGIBLE` for an independent Price change when the omitted Quantity is not safety-critical.
- A requested unavailable outcome that cannot be enforced is `BLOCKED`.

The Owner-facing eligibility badge is always separate: `Eligible` or `Blocked`. Blocked details list stable codes and remediation.

## 11. Auto-selection

Define:

`has_actionable_business_change = at least one governed field is supported, normalized, different from authoritative current state, not suppressed, and capable of becoming a verified Manifest operation`

Initial auto-selection is exactly, at candidate-operation scope:

`row ELIGIBLE AND has_actionable_business_change AND no row-wide blocker AND candidate field has no blocker`

A field-scoped Matrix/provider Price blocker therefore excludes that Price candidate but does not violate the Owner's “no blocker” rule for an independent Stock candidate.

Therefore:

| Row result | Auto-select? |
|---|---:|
| Price changed only | Yes |
| Quantity changed only | Yes |
| Stock Status changed only | Yes |
| Price and Quantity changed | Yes |
| Any combination of actionable fields plus warning | Yes |
| Matrix/provider Price field blocked, but QTY or Status safely changed | Yes; safe Stock operation(s) only |
| Matrix/provider Price field blocked and no independent safe change | No; row presents `Blocked`/not actionable |
| Warning only, no business change | No |
| Zero-decimal lexical fix applied, exact Price unchanged, and availability/all other governed fields unchanged | No; the fix itself is not actionable |
| All governed fields unchanged | No |
| Only unsupported/not-mapped/no-instruction fields | No |
| Blocked | No |

Selection must remain operation/field-aware behind the existing row-level `Include in Save` / `Exclude from Save` control. That row-level control selects or deselects all eligible actionable operations for the row; this plan does not require a new checkbox.

Once the Owner manually deselects a row or operation, pagination, filtering, polling, refetch, warning refresh, or component remount must not silently reselect it for the same immutable Preview. A newly generated Preview may compute a new initial selection. Saving an intentionally empty selection should be allowed; Dry Run and Apply remain unavailable until at least one operation is selected. An all-unchanged Preview should show “No actionable changes” rather than failing while attempting to create an empty Review.

## 12. Dry Run relationship

Badges describe the immutable expected business comparison established by the Preview/Review. Dry Run does not use badge text or badge state as authority.

For each selected candidate operation, canonical Dry Run must:

1. resolve the exact Listing identity;
2. read the governed field from the live Channel using the connector's authoritative read contract;
3. compare live current state with the immutable expected-before value for that same field;
4. classify the field scope as `write`, `no_op`, or `blocked` with drift/unverifiable evidence; and
5. include only verified `write` scopes in the Verified Write Set.

Price, Quantity, and Stock Status require independent expected/live comparisons. Price verification uses the precision-contract version and effective `fix_zero_decimal_prices` value pinned in the immutable Preview; it never rereads a mutable setting. A zero-decimal lexical fix that leaves the exact Price unchanged is a live no-op, not an operation. A stock operation must not be marked unverifiable merely because price is absent, and price evidence cannot stand in for stock evidence.

If live state drifted or is unverifiable, the affected scope is recorded as blocked evidence. Phase B is whole-scope atomic: if any selected scope in the Reviewed Scope is blocked, the Dry Run result is blocked and **no Apply Manifest is created at all**. Verified sibling scopes remain durable explanatory evidence, but they are not executable and must not be packaged into a partial Manifest. FlowHub must not silently recompute Preview badges, replace expected-before values, drop blocked scopes, or regenerate intent from live data. The Owner must correct the Source/selection/capability issue or create a new Preview/Review and run Dry Run again.

No provider write occurs during mapping, Preview, Review, or Dry Run.

## 13. Manifest relationship

The Apply Manifest is the only execution authority. Badges are explanation/presentation. The invariant is:

`badge classification → candidate operation → Owner selection → live verification → Verified Write Set → immutable Manifest operation`

Only changed governed fields enter the Manifest:

- `Price ↓ 4.9%`, `QTY +3`, `In stock` may generate `price` and `stock` operations, but no `status` operation.
- `Price unchanged`, `QTY -7`, `In stock → Out of stock` may generate `stock` and `status` operations, but no `price` operation.
- A warning never creates an operation.
- Eligibility never creates an operation.
- A neutral no-change badge never creates an operation.
- The `Fix zero-decimal prices` setting or evidence that it removed an all-zero fraction never creates an operation by itself.
- Provider payload companions required for complete-state writes remain retained evidence, not additional business operations.

Manifest numeric values remain exact Decimal/canonical integer data through the write boundary. A changed RIAL/TOMAN Price normalized from an all-zero fractional Source lexeme is serialized as its canonical integer target; an allowed fractional target in another currency remains an exact Decimal. Provider serialization is a connector responsibility and must not change business comparison semantics.

## 14. Channel capability behavior

Capabilities must be field-specific and distinguish read support, write support, mapping, instruction, and verification.

| Situation | Classification and behavior |
|---|---|
| Price supported; Quantity not supported | Classify and allow an independent price operation. Show Quantity as `NOT_SUPPORTED`. Emit a capability warning only when Source actually supplied a Quantity instruction. Do not block price unless omitted Quantity is necessary for safety or complete-state correctness. |
| Quantity supported but intentionally not mapped | `NOT_MAPPED`; no instruction, warning, comparison, badge delta, or operation. |
| Quantity mapped but blank | `NO_INSTRUCTION`; no quantity operation. Availability may still contribute the approved default `IN_STOCK` signal. |
| Mapped Source column disappeared | Blocking Source schema drift. Do not relabel it `NOT_MAPPED`. |
| Currency/unit monetary precision contract is absent or contradictory | Blocking configuration evidence; do not guess precision, round a Source value, or derive an availability signal. |
| Source Price is valid under the monetary contract but provider precision cannot represent it exactly | Provider capability/configuration blocker for the Price operation; do not round it or reinterpret it as Source OOS. Independently explicit QTY/Status work may continue, but do not execute a Status transition derived solely from the failed Price write. |
| Channel does not expose authoritative Stock Status | Do not claim a verified current status or transition. A requested status operation is `UNVERIFIABLE`/blocked; independent safe fields may proceed only when the requested outcome does not depend on status. |
| Channel supports write but not exact readback | It cannot produce a Phase B verified operation until the connector has an approved authoritative verification mechanism. |
| Channel requires complete-state payload | Manifest still contains only changed governed operations. The connector may carry verified unchanged companions in a hashed transport payload; those companions do not get change badges. |
| Channel lacks variation support | Variation-targeted instructions are `NOT_SUPPORTED`; never redirect them to the parent or siblings. |

Out-of-stock enforcement is deterministic and separates before-state read authority from target enforcement/post-read:

| Desired OOS source | Authoritative before-state | Enforcement and post-read capability | Result |
|---|---|---|---|
| Direct mapped Price unavailable/unusable, Status `0`, or QTY `0` | Direct status read proves current `OUT_OF_STOCK` | No status write required | Unchanged OOS. If Source explicitly supplied QTY `0`, create `stock=0` only when authoritative current QTY differs; otherwise it is a QTY no-op. |
| Direct mapped Price unavailable/unusable or Status `0` | Direct status read proves current `IN_STOCK` | Direct canonical status write and authoritative status readback | `status=OUT_OF_STOCK`; never synthesize QTY. |
| Explicit QTY `0`, no zero invariant | Direct status read proves current `IN_STOCK` | Managed-QTY write/readback plus direct status write/readback | `stock=0` only when current QTY differs, plus `status=OUT_OF_STOCK`. |
| Explicit QTY `0` with declared `0 ⇒ OUT_OF_STOCK` | Authoritative current QTY exists; current status may be authoritative or unavailable | Managed-QTY write and exact QTY readback | `stock=0` only when current QTY differs; it proves the final OOS outcome. Show a transition only with authoritative current status. Current QTY already `0` plus claimed current `IN_STOCK` contradicts the invariant and blocks as unverifiable evidence. |
| Any OOS source | Direct status read proves current `IN_STOCK` | Status is read-only and no qualifying QTY-zero mechanism applies | `UNAVAILABLE_OUTCOME_NOT_ENFORCEABLE`; block. |
| Direct mapped Price unavailable/unusable or Status `0` | No authoritative current status | Any status write, or no status write | `LIVE_STATE_UNVERIFIABLE`; block because expected-before/no-op versus change cannot be established. |
| Any required OOS change | Authoritative before-state exists | Target write lacks authoritative post-read | `LIVE_STATE_UNVERIFIABLE`; block under Phase B. |

In-stock enforcement is independently deterministic:

| Desired IN source | Authoritative before-state | Available enforcement | Result |
|---|---|---|---|
| QTY blank/positive or Status blank/`1` | Direct status read proves current `IN_STOCK` | No status write needed | Unchanged IN; positive QTY may still produce its own managed `stock` operation, blank QTY never does |
| QTY blank/positive or Status blank/`1` | Direct status read proves current `OUT_OF_STOCK` | Direct canonical status write plus authoritative readback | `status=IN_STOCK`; include positive QTY operation when independently changed/supported, never invent QTY for blank |
| Explicit positive QTY | Authoritative current availability exists | A separately declared full managed-inventory invariant proves both `0 ⇒ OOS` and `positive ⇒ IN`, with exact QTY write/readback | `stock=<positive>` may enforce final IN; transition label still uses authoritative before-state evidence |
| QTY blank | Current `OUT_OF_STOCK` | Quantity-only connector | Block; blank is no QTY instruction, so FlowHub cannot invent a positive quantity |
| Any mapped desired-IN signal | Current status unavailable | Any | `LIVE_STATE_UNVERIFIABLE`; no transition/Manifest because expected-before is unknown |
| Any mapped desired-IN signal | Direct status read proves current `OUT_OF_STOCK` | No verified direct or approved full-inventory IN mechanism | `IN_STOCK_OUTCOME_NOT_ENFORCEABLE`; no transition/Manifest |
| Optional positive QTY on unsupported/unmanaged dimension | Not applicable | QTY instruction is suppressed before executable precedence | Capability warning only; it does not create an IN transition or block an independent safe Price operation |

A direct status transition requires authoritative status read for the before-state, declared status write for the target, and authoritative post-write readback. Read support and write support must be declared separately. V1 assumes no full managed-inventory invariant unless a connector explicitly implements and tests both directions; the approved one-way zero invariant alone cannot establish IN_STOCK.

An unsupported field contributes no executable availability instruction unless another declared Channel mechanism explicitly implements that business outcome. A recognized unavailable instruction that cannot be safely represented by a supported, verifiable mechanism blocks. This differs from an optional positive Quantity instruction on a price-only Channel: suppress that Quantity with a warning and allow an independent Price operation. Blank input on an unsupported Quantity field is no instruction and creates neither warning nor block.

The current capability declarations for provider publication states must not be reused as Stock Status support. Each connector must explicitly declare and implement provider-neutral availability read/write mapping.

## 15. Variation behavior

Each product variation is its own Channel Listing and is independently matched, normalized, compared, warned, blocked, selected, live-verified, and represented in the Manifest.

- A variation price change creates a Price badge only on that variation.
- A variation's zero Quantity does not change sibling badges.
- A parent may provide display context, grouping, and navigation.
- The variation view model retains at least parent identifier, optional parent name, variation identifier, and variation attributes/label as display context.
- Existing `GroupedProduct.children` represent Channel Listing rows, not an authoritative sibling-variation tree; no badge roll-up may be inferred from that array.
- A variable parent is not an implicit operation target.
- No badge or operation is copied between a parent and child or between siblings.
- A future Phase C dependent-parent operation would require a separate explicit contract and is outside this plan.

## 16. Decision tables

The following tables are normative. Terra Medium should encode them as parameterized business tests before wiring presentation.

### A. Product matching

| Condition | Match result | Eligibility effect | Warning | Allowed fallback |
|---|---|---|---|---|
| Source Product Key is nonblank and unique among participating rows | Source participation and canonical binding may proceed | Continue to Channel match | None | None needed |
| Source Product Key is blank | No participating Source identity | `BLOCKED` before Channel match | None | No Channel ID, name, row-number, or SKU fallback |
| Source Product Key is duplicate under the pinned normalization version | Ambiguous Source identity | `BLOCKED` before Channel match | None | No heuristic duplicate winner |
| Mapped Channel Product Identifier exactly resolves one Listing in that Channel | Matched | Continue classification | None | None needed |
| Identifier resolves one Listing; product names differ completely | Matched | No effect | None | None |
| Identifier resolves one Listing; Source name blank | Matched | No effect | None | Display identifier as label |
| Name matches but mapped identifier differs | Not matched | `BLOCKED`/listing not found for that identifier | None | No name fallback |
| Identifier missing/blank | Not matched | `BLOCKED` | None | No name, SKU, or Source-key fallback |
| Identifier is literal `x`, `-`, or `0` | Pass exact present value to connector identifier contract | Continue if that Channel accepts it; otherwise connector-specific identity blocker | None | Never apply Price/QTY/Status sentinel semantics or truthiness |
| Identifier resolves multiple Listings | Ambiguous | `BLOCKED` | None | No heuristic tie-breaker |
| SKU differs, but mapped identifier matches | Matched | No effect | None | SKU is display evidence only |
| SKU is the explicitly configured Channel Product Identifier | Exact SKU-role match | Continue classification | None | Authority comes from mapping role, not the label `SKU` |
| Variation identifier resolves one child Listing | Match that child only | Continue child classification | None | Never fall back to parent/sibling |
| Provider requires canonical identifier parsing | Match only after connector-declared canonicalization | Block on parse failure | None | No generic normalization |

### B. Price normalization

Unless a row explicitly says `PRICING_MATRIX`, this table describes an observed `DIRECT_MAPPED_PRICE_CELL`. Direct mapped Price cells carry availability; Pricing Matrix results never do.

| Mapping/cell state | Instruction | Canonical price target | Stock signal | Price state | Eligibility | Warning | Badge |
|---|---|---:|---|---|---|---|---|
| `NOT_MAPPED` | `NO_INSTRUCTION` | none | none | `NOT_EVALUATED` | No block | None | `Price not mapped` only in details |
| Mapped header missing | `INVALID` | none | none | `NOT_EVALUATED` | `BLOCKED` | None | `Mapped price column missing` + `Blocked` |
| Blank | `UNAVAILABLE` / `PRICE_UNAVAILABLE_BLANK` | none | `OUT_OF_STOCK` | `NO_VALID_PRICE` | Eligible if OOS is enforceable or already satisfied | Conflict only with an explicit IN signal | `No usable price` |
| Canonical numeric zero after parsing: `0`, `0.0`, or `0.00`, fix ON or OFF | `UNAVAILABLE` / `PRICE_UNAVAILABLE_ZERO` | none | `OUT_OF_STOCK` | `NO_VALID_PRICE` | Eligible if OOS is enforceable or already satisfied | Conflict only with an explicit IN signal; no unusable-value warning | `No usable price` |
| Exact `x` after trim/case normalization | `UNAVAILABLE` / `PRICE_UNAVAILABLE_X` | none | `OUT_OF_STOCK` | `NO_VALID_PRICE` | Eligible if OOS is enforceable or already satisfied | Conflict only with an explicit IN signal | `No usable price` |
| RIAL/TOMAN positive integer lexeme | `SET` | exact integer | `IN_STOCK` | Compare with current | Continue subject to IN evidence/enforcement | Policy/evidence warnings only | Result from Table C |
| RIAL/TOMAN positive `.00`/`.000`, fix ON | `SET`; reason/evidence `PRICE_ZERO_DECIMAL_FIXED` | exact integer with scale removed | `IN_STOCK` | Compare with current | Continue subject to IN evidence/enforcement | None for the fix itself | Result from Table C; detail `Zero-decimal form fixed` |
| RIAL/TOMAN positive `.00`/`.000`, fix OFF | `UNUSABLE` / `PRICE_DECIMAL_LEXEME_NOT_ALLOWED` | none | `OUT_OF_STOCK` | `NO_VALID_PRICE` | Eligible if OOS is enforceable or already satisfied | `UNUSABLE_MAPPED_PRICE` | `No usable price` |
| RIAL/TOMAN real fraction such as `.50`, fix ON or OFF | `UNUSABLE` / `PRICE_FRACTION_NOT_ALLOWED` | none | `OUT_OF_STOCK` | `NO_VALID_PRICE` | Eligible if OOS is enforceable or already satisfied | `UNUSABLE_MAPPED_PRICE` | `No usable price` |
| Two-decimal currency/unit contract: positive `100.50` or `100.500` | `SET` | exact representable Decimal | `IN_STOCK` | Compare with current | Continue subject to IN evidence/enforcement | Policy/evidence warnings only | Result from Table C |
| Two-decimal currency/unit contract: positive `100.505` | `UNUSABLE` / `PRICE_PRECISION_NOT_ALLOWED` | none | `OUT_OF_STOCK` | `NO_VALID_PRICE` | Eligible if OOS is enforceable or already satisfied | `UNUSABLE_MAPPED_PRICE` | `No usable price` |
| Zero-decimal non-IRR contract: positive `100.00` | `SET` | exact integer-valued Decimal | `IN_STOCK` | Compare with current | Continue subject to IN evidence/enforcement | None | Result from Table C; RIAL/TOMAN toggle is not applicable |
| Zero-decimal non-IRR contract: positive `100.50` | `UNUSABLE` / `PRICE_PRECISION_NOT_ALLOWED` | none | `OUT_OF_STOCK` | `NO_VALID_PRICE` | Eligible if OOS is enforceable or already satisfied | `UNUSABLE_MAPPED_PRICE` | `No usable price` |
| Negative, NaN, or infinity | `UNUSABLE` with precise reason | none | `OUT_OF_STOCK` | `NO_VALID_PRICE` | Eligible if OOS is enforceable or already satisfied | `UNUSABLE_MAPPED_PRICE` | `No usable price` |
| Arbitrary text such as `hello`, dash, `n/a`, or provider word | `UNUSABLE` / `PRICE_NOT_NUMERIC` | none | `OUT_OF_STOCK` | `NO_VALID_PRICE` | Eligible if OOS is enforceable or already satisfied | `UNUSABLE_MAPPED_PRICE` | `No usable price` |
| Malformed numeric such as `10O000`, malformed grouping, or unsupported notation | `UNUSABLE` / `PRICE_MALFORMED` | none | `OUT_OF_STOCK` | `NO_VALID_PRICE` | Eligible if OOS is enforceable or already satisfied | `UNUSABLE_MAPPED_PRICE` | `No usable price` |
| Valid number but currency/unit absent or incompatible | `INVALID` for this comparison | none | none | `NOT_EVALUATED` | `BLOCKED` | None | `Price unit unavailable` + `Blocked` |
| `PRICING_MATRIX` successful positive target | `SET` | exact Matrix result | none | Compare with current | Price may continue | Matrix policy warnings only | Result from Table C; availability-neutral |
| `PRICING_MATRIX` activation/valuation/rule/guard/round/calculation failure or unusable result | `INVALID` | none | none | `NO_VALID_PRICE` | `BLOCKED` for the Price target | None | Calculation blocker; never an OOS signal |

### C. Price change

Comparison and badge direction use the exact target regardless of Price origin. In this table, “contributes IN” applies only to `DIRECT_MAPPED_PRICE_CELL`; a successful `PRICING_MATRIX` target gets the same Price badge but is availability-neutral.

| Authoritative Channel current | Valid Source target | Result | Derived delta | Percentage | Manifest candidate | Owner label |
|---:|---:|---|---:|---:|---:|---|
| `100` | accepted normalized `100.00` | `UNCHANGED` | `0` | `0%` | No | `Price unchanged`; a direct mapped target still contributes IN |
| `100` | `120` | `INCREASE` | `+20` | `+20%` | Yes | `Price ↑ 20 · 20%`; all amounts grouped when ≥1,000 |
| `100.00` | valid other-currency `95.07` | `DECREASE` | `-4.93` | `-4.93%` | Yes | `Price ↓ 4.93 · 4.93%` |
| `0` | `120` | `INCREASE` | `+120` | undefined | Yes if zero is authoritative | `Price ↑ 120 · from 0`; a direct mapped target contributes IN |
| `15,000,000` RIAL | Source `15758858.00`, fix ON | `INCREASE` | `+758,858` | derived exactly | Yes | `Price ↑ 758,858`; target displays `15,758,858` |
| `15,758,858` RIAL | Source `15758858.000`, fix ON | `UNCHANGED` | `0` | `0%` | No Price operation | `Price unchanged · 15,758,858` |
| Missing/malformed/untrusted | `120` | `NOT_EVALUATED` | none | none | No | `Price unverifiable` + `Blocked` |
| `100 RIAL` | `100 TOMAN` | `NOT_EVALUATED` | none | none | No | `Price unit mismatch` + `Blocked` |
| Regular `100`, active sale `80` | `100` regular/base | `UNCHANGED` | `0` | `0%` | No | `Price unchanged` + `Warning · Active sale price` |
| Regular `100`, active sale `80` | `120` regular/base | `INCREASE` | `+20` | `+20%` | Yes | `Price ↑ 20 · 20%` + `Warning · Active sale price`; never compare from `80` |
| Any | unavailable or unusable direct mapped Price | `NO_VALID_PRICE` | none | none | No Price operation; may create Status OOS operation | `No usable price`; warning for present unusable values |
| Any | direct schema/configuration failure or Pricing Matrix failure | `NOT_EVALUATED` | none | none | No | Price-blocking evidence; direct signal is unknown, Matrix has no availability signal |

### D. Quantity normalization

| Mapping/cell state | Instruction | Desired QTY | Availability signal | Eligibility | Warning | Write/badge behavior |
|---|---|---:|---|---|---|---|
| `NOT_MAPPED` | `NO_INSTRUCTION` | none | none | No block | None | No comparison/write; mapping detail only |
| Mapped header missing | `INVALID` | none | none | `BLOCKED` | None | No operation; `Mapped quantity column missing` + `Blocked` |
| Blank | `NO_INSTRUCTION` | none | `IN_STOCK` | Continue | None | Never convert to zero/write QTY; `No quantity instruction` |
| `0`, `0.0`, `0.00` | `SET` | `0` | `OUT_OF_STOCK` | Continue if OOS is enforceable or authoritatively already satisfied | Conflict with valid direct Price or explicit Status `1` | Compare/write zero when supported/managed; result from Table E |
| Positive integral Decimal | `SET` | canonical integer | `IN_STOCK` | Continue | Conflict only when an OOS signal exists; optional policy warning | Compare/write when supported/managed; result from Table E |
| Positive Set on unmanaged/unsupported QTY | `SET` | canonical integer retained as evidence | IN signal is not executable | No block for safe independent sibling | `CHANNEL_CAPABILITY_LIMITATION` | Suppress QTY; `Quantity unmanaged/not supported by Channel` |
| Negative | `INVALID` | none | none | `BLOCKED` | None | No operation; `Invalid quantity` + `Blocked` |
| Positive fractional value | `INVALID` | none | none | `BLOCKED` | None | No rounding/operation; `Invalid quantity` + `Blocked` |
| Malformed/Boolean/NaN/infinite/unsupported notation | `INVALID` | none | none | `BLOCKED` | None | No operation; `Invalid quantity` + `Blocked` |

### E. Quantity change

| Source instruction | Current quantity state | Final desired status | Quantity result | Manifest candidate | Owner label |
|---|---|---|---|---:|---|
| Blank | Any | Any | `UNMANAGED` / `NO_INSTRUCTION` | No | `No quantity instruction` |
| Set `8` | Managed current `8` | `IN_STOCK` | `UNCHANGED` | No | `Has 8 quantity` |
| Set `8` | Managed current `5` | `IN_STOCK` | `INCREASE` by `3` | Yes | `QTY +3` |
| Set `5` | Managed current `8` | `IN_STOCK` | `DECREASE` by `3` | Yes | `QTY -3` |
| Set `0` | Managed current `0` | `OUT_OF_STOCK` | `UNCHANGED` | No | `Has 0 quantity`; status operation only if authoritative status still needs change and no zero invariant resolves it |
| Set `0` | Managed current `7` | `OUT_OF_STOCK` | `DECREASE` by `7` | Yes when supported | `QTY -7` |
| Positive Set | Managed current differs | `OUT_OF_STOCK` due Price/Status | Directional change suppressed | No | `QTY not applied while out of stock` |
| Positive Set | Listing not quantity-managed | `IN_STOCK` | `UNMANAGED` | No; this scope never auto-enables management | `Quantity unmanaged by Channel` + capability warning |
| Set | Current quantity unauthoritative | Any | `NOT_EVALUATED` | No | `Quantity unverifiable` + `Blocked` |
| Invalid | Any | No result from invalid row | `NOT_EVALUATED` | No | `Invalid quantity` + `Blocked` |

### F. Stock Status normalization

| Mapping/cell state | Canonical desired status | Availability signal | Eligibility | Owner label/details |
|---|---|---|---|---|
| `NOT_MAPPED` | `NO_INSTRUCTION` | none | No block | `Stock status not mapped` in details |
| Mapped header missing | none | none | `BLOCKED` | `Mapped stock-status column missing` |
| Blank | `IN_STOCK` | in stock | Continue | `In stock` or transition after comparison |
| Numeric Decimal exactly equal to `0`, including `0.0`/localized digits | `OUT_OF_STOCK` | out of stock | Continue | `Out of stock` or transition |
| Numeric Decimal exactly equal to `1`, including `1.00`/localized digits | `IN_STOCK` | in stock | Continue | `In stock` or transition |
| Other number | none | none | `BLOCKED` | `Invalid stock status` |
| Grouped/signed/exponent numeric, `true`, `false`, `yes`, `no`, provider literal, arbitrary text | none | none | `BLOCKED` | `Invalid stock status` |
| Explicit mapping transform outputs canonical value | That canonical value | corresponding signal | Continue | Compare canonical value |

### G. Stock Status precedence

This table is exhaustive over normalized signal sets, regardless of which raw-cell combination produced them.

| Blocker set `B` | OOS signal set `O` | IN signal set `I` | Desired status | Conflict warning | Quantity effect | Eligibility |
|---|---|---|---|---|---|---|
| Non-empty | Any | Any | None from the invalid row | No warning required; blockers explain | No operations | `BLOCKED` |
| Empty | Non-empty | Contains valid positive direct Price, explicit positive QTY, or Status `1` | `OUT_OF_STOCK` | Yes | Positive QTY suppressed; QTY zero retained; valid Price may still write | Eligible if OOS enforceable |
| Empty | Non-empty | Empty or only blank-default signals | `OUT_OF_STOCK` | No | QTY zero retained; blank has no write | Eligible if OOS enforceable |
| Empty | Empty | Non-empty | `IN_STOCK` | No | Positive QTY compared; blank QTY no write | Eligible if status/current evidence sufficient |
| Empty | Empty | Empty | `NO_INSTRUCTION` | No | No quantity instruction unless independently Set without an availability mapping, which cannot occur after normalization | `ELIGIBLE`, not actionable unless Price changes |

Field-level signal examples:

| Price signal | QTY signal | Status signal | Result |
|---|---|---|---|
| Valid positive direct Price/IN | positive/IN | OOS | OOS; valid Price may write, suppress positive QTY, conflict warning |
| Valid positive direct Price/IN | OOS/zero | IN/`1` | OOS; retain QTY zero and valid Price, conflict warning |
| Unavailable/unusable direct Price/OOS | positive/IN | IN/`1` | OOS; no Price write, suppress positive QTY, unusable warning when applicable, conflict warning |
| Valid positive direct Price/IN | IN/default blank | IN/default blank | IN; compare Price, no QTY write |
| Pricing Matrix Price failure/no signal | positive/IN | IN | IN from QTY/Status; Matrix Price field is blocked/omitted and independently valid Stock work may continue |
| Direct mapped OOS Price | OOS QTY | OOS Status | OOS; no conflict; QTY zero may write |
| Valid positive direct Price/IN | no QTY signal | no Status signal | IN; Price may act and a Status transition is planned if needed/capable |
| Successful Pricing Matrix Price/no signal | no QTY signal | no Status signal | `NO_INSTRUCTION` for availability; Price may still act |

### H. Warning versus blocker

| Situation | Classification | Eligible? | Auto-select consequence |
|---|---|---:|---|
| Name differs | Neither warning nor blocker | Yes if otherwise valid | Based only on actionable fields |
| Configured large-price threshold exceeded with compatible unit/currency | Warning | Yes | Select if a business change exists |
| Large absolute price with no applicable policy | Nothing | Yes if otherwise valid | No effect |
| Active sale may alter effective selling price | Warning | Yes unless explicit hard policy says otherwise | Select if a business change exists |
| Explicit availability fields conflict | Warning; OOS wins | Yes if outcome enforceable | Select changed operations |
| Optional QTY instruction on price-only Channel | Capability warning; omit QTY | Yes for independent price | Select Price only |
| Mapped Price is malformed/non-price/negative/non-finite/disallowed fraction | Warning plus OOS signal | Yes if OOS can be verified/enforced | Select Status only when OOS changes; no Price operation |
| All-zero fraction removed by enabled fix; exact Price unchanged | Normalization evidence only; neither warning nor blocker; the valid direct Price still supplies IN | Yes | The fix itself is not actionable. Select only if the derived Status or another governed field changes. |
| Fractional/untrustworthy RIAL/TOMAN Channel current/readback | Price verification blocker; never a Source OOS signal | No for Price; independently safe Stock may remain eligible | Never select/Manifest the Price until corrected; safe Stock may select |
| Quantity or Stock Status is invalid/malformed | Blocker | No | Never select |
| Pricing Matrix calculation/policy failure | Price-field-only blocker; no availability signal | Yes for independently valid Stock operations; otherwise no executable Price | Never select the Price field; safe Stock fields may select |
| Valid Source Price cannot be represented exactly by provider precision/capability | Price-field-only provider blocker; Source validity is not rewritten, but a Status transition derived solely from that failed Price write is not independent | Yes for independently safe explicit QTY/Status operations; otherwise no executable outcome | Never select or round the Price field; only Stock work independent of the failed Price may select |
| Missing mapped Source header | Blocker | No | Never select |
| Identifier missing/ambiguous/not found | Blocker | No | Never select |
| Requested OOS cannot be enforced/verified | Blocker | No | Never select |
| Live current state drifted/unverifiable | Dry Run blocker | No for this Dry Run | Keep scope evidence, create no Manifest for the entire selected scope, and require correction/new Preview |
| Explicit configured hard policy exceeded | Blocker | No | Never select |

### I. Auto-selection eligibility

| Row eligible | Safe actionable business change | Row-wide blocker | Field-scoped Price blocker | Manual deselected for this Preview | Auto-selected? | Reason |
|---:|---:|---:|---:|---:|---:|---|
| Yes | Yes | No | No | No | Yes | All safe changed operations select |
| Yes | Yes | No | Yes | No | Yes, safe non-Price operations only | Matrix/provider Price is omitted; independent Stock may proceed |
| Yes | Yes | No | Any | Yes | No | Owner choice is authoritative |
| Yes | No | No | No | No | No | Unchanged, warning-only, zero-decimal repair-only, unmapped, unsupported, or no instruction |
| No | Any | Yes | Any | Any | No | Row-wide unsafe/indeterminate condition |
| No | No | No | Yes | Any | No | Requested Price is blocked and no independent safe operation exists |

### J. Manifest field generation

| Dimension/result | Selected? | Live verified? | Manifest operation |
|---|---:|---:|---|
| Price `INCREASE` or `DECREASE`, valid exact target | Yes | Yes, still differs | `field=price`, exact target, currency/unit and precision-contract version, exact expected-before; normalized RIAL/TOMAN target is an integer |
| Price `UNCHANGED`, zero-decimal repair-only, `NO_VALID_PRICE`, unusable, blocking-invalid, unsupported, or unmapped | Any | Any | No Price operation. A valid unchanged direct mapped Price may independently cause an IN Status operation; an unavailable/unusable direct mapped Price may independently cause an OOS Status operation; a Pricing Matrix result has neither availability effect. |
| QTY `INCREASE` or `DECREASE`, integral Set target, supported/managed, not suppressed | Yes | Yes, still differs | `field=stock`, canonical integer target, exact expected-before; explicit zero may also satisfy OOS only under the connector's declared zero invariant |
| QTY `UNCHANGED`, blank, unmanaged, unsupported, invalid, or suppressed | Any | Any | None |
| Stock `BECOMES_IN_STOCK` or `BECOMES_OUT_OF_STOCK` | Yes | Yes, still differs and direct availability write supported | `field=status`, canonical `IN_STOCK`/`OUT_OF_STOCK`; connector serializes provider value |
| Final OOS outcome derived solely from explicit QTY `0` | Yes | Exact managed-QTY read/write verifies connector-declared zero invariant | No separate `status`; `stock=0` is the authoritative mechanism. Show a transition only if current status is independently authoritative; otherwise status is `NOT_EVALUATED` with final-OOS detail. |
| Stock status unchanged, no instruction, unsupported, or unverifiable | Any | Any | None |
| Warning badge | Any | Any | None |
| Eligibility badge | Any | Any | None |
| Any candidate now a live no-op | Yes | Yes | Dry Run `no_op`; no Manifest operation |
| Any drifted/unverifiable/blocked selected candidate | Any | No | Dry Run `blocked`; no Apply Manifest for the whole Reviewed Scope; verified siblings remain evidence only |
| Unselected actionable field | No | Any | None |

## 17. Concrete examples

Assumptions in the examples: Source Product Key participation is valid, Channel identifiers resolve exactly, stated current values are authoritative, currency/unit match, and required Channel read/write capabilities exist unless the example says otherwise. `price`, `stock`, and `status` are canonical Manifest field names. Examples 7 and 19 intentionally assume a connector where QTY zero does not itself prove OOS, so both `stock` and `status` are needed; Example 28 shows the quantity-zero-invariant alternative.

| # | Current Channel state | Source instruction | Expected badges | Eligibility / selection | Manifest fields after successful Dry Run |
|---:|---|---|---|---|---|
| 1 | RIAL/TOMAN Price `100`; QTY `8`; `IN_STOCK` | Price `100.00`; `Fix zero-decimal prices` ON; QTY blank; Status blank | `Price unchanged`; `No quantity instruction`; `In stock` | `ELIGIBLE`; not selected because no actionable change | None |
| 2 | Price `100`; `IN_STOCK` | Direct mapped Price `95.07` under a two-decimal contract; stock fields not mapped | `Price ↓ 4.93 · 4.93%`; `In stock` | `ELIGIBLE`; selected | `price` |
| 3 | Price `100`; `IN_STOCK` | Direct mapped Price `104.20` under a two-decimal contract; stock fields not mapped | `Price ↑ 4.2 · 4.2%`; `In stock` | `ELIGIBLE`; selected | `price` |
| 4 | QTY `5`; `IN_STOCK` | QTY `8`; Status `1`; valid unchanged price | `Price unchanged`; `QTY +3`; `In stock` | `ELIGIBLE`; selected | `stock` |
| 5 | QTY `8`; `IN_STOCK` | QTY `5`; Status `1`; valid unchanged price | `Price unchanged`; `QTY -3`; `In stock` | `ELIGIBLE`; selected | `stock` |
| 6 | QTY `8`; `IN_STOCK` | QTY blank; Status blank; valid unchanged price | `Price unchanged`; `No quantity instruction`; `In stock` | `ELIGIBLE`; not selected | None |
| 7 | QTY `7`; `IN_STOCK` | QTY `0`; Status blank; valid unchanged Price | `Price unchanged`; `QTY -7`; `In stock → Out of stock`; `Warning · Conflicting availability instructions` | `ELIGIBLE`; selected; QTY OOS wins over the valid Price IN signal | `stock`, `status` |
| 8 | `IN_STOCK`; QTY not mapped | Status changes `1 → 0`; valid unchanged Price | `Price unchanged`; `In stock → Out of stock`; `Warning · Conflicting availability instructions` | `ELIGIBLE`; selected; Status OOS wins over the valid Price IN signal | `status` |
| 9 | `OUT_OF_STOCK`; QTY not mapped | Status changes `0 → 1`; valid unchanged price | `Price unchanged`; `Out of stock → In stock` | `ELIGIBLE`; selected | `status` |
| 10 | Price `100`; `IN_STOCK`; QTY not mapped | Valid Price `90`; Status `0` | `Price ↓ 10 · 10%`; `In stock → Out of stock`; `Warning · Conflicting availability instructions` | `ELIGIBLE`; selected; Status OOS wins over the valid Price IN signal | `price`, `status` |
| 11 | Price `100`; QTY `2`; `IN_STOCK` | Price blank; QTY `5`; Status `1` | `No usable price`; `QTY not applied while out of stock`; `In stock → Out of stock`; `Warning · Conflicting availability instructions` | `ELIGIBLE` if OOS enforceable; selected | `status` |
| 12 | Price `100`; `IN_STOCK`; QTY not mapped | Price `0`; Status `1` | `No usable price`; `In stock → Out of stock`; `Warning · Conflicting availability instructions` | `ELIGIBLE` if OOS enforceable; selected | `status` |
| 13 | Price `100`; QTY `2`; `IN_STOCK` | Price `hello`; QTY `5`; Status `1` | `No usable price`; `QTY not applied while out of stock`; `In stock → Out of stock`; `Warning · Unusable mapped price`; `Warning · Conflicting availability instructions` | `ELIGIBLE` if OOS enforceable; selected | `status` |
| 14 | ID `WC-42`; name `Red Shoe`; Price `100`; `IN_STOCK` | ID `WC-42`; name `کاملاً متفاوت`; direct mapped Price `120` | `Price ↑ 20 · 20%`; `In stock`; no name warning | `ELIGIBLE`; selected | `price` |
| 15 | Variation `WC-42-V2`, Price `100`, `IN_STOCK`; sibling `V1` unchanged | Variation `V2` direct mapped Price `110` | On V2 only: `Price ↑ 10 · 10%`; `In stock`; no badge on V1 or parent | V2 `ELIGIBLE` and selected | V2 `price` operation only |
| 16 | Authoritative current values exist | Configured Price header disappeared from Source | `Mapped price column missing`; `Blocked` | `BLOCKED`; not selected | None |
| 17 | RIAL Price `100`; `IN_STOCK`; stock fields not mapped | Direct mapped Price `100.000`; `Fix zero-decimal prices` ON | `Price unchanged`; `In stock`; detail `Zero-decimal form fixed` | `ELIGIBLE`; not selected; the lexical fix alone is not actionable | None |
| 18 | Price unchanged; QTY `2`; `IN_STOCK` | QTY `5`; Status `0` | `QTY not applied while out of stock`; `In stock → Out of stock`; conflict warning | `ELIGIBLE`; selected | `status` |
| 19 | QTY `7`; `IN_STOCK` | QTY `0`; Status `1`; Price unchanged | `QTY -7`; `In stock → Out of stock`; conflict warning | `ELIGIBLE`; selected | `stock`, `status` |
| 20 | Price `100`; `IN_STOCK`; Channel supports Price but not QTY | Direct mapped Price `110`; QTY `8`; Status not mapped | `Price ↑ 10 · 10%`; `In stock`; `Quantity not supported`; capability warning | `ELIGIBLE`; select Price only | `price` |
| 21 | Price/QTY/Status all unchanged at `IN_STOCK`; active sale evidence exists | Same values | `Price unchanged`; `In stock`; `Warning · Active sale price` | `ELIGIBLE`, but no actionable change; not selected | None |
| 22 | Current Stock Status cannot be authoritatively read | Source Status `0` | `Stock status unverifiable`; `Blocked` | `BLOCKED`; not selected | None |
| 23 | Price absent by recognized instruction; already `OUT_OF_STOCK` | Price blank; stock fields not mapped | `No usable price`; `Out of stock` | `ELIGIBLE`, no actionable change; not selected | None |
| 24 | Price `100`; QTY `2`; `IN_STOCK` | Price valid `110`; QTY `2.5`; Status `1` | `Invalid quantity`; `Blocked`; price badge may be explanatory but cannot proceed | `BLOCKED`; not selected | None |
| 25 | Price `100`; QTY not mapped; `OUT_OF_STOCK` | Price `120`; Status blank | `Price ↑ 20 · 20%`; `Out of stock → In stock` | `ELIGIBLE`; selected | `price`, `status` |
| 26 | Regular Price `100`; active sale `80`; `IN_STOCK` | Direct mapped regular/base Price `100`; stock unchanged | `Price unchanged`; `In stock`; `Warning · Active sale price` | `ELIGIBLE`, warning-only; not selected | None |
| 27 | Regular Price `100`; active sale `80`; `IN_STOCK` | Direct mapped regular/base Price `120`; stock unchanged | `Price ↑ 20 · 20%`; `In stock`; `Warning · Active sale price` | `ELIGIBLE`; selected; comparison is from regular `100`, not effective `80` | `price` |
| 28 | Managed QTY `7`; independently authoritative Status `IN_STOCK`; connector guarantees `QTY 0 ⇒ OOS` | QTY `0`; Status not mapped | `QTY -7`; `In stock → Out of stock`; final OOS evidence is quantity-derived | `ELIGIBLE`; selected | `stock` only |
| 29 | Price `100`; `IN_STOCK`; Channel writes Price only and has no qualifying OOS mechanism | Price blank; stock fields not mapped | `No usable price`; `Unavailable outcome not enforceable`; `Blocked` | `BLOCKED`; not selected | None |
| 30 | Source Product Key blank; Channel identifier/name happen to match | Any otherwise valid values | Blocked Data Quality row: `Missing Source Product Key`; dimensions `NOT_EVALUATED` | `BLOCKED`; not selected; no Listing operation projection | None |
| 31 | Source key valid; mapped Channel identifier not found; matching product name exists | Any values | Blocked Data Quality row: `Channel listing not found`; no name warning or fallback | `BLOCKED`; not selected | None |
| 32 | QTY-managed Listing is authoritatively `OUT_OF_STOCK`; connector is quantity-only and has no positive⇒IN invariant | QTY blank; Status not mapped; valid unchanged Price | `No quantity instruction`; `IN_STOCK_OUTCOME_NOT_ENFORCEABLE`; `Blocked` | `BLOCKED`; not selected; blank cannot invent a positive QTY | None |
| 33 | Managed QTY `0`; authoritative `OUT_OF_STOCK` | QTY `0`; Status `0`; valid unchanged Price | `Has 0 quantity`; `Out of stock`; `Price unchanged`; `Warning · Conflicting availability instructions` | `ELIGIBLE`; warning-only and no actionable change; not selected | None |
| 34 | RIAL Price `15,000,000`; `IN_STOCK` | Price `15758858.00`; `Fix zero-decimal prices` ON; stock fields not mapped | `Price ↑ 758,858 · 5.06%`; target evidence `15,758,858`; `In stock` | `ELIGIBLE`; selected | `price` with exact integer target `15758858` |
| 35 | TOMAN Price `15,758,858`; `IN_STOCK` | Price `15758858.000`; `Fix zero-decimal prices` ON; stock fields not mapped | `Price unchanged`; target evidence `15,758,858`; `In stock` | `ELIGIBLE`; not selected | None |
| 36 | RIAL Price `15,758,858`; `IN_STOCK` | Price `15758858.50`; `Fix zero-decimal prices` ON; stock fields not mapped | `No usable price`; `In stock → Out of stock`; `Warning · Unusable mapped price` | `ELIGIBLE` if OOS enforceable; selected; real fraction is not rounded | `status` |
| 37 | TOMAN Price `15,758,858`; `IN_STOCK` | Price `15758858.00`; `Fix zero-decimal prices` OFF; stock fields not mapped | `No usable price`; raw evidence `15,758,858.00`; `In stock → Out of stock`; `Warning · Unusable mapped price` | `ELIGIBLE` if OOS enforceable; selected; zero-fraction fix was disabled | `status` |
| 38 | Currency contract permits two fractional digits; Price `15,758,858`; `IN_STOCK` | Price `15758858.25`; stock fields not mapped | `Price ↑ 0.25 · <0.01%`; target evidence `15,758,858.25`; `In stock` | `ELIGIBLE`; selected | `price` with exact Decimal target `15758858.25` |
| 39 | Price `100,000`; `IN_STOCK` | Price `10O000`; stock fields not mapped | `No usable price`; `In stock → Out of stock`; `Warning · Unusable mapped price` | `ELIGIBLE` if OOS enforceable; selected | `status` |
| 40 | Two-decimal currency Price `100`; `IN_STOCK` | Direct mapped Price `100.505`; stock fields not mapped | `No usable price`; `In stock → Out of stock`; `Warning · Unusable mapped price` | `ELIGIBLE` if OOS enforceable; selected; precision overflow is not rounded | `status` |
| 41 | RIAL Price `100`; `IN_STOCK` | Direct mapped Price `0.00`; `Fix zero-decimal prices` OFF; stock fields not mapped | `No usable price`; `In stock → Out of stock`; no unusable-value warning | `ELIGIBLE` if OOS enforceable; selected; canonical zero is processed before the toggle | `status` |
| 42 | Preview expected RIAL Price `100`; Channel live readback lexeme `100.00`; `IN_STOCK` | Selected valid changed field elsewhere on the row | Price live evidence canonicalizes to exact `100`; no Price drift | Governed selected scope may continue | No Price operation from this equality |
| 43 | Preview expected RIAL Price `100`; Channel live readback `100.50`; authoritative `IN_STOCK` | Any selected Price operation | `Price unverifiable`; `Blocked`; no Source OOS claim | Dry Run `BLOCKED`; not executable | None; whole-scope Manifest withheld |
| 44 | Price `100`; authoritative `OUT_OF_STOCK` | Successful Pricing Matrix target `120`; stock fields not mapped | `Price ↑ 20 · 20%`; availability has `No instruction`; remains `Out of stock` | `ELIGIBLE`; selected for Price only | `price` |
| 45 | Price `100`; authoritative `IN_STOCK` | Pricing Matrix valuation fails; stock fields not mapped | `Price calculation failed`; `Blocked`; availability remains unchanged | `BLOCKED`; not selected | None |
| 46 | Two-decimal monetary contract; Price `100.00`; authoritative `IN_STOCK`; provider supports integer-only Price writes | Direct mapped valid Price `100.25`; stock fields not mapped | Explanatory `Price ↑ 0.25 · 0.25%`; `Provider cannot represent exact Price`; `Blocked`; no OOS reinterpretation | `BLOCKED`; not selected | None |
| 47 | RIAL Price `100`; authoritative `OUT_OF_STOCK` | Direct mapped Price `100.00`; fix ON; stock fields not mapped | `Price unchanged`; detail `Zero-decimal form fixed`; `Out of stock → In stock` | `ELIGIBLE`; selected for the Status change, not for the lexical fix | `status` |
| 48 | Price `100`; QTY `5`; authoritative `IN_STOCK` | Pricing Matrix valuation fails; QTY `8`; Status `1` | `Price calculation failed`/Price field blocked; `QTY +3`; `In stock` | Row `ELIGIBLE` for independent Stock; QTY selected, Price omitted | `stock` |

## 18. Current FlowHub gap analysis

### 18.1 Review basis

This analysis reviewed the current PR #16 branch head and its merged main context. The active canonical UI route is `/products`, rendered by the Source-centric dense Pricing Workspace. The repository also contains a reachable legacy `/api/v2/workspace/preview` path and legacy Workspace UI concepts; identifier/name behavior must not disagree between reachable paths.

### 18.2 Four dimensions

| Dimension | Data/comparison already present | Conflict with approved rules | Backend work | Frontend work | Contract/persistence | Presentation-only | Migration |
|---|---|---|---|---|---|---|---|
| Price | `Money` and Decimal equality exist in `unified_workspace/domain.py`; formatting-only equality is tested. Review and Manifest retain governed current/target/currency/unit. | Legacy paths parse/compare floats; target interpretation treats zero as writable and broad malformed Price as blocking; no Price-origin discriminator, direct-Price availability signal, zero-decimal setting, exact per-currency precision rule, or direction/delta classification exists. | Add origin-aware canonical normalization: direct usable Price→IN, every direct unusable Price→OOS/nonblocking, Matrix results availability-neutral; pin RIAL/TOMAN setting and currency precision; bind regular/base comparison; eliminate float leaks. | Render independent Price/status/warning evidence; add the mapping toggle; preserve raw edit lexemes; use one exact global grouped financial formatter rather than synthetic status or per-screen formatting. | Persist the effective setting in existing mapping `value_policy_json`; add versioned DTO/evidence fields for origin, raw lexeme, precision contract, fix applicability/effect, exact target, and signals. | Derive absolute/% delta, arrow, grouping, localized unit, and fix detail; no display value is authority. | No |
| Stock Quantity | Unified cache and Review/Manifest field `stock` exist; Decimal equality exists; frontend already displays stock target cells. | Fractional quantities pass until connector validation; blank, unmapped, unsupported, and current-value substitution collapse; stock-only legacy changes are ineligible; no QTY operation in legacy Dry Run. | Normalize to non-negative integer; preserve blank no-instruction; implement delta, suppression, zero invariant/capability behavior, and field-specific live verification. | Render `QTY +X`, `QTY -X`, unchanged/unmanaged/suppressed states; keep selection actionable. | Existing stock fields and JSON evidence suffice; canonical integer in DTO/Manifest. | Signed delta text, arrow/sign, neutral summary. | No |
| Stock Status | Legacy data-layer cache has separate `stock_status`; generic Draft/Review/Manifest `status` field exists. | Unified cache currently prefers publication `status` over `stock_status`; capability declarations describe publication/visibility values; Source accepts arbitrary status; UI displays provider literals; no precedence-derived status candidate exists. | Normalize Source `0/1/blank`; correct cache/current-state meaning to provider-neutral availability; add connector mapping, precedence-derived candidate, and field-specific Dry Run. | Render canonical transitions; never infer availability from publication strings. | Existing status/JSON fields can carry canonical availability and contributing signals. Ambiguous old cache values must be unverifiable until refreshed. | Localized from/to wording and neutral icon/tone. | No for scoped work |
| Warning | ReviewItem already stores warnings/errors/eligible independently; stale cache warning is non-blocking. | Legacy workflow combines warning/status and emits `product_name_mismatch`; one frontend field policy warning cannot represent zero-or-more; hardcoded absolute-price thresholds lack unit context; warning-only data can disappear when no-op ReviewItems are removed. | Stable policy-aware warning codes; remove name mismatch; expose warning-only classification outside changed ReviewItems. | Render zero or more warning badges independently in grid and Review; remove mismatch filter/copy; show remediation. | Existing warnings JSON plus grouped classification DTO suffice. | Localized label, order, tone, disclosure layout. | No |

### 18.3 Identity and name gaps

- `app/flowhub/source_workspace/service.py` already resolves exact `(channel_id, external_id)` Listings, consistent with the Identity Authority ADR.
- `app/flowhub/workspace/price_workflow.py` still performs implicit Product ID → SKU fallback and emits `product_name_mismatch`.
- `app/flowhub/integrations/spreadsheet.py` still constrains legacy Product ID to a positive whole number, which cannot represent provider-owned alphanumeric Channel identifiers.
- `app/flowhub/source_workspace/service.py` still makes Source Product Name part of row recognition/readiness and uses name as a grouping fallback.
- The same service currently applies generic `x`/dash handling to `external_id` and can lose numeric identifier `0` through truthiness, incorrectly borrowing business-field sentinels for identity.
- The same service correctly blocks blank/duplicate Source Product Keys; that accepted participation rule must be retained while name becomes optional.
- Current candidate construction can drop a resolved Listing entirely when any mapped value is invalid, and issue evidence may omit `listing_id`, so an Owner-facing blocked row can disappear.
- `frontend/src/pages/Workspace.tsx` still renders and filters `product_name_mismatch`, with related English/Persian translation entries and tests.

Required correction: implement the name-independent participation predicate; remove name from match, readiness, warning, blocker, grouping identity, selection, and Apply logic; and retain it only as optional display evidence. Preserve Source Product Key participation/canonical binding. Remove implicit SKU fallback unless SKU is the explicitly saved Channel Product Identifier. Keep identifier `x`/dash/zero out of business value policy and delegate their validity to the connector. Materialize invalid/unmatched Source-row/Channel projections with complete identity evidence even when they cannot create a Draft change.

### 18.4 Source normalization gaps

The current Source value policy in `app/flowhub/source_workspace/service.py` distinguishes blank, `x`, dash, zero, and invalid input, but `_interpret_target` reduces several meanings to `target=None`, accepts fractional stock, and passes arbitrary status text. The grouped service later substitutes current values when no Source target exists, which hides the difference among blank, unmapped, unsupported, and no instruction. Source-to-Draft generation emits only concrete field targets, so it currently cannot create the precedence-derived `status` candidate required for direct valid Price→IN, direct unavailable/unusable Price→OOS, or QTY zero→OOS.

Required correction: preserve Price origin, raw lexeme, normalized instruction/reason, effective zero-decimal setting, precision-contract version, and exact optional target. Do not infer business semantics from null alone. Generate the derived status candidate with signal provenance and apply the newly versioned Owner contract that intentionally supersedes the older generic blank/zero, malformed-Price, and Product Name clauses. Keep Pricing Matrix success/failure stock-neutral.

### 18.5 Review, selection, Dry Run, and Manifest gaps

- Current ReviewItems are field-level and already store warnings, errors, and an `eligible` value. Authoritative selection is persisted in `ReviewSelection` rows; `ReviewItem.selected` exists but is not the selection authority.
- Current backend `eligible = not errors and not unchanged` conflates safety eligibility with actionability, making unchanged fields ineligible. It also permits an eligible sibling field even when another row-wide fatal field on the Listing is blocked. The approved contract requires separate row safety eligibility and actionability, plus row-level blocking for invalid Quantity/Status, identity/shared-schema/direct-Price-configuration/evidence, and hard policy. A known unusable direct mapped Price is deliberately excluded because it requests OOS; Matrix/provider Price failures are separately excluded because they block only Price and must not suppress independently safe Stock work.
- Current auto-selection uses eligible Review items and preserves a manual-deselected state, which is a strong base, but it must consume the new separate actionability result.
- No-op changes are removed before Review, so warning-only and neutral no-change presentation need the grouped classification DTO rather than fake Review operations.
- Current Source review creation can block a mapped unsupported field too broadly. It needs field-specific optional capability behavior so safe sibling Price work can continue.
- The current live expected-state helper treats Price as the expected value for every field, and the Woo Phase B targeted live-verification request is Price-only even though generic provider reads expose more data. Price, stock, and status need independent requested/normalized live evidence.
- Current Manifest construction already emits only selected verified field operations and withholds the Manifest when a selected scope blocks. Preserve that whole-scope boundary.
- Exactness gaps extend beyond one late conversion: `WorkspaceWriteIntent` price/stock members in `app/flowhub/write_pipeline/workspace_contracts.py`, `ChannelProduct`/`ChannelProductUpdate` price/stock in `app/flowhub/channels/contracts.py`, current-state stock in `app/connectors/common/current_state.py`, and late service conversion use floats. Reachable business/verification contracts must carry Decimal/canonical integer through connector serialization.
- The WooCommerce path also accepts float Price in `app/connectors/destinations/woocommerce/connector.py` and formats it to two fractional digits in `rest_client.py`. Replace the float boundary with exact Decimal/string validation. A provider-required `.00` wire representation may remain only as an exact serialization of the canonical integer business target; it is not the Source fix and cannot feed back into classification.
- Current empty-selection/all-no-op handling rejects some valid “nothing to do” states. The UI and service should distinguish a successful no-change Preview from an invalid request.

### 18.6 Current provider-capability baseline

The current implementation is not yet capable of executing the full status model:

| Connector | Current relevant baseline | Consequence for this plan |
|---|---|---|
| WooCommerce | Generic reads can expose price/stock/status, but Phase B targeted live verification currently requests Price; declared writes are Price only and `write_status=False`. | Price can use the current boundary. QTY/Status transitions remain unavailable until exact targeted reads and declared writes exist. Woo `instock`/`outofstock` must be separated from publication `publish`/`draft`/`private`. |
| SnappShop | Declares Price and stock writes, no status write; current status literals are publication/visibility concepts. | Add exact integer QTY verification. Do not treat `active`/`inactive` as stock availability without an explicit connector availability contract. |
| TapsiShop | Advertises Price/stock capability, but exact current-state readback is `UNSUPPORTED`; no status write. | Phase B cannot produce verified Price/QTY/Status operations until an approved exact verification mechanism exists. |
| Technolife | Declares Price and stock writes, no status write; current status literals are publication/visibility concepts. | Add exact integer QTY verification. Do not treat `active`/`hidden` as stock availability. |

All four current declarations have `write_status=False`. Therefore examples involving a direct `status` Manifest operation describe the required contract after connector support is implemented; under the current capability set those transitions are blocked unless explicit QTY zero and a declared authoritative quantity-zero invariant can satisfy OOS.

### 18.7 Frontend presentation gaps

The current dense `GroupedField` contract exposes current, target, changed, read-only, currency/unit, and one generic status. `GroupedListing` already exposes aggregate `state`, `changedFields`, `selected`, and `reviewItemIds`; product/page DTOs expose selection/change summaries. `ReviewItemResource` already carries warnings, errors, eligibility, and selection, but `ReviewDialog` does not render them. `PricingFieldPolicy` supports only one optional warning. None of these contracts provides independent change states, deltas, capability/mapping/instruction distinctions, canonical status transitions, zero-or-more warnings, or row Eligibility.

`DensePricingWorkspace.tsx` renders a single cell status. Its `AvailabilitySelect` and `statusTone` infer availability from provider/publication literals including `active` and `publish`; replace that inference with backend-supplied canonical `IN_STOCK`/`OUT_OF_STOCK`. Existing `Badge` can be reused, but every `GroupedListing` row and the Review dialog need a compact badge group with deterministic order: Price, QTY, Stock Status, Warnings, then Eligibility. The shared Product cell is populated only on the first Channel row and cannot own Channel-specific badges.

The frontend has an exact BigInt/scale Decimal parser in `frontend/src/features/pricingWorkspace/pricingWorkspaceState.ts`; it may format values, but the backend must remain the classification authority. The frontend must not independently reproduce precedence or eligibility rules.

Financial presentation is not yet global or contract-consistent. `frontend/src/utils/price.ts` groups ASCII digits and preserves fractional text, while `frontend/src/i18n/format.ts` accepts JavaScript `number` and delegates currency defaults to `Intl`; `Dashboard.tsx`, `Orders.tsx`, the Product/Workspace surfaces, Topbar/exchange-rate displays, and Activity/Review/Apply evidence use a mixture of those helpers and local formatting. Several reachable service/view contracts, including `frontend/src/services/types.ts`, `ApiWorkspaceService.ts`, `ApiProductService.ts`, and Dashboard monetary values, still expose JavaScript `number`, so a formatter alone cannot preserve values above the safe-integer boundary. Extend Owner-facing monetary DTOs to canonical decimal strings before routing every amount through one exact string/BigInt-safe formatter that groups the integer part and retains significant fractional digits allowed by the currency/unit contract. English uses commas; Persian may use locale digits/separators, with each numeric run bidi-isolated. Raw/API/audit payloads and Manifest hashes remain canonical unlocalized strings.

The current `pricingWorkspaceState.ts` edit path also strips trailing zeros and treats positive `100` and `100.00` as equal before submission. That would erase the lexical evidence needed when the RIAL/TOMAN fix is OFF. The mapping/editor UI must preserve and submit the raw Price lexeme for backend classification, display a grouped normalized value only after classification/commit, and ensure formatting-only display changes never create a Draft change.

Current `pricingDescriptors()` deliberately keeps Price eligible when a sibling stock field blocks, and a safety test pins that behavior. Change it for fatal invalid Quantity/Status and row-wide identity/shared-schema/direct-Price-configuration/evidence failures. Deliberately retain direct mapped Price unusability as an OOS instruction, keep Matrix/provider Price blockers field-scoped, and retain the optional unsupported/unmanaged positive-QTY exception.

Review creation covers the full unpaginated Draft, but the current dialog joins Review items against the loaded grid page. The immutable Review/read-model DTO must carry the full-scope display/classification context or provide an immutable full-scope lookup. Dry Run scopes also need field-specific evidence sufficient to render exact write/no-op/blocked outcomes. Apply confirmation must remain sourced only from `reviewContext.operations`/Verified Write Set.

Variation context is not fully retained in the dense view model. Add parent identifier/name and variation attributes/label without changing identity or propagating badges. Existing `GroupedProduct.children` are Channel Listing rows, not an authoritative sibling-variation hierarchy.

Accessibility requirements are concrete: arrow/icon glyphs are decorative; localized text explicitly says increase/decrease and from/to; numeric fragments stay LTR inside Persian RTL layout; details use a keyboard-operable named control; and warning/blocker evidence is programmatically associated with its Listing row. `frontend/src/globals.css` may be needed for bidi-safe numeric/badge wrapping.

### 18.8 Data-contract extension and migration decision

Use the existing persistence surfaces:

- `SourceMappingRevision.value_policy_json` for shared mappings, and `SourceWorksheetRule.value_policy_json` for per-worksheet mappings, extended backward-compatibly with a versioned `channel_price_policies` object keyed by immutable `channel_id` within that mapping scope. Each entry contains `fix_zero_decimal_prices_applicability` (`APPLICABLE`/`NOT_APPLICABLE`), explicit effective `fix_zero_decimal_prices`, and `monetary_precision_contract_version`. Existing flat blank/x/dash/zero/formula/invalid keys remain readable. The API/TypeScript `dict[str,str]`/`Record<string,string>` contracts must become typed versioned objects, and the entire value participates in the Mapping checksum;
- `SnapshotRow.normalized_data_json` for normalized instruction/evidence and classification version;
- `ReviewItem.normalized_value_json`, `payload_summary_json`, `warnings_json`, `errors_json`, and `eligible` for field evidence;
- `ReviewSelection` rows as authoritative Owner selection, rather than `ReviewItem.selected`;
- field-level `DraftRevisionChange` and `ApplyManifestOperation` records; and
- `DryRunScope` write/no-op/blocked evidence.

Add a versioned response/view model for the four dimensions and eligibility. For Price it includes origin, raw Source lexeme, exact normalized value, effective zero-decimal setting/applicability, fix-applied evidence, precision-contract version, and availability signal. Do not add columns for badges or deltas.

**Migration required: NO for this scoped plan.** The immutable JSON policy/evidence columns already support the versioned Channel Price setting and precision metadata; their API validators and serializers require contract changes, not schema changes. The existing Unified `ChannelCache.status` field can carry provider-neutral availability once cache construction stops preferring publication status and connectors normalize availability. Existing ambiguous cache entries must fail as `UNVERIFIABLE` until rebuilt/refreshed from authoritative evidence; they must not be guessed or silently backfilled. If a future feature needs Unified Workspace to preserve publication status and availability simultaneously, a distinct publication-status field may justify a separate migration, but that is outside this task.

## 19. Implementation plan for Terra Medium

Markers used below:

- **[APPROVED BUSINESS]** is fixed by this specification.
- **[IMPLEMENTATION DETAIL]** may be chosen by Terra Medium if all invariants and contract outputs remain intact.
- There are no **[OWNER QUESTION]** items in this plan.

### Step 1 — Business data contracts — Risk: HIGH

**[APPROVED BUSINESS]** Define the versioned four-dimension classification, capability/mapping/instruction/verification axes, stable warning/blocker codes with explicit `ROW`/`PRICE_FIELD` scope, row eligibility, actionability, exact normalized values, and blocked Source-row/Data Quality projection. Make names display-only while preserving required Source Product Key participation. The Price contract includes immutable origin, raw lexeme, exact target, currency/unit precision-contract version, zero-decimal-setting applicability/effective Boolean, fix-applied reason, and availability signal.

**[IMPLEMENTATION DETAIL]** Prefer small typed value objects/enums in existing modules rather than a new framework. Likely files to inspect/change:

- `app/flowhub/unified_workspace/domain.py`
- `app/flowhub/unified_workspace/models.py` only for semantic review, not schema changes
- `app/flowhub/source_workspace/service.py`
- `app/flowhub/source_workspace/models.py` for existing JSON-surface review only
- `app/flowhub/api/v2/source_workspace.py`
- `app/flowhub/api/v2/unified_workspace.py`
- `frontend/src/pages/SourceConfiguration.tsx`
- `frontend/src/pages/sourceConfiguration/WorksheetRuleEditor.tsx`
- `frontend/src/features/sourceWorkspace/types.ts`
- `frontend/src/services/unifiedWorkspace/types.ts`
- `frontend/src/services/types.ts`
- `frontend/src/services/workspace/ApiWorkspaceService.ts`
- `frontend/src/services/products/ApiProductService.ts`
- `docs/architecture/SOURCE_CENTRIC_PRICING_WORKSPACE.md`
- `docs/architecture/SOURCE_SCHEMA_ASSESSMENT_CONTRACT.md`

Contract tests must pin serialized codes, Decimal-as-string behavior, the backward-compatible versioned `channel_price_policies` JSON shape, its Mapping checksum contribution, and the default-ON materialization for legacy RIAL/TOMAN mappings. Bump existing normalization/validation or snapshot-contract versions rather than silently changing old semantics.

### Step 2 — Backend classification — Risk: HIGH

**[APPROVED BUSINESS]** Implement Tables B–F and the pinned Price/QTY/Status lexical grammars in one canonical backend classifier. For a direct mapped Price, order classification as: mapping/evidence checks; blank or exact `x`; trustworthy exact numeric parse; canonical zero before the toggle; negative/non-finite/unusable; resolve currency/unit precision; positive RIAL/TOMAN integer/fix rules; then positive non-IRR exact representability. A valid direct Price contributes IN; every observed unusable direct Price contributes OOS with a warning when present/non-command and is not blocking by itself. Pricing Matrix success stays availability-neutral and Matrix failure blocks its Price target with no stock signal. Quantity/Status invalid values remain fatal; Quantity must be whole; Stock Status normalizes only to `IN_STOCK`/`OUT_OF_STOCK`. Keep identifier values outside business sentinels and retain blocked rows rather than dropping candidates.

Likely files:

- `app/flowhub/source_workspace/service.py`
- `app/flowhub/unified_workspace/domain.py`
- `app/flowhub/unified_workspace/services.py`
- `app/flowhub/channels/write_validation.py`
- `app/flowhub/channels/contracts.py`
- reachable legacy parsing in `app/flowhub/integrations/spreadsheet.py` and `app/flowhub/workspace/price_workflow.py`

**[IMPLEMENTATION DETAIL]** The classifier may use pure functions or domain types, but one implementation must own business decisions for both DTOs and tests. Do not duplicate rules in React or reuse Pricing Matrix quote normalization for direct selling-price input.

### Step 3 — Remove name mismatch validation — Risk: MEDIUM

**[APPROVED BUSINESS]** Delete `product_name_mismatch` as a validation/warning/filter concept. Replace name-based recognition with the pinned non-display participation predicate, remove name-required readiness and name/group fallback, and preserve Source Product Key validation. Delete implicit SKU fallback unless the saved mapping declares SKU as the Channel identifier.

Likely files:

- `app/flowhub/workspace/price_workflow.py`
- `app/flowhub/source_workspace/service.py`
- `frontend/src/pages/Workspace.tsx`
- `frontend/src/services/types.ts`
- `frontend/src/i18n/locales/en/workspace.json`
- `frontend/src/i18n/locales/fa/workspace.json`
- related backend/frontend tests

**[IMPLEMENTATION DETAIL]** Preserve optional display names and use identifier-based fallback labels.

### Step 4 — Stock precedence — Risk: HIGH

**[APPROVED BUSINESS]** Implement the set-based blocker/OOS/IN/no-instruction precedence from Table G, including direct valid Price as IN and every direct unavailable/unusable Price as OOS; keep all Pricing Matrix outcomes availability-neutral. Add explicit-conflict warning, positive-QTY suppression, QTY-zero retention, deterministic direct-status/quantity-zero enforcement, derived status candidate with signal provenance, and enforceability blocker.

Likely files:

- `app/flowhub/source_workspace/service.py`
- `app/flowhub/unified_workspace/domain.py`
- `app/flowhub/unified_workspace/services.py`
- provider capability declarations in `app/flowhub/unified_workspace/connectors.py`

**[IMPLEMENTATION DETAIL]** Store contributing signal codes in existing JSON evidence so UI explanations do not recompute precedence. Do not synthesize QTY zero and do not auto-enable quantity management.

### Step 5 — Badge DTO/view model — Risk: MEDIUM

**[APPROVED BUSINESS]** Expose all four dimensions plus Eligibility and actionability, including exact current/target, Price origin/raw lexeme/precision contract/zero-decimal evidence, reason codes, capability/mapping/instruction/verification states, warnings, and variation context. Derive deltas from exact evidence.

Likely files:

- `app/flowhub/unified_workspace/services.py`
- `app/flowhub/api/v2/unified_workspace.py`
- `frontend/src/features/sourceWorkspace/types.ts`
- `frontend/src/services/unifiedWorkspace/types.ts`

**[IMPLEMENTATION DETAIL]** The grouped read model may be computed from immutable Snapshot/Review evidence. It must preserve null meanings rather than substituting the current value for no instruction, retain blocked projections with no Listing, and supply the full unpaginated Review scope rather than depending on the loaded grid page.

### Step 6 — Auto-selection integration — Risk: MEDIUM

**[APPROVED BUSINESS]** Auto-select only eligible actionable operations; warning-only, zero-decimal repair-only, no-change, and row-blocked results remain unselected; manual deselection stays authoritative for the Preview. A field-scoped Matrix/provider Price blocker is never selected, but it does not prevent an independently safe QTY/Status operation from auto-selecting.

Likely files:

- `app/flowhub/unified_workspace/services.py`
- `frontend/src/features/sourceWorkspace/DensePricingWorkspace.tsx`
- `frontend/src/features/pricingWorkspace/pricingWorkspaceState.ts`

**[IMPLEMENTATION DETAIL]** Keep `ReviewSelection` operation-level rows as authority and let the existing `Include in Save` / `Exclude from Save` row control aggregate them. Permit an intentionally empty saved selection while disabling Dry Run/Apply; present all-no-op Preview as a successful no-change result.

### Step 7 — Dry Run integration — Risk: HIGH

**[APPROVED BUSINESS]** Verify expected-before against live current state independently for Price, Quantity, and Stock Status. Price evidence carries the pinned setting and monetary-precision-contract version; integral RIAL/TOMAN provider `.00` canonicalizes exactly regardless of the Source toggle, while a real fractional RIAL/TOMAN current value is `UNVERIFIABLE`, never an OOS instruction. Preserve write/no-op/blocked and drift/unverifiable semantics. Never use a badge as verification evidence.

Likely files:

- `app/flowhub/unified_workspace/services.py`
- `app/flowhub/unified_workspace/connectors.py`
- `app/connectors/common/current_state.py`
- `app/connectors/destinations/woocommerce/connector.py`
- `app/flowhub/channels/woocommerce.py`
- `app/flowhub/channels/snappshop.py`
- `app/flowhub/channels/tapsishop.py`
- `app/flowhub/channels/technolife.py`
- `app/flowhub/write_pipeline/workspace_contracts.py`

**[IMPLEMENTATION DETAIL]** Extend existing current-state/evidence objects rather than adding another verification service. Unsupported exact reads remain fail-closed. Preserve the current whole-scope rule: any selected blocked scope creates no Apply Manifest, while retaining all scope evidence.

### Step 8 — Manifest field planning — Risk: HIGH

**[APPROVED BUSINESS]** Generate operations exactly as Table J specifies. Field-scoped Matrix/provider Price blockers never become selectable operations and do not suppress an independently safe Stock operation. Keep canonical status in business/Manifest evidence and translate only at the connector. A normalized changed RIAL/TOMAN Manifest target is an exact integer; another currency retains its allowed exact Decimal. The fix governs Source normalization, so a connector may emit an equivalent provider-required `.00` wire lexeme, but never through float and never with a changed numeric value. Remove float types/conversion from reachable business, current-state stock, write-intent, and Channel product/update contracts. Retained complete-state companion values do not become operations.

Likely files:

- `app/flowhub/unified_workspace/services.py`
- `app/flowhub/unified_workspace/connectors.py`
- `app/flowhub/channels/contracts.py`
- `app/flowhub/channels/write_validation.py`
- `app/flowhub/write_pipeline/workspace_contracts.py`
- `app/connectors/destinations/woocommerce/connector.py`
- `app/connectors/destinations/woocommerce/rest_client.py`

**[IMPLEMENTATION DETAIL]** Preserve existing immutable Manifest hashing and idempotency boundaries.

### Step 9 — Frontend badges and global financial presentation — Risk: HIGH

**[APPROVED BUSINESS]** Render Price, QTY, Status, zero-or-more Warning badges, and separate Eligibility. Support multiple badges, no-change labels, suppressed/unmanaged states, and exact evidence details. Never show a name mismatch. Add the per-Channel `Fix zero-decimal prices` mapping control, default it ON for RIAL/TOMAN, hide/mark it `NOT_APPLICABLE` elsewhere, preserve raw Price edit lexemes, and group every Owner-facing financial amount while retaining allowed significant fractions.

Likely files:

- `frontend/src/features/sourceWorkspace/DensePricingWorkspace.tsx`
- `frontend/src/features/sourceWorkspace/types.ts`
- `frontend/src/features/pricingWorkspace/pricingWorkspaceState.ts`
- `frontend/src/pages/SourceConfiguration.tsx`
- `frontend/src/pages/sourceConfiguration/WorksheetRuleEditor.tsx`
- `frontend/src/utils/price.ts`
- `frontend/src/utils/price.test.ts`
- `frontend/src/i18n/format.ts`
- `frontend/src/i18n/i18n.test.ts`
- `frontend/src/pages/Products.tsx`
- `frontend/src/pages/Dashboard.tsx`
- `frontend/src/pages/Orders.tsx`
- `frontend/src/pages/Activity.tsx`
- `frontend/src/components/Topbar.tsx`
- `frontend/src/pages/ExchangeRates.tsx`
- `frontend/src/services/types.ts`
- `frontend/src/services/workspace/ApiWorkspaceService.ts`
- `frontend/src/services/products/ApiProductService.ts`
- `frontend/src/components/Badge.tsx`
- `frontend/src/globals.css`
- `frontend/src/i18n/locales/en/workspace.json`
- `frontend/src/i18n/locales/fa/workspace.json`
- `frontend/src/i18n/locales/en/sources.json`
- `frontend/src/i18n/locales/fa/sources.json`
- `frontend/src/i18n/locales/en/common.json`
- `frontend/src/i18n/locales/fa/common.json`
- legacy `frontend/src/pages/Workspace.tsx` cleanup while it remains reachable

**[IMPLEMENTATION DETAIL]** Reuse existing Badge primitives. Attach them to every Channel Listing row and Review dialog. Build one exact string/BigInt-safe shared financial formatter and audit Product, Dashboard, Order, Workspace, Review, Dry Run, Verified Write Set, Manifest/Apply, Activity, Topbar, and exchange-rate surfaces. Use deterministic order, accessible non-color localized wording, decorative arrows, bidi-isolated numeric runs, compact wrapping, Persian RTL support, a keyboard-named detail control, and programmatic row/evidence association. On edit, preserve the unformatted raw lexeme; after classification/commit, show the grouped normalized value. Invalidate or mark badges stale after unsaved local edits.

### Step 10 — Regression tests — Risk: HIGH

**[APPROVED BUSINESS]** Turn all normative tables and examples into parameterized tests. Verify identifier-only matching, exact Decimal/precision behavior, zero-decimal setting/default/version pinning, direct-Price versus Matrix provenance, precedence, independent badges, global grouping, warning/blocker separation, selection, field-specific Dry Run, Manifest fields, and variations.

Likely test areas:

- `tests/flowhub/source_workspace/test_service.py`
- `tests/flowhub/source_workspace/test_identity_authority_architecture.py`
- `tests/flowhub/source_workspace/test_workspace_integration.py`
- `tests/flowhub/integrations/test_spreadsheet.py`
- `tests/test_blank_price_regression.py`
- `tests/flowhub/unified_workspace/test_domain.py`
- `tests/flowhub/unified_workspace/test_connectors.py`
- `tests/flowhub/api/v2/test_unified_workspace.py`
- `tests/flowhub/source_workspace/test_worksheet_rules.py`
- `tests/connectors/destinations/test_woocommerce_connector.py`
- `tests/connectors/destinations/test_woocommerce_rest.py`
- `tests/beta/test_workspace_price_workflow.py`
- `frontend/src/features/sourceWorkspace/DensePricingWorkspace.safety.test.ts`
- `frontend/src/features/sourceWorkspace/SourceCentricWorkspace.test.tsx`
- `frontend/src/features/pricingWorkspace/pricingWorkspaceState.test.ts`
- `frontend/src/pages/Products.test.tsx`
- `frontend/src/pages/SourceConfiguration.test.tsx`
- `frontend/src/pages/sourceConfiguration/WorksheetRuleEditor.test.tsx`
- `frontend/src/pages/Dashboard.test.tsx`
- `frontend/src/pages/Orders.test.tsx`
- `frontend/src/pages/Activity.test.tsx`
- `frontend/src/components/Topbar.test.tsx`
- `frontend/src/services/workspace/ApiWorkspaceService.test.ts`
- `frontend/src/services/products/ApiProductService.test.ts`
- `frontend/src/pages/UnifiedWorkspace.test.tsx`
- `frontend/src/pages/Workspace.test.tsx`
- `frontend/e2e/pricing-workflow-redesign.spec.ts`
- `frontend/e2e/source-centric-workspace.spec.ts`

### Step 11 — CI — Risk: MEDIUM

**[IMPLEMENTATION DETAIL]** Run focused backend and frontend tests first, then the repository's full required lint/type/test/build checks. Include both English and Persian rendering/translation checks, architecture/contract checks, and PostgreSQL-backed Phase B safety tests. Verify the schema head remains unchanged and no migration file was introduced.

Failures in exact Decimal, identifier authority, no-provider-write Preview/Dry Run boundaries, Manifest hashing, or drift/unverifiable semantics block merge.

### Step 12 — Owner acceptance — Risk: MEDIUM

**[APPROVED BUSINESS]** Present a seeded Preview containing the required examples and demonstrate that badges explain—but do not authorize—the exact selected, verified Manifest operations. Demonstrate manual deselection persistence, warning-only non-selection, direct mapped unusable Price→OOS without a Price blocker, fatal invalid Quantity/Status row blocking, Matrix/provider Price-only blocking with safe Stock continuation, zero-decimal ON/OFF behavior, variation independence, globally grouped financial display, and zero writes during Preview/Dry Run.

**[IMPLEMENTATION DETAIL]** Use an Owner-review fixture or controlled non-production environment. Any live FlowHub review URL must comply with the repository live-version rule and be tied to the then-current `origin/main` commit.

### Complexity estimate

- Backend: **HIGH** — normalization, availability precedence, provider-neutral status semantics, capability behavior, exact live verification, and reachable legacy alignment cross several existing boundaries.
- Frontend: **HIGH** — DTO adoption, the mapping toggle/raw-lexeme editor contract, independent badges, global exact financial formatting across Owner surfaces, selection behavior, RTL/accessibility, and legacy mismatch cleanup; backend remains rule authority.
- Migration: **NO** — existing JSON and field-level persistence are sufficient for this scope; authoritative cache refresh and contract-version handling are required.

## 20. Required tests

At minimum, implementation is incomplete without these tests:

### Business normalization and comparison

- Parameterize every row of Tables B, D, and F and every lexical-grammar step: valid grouping, malformed grouping, Persian/Arabic digits and separators, leading sign, exponent, currency text, Boolean, and native numeric cells.
- Pin Stock Status lexemes independently: blank, `0`/`0.0`/localized zero, `1`/`1.00`/localized one, and rejection of grouping, signs, exponent, Boolean, words, and all other numbers.
- Assert Decimal scale equality for Price only after the currency/unit contract and effective zero-decimal setting accept the Source lexeme; assert mathematical integrality for Quantity.
- Assert no binary float crosses parsing, classification, policy evaluation, DTO, Manifest, or connector intent boundaries.
- Test the direct Price normalization order: missing evidence; blank/exact `x`; exact parse; canonical zero; negative/non-finite; precision resolution; RIAL/TOMAN rule; other-currency representability.
- Test direct mapped malformed, arbitrary text (`hello`), malformed numeric (`10O000`), negative, fractional, NaN, infinity, unsupported notation, missing mapped header, and intentionally unmapped fields. Every observed unusable direct Price requests OOS without being a blocker by itself; missing/untrusted evidence blocks and supplies no signal.
- Test blank/zero/x as warning-free unavailability; test `0.00` as canonical zero even when the fix is OFF; test present unusable Price as `UNUSABLE_MAPPED_PRICE` plus OOS.
- Test the provenance pair: unusable direct mapped Price→nonblocking warning/OOS, while the same bad value as a Pricing Matrix activation/input/output/calculation failure→Price blocker/no availability change. A successful Matrix Price target also remains availability-neutral.
- For RIAL/TOMAN, test default ON, explicit ON/OFF, positive `.00`/`.000`, integer lexemes, and real `.50` under both settings. Assert no rounding, truncation, Source-cell mutation, warning, selection, or provider write for an all-zero-fraction fix alone.
- Test per-Channel isolation, new-mapping explicit default `true`, sealed-legacy derived default pinned into new Snapshot/Preview without mutation, `NOT_APPLICABLE` for other currencies, mapping checksum/version pinning, setting change→new Preview, and no historical Snapshot mutation.
- Test native numeric spreadsheet cells with authoritative formatted `.00` evidence and integer-form evidence. With RIAL/TOMAN fix OFF, missing/erased scale evidence must block as `SOURCE_PRICE_LEXEME_UNVERIFIABLE` with no OOS signal.
- For other currencies, test exact allowed-scale representability: two-decimal `100.50`/`100.500` accepted, `100.505` unusable; zero-decimal `100.00` accepted, `100.50` unusable; missing/conflicting precision contract blocks with no stock signal.
- Test that stricter provider precision/capability does not redefine Source usability: a valid fractional Source Price remains valid, the provider Price operation blocks/marks unsupported with no rounding, and stock is not reinterpreted as OOS. Explicit independent QTY/Status work may continue, while a Status transition derived solely from the failed Price write does not.
- Test authoritative RIAL/TOMAN current/readback `100.00` equals canonical `100` independently of the Source toggle; current/readback `100.50` is unverifiable and never becomes Source OOS.
- Test current Price zero with an undefined percentage and no infinity/NaN serialization.
- Test `ROUND_HALF_UP` percentage display, trailing-zero trimming, and nonzero changes displayed as `<0.01%` rather than `0%`.
- Test currency/unit mismatch and warning thresholds in compatible and incompatible units.
- Test regular/base Price as the governed baseline with active sale evidence for both unchanged and changed targets.

### Identity

- Exact identifier match with completely different names succeeds with no warning.
- Equal names with different identifiers do not match.
- Blank name does not affect recognition, eligibility, or Apply.
- Duplicate names with unique identifiers remain valid.
- Blank and duplicate Source Product Keys block Source participation/canonical binding even when a Channel identifier resolves.
- A completely blank or display-only row is ignored; Source-key/Channel-ID/Price/cost/QTY/Status or another configured non-display pricing input makes a row participate, including raw zero/sentinel values; participating data with a missing Source key becomes a visible blocker.
- No implicit SKU/name/Source-key/parent/sibling fallback.
- Identifier literals `x`, `-`, and `0` bypass Price/QTY/Status sentinel policy and reach connector identifier validation unchanged; test both a connector that accepts and one that rejects each value.
- Connector-declared identifier canonicalization succeeds; unapproved generic canonicalization does not.
- Missing, not-found, ambiguous, and invalid projections remain visible as blocked Data Quality rows with Source/channel/identifier/optional Listing evidence and no operation.

### Precedence and eligibility

- Parameterize the normalized Cartesian rule in Table G, including all requested conflict examples.
- Assert fatal identity/shared-schema/direct-Price-configuration/evidence, invalid Quantity/Status, and hard-policy failures block before signals. Assert direct mapped Price unusability is excluded and supplies OOS; Matrix/provider Price blockers are also excluded from availability precedence and block only Price.
- Assert every valid OOS signal wins over explicit/default IN signals.
- Assert valid positive direct Price, explicit positive QTY, and Status `1` are explicit IN signals for conflict warnings; blank QTY/Status defaults do not create warning noise.
- Assert positive Quantity is suppressed under final OOS while zero remains relevant.
- Assert current QTY `0` versus Source QTY `0` is a quantity no-op and never creates a redundant `stock` Manifest operation.
- Cover direct status enforcement, quantity-zero-derived OOS, both mechanisms with the minimal operation set, and neither mechanism blocked. Assert Price/Status OOS never synthesizes QTY zero, and the one-way zero invariant never infers current IN_STOCK from positive QTY or claims a transition without authoritative current status.
- Cover desired-IN from valid positive direct Price, positive/blank QTY, and Status `1`/blank: already-IN no-op, direct status transition, explicitly declared full managed-inventory invariant, blank-QTY inability to invent stock, and unverifiable/unenforceable blocker.
- Assert recognized unavailable input blocks when the Channel cannot enforce or verify OOS.
- Assert warning-only rows remain eligible but non-actionable.
- Assert optional unsupported QTY does not block independent Price, while safety-critical unsupported OOS does.
- Assert invalid/malformed Quantity or Stock Status and fatal row-wide identity/shared-schema/direct-Price-configuration/evidence failures block the whole Listing row and otherwise valid siblings. Separately assert that unusable direct mapped Price is OOS/nonblocking, Matrix/provider Price failures omit only Price while safe Stock proceeds, and preserve the approved unsupported/unmanaged positive-QTY exception.
- Preserve `channel_cache_not_fresh` as non-blocking and failed/untrustworthy cache as blocking.

### Badge DTO and frontend

- Contract snapshots for every dimension, reason code, capability/mapping/instruction/verification state, eligibility, and variation context.
- Owner-facing monetary DTO snapshots use canonical decimal strings, not JavaScript `number`, including values above `2^53`.
- Multiple badges render together in deterministic order without a synthetic combined status.
- Absolute/percentage Price and Quantity deltas derive correctly from exact values.
- Neutral labels cover no instruction, unchanged managed QTY, unchanged IN/OUT status, and no usable Price.
- Warning count may be zero, one, or many.
- `product_name_mismatch` and its filter/translation/API value are absent.
- English LTR and Persian RTL layouts wrap safely; arrows/text remain unambiguous without color.
- Badges and blockers are keyboard/screen-reader accessible.
- Every `GroupedListing` row and the full Review dialog show its own badges; Review content remains complete when the matching grid row is on another page.
- Unsaved local edits clear or mark immutable server badges stale until reclassification.
- A positive RIAL/TOMAN raw edit lexeme such as `100.00` survives submission when the fix is OFF; client formatting/equality must not erase it before backend classification.
- Every Owner-facing financial amount in Product/Workspace, mapping editors, Dashboard, Orders, Review, Dry Run, Verified Write Set, Manifest/Apply, Activity, Topbar, and exchange-rate displays uses thousands grouping. Accepted normalized RIAL/TOMAN integer display removes `.00`; strict-OFF raw evidence retains it; allowed other-currency fractions such as `15,758,858.25` remain visible.
- Test English and Persian digits/grouping, bidi isolation, values above JavaScript's safe-integer range, grouped input round-trip, and locale-independent canonical DTO/Manifest/hash/provider values.
- Frontend never recomputes business precedence or eligibility from provider strings.

### Auto-selection

- Price-only, QTY-only, Status-only, and multi-field actionable changes auto-select.
- Warning-only, zero-decimal repair-only, unchanged, no-instruction, not-mapped, not-supported-only, and blocked rows do not auto-select.
- A Matrix/provider Price field blocker plus an independent safe Stock change auto-selects only the Stock operation; a Price-only field blocker selects nothing and presents no executable row.
- Manual deselection survives filters, pagination, refetch, polling, and remount for the same Preview.
- A new immutable Preview can compute a fresh initial selection.
- Empty manual selection saves without creating a Dry Run/Manifest.
- All-unchanged Source returns a successful “no actionable changes” state.

### Dry Run and Manifest

- Price, stock, and status read/compare their own expected/live fields independently.
- Each dimension covers live write, live no-op, drift, and unverifiable outcomes.
- Drift/unverifiable does not silently update Preview badges or expected-before.
- Any blocked selected scope produces no Apply Manifest for the whole Dry Run; verified sibling scopes remain evidence only and are never partially packaged.
- A classification-time field-scoped Price blocker is excluded before selection and therefore does not poison Dry Run for independently selected Stock; attempting to inject that blocked Price into Reviewed Scope is rejected.
- Only selected verified changed fields enter the Manifest exactly as Table J states.
- Warning, eligibility, neutral badges, suppressed QTY, and unchanged companions create no operation.
- Complete-state connectors retain hashed unchanged companions without representing them as business changes.
- Decimal/integer targets survive exact round trip into connector validation.
- Dry Run uses the pinned effective zero-decimal setting and precision-contract version. A changed RIAL/TOMAN Manifest target is a canonical integer; a connector-required equivalent `.00` wire lexeme is permitted only through exact serialization and must verify to the same value.
- Financial display locale/grouping changes do not alter Manifest content, hashes, expected-before, target, or provider payload values.
- Preview, Review, and Dry Run produce zero provider writes.
- Manifest immutability, hashing, idempotency, expiry, and stale-evidence regressions remain green.

### Variations and compatibility

- A variation is matched and classified by its own identifier.
- A change on one variation creates no sibling or parent badge/operation.
- Unsupported variation capability blocks only the relevant target and never redirects it.
- Old ambiguous Unified cache publication-status values fail as `UNVERIFIABLE` until authoritative refresh.
- Both reachable legacy and canonical paths obey identifier-only/no-name-warning behavior until legacy removal is explicit.
- Existing PR #16 PostgreSQL persistence and live-verification tests remain green without a new migration.

## 21. Owner acceptance criteria

The plan is implemented only when the Owner can verify all of the following:

1. A matched row with a completely different name proceeds normally and shows no name warning.
2. A name match cannot rescue a missing or wrong Channel Product Identifier.
3. `100`, `100.0`, and `100.00` compare numerically equal after the Source lexeme is accepted by its currency/unit contract; for a positive RIAL/TOMAN Source lexeme, `.00` is accepted only when `Fix zero-decimal prices` is ON, while provider current/readback integral `.00` always canonicalizes exactly.
4. Price increases and decreases show correct exact absolute and percentage evidence without float artifacts.
5. Blank, zero, and exact `x` Price produce no price write and intentionally request unavailability.
6. An observed arbitrary/malformed/negative/non-finite/disallowed-fraction direct mapped Price produces no Price target, requests OOS, and is not a blocker merely for unusability; present unusable input shows an actionable warning.
7. Blank Quantity produces no quantity target or write and is never converted to zero.
8. Quantity zero requests OOS; positive whole Quantity compares/writes; negative/fractional/malformed Quantity blocks.
9. Stock Status `0`, `1`, and blank normalize exactly as specified; unsupported values block.
10. The precedence algorithm yields OOS for every valid OOS signal. Fatal row-wide identity/shared-schema/direct-Price-configuration/evidence, Quantity/Status, and hard-policy failures block before signals. Direct mapped Price unusability is deliberately OOS; Pricing Matrix/provider Price failures are field-scoped, availability-neutral blockers.
11. Explicit availability conflicts show one actionable warning while OOS wins; default blanks do not create warning noise.
12. Price, QTY, Status, Warning, and Eligibility appear as independent UI concepts and can coexist.
13. Warning-only, zero-decimal repair-only, and unchanged rows are not selected; eligible actionable Price/QTY/Status changes are selected.
14. Manual deselection remains authoritative for the immutable Preview.
15. Unsupported optional QTY does not block an independent supported Price change.
16. FlowHub never claims a verified Stock Status transition without authoritative Channel evidence.
17. Each variation is classified and operated independently.
18. Dry Run field scopes explain live write/no-op/blocked outcomes without changing the Preview intent.
19. The Manifest contains exactly the selected, live-verified, changed governed fields and nothing derived merely from badges.
20. Mapping, Preview, Review, and Dry Run cause zero provider writes.
21. No new migration, rule framework, fuzzy matching, name fallback, or provider-state leakage is introduced.
22. Backend, frontend, contract, PostgreSQL safety, RTL/accessibility, and full CI suites pass.
23. Blank/duplicate Source Product Keys still block Source participation, while Product Name is optional display evidence and Channel matching remains identifier-only.
24. Price classification, live verification, and Manifest all use the same governed regular/base field; an active sale is separate warning evidence.
25. QTY zero enforces OOS only through a declared authoritative quantity-zero invariant or a separate verified status operation; Price/Status instructions never synthesize QTY zero.
26. Any blocked selected Dry Run scope prevents creation of the entire Apply Manifest; verified sibling scopes remain evidence only.
27. Fatally invalid and unmatched Source rows remain visible as blocked Data Quality projections instead of disappearing from Owner review; an unusable direct mapped Price instead remains visible as an OOS/warning classification.
28. Row participation uses only non-display mapped cells: blank/name-only rows are ignored, while any business/identifier data with a missing Source Product Key is visibly blocked.
29. Identifier literals such as `x`, `-`, and `0` are never consumed by Price/QTY/Status sentinel policy and remain connector-owned identity values.
30. Source QTY `0` creates no redundant `stock` operation when authoritative current QTY is already `0`.
31. A valid positive direct mapped Price contributes `IN_STOCK`; an unavailable/unusable direct mapped Price contributes `OUT_OF_STOCK`; OOS wins deterministically over Price/QTY/Status IN signals.
32. `Fix zero-decimal prices` is a per-Channel mapped Price setting, defaults ON for RIAL/TOMAN, is `NOT_APPLICABLE` to other currencies, is included in immutable Mapping/Snapshot/Preview evidence, and a change requires a new Preview. A sealed legacy mapping is not mutated; its derived default is pinned in the new Snapshot/Preview.
33. With the fix ON, positive RIAL/TOMAN `15758858.00` and `.000` normalize to exact integer `15758858` without creating a warning or operation by themselves; with it OFF, the positive decimal lexeme is unusable/OOS. Canonical zero such as `0.00` remains the zero/OOS command under either setting.
34. A real fractional RIAL/TOMAN Source Price such as `15758858.50` is never rounded or fixed; it is unusable/OOS. A real fractional RIAL/TOMAN Channel current/readback is instead unverifiable and never interpreted as Source OOS.
35. Other currencies accept exact decimals under their pinned FlowHub currency/unit monetary precision contract and are never subjected to the RIAL/TOMAN fix or silent rounding; stricter provider precision is a separate capability/blocker and never an OOS reinterpretation.
36. Pricing Matrix success and failure remain availability-neutral; a Matrix failure blocks only its Price target, never delists a product, and never suppresses an independently valid Stock operation.
37. Every Owner-facing financial amount uses thousands grouping—an accepted/fixed RIAL/TOMAN `15758858.00` displays as `15,758,858`, strict-OFF raw evidence retains grouped `15,758,858.00`, and valid other-currency `15758858.25` displays as `15,758,858.25`—without altering exact DTO, comparison, Manifest, hash, provider, or audit authority.
38. Raw Price lexemes remain available for classification/evidence, so frontend formatting cannot erase strict-OFF `.00` semantics; the fix never edits the Source cell.
39. If acquisition cannot prove whether a positive RIAL/TOMAN Source value used integer or decimal form while the fix is OFF, FlowHub blocks as unverifiable evidence and does not guess an OOS or Price instruction.
40. Owner-facing monetary API/view contracts retain canonical decimal strings end to end; JavaScript `number` conversion cannot lose exact values before global grouping.

## 22. Open questions

None. This plan deliberately resolves the formerly ambiguous points as follows:

- a trustworthy observed direct mapped Price cell always carries availability: valid positive→IN; blank, zero, exact `x`, or any unusable value→OOS;
- blank/zero/x are warning-free unavailable commands; other present unusable direct Price values add `UNUSABLE_MAPPED_PRICE` but do not block merely for unusability;
- missing/untrusted cell evidence and unit/precision configuration failures block with no availability signal; Pricing Matrix success/failure is availability-neutral and Matrix failure blocks only its Price target;
- canonical numeric zero is handled before the RIAL/TOMAN toggle, so `0.00` is the zero/OOS command even when the fix is OFF;
- `Fix zero-decimal prices` is saved per Channel Price mapping, defaults ON for RIAL/TOMAN, is `NOT_APPLICABLE` elsewhere, removes only all-zero positive fractions when ON, and treats positive decimal lexemes as unusable when OFF;
- strict-OFF classification requires authoritative raw/formatted Source scale evidence; lost lexical evidence blocks without an availability signal;
- real fractional RIAL/TOMAN Source values are never rounded/fixed; other currencies use exact representability under a pinned precision contract;
- the Source setting does not govern provider wire grammar: the Manifest remains canonical, and connectors may use only a mathematically equivalent provider-required serialization;
- every Owner-facing financial amount is grouped for display while canonical unlocalized exact values remain authoritative;
- Product Name alone does not make a row participate, while any non-display mapped business/identity cell does;
- business value sentinels never apply to Channel Product Identifiers;
- out of stock wins over in stock after normalization;
- explicit conflicts warn but do not block when the outcome is enforceable;
- positive Quantity is suppressed under a final OOS outcome, while zero remains actionable;
- the pinned numeric grammar classifies unsupported direct Price lexemes as unusable/OOS; invalid Quantity/Status and row-wide technical failures block the row, while Matrix/provider Price failures stay field-scoped; percentage display uses `ROUND_HALF_UP`;
- Stock Status has its own pinned blank/zero/one grammar and never guesses Boolean, word, sign, exponent, or grouped values;
- regular/base Price is the governed comparison field and sale price is separate warning evidence;
- explicit QTY zero may prove OOS only through a connector-declared authoritative invariant; other OOS signals never synthesize QTY zero;
- any selected blocked Dry Run scope prevents creation of the whole Apply Manifest;
- advisory warnings are disabled until a currency/unit-aware policy explicitly configures them;
- provider publication status is not Stock Status;
- badge deltas are derived from exact evidence; and
- no database migration is required for the scoped implementation.
