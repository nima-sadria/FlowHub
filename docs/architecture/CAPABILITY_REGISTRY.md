# Capability Registry

**Status:** Draft — documentation only. Not implemented, not wired to any
code or CI. Nothing in this file is imported by application code, referenced
by any test, or run in CI.

This file now contains two registries at two different granularities,
produced in two phases. Both are preserved:

1. **Part A — Domain-Level Capability Registry (v1 draft, this update).**
   Ten Owner/Admin/Operator-facing domain capabilities, matched to the
   `business_capabilities` row and the ten capability nodes drawn in
   [`docs/draw/00-flowhub-master.drawio`](../draw/00-flowhub-master.drawio)
   (`source_providers`/`workspace`/`pricing`/`channel_providers`/`approval`/`X`
   (Write Pipeline) as Core, plus the `cross` cutting-capabilities box —
   `admin`, `audit`, `diagnostics`, `business_observability_capability` — as
   Supporting). This is the "first real draft" requested; see Methodology
   below for how each entry was verified.
2. **Part B — Fine-grained illustrative seed (Phase 4.2, original).**
   The original per-feature schema and four-row seed set from the first
   version of this document, preserved unchanged below in
   [Appendix A](#appendix-a-phase-42-fine-grained-registry-original). It
   answers a narrower question ("does this one named feature have
   Backend+API+UI+Test") than Part A ("does this whole domain exist and
   how mature is it"). Both are legitimate views; this draft does not
   collapse them into one schema.

Neither part modifies, replaces, or is consumed by
`MarketplaceConnectorRegistry` (`app/flowhub/channels/registry.py`), which
answers a different, runtime question ("can this connector do X").

## Principle

Quoting the `capability_principle` node in the target-architecture diagram:

> Every Owner/Admin/Operator-facing capability must maintain coherent
> Backend ↔ API ↔ UI ↔ Test coverage. Excludes internal-only transaction,
> locking, CAS, migration engine, and worker internals.

## Non-goals

- **No reflection, no auto-discovery.** Every entry below is hand-written
  and reviewed, not produced by scanning routes or walking the router.
- **Not a CI gate.** This document defines shape and current-state evidence
  only. No check enforces it.
- **Not a runtime capability system.** Not imported by `app/flowhub/`, not a
  dependency of any request path.
- **Not a claim of completeness for the diagram's TARGET architecture.**
  Every diagram node reproduced in this file that is marked
  `TARGET / PROPOSED — ⚠ VERIFY` is reproduced *as a target*, not
  reclassified as implemented because a same-named module exists.

## Governance rule: status and maturity are Owner/Architecture decisions

> **Business status and maturity are Owner/Architecture decisions.
> Repository evidence may confirm or downgrade confidence, but must not
> silently upgrade capability maturity.**

Repository inspection (reading code, checking router mounts, counting
test files) is **implementation evidence only**. It can support a
downgrade — e.g. finding a stub `raise NotImplementedError` is sufficient
on its own to justify `PARTIAL` or `NOT_IMPLEMENTED` — but it cannot, by
itself, justify marking something `IMPLEMENTED` at business-capability
grain. A capability being *technically wired end-to-end in the code* is
necessary but not sufficient for that call: whether it is trustworthy
enough for the business to rely on, whether it has been exercised at
runtime rather than only read statically, and how mature the surrounding
workflow really is are Owner/Architecture judgments, not something an
automated read of the repository is entitled to assert.

Practically, this means:

- `IMPLEMENTED` is reserved for capabilities the Owner/Architecture has
  affirmatively signed off on at this grain. An AI-run repository scan
  should default to `IMPLEMENTED_UNVERIFIED` when its evidence is purely
  static (code exists, routes are mounted, tests exist) and no runtime or
  Owner verification has actually taken place.
- `PARTIAL` is the safe default whenever evidence is mixed (some real
  modules, some stubs; some mounted routes, some dead ones) rather than
  rounding up to `IMPLEMENTED` because *most* of the surface looks real.
- The **status and maturity values in this registry are the
  Owner-approved classifications** as of the most recent correction, not
  the AI's original static-evidence estimates. Where those two diverge,
  each entry below records both: the Owner-approved value (authoritative)
  and, in its `notes`, what the static evidence alone would have
  suggested and why that isn't sufficient on its own.

## Methodology (research-first, evidence-based)

Every `status` below was set only after direct repository verification, in
this order:

1. Read [`docs/draw/00-flowhub-master.drawio`](../draw/00-flowhub-master.drawio)
   for the target shape and the capabilities it names.
2. Read [`docs/architecture/CURRENT_ARCHITECTURE.md`](CURRENT_ARCHITECTURE.md),
   [`docs/architecture/BU5_INTEGRATIONS.md`](BU5_INTEGRATIONS.md), and the
   prior version of this file for previously-approved decisions.
3. For **API surface**, checked which routers are actually mounted by
   reading `app.include_router(...)` calls in
   [`app/flowhub/app.py`](../../app/flowhub/app.py) (lines 219–243) against
   the router *files present* in `app/flowhub/api/v2/`. A file existing in
   that directory is **not** evidence of a live endpoint — several are
   unmounted stubs (see [Cross-cutting finding](#cross-cutting-finding-ten-dead-stub-routers) below).
4. For **backend surface**, opened each module and distinguished real
   service logic (multi-hundred-line files with working methods) from
   stub classes (methods that `raise NotImplementedError` or docstrings
   reading "Implementation begins in B__").
5. For **UI surface**, matched pages under `frontend/src/pages/` to the
   API calls they actually make (e.g. `Workspace.tsx` calling
   `writePipeline.approve(...)`), not just filename similarity.
6. For **test surface**, listed files under the matching `tests/flowhub/*`
   and `frontend/src/pages/*.test.tsx` directories; an empty or missing
   test directory is recorded as a gap, not silently omitted.

Where a step above could not be completed inside the 60-minute time budget
for this draft, the entry is marked `NEEDS_VERIFICATION` rather than guessed.

## Schema (Part A)

| Field | Meaning |
| --- | --- |
| `id` | Stable snake_case identifier. |
| `name` | Human-readable capability name. |
| `domain` | The business/architecture domain the capability belongs to. |
| `classification` | `Core` or `Supporting`, per the task's requested split. |
| `audience` | `Operator-facing`, `Admin-facing`, `Internal-only`, or `Hybrid`. |
| `status` | `IMPLEMENTED`, `IMPLEMENTED_UNVERIFIED`, `PARTIAL`, `PLANNED`, `NOT_IMPLEMENTED`. |
| `maturity` | `FOUNDATION` → `BASELINE` → `OPERATIONAL` → `ADVANCED` → `INTELLIGENT`. |
| `backend surface` | Real backend modules found. |
| `API surface` | Mounted router(s) and confirmed live endpoints. |
| `UI surface` | Frontend pages that actually call the above. |
| `test surface` | Test files found (backend + frontend). |
| `evidence` | Exact file paths / grep results this entry is based on. |
| `notes` | Caveats, open questions, distinctions from same-named stub code. |

---

## Part A — Domain-Level Capability Registry (v1 draft)

### Core Capabilities

#### `sources` — Sources

- **domain:** Sources
- **classification:** Core
- **audience:** Hybrid — Commerce Hub source list is read by any signed-in
  user (`app/flowhub/api/v2/commerce.py` `list_sources`/`list_source_types`
  use `get_current_user`, not an admin check); source *configuration* is
  admin-gated per `settings_routes.py` / `sources.py` (`require_admin`
  usage confirmed by import, exact per-route gating **NEEDS_VERIFICATION**).
- **status:** PARTIAL — Owner-approved classification (overrides this
  draft's original static-evidence estimate of `IMPLEMENTED`)
- **maturity:** BASELINE — Owner-approved classification (overrides
  original estimate of `OPERATIONAL`)
- **backend surface:** `app/flowhub/sources/spreadsheet_source.py`;
  `app/flowhub/source_acquisition/{service.py,execution.py,errors.py,
  models.py,nextcloud_provider.py,observations.py,schema_assessment.py}`
- **API surface:** `app/flowhub/api/v2/sources.py` (mounted,
  `app.py:228`), `app/flowhub/api/v2/source_workspace.py` (mounted,
  `app.py:243`)
- **UI surface:** `frontend/src/pages/SourceCenter.tsx`,
  `SourceConfiguration.tsx`, `SourceImportWizard.tsx`,
  `frontend/src/pages/sourceConfiguration/`
- **test surface:** `tests/flowhub/source_acquisition/` (7 files),
  `tests/flowhub/source_workspace/` (7 files),
  `SourceCenter.test.tsx`, `SourceConfiguration.test.tsx`
- **evidence:** directory listings above; `app/flowhub/app.py` lines 96,
  228, 243 (`include_router` calls); `CURRENT_ARCHITECTURE.md` current
  Nextcloud and CSV/Excel Sources, with Google Sheets and ERP/API explicitly
  retained as planned placeholders
- **notes:** The diagram's Source Boundary is `CURRENT / CONFIRMED` for
  `SourceHttpClient` and for Nextcloud's `SourceConnector` implementation.
  The unified multi-provider Source Gateway contract spanning CSV/Excel and
  future providers remains **NEEDS_VERIFICATION**; repository evidence must
  not upgrade that target. Static evidence alone
  (mounted routers, populated backend modules, present tests) would have
  supported `IMPLEMENTED`/`OPERATIONAL`; the Owner-approved
  `PARTIAL`/`BASELINE` reflects that this evidence is unverified at runtime
  and the source-adapter abstraction gap above is unresolved, not that
  the underlying code was found broken.

#### `workspace` — Workspace

- **domain:** Workspace
- **classification:** Core
- **audience:** Operator-facing
- **status:** IMPLEMENTED_UNVERIFIED — Owner-approved classification
  (overrides original estimate of `IMPLEMENTED`; static code reading is
  not runtime/Owner verification)
- **maturity:** OPERATIONAL — Owner-approved, unchanged from original
  estimate
- **backend surface:** `app/flowhub/workspace/{preview_store.py,
  price_workflow.py}`; `app/flowhub/unified_workspace/{authorization.py,
  connectors.py,domain.py,events.py,listing_guard.py,models.py,
  repositories.py,services.py}` (`services.py` is 4,429 lines — substantial,
  not a stub); `app/flowhub/source_workspace/`
- **API surface:** `app/flowhub/api/v2/workspace.py` (mounted,
  `app.py:229`), `unified_workspace.py` (mounted, `app.py:242`),
  `source_workspace.py` (mounted, `app.py:243`)
- **UI surface:** `frontend/src/pages/Workspace.tsx`,
  `UnifiedWorkspace.tsx` — `Workspace.tsx` implements a real phase state
  machine (`idle → previewing → preview_ready → dry_running →
  dry_run_ready → approving → approved → applying → result/error`,
  `Workspace.tsx:74`)
- **test surface:** `tests/flowhub/workspace/` (2 files),
  `tests/flowhub/unified_workspace/` (4 files), `Workspace.test.tsx`,
  `UnifiedWorkspace.test.tsx`
- **evidence:** `Workspace.tsx:74,184,333-347`; module line counts above;
  `app.py:229,242,243`
- **notes:** Workspace is the UI host for both the Review & Approval and
  Write Pipeline capabilities below (same phase machine, same page) —
  recorded here as the read/preview surface; approve/execute behavior is
  attributed to its own capability entries per the task's requested split.

#### `pricing_intelligence` — Pricing Intelligence

- **domain:** Pricing Intelligence
- **classification:** Core
- **audience:** Hybrid (operator-facing editors; admin-adjacent policy
  configuration — exact per-route gating not individually verified for
  every pricing endpoint, **NEEDS_VERIFICATION**)
- **status:** PARTIAL — Owner-approved classification (overrides original
  estimate of `IMPLEMENTED`)
- **maturity:** FOUNDATION — Owner-approved classification (overrides
  original estimate of `ADVANCED`)
- **backend surface:** `app/flowhub/pricing_matrix/{arithmetic.py,
  contracts.py,errors.py,evaluator.py,guards.py,models.py,service.py,
  units.py}`; `app/flowhub/pricing_authority/{contracts.py,errors.py,
  models.py,service.py}`; `app/flowhub/pricing_evaluation/`;
  `app/flowhub/product_pricing/{models.py,service.py}`;
  `app/flowhub/formula_migration_preview/`; `app/flowhub/formula_translator/`
- **API surface:** `app/flowhub/api/v2/pricing_matrix.py` (mounted,
  `app.py:227`), `app/flowhub/api/v2/products.py` (mounted, `app.py:226`,
  includes `/{product_id}/channel-prices` per prior registry finding)
- **UI surface:** `frontend/src/pages/PricingMatrix.tsx`,
  `PricingPolicyEditor.tsx`, `PricingProductGroupEditor.tsx`,
  `PricingUnitEditor.tsx`, `Products.tsx`
- **test surface:** `tests/flowhub/pricing_matrix/` (5 files),
  `tests/flowhub/pricing_authority/` (2 files),
  `tests/flowhub/pricing_evaluation/`, `tests/flowhub/formula_migration_preview/`,
  `tests/flowhub/formula_translator/`, `tests/beta/test_multi_channel_pricing.py`,
  plus `PricingMatrix.test.tsx`, `PricingPolicyEditor.test.tsx`,
  `PricingProductGroupEditor.test.tsx`, `PricingUnitEditor.test.tsx`,
  `Products.test.tsx`
- **evidence:** module/test listings above; `app.py:226,227`
- **notes:** The former `product_channel_price_editor` UI finding is resolved
  by current repository evidence. `Products.tsx` creates or restores a catalog
  Unified Workspace and embeds `DensePricingWorkspace`, which renders editable
  per-Listing channel price cells and submits Draft to Review to selected Apply
  through `/api/v2/unified-workspaces`. The legacy
  `/{product_id}/channel-prices` API remains a real protected compatibility
  facade over `ProductPricingService` and `WritePipelineService`, but the
  current frontend has no caller for it. It is therefore a duplicate legacy
  API surface, not a missing operator UI. Preserve it until an Owner makes a
  compatibility-removal decision. The Owner-approved `PARTIAL`/`FOUNDATION`
  classification remains unchanged: this correction resolves a stale parity
  finding, not a maturity upgrade.

#### `channel_management` — Channel Management

- **domain:** Channel Management
- **classification:** Core
- **audience:** Hybrid — Commerce Hub channel list readable by any
  signed-in user; channel credential/config writes require admin
  (`commerce.py` `_require_admin` helper present, used selectively)
- **status:** PARTIAL — Owner-approved classification (overrides original
  estimate of `IMPLEMENTED`)
- **maturity:** BASELINE — Owner-approved classification (overrides
  original estimate of `OPERATIONAL`)
- **backend surface:** `app/flowhub/channels/{gateway.py,marketplace.py,
  marketplace_product_sync.py,registry.py,snappshop.py,
  snappshop_product_sync.py,tapsishop.py,technolife.py,digikala.py,woocommerce.py,
  write_validation.py}`; `app/flowhub/commerce/service.py`
- **API surface:** `app/flowhub/api/v2/commerce.py` (mounted,
  `app.py:232`) — confirmed live routes include `GET /commerce/sources`,
  `GET /commerce/source-types`
- **UI surface:** `frontend/src/pages/Channels.tsx`, `ChannelDetail.tsx`,
  `CommerceHub.tsx`
- **test surface:** `tests/flowhub/channels/` (2 files),
  `tests/test_marketplace_connectors.py`, `test_marketplace_product_sync.py`,
  `test_snappshop_connector.py`, `test_snappshop_product_sync.py`,
  `test_tapsishop_connector.py`, `test_technolife_connector.py`,
  `test_digikala_connector.py`,
  `Channels.test.tsx`, `CommerceHub.test.tsx`
- **evidence:** listings above; `app.py:232`; `CURRENT_ARCHITECTURE.md`
  current WooCommerce, SnappShop, TapsiShop, and Technolife Channels, plus
  Digikala's static `IMPLEMENTED_UNVERIFIED` read-side adapter; Shopify remains
  a future placeholder
- **notes:** the diagram confirms `WorkspaceConnectorFactory` as the
  canonical Channel Gateway for the current four write-capable providers.
  Digikala is registered on the read side but intentionally remains absent
  from that gateway, because its provider-documented writes are
  `DOCUMENTED_NOT_IMPLEMENTED`. The same contract for future providers remains
  **NEEDS_VERIFICATION** and is not inferred from filenames or placeholder
  registry entries. The
  Owner-approved status remains `PARTIAL`/`BASELINE` rather than this
  draft's original `IMPLEMENTED`/`OPERATIONAL` estimate: a per-channel
  adapter existing in code for four marketplaces is not the same as the
  channel domain being verified-mature across all of them.

#### `digikala_read_side_channel` â€” Digikala Read-side Channel

- **domain:** Channel Management
- **classification:** Core
- **audience:** Admin-facing configuration and diagnostic probe; sanitized
  channel state is visible through the shared Commerce Hub and Diagnostics UI.
- **status:** `IMPLEMENTED_UNVERIFIED` â€” implementation and static contract
  tests exist, but no successful live, Owner-credential read has been recorded.
- **maturity:** FOUNDATION â€” this records no architecture-maturity promotion;
  live evidence must be reviewed by the Owner and Diagram Keeper first.
- **backend surface:** `app/flowhub/channels/digikala.py`,
  `app/flowhub/channels/registry.py`,
  `app/flowhub/commerce/service.py`, and
  `app/flowhub/diagnostics/channel_health.py`.
- **API surface:** shared Commerce Hub configuration and connection-test
  routes in `app/flowhub/api/v2/commerce.py`; no Digikala-specific write route.
- **UI surface:** `frontend/src/pages/CommerceHub.tsx`, shared Channels,
  Diagnostics, Activity, and brand-icon registry surfaces; no standalone
  Digikala UI.
- **test surface:** `tests/flowhub/test_digikala_connector.py`, Commerce Hub
  regression tests, Diagnostics status tests, and Channels/Commerce Hub UI
  registration tests.
- **evidence:** `docs/api/channel/digikala-api.md`; it explicitly documents
  bearer authentication, token/refresh routes, `GET /orders`,
  `GET /orders/{order_item_id}`, catalog/inventory read routes, a generic list
  envelope, and broad write groups, but does not supply endpoint-specific
  field, filter, pagination-query, or write-request schemas.
- **notes:** Test Connection uses exactly the documented read-only `GET
  /orders` probe and persists sanitized health evidence. Raw documented reads
  are not treated as normalized product or order sync: identifiers, prices,
  inventory, order statuses/dates, line items, quantities, and totals remain
  unsupported until the missing endpoint schemas are supplied. All product,
  inventory, package/shipment, promotion, webhook, and order-changing
  operations are `DOCUMENTED_NOT_IMPLEMENTED`; accepting, fulfilling,
  cancelling, rejecting, or otherwise mutating an order is prohibited.

#### `review_approval` — Review & Approval

- **domain:** Review & Approval
- **classification:** Core
- **audience:** Operator-facing
- **status:** IMPLEMENTED_UNVERIFIED — Owner-approved classification
  (overrides original estimate of `IMPLEMENTED`). All evidence below is
  static code reading (source, route decorators, UI callback wiring); no
  runtime exercise of the dry-run→approve flow was performed, so per the
  governance rule above this must not be marked fully `IMPLEMENTED`.
- **maturity:** OPERATIONAL — unchanged from original estimate; not
  explicitly overridden
- **backend surface:** `app/flowhub/write_pipeline/contracts.py`
  (`WritePipelineDryRunRequest`, `WritePipelineApprovalRequest`),
  `app/flowhub/write_pipeline/service.py` (1,383 lines)
- **API surface:** `app/flowhub/api/v2/write_pipeline.py` (mounted,
  `app.py:230`) — confirmed live routes: `POST /write-pipeline/dry-run`,
  `GET /write-pipeline/batches/{batch_id}`,
  `POST /write-pipeline/batches/{batch_id}/approve`
- **UI surface:** `frontend/src/pages/Workspace.tsx` — `approveDryRun`
  callback at `Workspace.tsx:333` calls `writePipeline.approve(batch.id,
  'Approved from Workspace')` (`Workspace.tsx:338-339`); phase labels
  include `workspace:workspace.steps.approve` (`Workspace.tsx:189`)
- **test surface:** `tests/flowhub/write_pipeline/` (3 files),
  `Workspace.test.tsx`
- **evidence:** `app/flowhub/api/v2/write_pipeline.py:27,36,45`
  (`@router.post("/dry-run"...)`, `@router.get("/batches/{batch_id}"...)`,
  `@router.post("/batches/{batch_id}/approve"...)`); `app.py:230`;
  `BU5_INTEGRATIONS.md:24` — "Manual WooCommerce price execution... is
  available only through Preview, Row Selection, Dry Run, Approval,
  Manual Execute, Read-back Verification, and Audit" (prior approved
  architecture decision naming this exact flow)
- **notes:** **Do not confuse with** `app/flowhub/api/v2/dryrun.py` and
  `changesets.py` — these are separate, unimplemented stub routers (see
  [cross-cutting finding](#cross-cutting-finding-ten-dead-stub-routers)
  below) for a differently-scoped, unbuilt "Dry Run Engine" / "Change Set
  Engine" (B6 phase). The real, live Dry Run + Approval flow described
  here lives entirely inside `write_pipeline`, not those files.

#### `write_pipeline` — Write Pipeline

- **domain:** Write Pipeline
- **classification:** Core
- **audience:** Operator-facing (execution gated behind
  `require_write_operation_available`, `app/flowhub/maintenance.py`)
- **status:** IMPLEMENTED_UNVERIFIED — Owner-approved classification
  (overrides original estimate of `IMPLEMENTED`), for the same reason as
  Review & Approval directly above: static code/route/UI evidence only,
  no runtime verification performed.
- **maturity:** OPERATIONAL — unchanged from original estimate; not
  explicitly overridden
- **backend surface:** `app/flowhub/write_pipeline/{adapters.py,
  contracts.py,models.py,registry.py,service.py,workspace_contracts.py}`;
  `app/flowhub/maintenance.py` (`require_write_operation_available`)
- **API surface:** `app/flowhub/api/v2/write_pipeline.py` (mounted,
  `app.py:230`) — confirmed live routes: `POST
  /write-pipeline/batches/{batch_id}/execute`, `GET
  /write-pipeline/batches/{batch_id}/events`
- **UI surface:** `frontend/src/pages/Workspace.tsx` (`applying → result`
  phases), `frontend/src/pages/Products.tsx` (multi-channel price write
  path per `CURRENT_ARCHITECTURE.md`)
- **test surface:** `tests/flowhub/write_pipeline/` (3 files),
  `Workspace.test.tsx`, `Products.test.tsx`
- **evidence:** `app/flowhub/api/v2/write_pipeline.py:55,64`; `app.py:230`;
  `CURRENT_ARCHITECTURE.md` "the protected Write Pipeline is the only
  external WooCommerce write path... requires no-write Dry Run, explicit
  Approval, and Apply"
- **notes:** `CURRENT_ARCHITECTURE.md`'s Safety Model section explicitly
  scopes out stock writes, source writes, and automatic pricing/Apply for
  this capability — these are **prior-approved exclusions**, not gaps to
  flag. `execution.py` (the stub `/api/v2/execution` router) is unrelated
  dead code, not this capability's implementation — see cross-cutting
  finding.

### Supporting Capabilities

#### `diagnostics` — Diagnostics

- **domain:** Diagnostics
- **classification:** Supporting
- **audience:** Hybrid — base `channelHealth` read is shared by
  Dashboard + Diagnostics; explicit provider probes are
  "administrator-only" per `CURRENT_ARCHITECTURE.md`
- **status:** IMPLEMENTED_UNVERIFIED — Owner-approved classification
  (overrides original estimate of `IMPLEMENTED`; endpoint/text evidence
  is static, not a confirmed runtime check of live diagnostic output)
- **maturity:** OPERATIONAL — Owner-approved, unchanged from original
  estimate
- **backend surface:** `app/flowhub/diagnostics/{channel_health.py,
  repair.py,report.py,runner.py,semantics.py}`
- **API surface:** `app/flowhub/api/v2/diagnostics.py` (mounted,
  `app.py:236`) — `GET /diagnostics/status`, `GET
  /diagnostics/channels/health`, `POST
  /diagnostics/channels/health/refresh` (all named explicitly in
  `CURRENT_ARCHITECTURE.md`)
- **UI surface:** `frontend/src/pages/Diagnostics.tsx`, `DataQuality.tsx`
- **test surface:** `tests/flowhub/diagnostics/` (6 files),
  `Diagnostics.test.tsx`, `DataQuality.test.tsx`
- **evidence:** `app.py:236`; `CURRENT_ARCHITECTURE.md` "Health And
  Diagnostics" section
- **notes:** the diagram's proposed **Architecture Health** feature
  (Phase 4.3 of this document's own history — see
  [Appendix A](#appendix-a-phase-42-fine-grained-registry-original)),
  which would surface capability-registry violations through Diagnostics,
  is a documented future design, not part of current Diagnostics. Do not
  count it toward this entry's maturity.

#### `administration` — Administration

- **domain:** Administration
- **classification:** Supporting
- **audience:** Admin-facing
- **status:** PARTIAL — not separately corrected by the Owner; this
  draft's original evidence-based estimate already landed here and is
  consistent with the governance rule above (mixed real/stub evidence →
  `PARTIAL`, not rounded up)
- **maturity:** BASELINE — not separately corrected; same reasoning
- **backend surface:** `app/flowhub/security/{redaction.py,
  upstream_errors.py}`; `app/flowhub/users/{models.py,repository.py,
  service.py}`; `app/flowhub/runtime_config/{record.py,service.py}`;
  `app/flowhub/feature_flags/{defaults.py,evaluator.py,models.py}`;
  `app/flowhub/rate_limit/{limiter.py,service.py}`;
  `app/flowhub/backup/{manifest.py,service.py}` — all real service code
- **API surface:** **Split.** `app/flowhub/api/v2/settings_routes.py`
  (mounted, `app.py:231`) and `users.py` (mounted, `app.py:225`) and
  `config.py` (mounted, `app.py:233`) are real and live. But
  `app/flowhub/api/v2/flags.py`, `backup.py`, `rules.py`, `safety.py` are
  **present in the tree and never imported or mounted in `app.py`**
  (confirmed: absent from both the router-import block at `app.py:78-102`
  and the `include_router` block at `app.py:219-243`) — each is a stub
  router with a "# Endpoints implemented in B__" comment and zero routes.
- **UI surface:** `frontend/src/pages/Settings.tsx`,
  `AdvancedSettings.tsx`, `UserManagement.tsx`, `RateLimits.tsx`
- **test surface:** `tests/flowhub/users/` (1), `backup/` (5),
  `feature_flags/` (1), `runtime_config/` (5), `security/` (2),
  `tests/flowhub/api/v2/test_settings_routes.py`; frontend:
  `Settings.test.tsx`, `AdvancedSettings.test.tsx`,
  `UserManagement.test.tsx`, `RateLimits.test.tsx`
- **evidence:** `app.py:78-102,219-243` (router import/mount lists,
  compared against `ls app/flowhub/api/v2/`); stub file headers in
  `flags.py`, `backup.py`, `rules.py`, `safety.py`
- **notes:** Rate Limits parity is confirmed: `RateLimits.tsx` calls
  `ApiSettingsService`, which uses the mounted
  `GET/POST /api/v2/settings/rate-limits` routes backed by
  `RateLimitService`; backend authorization and frontend behavior have
  regression coverage. Backup and feature-flag service modules remain
  separate from their intentionally unmounted TARGET router stubs. This
  confirmation does not change the Owner-approved domain maturity.

#### `audit_governance` — Audit & Governance

- **domain:** Audit & Governance
- **classification:** Supporting
- **audience:** Hybrid — `activity.py` uses
  `require_workspace_permission`, a broader gate than admin-only; exact
  role set **NEEDS_VERIFICATION**
- **status:** PARTIAL — not separately corrected by the Owner; consistent
  with the governance rule (a real working surface plus a dead-stub
  module both named for this capability → `PARTIAL`, not `IMPLEMENTED`)
- **maturity:** BASELINE — not separately corrected; same reasoning
- **backend surface:** **Two distinct code paths, not one:**
  1. Real: `app/flowhub/auth/repository.py` (`create_audit_event`, used
     by `settings_routes.py`), `FlowHubLoginAudit` model
     (`app/flowhub/auth/models.py`), `UnifiedAuditEntry` model
     (`app/flowhub/unified_workspace/models.py`).
  2. Stub, dead code: `app/flowhub/audit/logger.py` — `AuditLogger.log()`
     literally `raise NotImplementedError("Implementation begins in
     B10.")`; docstring claims it "writes structured audit events to
     `FLOWHUB_STORAGE_PATH/logs/audit.log`" and "every security-relevant
     event is recorded" — none of that is true yet. Grep confirms
     `AuditLogger`/`from app.flowhub.audit` has **zero references**
     anywhere else in `app/`.
- **API surface:** `app/flowhub/api/v2/activity.py` (mounted,
  `app.py:234`) — `GET /api/v2/activity`, real, BU5-scoped, backed by
  `FlowHubLoginAudit` + `UnifiedAuditEntry`
- **UI surface:** `frontend/src/pages/Activity.tsx`
- **test surface:** `Activity.test.tsx`; `tests/flowhub/audit/` — **no
  test files found** (directory absent/empty)
- **evidence:** `app/flowhub/audit/logger.py:23-28`; grep for
  `AuditLogger|from app.flowhub.audit` across `app/` returning only
  `audit/logger.py` itself; `app.py:234`; `activity.py:1-10` docstring
  "Paginated audit event log. Backed by the flowhub_login_audit table."
- **notes:** the operator-facing surface (Activity page) genuinely works.
  But the module whose name matches this capability
  (`app/flowhub/audit/`) is entirely unimplemented and unused — a
  filename-only read would have wrongly credited this capability with a
  dedicated audit-logging subsystem. **Owner should clarify** whether
  `app/flowhub/audit/logger.py` is (a) superseded by `create_audit_event`
  and should be deleted, or (b) still planned (per its B10 marker) and
  should eventually replace/supplement it.

#### `business_observability` — Business Observability

- **domain:** Business Observability
- **classification:** Supporting
- **audience:** Hybrid (diagram: "Owner / Admin / Operator")
- **status:** PARTIAL — Owner-approved classification (overrides this
  draft's original estimate of `NOT_IMPLEMENTED`). Reason (Owner):
  Dashboard/Activity/Audit surfaces provide *partial* business
  visibility today, but the target structured business-event contract
  (status + impact + reason + affected scope + recommended action +
  correlation) does not yet exist consistently — so the capability is
  not simply absent, it is unevenly and informally covered.
- **maturity:** FOUNDATION — Owner-approved, unchanged from original
  estimate
- **backend surface:** no dedicated `business_event`/structured-contract
  code found (see evidence below); partial, informal coverage exists via
  `app/flowhub/audit/`-adjacent and dashboard/activity code cited in the
  `audit_governance` and `diagnostics` entries above
- **API surface:** no dedicated endpoint implementing the structured
  contract; `GET /api/v2/activity` (see `audit_governance`) and dashboard
  endpoints carry informal, non-contractual business-relevant data
- **UI surface:** no dedicated UI implementing the structured contract;
  `Activity.tsx` and `Dashboard.tsx` surface related but non-conformant
  information
- **test surface:** none found for a structured business-event contract
  specifically
- **evidence:** `docs/draw/00-flowhub-master.drawio` nodes
  `business_observability_group`, `business_observability_capability`,
  `business_observability_layer`, `business_event_contract`,
  `business_observability_rule` — every one explicitly labeled
  `TARGET / PROPOSED — ⚠ VERIFY`; grep for
  `business.observability|business_event|BusinessEvent` (case-insensitive)
  across `app/` and `frontend/src` returned **zero matches** in either
  tree
- **notes:** this draft's original static-evidence read found **zero**
  code matches for `business_event`/`BusinessEvent`/"business
  observability" anywhere in `app/` or `frontend/src` and concluded
  `NOT_IMPLEMENTED`. The Owner's `PARTIAL` correction does not dispute
  that evidence — it reframes the question: the *contract-shaped*
  capability (structured business events) is indeed absent, but the
  *business outcome* the capability exists to serve (an operator being
  able to see what happened and what to do about it) is partially met
  today through Dashboard/Activity/Diagnostics, informally and
  inconsistently. This is the clearest example in this registry of why
  repository evidence alone cannot set business-capability status: code
  absence proved one thing (no contract exists); it could not by itself
  determine whether the business need is nonetheless partly served
  elsewhere. The diagram proposes a "Structured Business Event Contract"
  (capability/domain, status, business impact, reason, affected scope,
  recommended operator action, timestamp/correlation reference) that is
  explicitly distinct from the existing, already-implemented Unified
  Logging Platform (`CURRENT_ARCHITECTURE.md` "Unified Logging Platform"
  section — structured *technical* logs, correlation IDs, redaction).
  The diagram itself draws this distinction via its "Separate
  Observability Layers" box (Technical Observability vs. Business
  Observability) — do not treat Unified Logging Platform as satisfying
  this capability.

---

## Cross-cutting finding: ten dead stub routers

While tracing API surface for the entries above, ten files under
`app/flowhub/api/v2/` were found to define an `APIRouter` with a
docstring naming a future build phase, but are **not imported anywhere in
`app/flowhub/app.py`** (verified against both the import block,
`app.py:78-102`, and the `include_router` block, `app.py:219-243`):

| File | Prefix | Docstring phase marker |
| --- | --- | --- |
| `dryrun.py` | `/dryrun` | "Implementation begins in B6." |
| `changesets.py` | `/changesets` | "Implementation begins in B6." |
| `execution.py` | `/execution` | "Implementation begins in B7." |
| `rules.py` | `/rules` | "Implementation begins in B5." |
| `safety.py` | `/safety` | "Implementation begins in B5." |
| `flags.py` | `/flags` | "Implementation begins in B11." |
| `backup.py` | `/backup` | "Implementation begins in B13." |
| `ai.py` | `/ai` | TARGET stub; no routes |
| `plugins.py` | `/plugins` | TARGET stub; no routes |
| `scheduler.py` | `/scheduler` | TARGET stub; no routes |

None of these have live endpoints today, regardless of what their
filenames suggest. This is exactly the failure mode the task instructions
warned against ("do not infer implementation from filenames only") and is
recorded here as a standing caveat for anyone reading `ls
app/flowhub/api/v2/` and assuming coverage.

The architecture diagrams confirm all ten as intentionally unmounted planned
surfaces. Their existence is not permission to mount or implement them.

---

## Remaining verification and Owner-decision items

Consolidated list of items still needing runtime or Owner verification beyond
what repository reading and executable tests could settle, per the governance
rule above.

1. **Ten unmounted/stub API routers** (`dryrun.py`, `changesets.py`,
   `execution.py`, `rules.py`, `safety.py`, `flags.py`, `backup.py`,
   `ai.py`, `plugins.py`, `scheduler.py`) — mount status and zero-route
   state are confirmed. Their disposition remains an Owner decision; they
   must not be mounted merely because the files exist.
2. **`app/flowhub/audit/logger.py` disposition** — see `audit_governance`
   entry above. `AuditLogger.log()` raises `NotImplementedError` and has
   zero references anywhere else in `app/`, while a separate, real audit
   trail (`create_audit_event` + `FlowHubLoginAudit`/`UnifiedAuditEntry`)
   already does the job. Verify: delete the stub, or is B10 still planned
   to supersede the working path?
3. **Legacy Product Channel Price API removal** — the old
   `/{product_id}/channel-prices` compatibility facade has no current frontend
   caller. Operator editing is provided by Products through Unified Workspace.
   An Owner must decide the public/API compatibility window before removal; this
   is not a UI-parity gap.
4. **Legacy deployment state** — active import and entrypoint reachability
   from FlowHub, CLI, canonical migrations, Docker, workers, and installer
   paths is now confirmed absent and enforced by
   `tests/flowhub/test_no_direct_httpx.py`. The deployed database state of
   quarantined `app/a2` remains an external operational verification item;
   no legacy files are approved for deletion.

5. **Business Observability contract coverage** — see
   `business_observability` entry above. The structured contract remains
   TARGET / PROPOSED; Dashboard, Activity, and Diagnostics provide the
   Owner-approved partial informal coverage. Defining or implementing the
   target requires an Owner decision.

## Resolved verification evidence

- **Rate Limits API mapping:** `RateLimits.tsx` → `ApiSettingsService` →
  mounted `GET/POST /api/v2/settings/rate-limits` → `RateLimitService`, with
  backend authorization and frontend regression tests.
- **Legacy active reachability:** no active runtime, deployment, CLI, worker,
  canonical migration, or installer boundary imports or launches
  `app.main`, `app.services`, or `app.a2`; the architecture guard enforces
  this quarantine.
- **Shadow Validation migration:** forward-only revision `FLOWHUB_030` creates
  the `sv_*` persistence schema and is followed by active head
  `FLOWHUB_031`; executable migration tests cover creation and downgrade
  rejection. C5 orchestration remains TARGET / PROPOSED.
- **Product Channel Price operator parity:** `Products.tsx` through catalog
  Unified Workspace and `DensePricingWorkspace` provides the current editable
  multi-channel price path. The older Product Pricing API remains a tested,
  UI-unreferenced compatibility facade and is not an operator UI gap.

---

## Appendix A: Phase 4.2 fine-grained registry (original)

Everything below this line is preserved unchanged from the original
version of this document (the "design only" Phase 4.2 draft). It defines
a different, narrower-granularity schema (per named feature rather than
per domain) and its own four-row illustrative seed set. It is kept intact
rather than merged into Part A above, per the instruction to treat prior
approved architecture decisions as evidence to build on, not overwrite.

### Schema

| Field | Type | Meaning |
| --- | --- | --- |
| `capability_id` | string | Stable short identifier, snake_case. |
| `domain` | enum | One of: `Sources`, `Channels`, `Pricing`, `Review & Approval`, `Diagnostics`, `Administration`, `Audit & Governance`. |
| `status` | enum | `operator_facing` or `internal_only` (see below). |
| `backend_ref` | path or module reference | Where the capability's logic lives. |
| `api_ref` | path/route reference, nullable | The callable endpoint(s), if any. |
| `ui_ref` | path/route reference, nullable | The frontend surface, if any. |
| `test_ref` | path reference(s) | Test(s) exercising the capability. |
| `exemption_reason` | string, nullable | Required when `status = operator_facing` and `api_ref` or `ui_ref` is null. Free text, one line, human-written. |

### Status rules

**`operator_facing`** — an Owner, Admin, or Operator directly interacts with
this capability (configures it, reviews it, approves it, reads its output).
Requires `backend_ref`, `api_ref`, `ui_ref`, and `test_ref` all populated,
*or* a non-null `exemption_reason` explaining why one is missing (e.g. a
phased rollout where backend/API landed ahead of UI).

**`internal_only`** — plumbing that no Owner/Admin/Operator ever addresses
directly: adapters, gateways, locking, transaction/CAS mechanics, migration
engine, worker internals. Requires `backend_ref` and `test_ref` only.
`api_ref`/`ui_ref` are not required and are typically null.

The rule is deliberately asymmetric: `internal_only` is a narrow, named
exclusion list (matching the diagram's principle text verbatim), not a
default anyone can reach for. Changing an entry's `status`, or adding an
`exemption_reason`, is a human-reviewed edit — this design does not attempt
to make that judgment mechanically (see Phase 4.3 design below on why
that stays a warning surface, not a CI-blocking one).

### Illustrative seed set

Four entries, each verified against the current tree at the time this
document was written. This is not a claim of completeness — it exists to
show the schema handling one fully-covered case, one honest gap, and two
`internal_only` entries.

| `capability_id` | `domain` | `status` | `backend_ref` | `api_ref` | `ui_ref` | `test_ref` | `exemption_reason` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `trusted_private_networks_setting` | Administration | `operator_facing` | [`app/flowhub/integrations/nextcloud.py`](../../app/flowhub/integrations/nextcloud.py) | [`app/flowhub/api/v2/settings_routes.py`](../../app/flowhub/api/v2/settings_routes.py) | [`frontend/src/pages/AdvancedSettings.tsx`](../../frontend/src/pages/AdvancedSettings.tsx) | `tests/flowhub/api/v2/test_settings_routes.py`, `tests/connectors/sources/test_nextcloud_webdav.py` | — |
| `product_channel_price_editor` | Pricing | `operator_facing` | [`app/flowhub/product_pricing/service.py`](../../app/flowhub/product_pricing/service.py) | [`app/flowhub/api/v2/products.py`](../../app/flowhub/api/v2/products.py) (`/{product_id}/channel-prices`) | *null* | `tests/beta/test_multi_channel_pricing.py` | **NEEDS OWNER REVIEW** — backend and API are implemented; no dedicated frontend surface was found under `frontend/src/pages`. Confirm whether UI is scheduled, intentionally backend/API-only for now, or a real gap. |
| `channel_gateway_resolution` | Channels | `internal_only` | [`app/flowhub/channels/gateway.py`](../../app/flowhub/channels/gateway.py) (`WorkspaceConnectorFactory`) | *n/a* | *n/a* | `tests/flowhub/channels/test_gateway.py` | *n/a* |
| `source_http_transport_boundary` | Sources | `internal_only` | [`app/connectors/common/source_http.py`](../../app/connectors/common/source_http.py) (`SourceHttpClient`) | *n/a* | *n/a* | `tests/flowhub/test_no_direct_httpx.py`, `tests/connectors/sources/test_nextcloud_webdav.py` | *n/a* |

The second row is intentionally left as a real, currently-true gap rather
than a clean example — it is the exact shape of finding the future
Architecture Health surface (Phase 4.3/4.4) is meant to raise: not a CI
failure, a question for a human. **This draft's Part A above independently
re-found the same gap** (see `pricing_intelligence` notes) — it remains
unresolved.

### Where this would live if promoted

Not decided here — that is an implementation question for a later phase,
not a design-only one. Candidates worth weighing then: a single file (keeps
the "small enumerable set" property visible in one diff) versus one entry
per domain module (keeps ownership local to the team that owns the domain).
This document takes no position beyond keeping the seed table above small
enough that the question doesn't matter yet.

---

### Phase 4.3 design (not implemented): Architecture Health

Matches the diagram's `architecture_health` node: *"Exposes existing
violations to Owner/Admin through FlowHub Diagnostics."*

- A read-only report, not a gate. Consumes the registry above (once it has
  a real population) and lists `operator_facing` entries with a missing
  `api_ref` or `ui_ref` and no `exemption_reason`.
- Natural host: [`app/flowhub/diagnostics/`](../../app/flowhub/diagnostics/)
  (alongside `report.py`, `channel_health.py`), following the same shape as
  existing diagnostics reports — a function that returns structured findings,
  not a new subsystem.
- Explicitly **not** a CI check. It answers "what's currently incomplete,"
  which is a roadmap question, not a merge-blocking one. Tier separation
  (blocking guard tests in CI vs. warning-only health report in Diagnostics)
  is why Phase 4.3 stays a design note here rather than code: building it
  now, before the registry has real content or an owner has signed off on
  the seed set, risks exactly the "large governance framework" this phase
  was told to avoid.
- Open question for the Phase 4.3 plan itself: whether findings surface via
  an existing diagnostics endpoint/report or need a new one — not decided
  here.

### Phase 4.4 design (not implemented): Diagnostics integration

- Wires the Phase 4.3 report into whatever Diagnostics already exposes to
  Owner/Admin (UI page, CLI, or existing report endpoint — to be determined
  by whoever plans 4.4, informed by how `diagnostics/report.py` and
  `diagnostics/runner.py` currently surface their output).
- No new UI framework, no new permission model: reuses existing
  Diagnostics access control as-is.
- Depends on 4.3 existing and on the registry (4.2) having been reviewed
  and populated beyond the four illustrative rows above — sequencing, not
  parallelizable with 4.2.
