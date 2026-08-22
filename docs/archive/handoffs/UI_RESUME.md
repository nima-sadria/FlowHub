# FlowHub UI continuation handover — Pricing Matrix (Claude UI Stages 1–6)

## Read this first

This document is the **UI-side** companion to Codex's backend `RESUME.md`. It
records the state of the Claude UI work for the Pricing Matrix:

- **Stage 1** (commit `30334ca`) — contract-boundary correction + callable-endpoint
  mapping and client scaffolding.
- **Stage 2** (commit `8ae5424`) — read-only Pricing Matrix surfaces built on the
  callable contract, after merging Codex's PM-1…PM-7 answers from `main`.
- **Stage 3** (commit `001ec5c`) — editable configuration for Policy Revisions,
  Product Group Revisions, and Unit Declarations, on the same callable contract.
- **Stage 4** (commit `7421a93`) — Channel Policy Lifecycle mutations
  (activate/deactivate) with `headVersion` optimistic concurrency and 409
  conflict handling.
- **Stage 5** (commit `5eb5bd6`) — RTL, responsive (mobile/tablet/desktop),
  light/dark theme, and accessibility hardening across all four Pricing pages.
- **Stage 6** — real end-to-end browser verification (frontend + a live local
  backend on this branch's data), full regression, three real defects found
  and fixed, and this merge handover.

- **Do not** treat this file as a backend contract. The callable contract is
  `docs/development/contracts/FRONTEND_CONTRACT.md` under development contracts.
- **Do not** treat `docs/evidence/architecture/PRICING_UI_CONTRACT.md` as callable. It is
  `Proposed` architecture for later phases.

## Worktree and branch state

- Worktree: `C:\Users\nima\Documents\GitHub\FlowHub-Claude-UI` (dedicated, Claude-owned)
- Branch: `claude/ui-phase-1`
- Stage 1 base commit (Phase 1B): `6d91edb`
- **Stage 2 contract sync:** `main` (`6eb5610`, Backend Phase 2A/2B + the
  PM-1…PM-7 answers) was merged into `claude/ui-phase-1` at merge commit
  `e2ec982` (`--no-ff`; the approved Stage 1 commit `30334ca` is preserved as a
  parent — no rebase, no squash). No conflicts.
- Isolated from Codex `main` worktree (`C:\Users\nima\Documents\GitHub\FlowHub`).
- Claude modified **no** backend files, migrations, backend tests, `RESUME.md`,
  or root `docs/development/contracts/FRONTEND_CONTRACT.md`. (Those files appear in the branch only via the
  merge of Codex's own `main` commits.)

## Contract boundary — corrected

Two contracts, two roles:

| Document | Path | Role | Status |
|---|---|---|---|
| `docs/development/contracts/FRONTEND_CONTRACT.md` | repo root | **Authoritative, callable** backend contract (APIs available now) | `v1-draft`, unchanged by Claude |
| `PRICING_UI_CONTRACT.md` | `docs/evidence/architecture/` | **Proposed** architectural contract (future UI + backend exposure, not implemented) | `Proposed` |

**Fix applied in this phase (step 4):** `PRICING_UI_CONTRACT.md` already carried
`Status: Proposed`, but it did **not** state the reciprocal boundary — that
`docs/development/contracts/FRONTEND_CONTRACT.md` is the "available now" contract and that this document's
Source Acquisition, Diagnostics, Workspace Preview, Apply Result,
`allowed_actions`, and `contract_version` mechanism are **not implemented yet**.
A `## Contract Boundary — What Is Callable Today` section was added near the top
of `PRICING_UI_CONTRACT.md`, and an `## Open Questions for Codex` section was
added at the end. `docs/development/contracts/FRONTEND_CONTRACT.md` already declared the boundary from its
side and was left untouched.

## Cross-check: docs/development/contracts/FRONTEND_CONTRACT.md vs PRICING_UI_CONTRACT.md (§ domain vocab, exact monetary, required API views)

For each shape proposed in `PRICING_UI_CONTRACT.md`, whether Codex's callable
contract satisfies it, partially satisfies it, or has not reached it:

| Proposed in PRICING_UI_CONTRACT.md | Callable contract status | Open Q |
|---|---|---|
| Common envelope `{ contract_version, data }` | **Not reached / conflict** — responses are bare objects, no `contract_version`; version string differs (`v1-draft` vs `source-pricing-interface-v1`) | PM-1 |
| Field-naming convention (snake_case throughout) | **Conflict** — callable responses are camelCase, requests snake_case | PM-2 |
| Cursor pagination for growable lists | **Not reached / conflict** — callable lists return `{ items: [...] }`, no cursor | PM-3 |
| Domain State Vocabulary (run/execution/readiness/cell/apply enums) | **Not reached** — callable surface only has `rate_mode`, `round_order`, `round_mode`, channel `status`, `eventKind`, `basisStrategy` | — |
| Exact Monetary Values (`ExactAmount` rational) | **Partial** — config uses integer minor-unit / basis-point fields; `ExactAmount` is for future computed prices | PM-4 |
| Source Detail (readiness dims, `allowed_actions`, `open_signals`, `current_run`) | **Not reached** — no endpoint | — |
| Diagnostics (stages, freshness, cohorts) | **Not reached** — no endpoint | — |
| Schema Drift | **Not reached** — no endpoint | — |
| Workspace Pricing Preview Row | **Not reached** — explicitly not delivered (docs/development/contracts/FRONTEND_CONTRACT.md "Important Frontend Rules") | — |
| Apply Result (projection + write attempts) | **Not reached** — explicitly not delivered | — |
| Unit declaration `unresolved`/`resolved` primitive | **Satisfies** — `GET/PUT /units/{scope}/{scopeReference}` | — |
| `workspace_precondition` composed projection | **Partial** — primitives exist (units + activation), composed per-channel projection does not | PM-7 |
| Channel activation gating (`operation_gate allowed|blocked`) | **Partial** — activate/deactivate lifecycle + head `status` exist; per-channel gate *evidence* projection does not | — |
| Contract-revision / fail-closed mechanism | **Conflict** — callable contract uses a doc + `RESUME.md` change process, not the fail-closed unknown-version/enum handling | PM-1/PM-2/PM-3 |

No conflict above was silently resolved. Each was filed under *Open Questions for
Codex* in `PRICING_UI_CONTRACT.md` (PM-1 … PM-7).

**Resolution (synced from `main` `6eb5610`):** Codex answered all of PM-1 … PM-7
in `docs/development/contracts/FRONTEND_CONTRACT.md` → "Claude UI Phase 1 Decisions". Summary:

- **PM-1** no envelope / `contract_version`; documented shapes authoritative.
- **PM-2 / PM-6** requests `snake_case`, responses `camelCase`; frontend must not normalize.
- **PM-3** lists are complete `{ items: [...] }`, no pagination.
- **PM-4** monetary integers/ids may exceed JS safe range: send as decimal strings
  when needed; responses may still be JSON numbers → render as text/BigInt, never
  `number` math. (Reflected as `ExactInteger` in `types.ts` + `formatExactInteger`.)
- **PM-5** head activation fields nullable when `inactive`; event activation fields
  nullable only for `deactivate`.
- **PM-7** `workspace_precondition` not exposed by the callable API; deferred;
  Review/Apply safety stays server-side.

The `PRICING_UI_CONTRACT.md` Open Questions section is retained as the historical
record; the authoritative answers live in `docs/development/contracts/FRONTEND_CONTRACT.md`.

## Implemented endpoints → frontend types & client (mapped this phase)

Source: `docs/development/contracts/FRONTEND_CONTRACT.md`. Base path `/api/v2/pricing-matrix`. Client:
`frontend/src/features/pricingMatrix/api.ts` (`pricingMatrixApi`); types:
`frontend/src/features/pricingMatrix/types.ts`.

| Route | Method | Request type | Response type | Client method |
|---|---|---|---|---|
| `/policies` | GET | — | `ListResponse<PolicySummary>` | `listPolicies` |
| `/policies/{revisionId}` | GET | — | `PolicyRevision` | `getPolicy` |
| `/policies` | POST | `CreatePolicyRequest` | `PolicyRevision` | `createPolicy` |
| `/product-groups` | GET | — | `ListResponse<ProductGroupRevision>` | `listProductGroups` |
| `/product-groups/{revisionId}` | GET | — | `ProductGroupRevision` | `getProductGroup` |
| `/product-groups` | POST | `CreateProductGroupRequest` | `ProductGroupRevision` | `createProductGroup` |
| `/units/{scope}/{scopeReference}` | GET | — | `UnitDeclaration` (union) | `getUnit` |
| `/units/{scope}/{scopeReference}` | PUT | `PutUnitRequest` | `UnitDeclaration` (union) | `putUnit` |
| `/channels/{channelId}/head` | GET | — | `ChannelPolicyHead` | `getChannelHead` |
| `/channels/{channelId}/lifecycle-events` | GET | — | `ListResponse<LifecycleEvent>` | `listChannelLifecycleEvents` |
| `/channels/{channelId}/activate` | POST | `ActivateRequest` | `ChannelPolicyHead` | `activateChannel` |
| `/channels/{channelId}/deactivate` | POST | `DeactivateRequest` | `ChannelPolicyHead` | `deactivateChannel` |

The client is a thin, lightweight feature-api object (same pattern as
`features/sourceWorkspace/api.ts`), built on `apiFetch` + `authFetch`. Stage 2's
`PricingMatrix` page consumes it directly; it is **not** registered in
`ServiceContext` (deliberate — no app-wide DI change for a read-only surface).

Scaffolding notes / faithfulness:
- Every method maps 1:1 to a documented, implemented route. No mocks, no
  fabricated endpoints, no clients for routes absent from `docs/development/contracts/FRONTEND_CONTRACT.md`.
- `headVersion` and monetary fields are typed as `ExactInteger` (PM-4) and
  rendered only as text via `formatExactInteger` — never through `number` math.
- Nullability follows PM-5; rule response casing follows PM-6.

## Reusable frontend components inventory

Existing pieces the Pricing Matrix UI should reuse (do not re-invent):

- **Layout:** `PageShell` (`fh-page`/`fh-grid-12` container — mandatory for
  primary pages), `AppShell`, `Sidebar`, `Topbar`.
- **Status/feedback:** `Alert` (`success|warning|error|info`), `Badge` (7
  semantic variants + legacy aliases, dot/icon), `DiagnosticStateBadge`
  (evidence → `Badge`, backed by `features/diagnostics/diagnosticPresentation`),
  `Empty`, `ErrorBoundary`.
- **Primitives:** `Icon` / `IconButton`, `KpiCard`, `SecretField`,
  `LocalizedText`, `BrandIcon`/`SourceIcon`.
- **Loading:** `Spinner`, `PageLoading`, `Skeleton`/`SkeletonText`/`SkeletonCard`.
- **Design tokens/classes:** `.fh-card`, `.fh-table`, `.fh-alert`, `.fh-badge`,
  `fh-button-primary`, existing focus / light-dark / RTL tokens in `globals.css`.
- **API & cross-cutting:** `apiFetch` + `ApiError` + `apiErrorMessage`
  (`api/client.ts`), `authFetch` (`api/authFetch.ts`, with secret redaction),
  `ServiceContext`, `ThemeProvider` (light/dark), `DirectionProvider` (LTR/RTL),
  `react-i18next` + `translate()` (EN + FA locale bundles).
- **Status presentation pattern:** `diagnosticPresentation.ts` is the existing
  `DomainStatusPresentation`-style mapping. A Pricing equivalent (label/tone/
  icon per domain enum) should follow it — colors never hardcoded at page level.

## Routes & component boundaries — for what is callable today only

Scoped strictly to the callable endpoints. Stage 1 proposed these boundaries;
**Stage 2 implemented them** as a single consolidated read-only page (see
"UI Stage 2 — delivered" below). Mutations and future evidence surfaces remain
out of scope.

- **Pricing policies (read):** route `/settings/pricing` (guard
  `can_view_settings` / `workspace.read`).
  - `PricingPoliciesPage` → `PolicyList` (`listPolicies`) → `PolicyDetail`
    (`getPolicy`). Read-only browse of immutable revisions.
- **Channel policy lifecycle (read + admin mutations):** embedded panel in the
  existing channel surface (`/channels/:channelId` or CommerceHub channel view).
  - `ChannelPolicyLifecyclePanel` → `getChannelHead` + `listChannelLifecycleEvents`;
    `activate`/`deactivate` behind `workspace.admin`, sending `expected_head_version`
    from the last head and refetching on 409.
- **Unit declaration (read + write):** embedded control in existing Source /
  Channel configuration forms (CommerceHub / SourceConfiguration).
  - `UnitDeclarationField` → `getUnit` / `putUnit`; IRR requires explicit
    `RIAL`/`TOMAN`.
- **Policy / product-group authoring (create):** deferred — `createPolicy` /
  `createProductGroup` clients exist, but authoring UX is Phase 2+.

Explicitly **out of scope today** (await backend per `PRICING_UI_CONTRACT.md`):
pricing preview grid, apply-result views, diagnostics stages, source acquisition,
`allowed_actions` gating, attention-signal surfaces.

## UI Stage 2 — delivered

One coherent read-only page at **`/settings/pricing`** (`RequirePermission
"can_view_settings"`; the API additionally enforces `workspace.read`), presenting
three surfaces driven by a shared selected-policy context:

1. **Pricing policies** — `listPolicies` (summaries) → select → `getPolicy`
   (metadata + rules table).
2. **Channel policy lifecycle** — for each channel a rule targets (derived from
   the policy's rules, so only pricing-matrix endpoints are used): `getChannelHead`
   (status + nullable head fields per PM-5) and `listChannelLifecycleEvents`
   (collapsible timeline).
3. **Unit declarations** — `getUnit('channel', id)` per targeted channel;
   unresolved states are called out explicitly with a warning.

Design & safety properties:
- **Read-only.** No create/edit/delete/activate/deactivate; no preview, dry-run,
  apply, diagnostics, or source-acquisition. Only endpoints in
  `docs/development/contracts/FRONTEND_CONTRACT.md` are called; channel identities are derived from policy
  rules, so no non-contract endpoint is used.
- **String-safe money (PM-4):** all monetary/ID integers render via
  `formatExactInteger` — text only, no `number` arithmetic; `<bdi dir="ltr">`
  isolates IDs/numbers under RTL.
- **Fail-closed:** unknown enum values / malformed shapes raise
  `ContractMismatchError` → a distinct "unsupported response" state instead of
  rendering wrong data.
- **All required states:** loading, empty, permission-denied (403),
  unavailable (transport/5xx, with HTTP status), validation-error (422), and
  contract-mismatch — each with a distinct `data-testid` and presentation.
- **i18n / a11y:** new `pricing` namespace (EN + FA), reuses `PageShell`,
  `Alert`, `Badge`, `Icon`, `Empty`, `Spinner`, `.fh-card`, `.fh-table`; status
  via a `pricing` `DomainPresentation` mapping (no hardcoded page-level colors).

### Files added / changed

Stage 1 (commit `30334ca`): `docs/evidence/architecture/PRICING_UI_CONTRACT.md`,
`frontend/src/features/pricingMatrix/{types,api,index}.ts`, `UI_RESUME.md`.

Stage 2:
- `frontend/src/features/pricingMatrix/types.ts` — synced to PM-4/5/6
  (`ExactInteger`; monetary/head fields).
- `frontend/src/features/pricingMatrix/presentation.ts` — new (formatting, enum
  guards, `DomainPresentation`, validators + `ContractMismatchError`, error
  classification).
- `frontend/src/features/pricingMatrix/presentation.test.ts` — new (unit tests).
- `frontend/src/features/pricingMatrix/index.ts` — re-export presentation.
- `frontend/src/pages/PricingMatrix.tsx` — new (the read-only page).
- `frontend/src/pages/PricingMatrix.test.tsx` — new (surface + state tests).
- `frontend/src/i18n/locales/en/pricing.json`, `.../fa/pricing.json` — new.
- `frontend/src/i18n/index.ts` — registered the `pricing` namespace.
- `frontend/src/App.tsx` — lazy route `/settings/pricing`.
- `UI_RESUME.md` — this update.

`i18n` manifests were left unchanged (they gate FA completeness, which stays
`true`; the new keys have full EN + FA translations).

## Verification (Stage 2)

Run in the `FlowHub-Claude-UI` worktree after `npm ci` (`package-lock.json`
unchanged):

- **Targeted tests** — `vitest run` on `presentation.test.ts` +
  `PricingMatrix.test.tsx`: **28 passed**.
- **TypeScript build** — `npx tsc -b`: **passed** (exit 0).
- **Full frontend unit suite** — `npx vitest run`: **69 files, 512 tests passed**,
  0 failures.
- **Production build** — `npm run build` (`tsc -b` + `vite build`): **passed**;
  `PricingMatrix` emits its own ~20 kB lazy chunk.
- `i18n:validate` not run — its pre-existing non-zero exit (two legacy hardcoded
  strings) is unrelated; the `pricing` namespace has complete EN + FA keys.

## UI Stage 3 — delivered (editable configuration)

Three new editor pages, each creating an **immutable revision** (never editing
in place), on the callable contract only:

1. **Policy Revision editor** (`pages/PricingPolicyEditor.tsx`) —
   `/settings/pricing/policies/new` and
   `/settings/pricing/policies/:revisionId/new-revision` (prefills from
   `getPolicy`, reuses the existing `policy_id`). Full form for name, currency,
   round order, quote-age/count, timezone, and a repeatable rules editor
   (channel from `commerce.getChannels()`, target = channel-default / product /
   product-group-revision from `listProductGroups()`, rate/round/surcharge
   fields). Client validation: exact-integer format (never floating point),
   product_ref XOR product_group_revision_id, duplicate
   `(channel, target)` scope detection — all via
   `features/pricingMatrix/validation.ts`. Submits `POST /policies`.
2. **Product Group Revision editor** (`pages/PricingProductGroupEditor.tsx`) —
   `/settings/pricing/product-groups/new` and
   `/settings/pricing/product-groups/:revisionId/new-revision`. Name + a
   dynamic list of canonical product identifiers (direct identifier-entry —
   see limitation below), duplicate-member detection, reuses the existing
   `product_group_id`. Submits `POST /product-groups`.
3. **Unit Declaration editor** (`pages/PricingUnitEditor.tsx`) —
   `/settings/pricing/units/new`. Scope = **Source or Channel only** (Global
   excluded — see PM-8 below); reference from `commerce.getSources()` /
   `commerce.getChannels()`; currency from a fixed supported list; IRR forces
   an explicit RIAL/TOMAN choice with no default; a non-IRR currency
   auto-fills its matching unit (a fixed enumerated pair, not inference from a
   price value) and unsupported pairs are rejected before submit. Shows the
   current resolved/unresolved state via `GET /units/...` before editing.
   Submits `PUT /units/{scope}/{scopeReference}`.

Shared building blocks (new): `features/pricingMatrix/validation.ts`
(exact-integer format, currency/unit pairs, rule-target/duplicate detection,
member-duplicate detection), `features/pricingMatrix/useDirtyGuard.ts`
(`beforeunload` + confirm-on-cancel, mirrors `SourceConfiguration.tsx`'s
pattern), `features/pricingMatrix/PricingErrorPanel.tsx` (now the single
source of error presentation, reused by the Stage 2 page too).

### Immutable-revision UX

Every editor states explicitly, near the top, that submitting **creates a new
immutable revision** — never an in-place edit. The optional `policy_id` /
`product_group_id` field is disabled and pre-filled (not editable) on the
"create next revision" route, with copy explaining that the backend creates a
new revision reusing that identity. No edit/patch/delete/archive action is
exposed anywhere, matching the callable contract having none.

### Error taxonomy (extended from Stage 2)

`classifyPricingError` / `PRICING_ERROR_PRESENTATION` (in `presentation.ts`)
now distinguish: `unauthenticated` (401), `permission_denied` (403),
`not_found` (404), `stale_state` (409 — shown as "this changed since you
loaded it," never silently retried), `validation_error` (422),
`contract_mismatch` (unknown enum/shape), `unavailable` (5xx/network). Stage
2's `PricingMatrix.tsx` was refactored to use this shared module instead of
its own local copy (behavior-preserving; its 8 tests still pass unchanged).

### Financial safety

Every monetary/version/id integer that could exceed JS safe-integer range
(`rate_value`, `*_minor` fields, `headVersion`, `canonicalFactor`) is typed
`ExactInteger` (`string | number`) and only ever displayed or round-tripped as
text — inputs are validated against `-?(0|[1-9][0-9]*)` and never parsed to
`Number` before submission. No price or currency-conversion arithmetic is
performed client-side anywhere in these editors.

### Duplicate-submit / re-entrancy fix

While building the duplicate-submit-prevention test, found and fixed a real
bug: guarding re-entrant submits with `if (saving) return` (React state) is
insufficient — two synchronous clicks in the same tick both read `saving` as
`false` before the first `setSaving(true)` flushes. All three editors now use
a `useRef` lock (`submitLock.current`) set/cleared synchronously around the
request, which is what the test caught and required.

### Contract limitations documented, not worked around

- **PM-8 (Global unit scope):** no authoritative scope reference exists in the
  current UI for `scope=global`, and `docs/development/contracts/FRONTEND_CONTRACT.md` does not document
  one. The Unit editor offers **Source and Channel only**; Global is not
  guessed at. Filed in `PRICING_UI_CONTRACT.md`.
- **PM-9 (No product lookup API):** `product_ref` (policy rules) and
  `canonical_product_ids` (product groups) have no documented or discoverable
  Pricing-Matrix-scoped search/lookup endpoint. Both editors use **direct
  identifier-entry** (the operator types the canonical id) instead of
  inventing a search API. Filed in `PRICING_UI_CONTRACT.md`.

### Files added / changed (Stage 3)

- `frontend/src/features/pricingMatrix/validation.ts` — new.
- `frontend/src/features/pricingMatrix/validation.test.ts` — new (14 tests).
- `frontend/src/features/pricingMatrix/useDirtyGuard.ts` — new.
- `frontend/src/features/pricingMatrix/PricingErrorPanel.tsx` — new (shared).
- `frontend/src/features/pricingMatrix/presentation.ts` — extended error
  taxonomy (`PricingErrorKind`, `PRICING_ERROR_PRESENTATION`); `types.ts`
  unchanged in Stage 3 (already PM-4/5/6-synced in Stage 2).
- `frontend/src/features/pricingMatrix/index.ts` — re-export `validation.ts`.
- `frontend/src/pages/PricingPolicyEditor.tsx` + `.test.tsx` — new (11 tests).
- `frontend/src/pages/PricingProductGroupEditor.tsx` + `.test.tsx` — new (7 tests).
- `frontend/src/pages/PricingUnitEditor.tsx` + `.test.tsx` — new (9 tests).
- `frontend/src/pages/PricingMatrix.tsx` — refactored to shared error panel;
  added "Create policy revision" / "Create product group revision" / "Declare
  unit" entry points and a `?revision=` param to auto-select a newly created
  policy on return; corrected `readOnlyNote` copy (authoring is now possible).
  Uses `useNavigate`/`useSearchParams`, so its test now wraps in `MemoryRouter`.
- `frontend/src/pages/PricingMatrix.test.tsx` — updated for the `MemoryRouter`
  wrap and corrected `readOnlyNote` text (still 8 tests, all passing).
- `frontend/src/i18n/locales/{en,fa}/pricing.json` — editor + new error-state strings.
- `frontend/src/App.tsx` — 5 new lazy routes, gated `workspace.admin`.
- `docs/evidence/architecture/PRICING_UI_CONTRACT.md` — Open Questions PM-8, PM-9.
- `UI_RESUME.md` — this section.

## Verification (Stage 2 + 3)

Run in the `FlowHub-Claude-UI` worktree (`package-lock.json` unchanged):

- **Targeted Stage 3 tests** — `validation.test.ts` (14) +
  `PricingPolicyEditor.test.tsx` (11) + `PricingProductGroupEditor.test.tsx` (7) +
  `PricingUnitEditor.test.tsx` (9): **41 passed**.
- **TypeScript build** — `npx tsc -b`: **passed** (exit 0).
- **Full frontend unit suite** — `npx vitest run`: **73 files, 553 tests
  passed**, 0 failures (up from 69/512 in Stage 2 — the +4 files/+41 tests are
  exactly the new Stage 3 test files). Stage 2's `PricingMatrix.test.tsx`
  (8 tests) still passes unchanged after the `MemoryRouter` wrap.
- **Production build** — `npm run build` (`tsc -b` + `vite build`): **passed**;
  each new editor page bundles as its own lazy chunk
  (`PricingPolicyEditor` ~18 kB, similarly for the other two).
- `i18n:validate` not run — its pre-existing non-zero exit (two legacy
  hardcoded strings) is unrelated; the `pricing` namespace has complete EN + FA
  keys for every new string.
- Browser verification: **not performed** (out of scope for this stage per
  instruction).

## Verification (Stage 4)

- **Targeted tests** — `PricingMatrix.test.tsx` (now 15 tests: the original
  8 Stage 2/3 tests + 7 new "channel lifecycle actions" tests): **15 passed**.
- **TypeScript build** — `npx tsc -b`: **passed** (exit 0).
- **Full frontend unit suite** — `npx vitest run`: **73 files, 560 tests
  passed**, 0 failures (up from 553 in Stage 3 — the +7 tests are exactly the
  new Stage 4 tests; no file count change since they were added to the
  existing `PricingMatrix.test.tsx`).
- **Production build** — `npm run build`: **passed**.
- Browser verification: **not performed** (excluded per instruction).
- Confirmed before starting: `main` had not advanced the pricing contract
  (`docs/development/contracts/FRONTEND_CONTRACT.md` / `app/flowhub/pricing_matrix/`) since the Stage 2
  sync at `6eb5610` — no merge was needed for this stage.

## UI Stage 4 — delivered (channel policy lifecycle mutations)

Activate/deactivate added directly to the existing Channel Policy Lifecycle
card in `pages/PricingMatrix.tsx` (no new route, no new page — extends the
Stage 2 read-only card in place):

- **Activate:** `POST /channels/{channelId}/activate` with
  `{ policy_revision_id: <the currently selected/viewed policy's own revision
  id>, expected_head_version, reason }`. The policy revision is the one
  already on screen — no separate policy picker was introduced.
- **Deactivate:** `POST /channels/{channelId}/deactivate` with
  `{ expected_head_version, reason }`.
- **`expected_head_version`** is sent **exactly as received** from the last
  `ChannelPolicyHead` fetch (`ExactInteger`, PM-4) — never recomputed or
  incremented client-side.
- **409 (`pricing_policy_head_conflict`) handling:** on conflict the code
  refetches `GET .../head` and `GET .../lifecycle-events` for that channel
  (`refreshChannelEvidence`), shows the existing `stale_state` presentation
  ("This changed since you loaded it… reload before trying again"), and keeps
  the action form open with the reason text intact. **The mutation itself is
  never resubmitted automatically** — the user must review the refreshed Head
  and click Activate/Deactivate again explicitly.
- **Permission gating:** the inline Activate/Deactivate buttons only render
  when `effectiveHasPerm(user, WORKSPACE_PERMISSION.admin)` is true. A
  non-admin viewer still sees the full read-only card (status, head fields,
  lifecycle events) — nothing is hidden beyond the mutation controls. This is
  a UX convenience only; the backend enforces `workspace.admin` independently
  (verified by the distinct-403 test), so client-side gating is not relied on
  for security.
- **Re-entrancy:** a `useRef`-based per-channel lock (`actionSubmitLock`)
  prevents a duplicate POST from two synchronous clicks, matching the
  Stage 3 fix.
- **Form-state preservation:** on any failure (403/404/409/422/5xx/network)
  the reason text and open form are preserved — only a fresh error panel is
  shown via the existing `PricingErrorPanel`.
- **No hardcoded colors / reused presentation:** the Active/Inactive badge
  still uses Stage 2's `channelStatusPresentation` → `Badge` variant; errors
  use the existing `PRICING_ERROR_PRESENTATION` map (unchanged in Stage 4).

### Files changed (Stage 4)

- `frontend/src/pages/PricingMatrix.tsx` — added `ChannelLifecycleActions`,
  extended `ChannelLifecycleCard` with `canAdminister`/`action`/handlers,
  added `channelActions` state, `refreshChannelEvidence`,
  `openChannelAction`/`changeChannelActionReason`/`cancelChannelAction`/
  `submitChannelAction` to the page component.
- `frontend/src/pages/PricingMatrix.test.tsx` — added `AuthContext.Provider`
  wrapping (now required: the page calls `useAuth()` for permission gating)
  and a new "channel lifecycle actions" describe block (7 tests). The
  existing 8 Stage 2/3 tests needed the same `AuthContext.Provider` wrap to
  keep passing — no behavioral change, just the added auth context the page
  now reads.
- `frontend/src/i18n/locales/{en,fa}/pricing.json` — 5 new
  `channels.actions.*` keys (reuses existing `editor.cancel`/`editor.saving`/
  `state.staleState.*`/`state.permissionDenied.*`/`state.unavailable.*` —
  no duplicate error strings were added).

## UI Stage 5 — delivered (RTL, responsive, theme, accessibility)

Since browser verification is excluded, "verification" here means: (1) an
in-code audit of all four Pricing pages against the requirement list, fixing
every real gap found, and (2) jsdom-based automated tests that exercise the
same DOM properties a manual check would (document direction, class presence,
ARIA linkage, focus target) — not visual/pixel review.

### Real gaps found and fixed

- **Responsive grids inconsistent with the rest of the app.** All three
  editors' `fh-form-grid` containers (top-level fields in all three, plus the
  per-rule field grid in the Policy editor) were bare `fh-form-grid` —
  single-column at every breakpoint. Fixed to `fh-form-grid md:grid-cols-2`,
  matching the established convention already used in `CommerceHub.tsx`.
- **Long text could overflow instead of wrap.** The policy-list row (name +
  revision badge) and the channel-lifecycle-card header (channel id + status
  badge) had no `min-w-0`/`break-words` on the text sibling in a
  `justify-between` flex row — a long English or Persian name would not wrap
  and could overflow the row. Fixed both, following the `min-w-0` convention
  already used in `CommerceHub.tsx`.
- **Action bars not wrap-safe.** All three editors' submit/cancel bar, and the
  channel lifecycle action form's Cancel/Confirm row, used bare `flex
  items-center justify-between gap-2` with no `flex-wrap` — on a narrow
  viewport with longer (esp. Persian) button labels this could force
  horizontal overflow instead of wrapping to a second line. Fixed to
  `flex flex-wrap …`, matching the sticky action bar pattern already
  established in `SourceConfiguration.tsx` (`flex flex-wrap items-center
  gap-2`).
- **Inconsistent/missing `aria-describedby`.** Only one field
  (`policy-name`) had a proper `id`/`aria-describedby` pairing from its error
  message back to its own field; every other field across all three editors
  had `aria-invalid` (or nothing at all, in the Unit editor) but no announced
  link to its error text. Fixed every field in all three editors — including
  the two row-level rule errors (`target`/`duplicate`), which are now
  associated with the most relevant control (target-kind select, channel
  select) rather than left floating. The channel lifecycle action form's
  reason field and its error region got the same treatment.
- **No focus management on the lifecycle action reveal.** Opening "Activate"/
  "Deactivate" showed the reason field but never moved focus there, so
  keyboard/screen-reader users had to tab-hunt for it. Added a
  `ref.current?.focus()` on open, matching the lightweight
  `ref.current?.focus()` pattern already used in `Setup.tsx` and
  `SourceCenter.tsx` (not a full focus-trap — that pattern is reserved in this
  codebase for actual `role="dialog"` modals, which the Pricing pages don't
  have).

### Confirmed already compliant (no change needed)

- No hardcoded `left`/`right`/`ml-`/`mr-`/`pl-`/`pr-` classes anywhere in the
  four pages — already using logical properties (`gap`, `ms-auto`, flex
  direction-awareness). No hardcoded hex/rgb colors or inline color styles
  anywhere (now locked in by `pages/pricingThemeCompliance.test.ts`).
- `.fh-button-secondary`/`.fh-button-primary` (`min-height: 44px`) and
  `.fh-input`/`.fh-select` (`min-height: 46px`, `width: 100%`) already meet the
  44×44 CSS px touch-target minimum by reuse of the shared design system — no
  page-level sizing overrides exist.
- Both data tables (`PolicyRulesTable`, `UnitsTable`) were already wrapped in
  `overflow-x-auto` since Stage 2 — confirmed still present, not clipped.
- No custom dropdowns/listboxes exist (only native `<select>`) and no
  dialogs/modals/overlays exist anywhere in the Pricing feature — both "no
  clipped dropdowns" and "no clipped dialogs" are satisfied by construction,
  confirmed by a source grep for `fixed `/`absolute `/`role="dialog"`/`<dialog`
  (no matches).
- IDs, channel identifiers, revision numbers, and monetary values were already
  wrapped in `<bdi dir="ltr">` since Stage 2/3 for bidirectional isolation —
  confirmed still present and exercised under `dir="rtl"` in new tests.

### Files changed (Stage 5)

- `frontend/src/pages/PricingMatrix.tsx` — responsive/wrap fixes (policy row,
  channel card header, lifecycle action button row), full `aria-describedby`
  wiring on the reason field, focus-on-open for the lifecycle action form.
- `frontend/src/pages/PricingPolicyEditor.tsx` — `md:grid-cols-2` on both
  form grids, full `aria-describedby` wiring on every top-level and rule field
  (including the two row-level rule errors), `flex-wrap` on the action bar.
- `frontend/src/pages/PricingProductGroupEditor.tsx` — `md:grid-cols-2`,
  `aria-describedby` on name + member fields, `flex-wrap` on the action bar.
- `frontend/src/pages/PricingUnitEditor.tsx` — `md:grid-cols-2`,
  `aria-describedby` on every field, `flex-wrap` on the action bar.
- `frontend/src/pages/pricingThemeCompliance.test.ts` — new; static source
  guard (via the same `import.meta.glob('./*.tsx', { query: '?raw' })` raw-read
  pattern as the existing `pages/layoutRules.test.ts` and
  `mojibakeGuard.test.ts`) asserting none of the four Pricing pages contain a
  hardcoded hex/rgb color or inline color style.
- `frontend/src/pages/PricingMatrix.test.tsx`,
  `PricingPolicyEditor.test.tsx`, `PricingProductGroupEditor.test.tsx`,
  `PricingUnitEditor.test.tsx` — added a "RTL, responsive, and accessibility
  (UI Stage 5)" describe block to each (24 new tests total): document
  direction under Persian, `<bdi dir="ltr">` isolation, long English/Persian
  text preserved without truncation, responsive grid/action-bar classes
  present, table `overflow-x-auto` wrapping, `aria-describedby` linkage,
  label/control `id` pairing, and focus landing in the reason field on open.

## Verification (Stage 5)

- **Targeted tests** — the four `Pricing*.test.tsx` files plus
  `pricingThemeCompliance.test.ts`: **66 tests passed** (23 + 17 + 12 + 13 + 1).
- **TypeScript build** — `npx tsc -b`: **passed** (exit 0).
- **Full frontend unit suite** — `npx vitest run`: **74 files, 584 tests
  passed**, 0 failures (up from 560 in Stage 4 — +24 Stage 5 tests, no
  regressions in the pre-existing 560).
- **Production build** — `npm run build`: **passed**.
- Browser verification: **not performed** (excluded per instruction; the
  audit above is a code-level review plus jsdom-testable properties, not a
  visual/pixel check).
- Confirmed before starting: `main` had not advanced the pricing contract
  since the Stage 2 sync — no merge needed.

## UI Stage 6 — delivered (browser verification, regression, merge handover)

### A. Local application startup used for verification

- **Frontend HEAD verified:** `5eb5bd6` at the start of the stage; `main` was
  confirmed to have advanced only with unrelated Source Acquisition backend
  work (`5e37679`…`f86f07d`, none touching `docs/development/contracts/FRONTEND_CONTRACT.md` or
  `app/flowhub/pricing_matrix/`) — **no merge was performed**, per instruction.
- **Backend used for verification:** the same worktree's checked-out backend
  code (this branch's merge at `e2ec982` already carries the Pricing Matrix
  backend through `main@6eb5610`; nothing backend-side changed since). Run via
  `uvicorn app.flowhub.app:app` using the Python venv already present in the
  Codex `main` worktree (`../FlowHub/.venv`) — read-only reuse of an installed
  interpreter, invoked against **this** worktree's checkout; no backend files
  were modified.
- **Database:** a fresh local SQLite DB (`data/flowhub-local.db`, gitignored)
  migrated with `alembic -c alembic_flowhub.ini upgrade head` from this
  worktree's own `alembic_flowhub/versions/` (landed at `FLOWHUB_024`, the
  Pricing Matrix migration — consistent with this branch's contract; the
  separate legacy `alembic.ini` tree is unrelated/superseded and was not used
  after an initial false start, which was discarded).
- **Config:** a local-only `.env` (gitignored, copied from the Codex worktree's
  own local dev file — explicitly labeled "Local FlowHub development only. Do
  not use for production", placeholder credentials) plus
  `FLOWHUB_DATABASE_URL`/`FLOWHUB_JWT_SECRET` exported directly (the app reads
  these from the process environment, not from `.env`, unlike Alembic's legacy
  tree which goes through `app.config.get_settings()`).
- **URLs:** backend `http://127.0.0.1:8000`, frontend (Vite) bound to IPv4
  explicitly — `http://127.0.0.1:5173` (the default `localhost`/`::1` binding
  was unreachable from this environment's tooling; `--host 127.0.0.1` fixed
  it). The dev proxy (`/api` → backend) was confirmed working end-to-end.
- Completed the real `/setup` wizard (workspace → database check → owner
  account `local_owner`) and, later, created two more real accounts via
  `/settings/users` (`verify_operator` role Operator, `verify_viewer` role
  Viewer) to probe admin gating — see finding below.
- Both dev servers were stopped at the end of the stage
  (`uvicorn`/`vite` processes killed). `.env` and `data/*.db` are gitignored
  local artifacts, confirmed absent from `git status`.

### B–F. Browser verification matrix — what was actually exercised, with real evidence

All of the following were driven through the real UI against the live local
backend above (not test doubles). Network requests/responses were inspected
directly in every case a domain error occurred, to distinguish a real backend
rule from a frontend bug before drawing any conclusion.

**`/settings/pricing`:** loading, empty state (before any policy existed),
policy list, policy detail (rules table with real exact-integer values),
channel head display, lifecycle history (grew 0→1→3→4 events across the
scenarios below), unresolved-unit state (before a unit was declared),
resolved-unit state (after). Permission-denied/unavailable/contract-mismatch
states were already covered by the Stage 2/5 automated suite with fabricated
responses (jsdom); this stage additionally found and fixed one real
contract-mismatch case the automated suite hadn't caught — see Finding 3.

**Policy Revision editor:** created a real revision ("Retail Verification
Policy", EUR, one rule targeting `woocommerce:primary` with a `product_ref`
target). Confirmed: validation errors, a real 404 (`channel_not_found` — the
callable contract's own precondition, "Referenced Channels… must already
exist," satisfied by seeding `uw_channels` through the backend's own
`UnifiedWorkspaceService._seed_channels()` — see note below), failed-submit
data preservation (rule fields all intact after the 404), and successful
submit + navigation to the created revision. `product_group_revision_id`
targeting was not separately re-verified live (identical code path to
`product_ref`, already covered by Stage 3's automated tests); duplicate rule
scope is Stage 3 automated-only for the same reason. Dirty-form navigation
warning and duplicate-submit prevention were not re-driven live (timing- and
`beforeunload`-dependent; already covered by dedicated Stage 3 tests that are
more reliable than manual browser timing).

**Product Group Revision editor:** created with two members, reproduced and
fixed a live duplicate-member validation error, confirmed failed-submit data
preservation. Full successful-submit was not completed live: the backend
requires canonical products to exist (`canonical_product_not_found`, a real
404 matching docs/development/contracts/FRONTEND_CONTRACT.md's "Every supplied canonical product must
exist") and this fresh dev environment has no synced products — creating one
would require an unrelated Source-import flow, out of Strict Scope. The
identical successful-submit code path is already exercised by Stage 3's
automated tests.

**Unit Declaration editor:** Channel scope — IRR/RIAL, IRR/TOMAN (both
succeeded; backend canonicalizes both to a RIAL base with `canonicalFactor`,
e.g. TOMAN → `canonicalUnit: RIAL, canonicalFactor: 10` — confirmed this is
real backend business logic the UI faithfully displays, not a UI bug), a
supported non-IRR pair (EUR/EUR and USD/USD, both succeeded — USD canonicalizes
to CENT/100). "Unsupported pair blocked" and "no magnitude inference" were not
forced via a raw invalid submission because the UI structurally prevents one:
non-IRR currencies auto-fill their unit (disabled input, no free-text field),
and IRR requires an explicit RIAL/TOMAN choice with no pre-selected default —
confirmed by inspection and already covered by Stage 3's `validation.test.ts`.
Source scope was not separately exercised (identical code path to Channel
scope, parameterized only by `scope`/`scopeReference`).

**Channel lifecycle:** activated `woocommerce:primary` for the created policy
(after first hitting a real, correct `channel_computation_currency_mismatch`
422 — the unit was declared IRR while the policy is EUR; fixed by declaring
the unit as EUR — this is exactly the contract's documented precondition,
not a bug). Confirmed focus moves into the reason field on open, reason
preserved through the failed 422 attempt, and a successful activation (head
version 0→1). Deactivated successfully (1→2, via a direct out-of-band API
call used to engineer the next scenario). **Forced a genuine 409:**
reactivated the channel out-of-band (server head → 3, status active) while
the browser's cached state still held head version 1/Active, then clicked
Deactivate in the UI — got a real `pricing_policy_head_conflict` 409. Verified
with real evidence: Head version display updated 1→3, Lifecycle Events count
updated, the distinct "This changed since you loaded it… not automatically
retried" state rendered, the reason text stayed in the input, and only one
409 request was sent (no automatic retry). Clicking Deactivate again
(explicit retry, now with the refreshed head version) succeeded immediately
(3→4). **Admin gating:** attempted to verify with real non-admin sessions —
created `verify_operator` (Operator role) and `verify_viewer` (Viewer role)
via the real `/settings/users` flow. Both are blocked at the **route** level
(`Access Denied` / no Settings link at all) before ever reaching the Pricing
page, because in this app's existing role model only `Owner`/`Admin` carry
`can_view_settings`, and `effectiveHasPerm` treats `is_admin`/`is_super_admin`
as a blanket bypass for every dotted permission including `workspace.admin`.
This means no role in the current seed data can view Pricing without also
being able to administer it — a **pre-existing, global permission-model
characteristic**, not a Pricing UI defect, and out of Fix Policy scope
("existing global design issues"). The client-side `canAdminister` gate
itself is already correctly verified by Stage 4's dedicated automated test
(`does not expose activate/deactivate controls without workspace.admin`,
using a mocked non-admin `AuthContext`).

**C. Responsive / RTL:** mobile `390×844`, tablet `768×1024`, desktop
`1440×900`, each confirmed via `document.documentElement.scrollWidth <=
clientWidth` (no page-level horizontal overflow) plus targeted
`getBoundingClientRect()` checks: the rules table stays scrollable within its
own `.overflow-x-auto` wrapper (648px content in a 324px wrapper at mobile,
page itself did not overflow); the header's three action buttons wrap onto two
lines at 390px width instead of overflowing; the lifecycle action form's
Cancel/Confirm buttons fit without overflow. At tablet width the two-column
`fh-form-grid` was confirmed active (`grid-template-columns: 335px 335px`) and
its column order was confirmed to **mirror correctly under RTL** (first field
renders on the right in `dir="rtl"`, left in `dir="ltr"` — verified by
comparing the same two fields' `getBoundingClientRect().left` in both
directions) and at desktop the policies list and detail panel render
side-by-side (`lg:grid-cols-2`). Persian rendering was confirmed throughout
(policy detail, rules table headers/enum values, channel lifecycle, unit
declarations) with identifiers, currency codes, checksums, and numeric values
staying in unmangled LTR reading order — confirming `<bdi dir="ltr">`
isolation works in the real browser, not just in jsdom.

**D. Themes:** dark mode toggled via the real UI control
(`<html class="dark">`). Inspected computed styles of a status badge, an
`.fh-card`, the page heading, and the rules table: all resolve to CSS-variable
-driven light-on-dark colors (no hardcoded light-only background or
dark-only text found), consistent with the Stage 5 static
`pricingThemeCompliance.test.ts` guard. Focus rings were confirmed **visible**
in dark mode via a real keyboard `Tab` press (`:focus-visible` matched, a
distinct `box-shadow` ring appeared) — confirming the app's shared
`:focus-visible { outline: none; box-shadow: var(--fh-focus-ring) }` rule
(pre-existing, shared, not Pricing-specific) renders correctly for
Pricing-page controls too.

**E. Accessibility / keyboard:** focus-into-reason-field-on-open confirmed via
`document.activeElement` immediately after opening Activate (real click, not
simulated focus). Confirmed no `tabIndex` overrides exist anywhere in the four
Pricing pages (`grep` — none found), meaning focus order strictly follows
DOM/visual order, the correct default. Labels/`aria-describedby`/accessible
names were verified extensively via the Stage 5/6 automated suite (label
`for`/`id` pairing, `aria-invalid`/`aria-describedby` linkage, `role="alert"`/
`role="status"` error regions) — this stage's contribution was live evidence
that the reason field's error linkage renders correctly for a real 403 (see
Finding pattern in F) and that no premature "required" errors appear on a
pristine form in the real browser (see Finding 1). A full manual screen-reader
pass and a formal WCAG audit were **not** performed — out of scope per
instruction ("Do not claim a formal WCAG audit unless one is actually
performed").

**F. Console / network:** the **only** console error found across the entire
session was the one-time `<bdi>` inside `<option>` hydration warning (Finding
2, fixed; confirmed via the console message timeline that it occurred exactly
once, before the fix's HMR update, and never recurred after). Every domain
error surfaced (404 `channel_not_found`, 404 `canonical_product_not_found`,
422 `channel_computation_currency_mismatch`, 422 `pricing_policy_not_activated`,
409 `pricing_policy_head_conflict`) was inspected at the network layer and
confirmed to map to the correct distinct UI state, with the raw
`{"detail":{"code":...}}` body **never** shown to the user (only the localized
state title/message). Repeated `401`s on `/api/v2/exchange-rates/me` were
inspected and confirmed to be the pre-existing, unrelated,
already-correctly-working JWT auto-refresh flow (`authFetch` in
`api/authFetch.ts`) — every 401 was immediately followed by a 200 via
`/api/auth/refresh`; not a Pricing UI concern. No secret/token values were
observed in any request URL (the bearer token used to engineer the 409 test
was read from `localStorage` for test purposes only, never logged or
displayed in the UI). No duplicate submit requests and no automatic retry
after 409 were observed in any network trace.

### Findings — 3 real defects found and fixed (Fix Policy: proven by browser evidence)

1. **Validation errors rendered on a pristine, untouched form.** All three
   editors computed field errors unconditionally from the very first render
   (an empty form is "invalid" by construction), so "This field is required"
   appeared before the user had touched anything — reading as a broken form.
   Root cause: Stage 3 never gated the *display* of errors, only the
   submit-disabled state. **Fix:** each editor now derives a `displayErrors`
   view gated on the existing `dirty` flag (`dirty ? errors : <empty>`); the
   real `errors` object (and therefore `hasErrors`/submit-disabled) is
   completely unchanged. `PricingUnitEditor`'s `dirty` computation was also
   widened to include `scopeReference` (previously excluded), so picking a
   scope alone now correctly starts revealing validation feedback too. Files:
   `pages/PricingPolicyEditor.tsx`, `pages/PricingProductGroupEditor.tsx`,
   `pages/PricingUnitEditor.tsx`. Regression tests added to all three
   (`PricingMatrix.test.tsx` needed no change here — it never had this pattern).

2. **`<bdi>` nested inside `<option>` — invalid HTML, React hydration
   warning.** `PricingUnitEditor.tsx`'s currency/IRR-unit `<select>` options
   wrapped their text in `<bdi dir="ltr">`, which browsers cannot render as a
   child of `<option>` (option content is always plain text). **Fix:** moved
   `dir="ltr"` onto the `<option>` element itself (a valid HTML attribute)
   instead of a child `<bdi>`. Confirmed via the browser console timeline
   that the warning occurred exactly once (before the fix) and never recurred
   after. No other Pricing file had this pattern (checked by regex).

3. **Unit-declaration validator assumed a `status: "resolved"` literal the
   backend never sends, and treated `version` as always a string.** The real
   backend's resolved-declaration response omits `status` entirely (only the
   unresolved example in docs/development/contracts/FRONTEND_CONTRACT.md carries
   `status: "unresolved"`) and returns `version` as a JSON number (observed:
   `"version":1`). `validateUnitDeclaration` required a literal
   `status === 'resolved'` (throwing `ContractMismatchError` on every real
   resolved response — reproduced live as "Unsupported pricing response") and
   used `optionalString` for `version` (silently discarding a numeric value
   to `''`). **Fix:** treat "resolved" as "anything that isn't the
   `'unresolved'` marker" (an explicit *unrecognized* status still fails
   closed), and format `version` with the same `formatExactInteger` helper
   used for other `ExactInteger` wire values (PM-4) instead of
   `optionalString`. Files: `features/pricingMatrix/presentation.ts`,
   `features/pricingMatrix/types.ts` (updated doc comments to record the real
   observed shape). Regression test added to `presentation.test.ts` using the
   exact shape observed in the browser (no `status` key, numeric `version`
   and `canonicalFactor`).

None of the three required backend changes — all were frontend assumptions
that didn't match the real, already-correct backend response shape, or a
frontend-only markup/UX defect.

### G. Test and build verification (after all three fixes)

- **Targeted Pricing UI tests:** all `Pricing*.test.tsx` +
  `pricingThemeCompliance.test.ts` + `features/pricingMatrix/`: **105
  passed** (100 before the Stage 6 fixes' regression tests were added, +5).
- **`npx tsc -b`:** passed (exit 0).
- **Full frontend unit suite:** `npx vitest run` → **74 files, 589 tests
  passed**, 0 failures (up from 584 pre-fix — the +5 are exactly the new
  regression tests for Findings 1 and 3).
- **`npm run build`:** passed.
- **`npm run i18n:validate`:** fails with the **same two pre-existing,
  unrelated strings** as every prior stage — not touched, not fixed (out of
  Fix Policy scope: "unrelated i18n debt"):
  - `frontend/src/components/SiteFooter.tsx:30` — JSX text `FlowHub v`
  - `frontend/src/pages/ExchangeRates.tsx:153` — JSX text `/ day ·`
- **Browser verification matrix:** completed as detailed above (sections
  A–F), against a real local backend on this branch's own code and a fresh
  migrated database.

### Remaining frontend blockers (none block merge)

- None of the three fixed defects, nor any other Pricing UI behavior,
  currently blocks integration. The two i18n pre-existing strings are a known,
  documented, unrelated blocker for a **clean** `i18n:validate` run — not a
  Pricing UI blocker.
- Full "Product Group successful submit" and "unsupported currency/unit pair
  rejected" were verified by code + automated test but not by a live
  browser round-trip (see B–F for exact reasons: no synced canonical
  products in this fresh dev DB; the UI structurally prevents constructing an
  unsupported pair). Recommended before a production release (not before
  merge): re-verify Product Group successful-submit once a Source has synced
  real canonical products.
- The admin-gating finding (no role in the seed data can view Pricing without
  `workspace.admin`) is a pre-existing app characteristic to flag to Codex/
  Owner if a "can view but not administer Pricing" role is ever required — it
  is not something this branch should fix unilaterally (global permission
  model, out of Strict Scope).

## Not done (by design)

- No lifecycle CAS **conflict-resolution UI** beyond "refetch + notify +
  require explicit retry" (no diff/merge view of what changed — out of scope
  per instruction).
- No Preview/Dry Run/Apply, no Source Acquisition, no Diagnostics, no
  schema-drift UI, no automatic currency conversion.
- No `ServiceContext` registration for the pricing client (used directly by
  pages, matching Stages 2–3).
- No nav entry in `SettingsNav` (routes reachable directly; nav wiring
  deferred to avoid touching shared nav + its tests).
- No Global unit scope (PM-8) and no product-search integration (PM-9) — both
  documented limitations, not silent gaps.
- Not merged again beyond the Stage-2 sync (Stages 3–6 all confirmed no
  pricing-contract changes landed on `main` since), not pushed, not deployed;
  Codex `main` untouched (confirmed separate worktree, unchanged HEAD).

## Exact merge prerequisites

1. Owner review and approval of this branch (`claude/ui-phase-1`,
   6 commits: `30334ca`, `8ae5424`, `001ec5c`, `7421a93`, `5eb5bd6`, and the
   Stage 6 commit below) — no commit has been pushed.
2. Confirm `main` still has not changed `docs/development/contracts/FRONTEND_CONTRACT.md` or the callable
   Pricing Matrix API between the Stage 6 HEAD check (`f86f07d`) and the
   actual merge time — re-run the same `git log`/`git diff --stat` check used
   in every stage's pre-flight before merging.
3. Merge (not rebase, not squash) `claude/ui-phase-1` into `main`, preserving
   every stage commit exactly as approved.
4. After merge, run the full backend suite (Codex-owned) once to confirm no
   incidental interaction — this branch touched zero backend files across all
   6 stages, so none is expected, but it's cheap insurance before any
   deployment.
5. Do not deploy until Owner explicitly authorizes it — this handover ends at
   merge-readiness, not release.

## Exact recommended integration sequence

1. Merge `claude/ui-phase-1` → `main` (fast-forward or merge commit, Owner's
   choice; no rebase/squash per this session's standing instruction).
2. Add a `SettingsNav` entry for `/settings/pricing` (small, isolated change;
   deferred across all 6 stages specifically to avoid touching shared nav +
   its tests before Owner sign-off on the feature itself).
3. Re-verify Product Group successful-submit against a Source with real
   synced canonical products (the one browser scenario this stage could not
   complete end-to-end — see "Remaining frontend blockers").
4. Flag the admin-gating / role-model observation to Codex or Owner for a
   decision (not a required fix): whether a "view Pricing but cannot
   administer channels" role should exist.
5. Only after Preview, Apply, Diagnostics, or Source Acquisition become
   callable in `docs/development/contracts/FRONTEND_CONTRACT.md` (per Codex's backend roadmap), begin a
   new UI phase for those surfaces — never before, and never by inventing
   endpoints ahead of the contract.
