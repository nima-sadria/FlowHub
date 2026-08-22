# FlowHub Workspace Canonical Owner Spec — 2026-08-22

Status: Audit output. Read-only analysis document. Does not authorize
implementation, commit, push, merge, or deployment.

Produced from the 11-source review requested in the Owner's "FULL WORKSPACE
RECONCILIATION REVIEW BEFORE ANY MORE IMPLEMENTATION" message, using the
now-complete document set:

1. `WORKSPACE_TEST_MATRIX.md` (WooPrice reference)
2. `WORKSPACE_STATE_MACHINE.md` (WooPrice reference)
3. `WORKSPACE_MIGRATION_GUIDE.md` (WooPrice reference)
4. `WORKSPACE_REFERENCE_PSEUDOCODE.md` (WooPrice reference)
5. `WORKSPACE_DECISION_TABLES.md` (WooPrice reference)
6. `WORKSPACE_BUSINESS_SPEC.md` (WooPrice reference)
7. `WORKSPACE_DATA_CONTRACTS.md` (WooPrice reference)
8. `WORKSPACE_CODE_TRACEABILITY.md` (WooPrice reference)
9. `FLOWHUB_BUSINESS_ENGINE_SPEC.md` (Owner-provided, FlowHub-framed)
10. `WORKSPACE_PHASE_B_CHANGE_BADGES_PLAN_OWNER_UPDATED_2026-08-22.md` (assistant-authored plan, Owner-approved 2026-08-22) — **provided this turn**
11. `WORKSPACE_OWNER_RULES_UPDATE_REPORT_2026-08-22.md` (change log for #10) — **provided this turn**

Plus the current repository at `origin/main` = `1f04c90` (clean working
tree, verified via `git status`/`git log` at the time of this review) and the
non-"OWNER_UPDATED" `WORKSPACE_PHASE_B_CHANGE_BADGES_PLAN.md` pasted in an
earlier turn, which is superseded by document #10 and is retained here only
as a historical-comparison artifact, not as a current source of truth.

**Source-of-truth order used throughout this document** (per document #10's
own stated priority, which this audit adopts): (1) explicit Owner decisions
in document #10/#11 (latest); (2) current FlowHub architecture/safety
invariants that do not conflict with (1); (3) WooPrice reference documents
#1–8 as historical business-reference evidence; (4) older FlowHub planning
documents, including the non-"OWNER_UPDATED" `WORKSPACE_PHASE_B_CHANGE_BADGES_PLAN.md`
and this session's own prior report text, which are **not authoritative**
and are audited, not trusted, in the companion Reconciliation Audit.

Every rule below is tagged:

- **[OWNER RULE]** — an explicit current Owner decision (document #10/#11 or
  the Owner's direct chat instructions).
- **[INHERITED]** — a WooPrice invariant that document #10 does not change.
- **[FLOWHUB OVERRIDE]** — a point where document #10 explicitly and
  intentionally supersedes older WooPrice or older FlowHub-plan behavior.
- **[CONNECTOR]** — behavior owned by a specific provider connector, not the
  business engine.
- **[PRESENTATION]** — display-only; never changes comparison, checksum, or
  write behavior.

---

## 1. Product identity and matching — [INHERITED], unchanged by #10

- A Source row matches a Channel Listing **only** through that Channel's
  configured Product Identifier, resolved in that Channel's context. No
  other Source/Channel attribute is implicit identity.
- Source participation requires a nonblank, unique Source Product Key
  (under the pinned normalization version) for Source identity/canonical
  binding. This key is **not** Channel match authority.
- Product Name and other display metadata are never match authority,
  fallback identity, eligibility input, warning input, or Apply input.
  `product_name_mismatch` is removed from the business-validation model.
- Identifier literals `x`, `-`, `0` are present, exact identifiers passed
  unchanged to the connector's identifier contract — Price/QTY/Status
  sentinel rules never apply to identity fields.
- A row participates (creates a projection, even if later blocked) when any
  non-display mapped cell — Source Product Key, Channel Product Identifier,
  Price, cost, Quantity, Stock Status, or another explicitly configured
  pricing input — is present (explicit null/blank check, never truthiness).
  A row with participating data but a blank Source Product Key becomes a
  visible blocked Data Quality row, never silently dropped.

## 2. Four Change Badge dimensions — [OWNER RULE], reaffirmed in #10

Every participating Source-row/Channel projection classifies independently
across:

1. **Price** — `UNCHANGED` / `INCREASE` / `DECREASE` / `NO_VALID_PRICE` / `NOT_EVALUATED`
2. **Stock Quantity** — `UNMANAGED` / `UNCHANGED` / `INCREASE` / `DECREASE` / `NOT_EVALUATED`
3. **Stock Status** — `UNCHANGED_IN_STOCK` / `UNCHANGED_OUT_OF_STOCK` / `BECOMES_IN_STOCK` / `BECOMES_OUT_OF_STOCK` / `NOT_EVALUATED`
4. **Warning** — zero or more independent, stable codes

...plus a separate **Eligibility** (`ELIGIBLE`/`BLOCKED`) and
**Actionability** (boolean) axis. These six concepts must never collapse
into one synthetic status. A missing/ambiguous/invalid projection is still
materialized as a `BLOCKED` Data Quality row with `NOT_EVALUATED` dimensions
rather than disappearing.

## 3. Price rules — [FLOWHUB OVERRIDE] for unusable-value handling

**[OWNER RULE — the central override in document #10]** For a **mapped**
Channel Price column, normalization has exactly two business outcomes:

- **usable finite positive Decimal** → `SET`, exact target, contributes
  `IN_STOCK`.
- **anything else that is not a usable selling price** — blank, canonical
  zero, exact token `x`, arbitrary text (`hello`), malformed numeric text
  (`10O000`), negative, non-finite, or an unsupported real fraction for a
  zero-decimal currency — → `UNAVAILABLE`/`UNUSABLE`, no price write,
  contributes `OUT_OF_STOCK`. **This is not a blocker.** It carries a
  stable reason code (and, for the non-blank/zero/x cases, warning
  `UNUSABLE_MAPPED_PRICE`) so the Owner can see why.

This **intentionally differs from the older WooPrice interpretation**
(WooPrice/the non-"OWNER_UPDATED" FlowHub plan treated malformed/arbitrary
price text as `INVALID` → `BLOCKED`). Document #10 §5.1/§8.1/Table B is
explicit that this supersession is deliberate. **Do not revert this to the
WooPrice blocking interpretation.**

**[INHERITED, unchanged]** Structural failures remain blockers and are
never reinterpreted as an Owner OOS instruction: a mapped Price header
disappearing, missing/ambiguous identity, missing currency/unit context,
schema drift, or an internal Pricing Matrix calculation failure.

**[FLOWHUB OVERRIDE, RIAL/TOMAN]** `RIAL`/`TOMAN` are zero-decimal business
currencies. Owner setting `Fix zero-decimal prices`, default `ON`, must be
persisted/configurable (not transient UI-only): `.00`/`.000` canonicalize
to the integer; a real non-zero fraction (`15758858.50`) is never silently
rounded — it follows the mapped-Price `UNUSABLE` → `OUT_OF_STOCK` rule.

**[PRESENTATION]** All Owner-facing financial values use thousands grouping
(`15758858` → `15,758,858`) everywhere the shared financial formatter is
used — grid, badges, Review, Dry Run, Apply confirmation. This never
changes persisted/checksummed/compared/written values.

**[INHERITED]** Comparison is bound to the exact governed regular/base
Channel field; `100 == 100.0 == 100.00`; percentage delta uses unrounded
Decimal internally, `ROUND_HALF_UP` at 2 decimals for display, `<0.01%`
instead of a misleading `0%`; a verified current price of `0` shows
`from 0`, never infinity/NaN; active sale price is separate
`SALE_PRICE_INTERACTION` warning evidence, never the comparison baseline.

## 4. Stock Quantity rules — [INHERITED], unchanged by #10

Blank → `NO_INSTRUCTION`, `IN_STOCK` default signal, never becomes zero or
a write. Canonical zero → `SET` target `0`, `OUT_OF_STOCK` signal. Positive
integer → `SET`, `IN_STOCK` signal. Negative/fractional/malformed →
`INVALID`, row `BLOCKED`. Unmanaged Listing + positive Set → suppressed
with `CHANNEL_CAPABILITY_LIMITATION`, independent Price may still proceed.
Positive Quantity is suppressed (not written, not badge-directional) when
final status is `OUT_OF_STOCK` from another signal; Quantity `0` remains
relevant and may still write. A connector-declared `QTY 0 → OUT_OF_STOCK`
invariant is one-way only — it never proves `IN_STOCK` from a positive
value.

## 5. Stock Status rules and precedence — [FLOWHUB OVERRIDE], expanded signal set

`0` → `OUT_OF_STOCK`; `1`/blank → `IN_STOCK`. Provider publication/visibility
states (`publish`, `draft`, `active`, `private`, …) are never Stock Status.

**[OWNER RULE, changed by #10]** The set of explicit **in-stock** signals
now includes a **usable positive mapped Price** (previously Price was
stock-neutral when valid). Precedence order is unchanged:
**blocker → OUT_OF_STOCK (any valid signal) → IN_STOCK (any valid signal)
→ NO_INSTRUCTION (preserve current)**. A valid positive Price can therefore
now *conflict* with an explicit `OUT_OF_STOCK` from Quantity `0` or Status
`0`; OOS still wins, and `SOURCE_AVAILABILITY_CONFLICT` is emitted as a
non-blocking warning. An unusable mapped Price contributes `OUT_OF_STOCK`
and can also participate in this same conflict logic (see §3).

## 6. Warning and blocker model — [INHERITED], unchanged by #10

Warnings never auto-block. Approved codes:
`LARGE_PRICE_CHANGE`, `PRICE_OUTSIDE_ADVISORY_BAND`, `SALE_PRICE_INTERACTION`,
`LARGE_QUANTITY_CHANGE`, `CHANNEL_CAPABILITY_LIMITATION`,
`SOURCE_AVAILABILITY_CONFLICT`, `channel_cache_not_fresh`. Blockers are
identity/schema/currency/evidence/enforceability failures, plus invalid
Quantity/Stock Status — **never** an unusable mapped Price cell by itself.

## 7. Eligibility and Actionability — [OWNER RULE], unchanged text, still not implemented as a split concept

`ELIGIBLE` = identity resolved, all mapped inputs valid, outcome
deterministic, required capabilities/evidence exist, no hard-policy/safety
blocker. `BLOCKED` = an actual business/safety condition. These are
explicitly **not** the same as **Actionability** (whether a supported
governed field would produce a Manifest operation if selected/verified) —
document #10 repeats the same "must never be collapsed" language as the
prior plan. See the companion audit for the current implementation gap
(CLS-006).

## 8. Auto-selection, Dry Run, Manifest — [INHERITED], unchanged by #10

`ELIGIBLE AND has_actionable_business_change AND no blocker`. Manual
deselection is authoritative for the life of a Preview across
pagination/refetch/remount. Dry Run verifies Price/Quantity/Stock Status
independently against live state; any blocked selected scope blocks the
**entire** Apply Manifest (whole-scope atomicity) — verified siblings
remain evidence only, never partially packaged. Only selected,
live-verified, changed governed fields enter the Manifest; warnings,
eligibility, and neutral badges never do.

## 9. Workspace product and route contract — [OWNER RULE], resolved 2026-08-22 (P0-1 decision)

**[OWNER RULE, superseding both document #10's own wording and the
already-shipped redirect]** The Owner resolved the P0-1 conflict flagged in
the Reconciliation Audit by rejecting all three originally-offered options
(revert, ratify, alias) and specifying a fourth, more precise architecture.
`/products` and `/workspace` are **two separate product surfaces with two
separate business responsibilities**, not one canonical UI reused two ways:

### `/products` — Manual Channel Editor

- The Owner directly edits Channel data when the Channel and permissions
  allow it: Price, Stock QTY, Stock Status, Name, SKU, Description, and
  other supported editable Channel fields.
- **Does not** run Workspace business rules: no Source comparison, no
  price-to-stock precedence, no auto-selection, no Workspace
  warnings/blockers, no Dry Run, no Workspace Manifest.
- An explicit Owner edit to a supported field must not be blocked merely
  because Workspace policy would have made a different automated decision.
- Still subject to normal technical/security controls: authentication,
  permissions, connector capability, provider validation, safe write
  execution, verification/audit.

### `/workspace` — Automated Source-to-Channel Pricing Reconciliation

- Combines Source desired state + cached/observed Channel state + the
  Owner-approved Workspace business rules (§§1–8 of this document).
- Runs the full pipeline: Normalize → Preview → Auto-selection → Review →
  Dry Run → Verified Write Set → Apply Manifest → Apply → Verify →
  Audit/Reconcile.
- This is where every rule in §§1–8 of this document (identity matching,
  four Change Badge dimensions, Price/Quantity/Stock Status normalization
  and precedence, warnings/blockers, eligibility/actionability,
  auto-selection, Dry Run, Manifest) applies. None of §§1–8 apply to
  `/products`.

### Shared infrastructure (not shared UI, not shared business responsibility)

`/products` and `/workspace` **may** share: Channel Listings, Channel
cache/current-state data, connectors, identity resolution, permissions,
write pipeline primitives, verification, and audit/reconciliation
infrastructure. They **must not** collapse into one product UI or one
business responsibility.

### Explicit exclusions (Owner-stated, verbatim intent preserved)

- No bare redirect `/workspace` → `/products`.
- `/workspace` must not simply render the `/products` component.
- No resurrection of the deleted legacy Workspace implementation
  (`app/flowhub/api/v2/workspace.py`, `price_workflow.py`, the old
  `Workspace.tsx`/`ApiWorkspaceService`) — the canonical Workspace surface
  is to be designed/reconstructed on top of current FlowHub primitives,
  not restored from the deleted code.
- No second competing business engine — the automated reconciliation logic
  that currently lives in `app/flowhub/unified_workspace/*` and is
  currently invoked from `/products` is the one canonical engine; it moves
  to (or is reachable from) `/workspace`, it is not duplicated.

See the Reconciliation Audit (R-1, now RESOLVED) and the Correction Plan
(P0-1, now the execution plan) for how this reconciles against the
current, as-shipped code, where `/products`
(`DensePricingWorkspace.tsx`) currently runs *both* manual editing *and*
the full Workspace automation pipeline in one surface.

## 10. Parent/variation-dependent write behavior — REQUIRES_OWNER_DECISION is not needed; this is NOT_APPLICABLE for the current scope

Both the non-"OWNER_UPDATED" plan and document #10 state, verbatim and
unchanged (§15/§22 in both): *"A future Phase C dependent-parent operation
would require a separate explicit contract and is outside this plan"* and
list it under "Approved scope boundary" as excluded ("does not define
Phase C parent-dependent operations"). Every variation is matched,
normalized, compared, and Manifest-represented **independently**; no
badge or operation is ever copied parent↔child or sibling↔sibling.

**Disposition: NOT_APPLICABLE to this reconciliation.** WooPrice reference
material (documents #1–8) was reviewed for parent/dependency write
semantics and contains no contradicting instruction that document #10
overrides — both the WooPrice-era and Owner-updated FlowHub plans agree
this is explicitly out of scope, deferred to a not-yet-specified Phase C.
No Owner decision is being requested here; one would only become relevant
if/when Phase C is scoped.

## 11. Explicitly not decided by this document

- Whether `/workspace` becomes a rebuilt first-class UI, a navigation
  alias that renders the identical canonical component, or the Owner
  instead amends OD-004/document #10 to ratify the already-shipped
  redirect. See Correction Plan P0-1.
- Timing/priority for CLS-006 (eligible/actionable split) and CLS-013
  (float→Decimal write-path migration) — both remain technically
  deferred-with-documented-reasoning, not silently dropped.
