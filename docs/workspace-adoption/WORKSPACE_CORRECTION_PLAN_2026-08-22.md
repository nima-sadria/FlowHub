# FlowHub Workspace Correction Plan — 2026-08-22

Status: P0-1 (Workspace route/product architecture) received an explicit
Owner decision on 2026-08-22 — see the Reconciliation Audit R-1 and
Canonical Spec §9. That decision authorizes implementation of P0-1's
phased plan below.

P0-1 progress: **Phase 1 complete** (`/workspace` renders the real
automated-reconciliation engine, PR #22, merged to `main` at `4b39611`).
**Phase 2 complete** (`/products` rebuilt as the Manual Channel Editor
against the existing `ProductPricingService`/`ApiProductService` backend,
fully detached from `unified_workspace`/`DensePricingWorkspace.tsx`).
Phase 2 also surfaced a scope correction: `ProductPricingService` only
ever covered **Price**, for exactly 3 hardcoded channels
(`woocommerce:primary`/`snappshop:main`/`tapsishop:main`) — not the full
Owner field list (Stock QTY, Stock Status, Name, SKU, Description) and not
a general, configured-channel-driven registry. The new `/products` is
honest about this: it only exposes editing for fields the backend can
actually write, and does not claim broader coverage. Extending backend
field/channel coverage is tracked as new item **P1-1** below (promoted
from a P2-implied assumption once the real gap was discovered).
Phase 3 (delete the dead Handsontable `/workspace/:workspaceId` surface)
and Phase 4 (docs/permissions/e2e) remain outstanding. P2 items (P2-1
through P2-4) remain planning-only pending Owner priority/timing
confirmation, as originally scoped.

**e2e note (found during Phase 1/2 verification, 2026-08-22):** the CI
`frontend` job only runs the `@browser-benchmark`-tagged e2e test by
default; the broader Playwright suite (`e2e/source-centric-workspace.spec.ts`,
`e2e/source-channel-ordering.spec.ts`, `e2e/unified-workspace-apply-visual.spec.ts`,
`e2e/unified-workspace-performance.spec.ts`) is not CI-gated. All four
files contained stale `page.goto('/workspace/<id>')` navigations that
depended on the now-removed `LegacyWorkspaceRedirect` bounce to
`/products?workspace=<id>`; these were updated to navigate directly to
`/workspace?workspace=<id>`, matching the real Phase 1 page, and the
CI-gating `@browser-benchmark` test plus 4 other previously-broken-by-this-
work tests were verified passing locally after the fix. Beyond that,
**8 pre-existing failures were found and confirmed unrelated to this
work** via direct comparison against `origin/main` at `1f04c90` (the
commit immediately before this entire reconciliation engagement began,
reproduced in an isolated `git worktree`):
- 5 tests across `source-centric-workspace.spec.ts` (2) and
  `unified-workspace-apply-visual.spec.ts` (3) fail on
  `getByRole('dialog'/'heading', { name: 'Review Changes' })` never
  appearing after a Save click — reproduced identically at `1f04c90`,
  before any Products/Workspace work in this engagement.
- 1 test (`source-centric-workspace.spec.ts`) expects a Source
  configuration tab literally named "Worksheet rules"; the live page
  renders "Worksheet discovery" and "Choose participating worksheets"
  instead — a stale label, unrelated to routing.
- 2 tests (`source-channel-ordering.spec.ts`) fail on a Channel
  "connected" resource-section grouping assertion, at a point in the test
  before any Workspace/Products navigation occurs.

None of these were introduced by this reconciliation; left untouched as
genuinely out of scope, consistent with this project's existing practice
of investigating and disclosing pre-existing failures rather than masking
or silently fixing them inline (see `WORKSPACE_GAP_ANALYSIS.md`'s
pre-existing-failures section for the same pattern applied to the backend
suite). Recommend a dedicated e2e-suite maintenance pass, separate from
Workspace/Products architecture work.

Based on `WORKSPACE_RECONCILIATION_AUDIT_2026-08-22.md`.

---

## P0 — Owner decision received 2026-08-22; execution plan below

### P0-1: Build the Products/Workspace split (R-1) — RESOLVED, now executable

**Owner decision (2026-08-22, verbatim intent):** `/products` = Manual
Channel Editor, no Workspace automation. `/workspace` = the full automated
Source-to-Channel reconciliation pipeline. Separate UI, separate business
responsibility; shared low-level infrastructure only (Channel Listings,
cache, connectors, identity resolution, permissions, write pipeline
primitives, verification, audit). No redirect, no alias, no legacy
resurrection.

**Grounding investigation (this turn) found the backend foundation for
`/products` already exists and is already shaped correctly** — this is not
a from-scratch build. Concretely:

| Concern | Current state | What's needed |
|---|---|---|
| `/products` manual-write backend | `app/flowhub/api/v2/products.py` (`channel-price-operations`, `channel-prices/validate`, `channel-prices/dry-run`, `.../approve`, `.../apply`) + `app/flowhub/product_pricing/service.py`'s `ProductPricingService` already implement permission → capability → provider-validation → execute → verify → audit for a single product's Channel fields, fully independent of `unified_workspace`. Dispatches through `WritePipelineService.execute_product_pricing_item` → the same `execute_workspace` low-level engine `unified_workspace` also uses (shared infrastructure, not shared business logic — consistent with the Owner's rule). | Confirm field coverage: today's service is scoped to Channel *price* operations (`ProductPriceOperation`/items) — verify/extend it to cover Stock QTY, Stock Status, Name, SKU, Description per the Owner's explicit field list, or confirm those already exist under a different method name. |
| `/products` frontend client | `frontend/src/services/products/ApiProductService.ts` already implements typed methods for all of the above and is registered as `services.products` (`App.tsx:56`). | Nothing — reuse as-is. |
| `/products` frontend page | `frontend/src/pages/Products.tsx` currently bootstraps `unified_workspace` (`createCatalog`/`getWorkspace`) and renders `DensePricingWorkspace.tsx`, whose Save/Apply drives the full Draft→Review→Dry-Run→Manifest cycle. | **Replace.** Build a new manual-editor view (new component, or a substantially stripped page — see Step 2 below) that lists products/Channel listings via `ApiProductService.getProducts`/`getChannelPrices` and edits/writes via `validateChannelPrices`→`createChannelPriceDryRun`→`approveChannelPriceOperation`→`applyChannelPriceOperation`. No `GroupedProduct`/Source-comparison concepts, no auto-selection, no Workspace warnings/blockers, no `ChangeBadges`. |
| `/workspace` automation engine | Already fully implemented — it's exactly what `DensePricingWorkspace.tsx` + `unified_workspace` backend do today (Preview, auto-selection, `ChangeBadges`, `ReviewDialog`, `DryRunStatus`, `ApplyResults`, Apply Manifest). | **Relocate, don't rebuild.** Mount this existing component/pipeline at a real `/workspace` route (new page wrapper analogous to today's `Products.tsx`, but without the manual-edit framing), keep `commitEdit`-style inline `TargetInput` editing (that's overriding a *Preview target* pre-Dry-Run, which is Workspace-internal review UX, not "manual Channel editing" in the Products sense — no reclassification needed there). |
| Dead Handsontable `UnifiedWorkspace.tsx` at `/workspace/:workspaceId` | Confirmed dead (OD-004): `entryPoint` always resolves to `'manual'`/`'source'`, both redirect to `/products` before the grid renders. Predates the Change-Badge/Dry-Run/Manifest engine — does not implement current business rules at all. | **Delete**, along with its route, as part of this work. It is not "the deleted legacy Workspace implementation" the Owner said not to resurrect (that refers to the already-deleted `api/v2/workspace.py`/`price_workflow.py`/old `Workspace.tsx`), but it is equally not "the correct current FlowHub primitives" to reconstruct on top of — reconstructing on it would mean building on dead, pre-badge-engine code, which contradicts the Owner's explicit instruction. Its route (`/workspace/:workspaceId`) and controller hook (`useUnifiedWorkspaceController`) should be removed once `/workspace` has its real replacement; not before. |

**Phased build order (each phase independently mergeable, matching this
session's established pattern of one PR per coherent scope boundary):**

1. **Phase 1 — `/workspace` gets the real engine.** Add a new page
   (e.g. `frontend/src/pages/Workspace.tsx`, name TBD to avoid colliding
   with the deleted file's old identity) that mounts the *same*
   `DensePricingWorkspace.tsx` automation component, wired the same way
   `Products.tsx` wires it today (`unifiedWorkspace.createCatalog`/
   `getWorkspace`). Route it at `/workspace` in `App.tsx`, replacing
   `LegacyWorkspaceRedirect`. At the end of this phase, `/workspace` is a
   real, working automated-reconciliation surface and `/products` is
   unchanged (still also running the same engine) — an intentional,
   short-lived duplication resolved by Phase 2, not a final state.
2. **Phase 2 — `/products` becomes the Manual Channel Editor.** Build the
   new manual-edit UI against `ApiProductService`, detach `Products.tsx`
   from `unified_workspace`/`DensePricingWorkspace.tsx` entirely. Verify
   field coverage per the table above; extend `ProductPricingService` if
   Stock QTY/Status/Name/SKU/Description aren't already covered by an
   existing method.
3. **Phase 3 — remove the dead Handsontable surface.** Delete
   `frontend/src/pages/UnifiedWorkspace.tsx`, its route
   (`/workspace/:workspaceId`), `useUnifiedWorkspaceController` and other
   now-orphaned support modules under `frontend/src/features/unifiedWorkspace/`
   (verify nothing else references them first), and their dedicated tests.
4. **Phase 4 — docs, permissions, i18n, e2e.** Update
   `WORKSPACE_OWNER_DECISIONS.md` OD-004 (correct the "Update:" paragraph
   to describe the real split instead of the redirect),
   `WORKSPACE_GAP_ANALYSIS.md` CLS-015/WS-001 (reflect the new state),
   `WORKSPACE_IMPLEMENTATION_PHASES.md` Phase 3. Confirm
   `WORKSPACE_PERMISSION`/`can_fetch` gating is correct per-route (Products
   vs. Workspace may warrant distinct permission checks now that they are
   functionally different — audit `RequirePermission` usage in `App.tsx`
   for both routes). Update/replace `frontend/e2e/pricing-workflow-redesign.spec.ts`
   and `source-centric-workspace.spec.ts` if they assume the old combined
   `/products` behavior. Update navigation labels so the two entries read
   distinctly ("Products" vs. "Workspace"/"Pricing Reconciliation").

**Sequencing note:** Phase 1 and Phase 2 together are the atomic
"reconciliation complete" milestone — shipping only Phase 1 leaves
`/products` still running Workspace automation, which is the exact defect
being corrected, so both should land before this item is considered
resolved, even if delivered as separate commits/PRs for reviewability.
Phase 3/4 can follow.

---

## P1 — discovered during P0-1 Phase 2 implementation

### P1-1: Extend the Manual Channel Editor backend beyond Price/3 channels

**Discovered, not yet implemented.** The Owner's field list for `/products`
is Price, Stock QTY, Stock Status, Name, SKU, Description, "other
supported editable Channel fields" — for whatever Channels are actually
configured. `ProductPricingService`
(`app/flowhub/product_pricing/service.py`) and its
`ProductPriceOperation`/`ProductPriceOperationItem` models are built
specifically around a single numeric `price` field (unit/currency
conversion, `.proposed_value: float`, TapsiShop rial-divisible-by-10
validation, etc.) for exactly the 3 channels hardcoded in its `CHANNELS`
tuple. There is no `field` column on the operation-item model — the whole
shape assumes "price" is the only editable concept.

The current `/products` UI (shipped in Phase 2) is truthful about this: it
only renders Price editing for the 3 supported channels and does not
present controls for fields that don't work.

Steps to close the gap:
1. Generalize channel discovery: replace the hardcoded `CHANNELS` tuple
   with the actual configured/enabled Channel registry
   (`IntegrationConnectorInstance` + `default_marketplace_registry()`),
   so any real Channel — not just 3 named ones — is editable.
2. Add Stock QTY and Stock Status as a second and third editable field
   type. These are numeric/enum, not price, so they don't need
   currency/unit conversion but do need their own validation rules
   (non-negative integer QTY; canonical `IN_STOCK`/`OUT_OF_STOCK` status —
   note this is a *different, simpler* rule than the Workspace engine's
   Source-precedence Stock Status logic in
   `unified_workspace/domain.py`; Products has no Source, so there is no
   precedence to compute, only a direct write).
3. Add Name/SKU/Description as text-field edits. These have no numeric
   validation, currency, or stale-token-per-value-magnitude concerns, but
   still need the same stale-conflict/audit ceremony.
4. Decide the data model: either (a) generalize
   `ProductPriceOperation`/`ProductPriceOperationItem` into a
   field-parameterized `ProductChannelFieldOperation`, or (b) introduce
   parallel operation types per field family. Given the existing model's
   validation logic is deeply price-specific (currency/unit, TapsiShop
   divisibility), (a) likely means significant refactoring; (b) risks
   duplicating the dry-run/approve/apply ceremony. This decision needs its
   own design pass, not a decision made inline while implementing.
5. Extend `WritePipelineService.execute_product_pricing_item` (or add a
   sibling method) to dispatch non-price fields through the same
   `execute_workspace` engine with correct per-field payload shaping.
6. Extend `app/flowhub/api/v2/products.py` and `ApiProductService.ts`/
   `services/types.ts` accordingly; extend the `/products` UI to render
   the new fields once the backend supports them.

Risk: **MEDIUM-HIGH** — touches a real write path (channel field writes),
though scoped away from Workspace's automation/precedence logic entirely.
Recommend scoping as its own dedicated pass per field family (QTY/Status
first, since they reuse simpler validation than free-text Name/SKU/
Description), not one large change.

---

## P2 — implementation-ready, pending Owner priority/timing confirmation

### P2-1: Backend Eligibility/Actionability split (R-5 / gap-analysis CLS-006)

Goal: introduce a first-class `actionable` concept distinct from
`ReviewItem.eligible`, without a schema migration (derivable at read time
via `values_equal(field, current_value, target_value)`).

Steps:
1. Audit each of the ~8 `item.eligible`/`item["eligible"]` call sites in
   `app/flowhub/unified_workspace/services.py` and classify which concept
   each one actually needs (row safety vs. "would produce a Manifest
   operation").
2. Add a derived `actionable` boolean alongside `eligible` in the
   classification/read-model output (`_change_badge_shape` and the
   `ReviewItem`/Review-shape serialization), without altering
   `ReviewItem.eligible`'s existing meaning where it gates Apply-selection
   safety (`select_review_items`, `apply_selected`).
3. Update the frontend `ReviewScopePresentation`/`ChangeBadges` consumers
   that currently work around this via `validationState` (CLS-005) to
   consume the new explicit field once available, without changing
   observed badge behavior (this is a refactor of the data path underneath
   already-correct UI, not a UI behavior change).
4. Add parameterized backend tests pinning `eligible` vs `actionable` for:
   unchanged-only rows, warning-only rows, blocked rows, mixed
   actionable+warning rows, and unsupported-optional-field rows (Table I
   in document #10).
5. Re-run the full backend suite plus the specific Apply-selection-gating
   tests to confirm no behavior change at the 8 audited call sites beyond
   the new field's addition.

Risk: **HIGH** per document #10's own risk marker for this class of change
(it touches Apply-selection safety gating). Do not bundle with P0-1 or
P2-2 in the same change.

### P2-2: Float → Decimal migration through the write-pipeline wire boundary (R-6 / CLS-013)

Goal: remove `float` typing from `WorkspaceWriteIntent`
(`app/flowhub/write_pipeline/workspace_contracts.py`),
`ChannelProduct`/`ChannelProductUpdate` (`app/flowhub/channels/contracts.py`),
`WriteItemContract` (`app/flowhub/write_pipeline/adapters.py`), and the
WooCommerce REST client's `.2f` formatting, replacing them with exact
Decimal/canonical-integer text through to the connector boundary.

Steps:
1. Map every read/write site of these four float-typed fields (already
   partially traced in CLS-013's investigation).
2. Change the contract types to `Decimal` or canonical string, one
   contract at a time, verifying each connector's serialization still
   produces byte-identical provider payloads for a representative set of
   RIAL/TOMAN/USD magnitudes (since float is currently exact at realistic
   magnitudes, this should be a no-observable-behavior-change migration —
   prove that with a snapshot/regression test before and after).
3. Update `app/connectors/common/current_state.py`'s `canonical_decimal()`
   call sites once the upstream float boundary is gone (it currently exists
   specifically to re-normalize *because* of the float boundary).
4. Add a regression test asserting no `float(...)` call remains reachable
   between classification (`domain.py`) and connector dispatch for these
   four contracts.

Risk: **HIGH** — touches the live Apply write boundary across ~4 files.
Needs its own dedicated, carefully-tested pass per the existing CLS-013
disposition; do not bundle with P0-1 or P2-1.

### P2-3: Close remaining thousands-grouping presentation gaps (R-4 / CLS-011)

Steps:
1. Audit the Review dialog, Dry Run confirmation, and Apply confirmation
   screens specifically (grid and badges are already confirmed correct)
   for any Owner-facing financial value not routed through the shared
   `formatMoney` formatter.
2. Leave `Dashboard.tsx`'s USD formatting as-is — it is a documented,
   intentional Figma-pixel-faithful exception, not a defect; do not touch
   it as part of this item.
3. Add frontend tests asserting grouped formatting in Review/Dry
   Run/Apply confirmation for a RIAL/TOMAN value and a decimal-currency
   value.

Risk: **LOW/MEDIUM** — presentation-only, no business-logic or write-path
risk.

### P2-4 (verification only, may resolve to "no action"): Confirm `Fix zero-decimal prices` Owner-facing settings path (R-3)

Steps:
1. Trace `channel_policy["fix_zero_decimal_prices"]` back to its source —
   confirm there is an Owner-visible settings control that writes it, and
   that the default is `ON` at that layer too (not just in
   `normalize_direct_price`'s Python default).
2. If no such control exists yet, that becomes a P2 gap with its own scope
   (add the setting to the relevant Channel/Source configuration UI); if
   it already exists, close R-3 as verified-correct in the gap analysis.

Risk: **LOW** — likely a verification-only outcome, but do not assume
either answer without checking.

---

## Tests

- Backend: extend `tests/flowhub/unified_workspace/test_domain.py` and
  `tests/flowhub/source_workspace/test_service.py` with any Table
  D/E/F/G/H rows from document #10 not already covered 1:1 by name (this
  audit confirmed Table B's malformed/arbitrary-price rows and the
  RIAL/TOMAN fix are covered; it did not exhaustively re-verify every row
  of every other table against test names within this budget — treat that
  as an open coverage-audit task, not a confirmed gap).
- Frontend: add coverage per P2-3 above.
- No new test should be needed for P0-1 until an option is chosen, since
  the option itself determines what "correct" routing behavior is.

## Docs

- `WORKSPACE_OWNER_DECISIONS.md` OD-004 and `WORKSPACE_GAP_ANALYSIS.md`
  CLS-015/WS-001: update as part of P0-1 Phase 4, to describe the real
  Products/Workspace split instead of the redirect.
- `WORKSPACE_GAP_ANALYSIS.md` CLS-006/CLS-011/CLS-013: update disposition
  text once P2-1/P2-3/P2-2 are actually implemented (not before).
- `WORKSPACE_IMPLEMENTATION_PHASES.md` Phase 3 "Remaining potential work"
  list: add P0-1's resolution and P2-1..P2-4 explicitly once scheduled.

## Route/UI consolidation

Now scoped and executable per P0-1's four-phase plan above. No other
route/navigation change (beyond what P0-1 itself specifies) should be made
outside that plan.

## Connectors

No connector-level change is required by this reconciliation beyond what
CLS-014 already tracks (SnappShop/TapsiShop/Technolife `write_status=False`
is a documented, intentional scope boundary, unchanged by document #10).

## Owner visual acceptance

Once P0-1 is resolved and any P2 items the Owner prioritizes are
implemented, present a seeded Preview containing document #10 §17's
concrete examples (particularly examples 10-13, which exercise the
Price-as-IN-signal conflict behavior new in this revision) per §12's
acceptance-criteria list, in a non-production environment, per the
existing "Owner acceptance" step already defined in
`WORKSPACE_IMPLEMENTATION_PHASES.md` Phase 5.

---

## Final response summary — this turn's update

1. Current `main` reviewed: `1f04c90` (clean working tree; `origin/main`
   matches local `main`) at the time this correction plan was updated.
2. P0-1 (R-1) status: **RESOLVED by explicit Owner decision, 2026-08-22.**
   The Owner rejected the original A/B/C framing and specified the
   Products/Workspace split recorded in `WORKSPACE_CANONICAL_OWNER_SPEC_2026-08-22.md`
   §9. Contradiction count requiring further Owner decision: **0**.
3. Grounding investigation found the `/products` manual-write backend
   (`ProductPricingService` + `app/flowhub/api/v2/products.py`) already
   exists, already independent of `unified_workspace`, and is currently
   orphaned (no frontend caller) — this substantially de-risks and
   shrinks P0-1's implementation scope versus a from-scratch build.
4. P0-1 execution plan: 4 phases (new `/workspace` page reusing the
   existing automation engine; new `/products` Manual Channel Editor
   against the existing `ApiProductService`; delete the dead Handsontable
   `UnifiedWorkspace.tsx` surface; docs/permissions/i18n/e2e cleanup).
   Phases 1+2 together are the atomic "reconciliation complete" milestone.
5. P1/P2/P3 counts unchanged from the original audit: P1 = 0, P2 = 3
   (R-4, R-5, R-6), P3 = 1 (R-3) — none of these were affected by this
   turn's P0-1 resolution.
6. Code modified this turn: **NO** — this turn updated only the three
   audit/plan documents per the Owner's explicit "update the docs, then
   continue" instruction; P0-1 implementation itself has not yet started.
7. Commits/pushes/merges: **NO** — none since `1f04c90`.
8. Production/deployment touched: **NO**.

Implementation of P0-1 Phase 1 begins next, in a separate step, following
this session's established phased-PR pattern.
