# FlowHub Workspace Reconciliation Audit — 2026-08-22

Status: Audit output. Read-only analysis document. Does not authorize
implementation, commit, push, merge, or deployment.

Reviewed against `origin/main` = `1f04c90` (verified via `git status`,
`git log --oneline -5`, `git log --oneline -1 origin/main` at review time;
working tree clean, no local commits ahead/behind). Findings are not
softened for convenience; several conclude the *current shipped code is
correct and the earlier "CONTINUE"/audit-trigger framing was based on a
stale premise*, and one concludes the opposite — that shipped code
contradicts an explicit, repeated Owner rule.

Legend: **Wrong?** = does the current FlowHub implementation need to
change to match the Owner rule. YES / NO / PARTIAL / N/A.

---

## R-1 — Workspace route/product architecture — **P0 — RESOLVED 2026-08-22 by explicit Owner decision**

**Owner decision (superseding the three options this audit originally
offered):** `/products` and `/workspace` are two separate product
surfaces with two separate business responsibilities — not a shared UI, not
an alias, not a redirect, not a restoration of the deleted legacy engine.
`/products` = Manual Channel Editor (no Workspace automation). `/workspace`
= Automated Source-to-Channel Pricing Reconciliation (the full existing
Normalize→Preview→Auto-selection→Review→Dry Run→Verified Write
Set→Apply Manifest→Apply→Verify→Audit/Reconcile pipeline). Full rule text
recorded in `WORKSPACE_CANONICAL_OWNER_SPEC_2026-08-22.md` §9.

**Follow-up investigation (this turn) into how this reconciles against
current code:**

- `frontend/src/pages/Products.tsx:116-153` bootstraps via
  `unifiedWorkspace.createCatalog`/`getWorkspace`
  (`ApiUnifiedWorkspaceService.createCatalog` → `POST
  /api/v2/unified-workspaces/manual`) and renders
  `DensePricingWorkspace.tsx`, whose Save/Apply chain
  (`saveAndReview()`→`apply()`, lines 317/386) drives the full
  `unified_workspace` Draft→Review→Dry-Run→Apply-Manifest cycle
  (`saveDraft`/`createReview`/`saveSelection`/`runDryRun`/`applySelected`,
  `ApiUnifiedWorkspaceService.ts:42-72` → `app/flowhub/api/v2/unified_workspace.py:302,350,376,390,412`).
  **`/products` today runs the exact automation pipeline the Owner's
  decision says it must not run.** This confirms R-1 was correctly
  diagnosed as a real architectural defect, not merely a routing
  cosmetic — the coupling is deep (shared component, shared backend
  calls), not just a redirect.
- Separately, `app/flowhub/api/v2/products.py` already exposes
  `channel-price-operations` / `channel-prices/validate` /
  `channel-prices/dry-run` / `approve` / `apply` endpoints, backed by
  `app/flowhub/product_pricing/service.py`'s `ProductPricingService`
  (`load`→`validate`→`dry_run`→`approve`→`apply`, service.py:84-205+).
  This service is **self-contained and independent of
  `unified_workspace`'s Draft/Review/Manifest objects** — it has its own
  stale-token/version-conflict check, its own connector-capability check
  (`CHANNEL_CAPABILITY` via `default_marketplace_registry()`), and its own
  audit trail (`_audit`, service.py:624), then dispatches through
  `WritePipelineService.execute_product_pricing_item` (service.py:205) →
  `execute_workspace` (write_pipeline/service.py:514) — the same low-level
  dispatch/verify engine `unified_workspace`'s Apply also calls
  (`unified_workspace/services.py:2937,3113`), but reached by direct
  in-process method call, not through Draft/Review/Manifest ceremony.
- `frontend/src/services/products/ApiProductService.ts` already implements
  typed client methods for all of the above
  (`getChannelPrices`/`validateChannelPrices`/`createChannelPriceDryRun`/
  `approveChannelPriceOperation`/`applyChannelPriceOperation`) and is
  registered as `services.products` in `App.tsx:56` — but **no frontend
  page currently calls any of these methods**; `Products.tsx` only uses
  `services.products.getCategories`/`getProducts` as a read-only listing
  fallback. Confirmed via full-repo grep: the only references to these
  client methods are the service file itself and its own test.

**Reclassified disposition: this is not a from-scratch build.** The
backend safety machinery for a genuinely separate, no-Workspace-ceremony
manual write path (permission check, connector-capability check, provider
validation, execute, verify, audit) **already exists, is already
Owner-decision-compliant in shape, and is currently orphaned** rather than
missing. The remaining work is: (1) detach `Products.tsx`/
`DensePricingWorkspace.tsx` from `unified_workspace` entirely, (2) build a
new Manual Channel Editor frontend against the existing
`ApiProductService` methods, (3) give `/workspace` its own real page that
owns the automation pipeline (today embedded inside
`DensePricingWorkspace.tsx`) without collapsing into `/products`'s new
component and without resurrecting the deleted
`app/flowhub/api/v2/workspace.py`/`price_workflow.py`/old `Workspace.tsx`
stack. See Correction Plan P0-1 for the phased execution plan.

The original three-option framing below is retained for the audit trail
but is **superseded** by the Owner's decision above; none of A/B/C was
selected.

| | |
|---|---|
| WooPrice reference | Silent on FlowHub's route topology (WooPrice is a spreadsheet-workflow spec, not a FlowHub routing spec). |
| Assistant-generated plan (old, non-"OWNER_UPDATED") | No route contract section at all — §18.1 merely notes `/products` as "the active canonical UI route" as an observed fact, not a decision. |
| Assistant-generated plan (#10, Owner-updated) | Explicit **"Workspace product and route contract"**: `/workspace` must remain first-class, must not be reduced to a generic redirect that erases the Workspace concept; `/products` may reuse the same engine but must not become a second competing engine. |
| Owner's direct chat instructions (this session, "CONTINUE" message) | Explicitly states: *"Owner explicitly rejected solving Workspace by simply turning it into `/products` or removing the Workspace product concept."* Same framing repeated in the "DO NOT STOP" message. |
| Current FlowHub implementation | `frontend/src/App.tsx`'s `LegacyWorkspaceRedirect()` sends `/workspace` straight to `/products`. The backend router `app/flowhub/api/v2/workspace.py`, its service `price_workflow.py`, the frontend page `Workspace.tsx`, and its dedicated client (`ApiWorkspaceService`) are **deleted** (PR #20, `3bc6dd2`/`e16e7e9`). There is no first-class `/workspace` UI or engine left — `/products` is the sole reachable Pricing Workspace surface. |
| Current governance docs | `WORKSPACE_OWNER_DECISIONS.md` OD-004 records this removal as an **approved** decision ("Update:" paragraph) and `WORKSPACE_GAP_ANALYSIS.md` CLS-015 records it "Resolved." Both were written *by the assistant during this same engagement*, not confirmed against a document like #10 that didn't exist yet at the time. |
| Current tests | `frontend/src/pages/layoutRules.test.ts` no longer lists `Workspace.tsx` as a primary page; 14 frontend test files had their empty `workspace: {}` service-registration entries removed; no test currently asserts a first-class `/workspace` UI exists. |
| Correct canonical result | Per document #10 and the Owner's own repeated chat instruction, `/workspace` must not be a bare redirect. **This is a direct, dated, explicit contradiction between an Owner-approved planning document and Owner-approved-looking repository governance text that was written earlier in the same engagement, before document #10 existed.** |
| Severity | **P0** — this is an architecture-level contradiction, not a classification bug, and it is already shipped to `origin/main`. |
| Affected files (if reverted) | `app/flowhub/app.py`, a restored `app/flowhub/api/v2/workspace.py` + `price_workflow.py` (or a new first-class `/workspace` entry that reuses `DensePricingWorkspace.tsx`), `frontend/src/App.tsx`, routing/navigation labels, `WORKSPACE_OWNER_DECISIONS.md` OD-004, `WORKSPACE_GAP_ANALYSIS.md` CLS-015/WS-001. |

**Status: RESOLVED by explicit Owner decision, 2026-08-22.** The Owner
rejected all three originally-offered options and specified the
Products/Workspace split above. See Correction Plan item P0-1 for the
phased execution plan now in force.

---

## R-2 — Malformed/arbitrary mapped Price → OOS, not blocked — **P2 (informational) — WRONG: NO, already correct**

| | |
|---|---|
| WooPrice reference / old plan | `WORKSPACE_PHASE_B_CHANGE_BADGES_PLAN.md` (non-"OWNER_UPDATED") Table B: *"Malformed numeric or unsupported notation → `INVALID` → none → `NOT_EVALUATED` → `BLOCKED`"*; §5.1: *"everything else: invalid and blocked."* |
| Assistant plan #10 (Owner-updated) | Table B: arbitrary text (`hello`), malformed numeric (`10O000`), negative, non-finite → `UNAVAILABLE`, `OUT_OF_STOCK` signal, **not** a blocker, warning `UNUSABLE_MAPPED_PRICE`. |
| Current FlowHub implementation | `app/flowhub/unified_workspace/domain.py:259-274,290-298` — `normalize_direct_price()` returns `SourceInstruction.UNUSABLE`, `AvailabilitySignal.OUT_OF_STOCK`, `warning_code="UNUSABLE_MAPPED_PRICE"`, `blocker_code=None` for exactly this input class, including the RIAL/TOMAN fractional case. |
| Current tests | `tests/flowhub/unified_workspace/test_domain.py::test_direct_mapped_unusable_price_is_an_oos_instruction_not_a_blocker`, parametrized over `None`/`"0.00"`/`"x"`/`"hello"`/`"10O000"`, asserts exactly this contract; `test_rial_zero_decimal_fix_and_strict_mode_are_exact` covers the RIAL fraction case. |
| Correct canonical result | Document #10's rule. |
| Wrong? | **NO.** Current code already implements document #10's rule precisely, including the arbitrary-text and malformed-numeric-text cases that the *earlier, non-Owner-updated* plan pasted in a prior turn got wrong (and which this assistant flagged as a contradiction before the Owner supplied document #10). Supplying document #10 resolves that earlier-flagged contradiction — it was a document-version mismatch, not an implementation defect. |
| Action needed | None. This is the one item the original "CONTINUE"/"DO NOT STOP" escalations assumed was still broken; it is not. |

---

## R-3 — RIAL/TOMAN `Fix zero-decimal prices` persistence — **P3 — WRONG: PARTIAL / UNVERIFIED**

| | |
|---|---|
| Document #10 | "must be persisted/configurable, not a transient UI-only switch." |
| Current implementation | `normalize_direct_price(fix_zero_decimal_prices=...)` reads from `channel_policy.get("fix_zero_decimal_prices")` in `app/flowhub/source_workspace/service.py:5137`, which in turn is read from a `policy` dict at lines 4371-4382 — this is backend-persisted, not a request-transient value. |
| Gap | This audit did **not** trace the setting to an Owner-facing settings UI control (page/form) to confirm an Owner can actually view/toggle it, only that the backend contract supports persistence. Not verified either way within this audit's budget. |
| Wrong? | Backend: **NO**. Frontend Owner-facing control: **UNVERIFIED** — flagged for the Correction Plan, not asserted as broken. |

---

## R-4 — Global thousands-grouping presentation — **P2 — WRONG: PARTIAL**

| | |
|---|---|
| Document #10 | "everywhere the shared financial formatter is used, including Workspace Preview/grid, badges, Review, Dry Run, Apply confirmation, and other Owner-facing financial views." |
| Current implementation / gap analysis | `WORKSPACE_GAP_ANALYSIS.md` CLS-011 (P2): grid `TargetInput` now formatted (`06523f5`); `ChangeBadges` price/quantity text is `dir="ltr"`-isolated (`80b58b5`). `Dashboard.tsx`'s USD `$`-prefix format intentionally bypasses the shared formatter (documented Figma-pixel-faithful exception) with a documented `number`-precision caveat. Review dialog, Dry Run confirmation, and Apply confirmation screens were **not individually re-verified** against the shared formatter in this or the prior pass. |
| Wrong? | **PARTIAL.** Grid and badges: correct. Dashboard: intentional, documented exception (not a defect). Review/Dry Run/Apply confirmation: open, unverified — carried forward from the existing CLS-011 disposition, not newly discovered. |

---

## R-5 — Eligibility/Actionability split (backend) — **P2 — WRONG: YES (still open, deliberately deferred)**

| | |
|---|---|
| Document #10 | Actionability "must never be collapsed" into Eligibility (Axis table, §4) — unchanged text from the prior plan version. |
| Current implementation | `WORKSPACE_GAP_ANALYSIS.md` CLS-006: `ReviewItem.eligible` still conflates row safety with actionability by design; the frontend works around it via `validationState` (CLS-005, resolved) rather than the backend exposing a first-class `actionable` field. Disposition recorded as "Deferred — Owner decision on scope/timing recommended," touching ~8 call sites in `services.py` including Apply-selection gating. |
| Wrong? | **YES**, in the sense that the backend model still does not literally separate the two concepts as document #10 requires — but this is a known, previously-disclosed, deliberately-deferred gap, not a newly discovered defect, and not something this audit implements per the explicit "do not implement" instruction. |
| Action needed | Owner disposition: implement now (Correction Plan P2-1 gives the concrete plan) or explicitly re-affirm the deferral. |

---

## R-6 — Float types remaining in the live write-path wire boundary — **P2/P3 — WRONG: YES (still open, deliberately deferred)**

| | |
|---|---|
| Document #10 | "No binary float may cross into Source normalization, business classification, DTO/Review/Manifest evidence, warning calculation, comparison, or governed write intent." (unchanged from the prior plan version). |
| Current implementation | `WORKSPACE_GAP_ANALYSIS.md` CLS-013: `WorkspaceWriteIntent` (`write_pipeline/workspace_contracts.py`), `ChannelProduct`/`ChannelProductUpdate` (`channels/contracts.py`), `WriteItemContract` (`write_pipeline/adapters.py`) still type price/stock as `float`; the WooCommerce REST client formats with `.2f` after a float boundary. `app/connectors/common/current_state.py`'s `canonical_decimal()` re-normalizes the float boundary back to Decimal for comparison purposes, using Python's exact-for-realistic-magnitudes float repr. |
| Wrong? | **YES** against the letter of the invariant, **NO practical/observed defect** at realistic RIAL/TOMAN/USD price magnitudes (previously investigated and documented, not newly found here). |
| Action needed | Same disposition as R-5: Owner call on priority/timing; Correction Plan P2-2 gives the concrete plan; a full migration touches the live Apply write boundary across ~4 files and needs its own dedicated, carefully-tested pass, not an incidental fix bundled into this reconciliation. |

---

## R-7 — Internal consistency of document #10 itself — **PASS**

Unlike the non-"OWNER_UPDATED" plan pasted in a prior turn (which contained
a self-contradiction between its own "CURRENT OWNER PRICE RULE" framing and
its pasted Table B), document #10 was checked end-to-end for the same class
of defect: every occurrence of the malformed/arbitrary-price rule (§2 approved
rules, §5.1, §8.1, §8.4, Table B, Table C, Table G, Table H, §20 required
tests, §21 acceptance criterion 6, §22 open questions) consistently states
`UNAVAILABLE`/`OUT_OF_STOCK`/not-a-blocker. No internal contradiction was
found on this axis. The Workspace route contract (new in #10) does not
contradict anything else *within* #10 — its only conflict is external, with
already-shipped `main` (R-1).

---

## R-8 — Parent/variation-dependent write behavior — **N/A**

Both plan versions state, identically, that Phase C dependent-parent
operations are out of scope and require a separate future contract (§15,
§22, "Approved scope boundary"). No WooPrice reference material contradicts
this. **Disposition: NOT_APPLICABLE — no Owner decision requested here.**
See canonical spec §10.

---

## Summary counts

| Severity | Count | IDs |
|---|---:|---|
| P0 | 1 | R-1 |
| P1 | 0 | — |
| P2 | 3 | R-4, R-5, R-6 |
| P3 | 1 | R-3 |
| N/A / informational | 2 | R-2, R-7, R-8 |

**Contradictions requiring an Owner decision before any implementation:**
0 remaining — R-1 was resolved by explicit Owner decision on 2026-08-22
(Products/Workspace split; see above). Implementation of R-1's execution
plan (Correction Plan P0-1) may now proceed.

**Current implementation confirmed already correct against document #10:**
R-2 (the specific rule the original escalation assumed was still broken).

**Current implementation confirmed still open, with pre-existing documented
reasoning, not newly discovered:** R-4, R-5, R-6, R-3.
