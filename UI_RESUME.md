# FlowHub UI continuation handover — Pricing Matrix (Claude UI Phase 1)

## Read this first

This document is the **UI-side** companion to Codex's backend `RESUME.md`. It
records the state of **Claude UI Phase 1** for the Pricing Matrix. It is scoped
to the *currently callable* backend contract and deliberately stops short of
building the Pricing Matrix UI.

- **Do not** treat this file as a backend contract. The callable contract is
  `FRONTEND_CONTRACT.md` at the repository root.
- **Do not** treat `docs/architecture/PRICING_UI_CONTRACT.md` as callable. It is
  `Proposed` architecture for later phases.

## Worktree and branch state

- Worktree: `C:\Users\nima\Documents\GitHub\FlowHub-Claude-UI` (dedicated, Claude-owned)
- Branch: `claude/ui-phase-1`
- Base commit (Phase 1B): `6d91edb28c89e0b9fc0a435ea25f6887ea1fdce4`
- Isolated from Codex `main` worktree (`C:\Users\nima\Documents\GitHub\FlowHub`).
- No backend files, migrations, backend tests, `RESUME.md`, or root
  `FRONTEND_CONTRACT.md` were modified in this phase.

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

No conflict above was silently resolved. Each is filed under *Open Questions for
Codex* in `PRICING_UI_CONTRACT.md` (PM-1 … PM-7).

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
`features/sourceWorkspace/api.ts`), built on `apiFetch` + `authFetch`. It is
**not** yet registered in `ServiceContext` and is **not** imported by any page —
that wiring is Phase 2.

Scaffolding notes / faithfulness:
- Every method maps 1:1 to a documented, implemented route. No mocks, no
  fabricated endpoints, no clients for routes absent from `FRONTEND_CONTRACT.md`.
- `headVersion` is typed as an opaque concurrency token (keep & resend
  unchanged; refetch on 409).
- Under-specified points are typed conservatively and flagged (PM-4 monetary
  number-vs-string; PM-5 nullability; PM-6 response rule casing).

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

## Routes & component boundaries — for what is callable today only (DESIGN, not wired)

Scoped strictly to the callable endpoints. These are **proposed** boundaries for
Phase 2 to implement; nothing below was added to `App.tsx` in Phase 1.

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

## Files changed in Claude UI Phase 1

- `docs/architecture/PRICING_UI_CONTRACT.md` — added Contract Boundary section +
  Open Questions for Codex (only additions; existing body preserved).
- `frontend/src/features/pricingMatrix/types.ts` — new (callable-contract types).
- `frontend/src/features/pricingMatrix/api.ts` — new (`pricingMatrixApi` client).
- `frontend/src/features/pricingMatrix/index.ts` — new (barrel re-export).
- `UI_RESUME.md` — new (this file).

## Verification

Run in the `FlowHub-Claude-UI` worktree after `npm ci` (fresh worktree;
`package-lock.json` unchanged):

- **TypeScript project build** — `npx tsc -b`: **passed** (exit 0). Type-checks
  the new `features/pricingMatrix/*` files against the whole project.
- **Frontend unit suite** — `npx vitest run`: **67 files, 484 tests passed**,
  0 failures. (Handsontable/jsdom CSS parse noise is pre-existing and did not
  fail the run.)
- **Not separately run, with rationale:**
  - Full `vite build` bundle — the new modules are additive and not yet imported
    by any entry, so they are not in the bundle graph; `tsc -b` already
    type-checked them.
  - `i18n:validate` — known pre-existing non-zero exit from two hardcoded strings
    (`SiteFooter.tsx`, `ExchangeRates.tsx`) per `RESUME.md`; this phase added no
    UI strings.
  - Backend suites — backend was not touched.

## Not done (by design)

- No Pricing Matrix UI components, pages, or routes were built or wired.
- No `ServiceContext` registration for the pricing client.
- No i18n strings, no CSS, no backend/mocks.
- UI Phase 2 was **not** started.

## Exact next recommended UI phase

**UI Phase 2 — Read-only Pricing surfaces on the callable contract**, pending
Owner approval and pending Codex answers to Open Questions PM-1 … PM-7 (envelope,
casing, pagination materially affect type generation). Suggested first slice:

1. `PricingPoliciesPage` at `/settings/pricing`: list + detail (read-only),
   reusing `PageShell`/`Badge`/`Alert`, EN/FA + light/dark + responsive.
2. `ChannelPolicyLifecyclePanel`: head + lifecycle events (read-only first;
   activate/deactivate mutations only after the head-version/409 refetch flow and
   `workspace.admin` gating are covered by tests).
3. A `PricingStatusPresentation` mapping (mirrors `diagnosticPresentation.ts`)
   for `status` / `eventKind` / unit-resolution states.

Do not implement preview, apply, diagnostics, or source-acquisition UI until
those contracts become callable in `FRONTEND_CONTRACT.md`.
