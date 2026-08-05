# FlowHub UI continuation handover — Pricing Matrix (Claude UI Phases 1–2)

## Read this first

This document is the **UI-side** companion to Codex's backend `RESUME.md`. It
records the state of the Claude UI work for the Pricing Matrix:

- **Stage 1** (commit `30334ca`) — contract-boundary correction + callable-endpoint
  mapping and client scaffolding.
- **Stage 2** — read-only Pricing Matrix surfaces built on the callable contract,
  after merging Codex's PM-1…PM-7 answers from `main`.

- **Do not** treat this file as a backend contract. The callable contract is
  `FRONTEND_CONTRACT.md` at the repository root.
- **Do not** treat `docs/architecture/PRICING_UI_CONTRACT.md` as callable. It is
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
  or root `FRONTEND_CONTRACT.md`. (Those files appear in the branch only via the
  merge of Codex's own `main` commits.)

## Contract boundary — corrected

Two contracts, two roles:

| Document | Path | Role | Status |
|---|---|---|---|
| `FRONTEND_CONTRACT.md` | repo root | **Authoritative, callable** backend contract (APIs available now) | `v1-draft`, unchanged by Claude |
| `PRICING_UI_CONTRACT.md` | `docs/architecture/` | **Proposed** architectural contract (future UI + backend exposure, not implemented) | `Proposed` |

**Fix applied in this phase (step 4):** `PRICING_UI_CONTRACT.md` already carried
`Status: Proposed`, but it did **not** state the reciprocal boundary — that
`FRONTEND_CONTRACT.md` is the "available now" contract and that this document's
Source Acquisition, Diagnostics, Workspace Preview, Apply Result,
`allowed_actions`, and `contract_version` mechanism are **not implemented yet**.
A `## Contract Boundary — What Is Callable Today` section was added near the top
of `PRICING_UI_CONTRACT.md`, and an `## Open Questions for Codex` section was
added at the end. `FRONTEND_CONTRACT.md` already declared the boundary from its
side and was left untouched.

## Cross-check: FRONTEND_CONTRACT.md vs PRICING_UI_CONTRACT.md (§ domain vocab, exact monetary, required API views)

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
| Workspace Pricing Preview Row | **Not reached** — explicitly not delivered (FRONTEND_CONTRACT.md "Important Frontend Rules") | — |
| Apply Result (projection + write attempts) | **Not reached** — explicitly not delivered | — |
| Unit declaration `unresolved`/`resolved` primitive | **Satisfies** — `GET/PUT /units/{scope}/{scopeReference}` | — |
| `workspace_precondition` composed projection | **Partial** — primitives exist (units + activation), composed per-channel projection does not | PM-7 |
| Channel activation gating (`operation_gate allowed|blocked`) | **Partial** — activate/deactivate lifecycle + head `status` exist; per-channel gate *evidence* projection does not | — |
| Contract-revision / fail-closed mechanism | **Conflict** — callable contract uses a doc + `RESUME.md` change process, not the fail-closed unknown-version/enum handling | PM-1/PM-2/PM-3 |

No conflict above was silently resolved. Each was filed under *Open Questions for
Codex* in `PRICING_UI_CONTRACT.md` (PM-1 … PM-7).

**Resolution (synced from `main` `6eb5610`):** Codex answered all of PM-1 … PM-7
in `FRONTEND_CONTRACT.md` → "Claude UI Phase 1 Decisions". Summary:

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
record; the authoritative answers live in `FRONTEND_CONTRACT.md`.

## Implemented endpoints → frontend types & client (mapped this phase)

Source: `FRONTEND_CONTRACT.md`. Base path `/api/v2/pricing-matrix`. Client:
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
  fabricated endpoints, no clients for routes absent from `FRONTEND_CONTRACT.md`.
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
  `FRONTEND_CONTRACT.md` are called; channel identities are derived from policy
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

Stage 1 (commit `30334ca`): `docs/architecture/PRICING_UI_CONTRACT.md`,
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

## Not done (by design)

- No mutations (activate/deactivate/create/edit), no preview/apply/diagnostics/
  source-acquisition, no `allowed_actions` gating.
- No `ServiceContext` registration for the pricing client.
- No nav entry in `SettingsNav` (route reachable at `/settings/pricing`; nav
  wiring deferred to avoid touching shared nav + its tests).
- Not pushed; Codex `main` untouched.

## Exact next recommended UI phase

**UI Stage 3** — once Codex exposes the future evidence endpoints in
`FRONTEND_CONTRACT.md` (Workspace Pricing Preview, Apply Result, Diagnostics,
Source Acquisition, `allowed_actions`), extend beyond read-only. Nearer-term
follow-ups that stay on the current callable contract, if the Owner wants them:
a `SettingsNav` entry for `/settings/pricing`; mutation surfaces
(activate/deactivate with the head-version/409 refetch flow behind
`workspace.admin`); and policy/product-group authoring (`createPolicy` /
`createProductGroup`). Do not implement preview, apply, diagnostics, or
source-acquisition UI until those contracts become callable.
