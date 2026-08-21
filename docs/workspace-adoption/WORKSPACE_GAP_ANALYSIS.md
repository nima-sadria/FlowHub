# FlowHub Workspace Gap Analysis

## Severity Definitions

- **P0:** safety, authorization, or write-integrity defect.
- **P1:** core workflow, recovery, or contract defect.
- **P2:** explainability, consistency, or maintainability gap.

## Authorization Gaps

| ID | Severity | Current behavior | Target behavior | Disposition |
| --- | --- | --- | --- | --- |
| AUTH-001 | P0 | `/api/auth/me` returned legacy `can_*` permissions only | Return canonical Workspace permissions plus compatibility aliases | Resolved in `557e221` |
| AUTH-002 | P0 | Source and Workspace routes used `can_access_site` or `can_fetch` | Route guards use `workspace.read`, `workspace.create`, and related capabilities | Resolved in `557e221` |
| AUTH-003 | P0 | Viewer could reach Source creation/import/edit controls | Mutating controls require their exact capability; viewer remains read-only | Resolved in `557e221` |
| AUTH-004 | P1 | Any API 403 changed the whole app to `permission_denied` | Action-level 403 remains local; only `/auth/me` defines global access state | Resolved in `557e221` |
| AUTH-005 | P0 | Maintenance write guard allowed admin roles only, while role policy granted operators `apply.execute` | Enforce `apply.execute`; retain owner/super-admin maintenance bypass | Resolved in `557e221` |
| AUTH-006 | P2 | Permission strings were repeated in frontend code | Use typed/shared frontend constants without introducing a new framework | Resolved in `557e221` |

## Workflow Gaps

| ID | Severity | Current behavior | Target behavior | Disposition |
| --- | --- | --- | --- | --- |
| WS-001 | P1 | Legacy `/workspace` and unified `/workspace/:id` coexist as separate user workflows | One canonical Workspace entry and lifecycle | Owner decided (OD-004): Unified Workspace is canonical; legacy `/workspace` deprecated on a later timeline. Route consolidation itself not yet implemented. |
| WS-002 | P0 | Unified Apply button saves selection and immediately sends `confirmed: true` | Separate confirmation bound to exact approved Review/operation scope | Owner approved (OD-005): in progress, see Apply Manifest feature in `WORKSPACE_IMPLEMENTATION_PHASES.md` Phase 3 |
| WS-003 | P1 | Unified Review is the approval boundary, but no presentation contract identifies an exact operation manifest for confirmation | Persist or expose exact intended operations and checksum before confirmation | Owner approved (OD-005): resolved by the same Apply Manifest feature as WS-002 |
| WS-004 | P1 | Legacy Workspace uses a separate Preview/Dry Run/Approval/Write Pipeline facade | Canonical state names and recovery behavior across entry points | Owner decision required |
| WS-005 | P2 | Presentation preferences use `workspace.read` for writes | Decide whether preferences are presentation-only read capability or need a dedicated permission | Keep current behavior pending evidence |

## Source and Sheet Gaps

| ID | Severity | Current behavior | Target behavior | Disposition |
| --- | --- | --- | --- | --- |
| SRC-001 | P1 | Source Configuration rendered editable controls for all readers | `workspace.read` can inspect; `workspace.edit` enables mapping mutation | Resolved in `557e221` |
| SRC-002 | P1 | FlowHub Sheet rendered editable cells/actions for all route users | `workspace.read` can inspect; `draft.save` enables revision mutation | Resolved in `557e221` |
| SRC-003 | P1 | Add Source and import entry points were visible without `workspace.create` | Creation paths require `workspace.create` in route and component | Resolved in `557e221` |
| SRC-004 | P2 | External connector setup appeared to non-admin Source creators | Preserve Sources/Channels separation and backend admin policy | Resolved in `acaff4d` |
| SRC-005 | P1 | Total Source-list failure rendered an empty state with no recovery | Preserve partial results; show retry when both authoritative lists fail | Resolved in `2e836ef` |

## Contract and Recovery Gaps

| ID | Severity | Current behavior | Target behavior | Disposition |
| --- | --- | --- | --- | --- |
| CON-001 | P1 | Browser could not distinguish all backend Workspace capabilities | `/api/auth/me` is the canonical frontend capability contract | Resolved in `557e221` |
| CON-002 | P1 | Action-level permission denial could destroy authenticated UI state | Preserve session and render local error | Resolved in `557e221` |
| CON-003 | P2 | Permission model is role-derived in code | Role-derived policy is acceptable until custom grants are approved | No schema change |
| CON-004 | P2 | Reference specification is present only in the Owner working tree during this audit | Adoption docs record reviewed filenames; reference publication remains Owner-controlled | Documented risk |

## Page Integration Findings

| ID | Page | Severity | Root cause | Layer | Disposition |
| --- | --- | --- | --- | --- | --- |
| UI-001 | Channels | P1 | Primary list rejection had no error/retry state | Frontend | Resolved in `acaff4d` |
| UI-002 | Channels | P1 | Add/Configure controls were visible to readers although backend requires admin | Frontend/contract | Resolved in `acaff4d` |
| UI-003 | Channels | P2 | KPI numbers used host locale instead of FlowHub locale | Frontend | Resolved in `acaff4d` |
| UI-004 | Sources | P1 | Sheet creation rejection escaped without user feedback | Frontend | Resolved in `acaff4d` |
| UI-005 | Orders | P1 | Detail rejection was swallowed and left no recovery message | Frontend | Resolved in `acaff4d` |
| UI-006 | Activity | P1 | Primary history rejection escaped its async handler | Frontend | Resolved in `b0615d8` |
| UI-007 | Sources | P1 | Total Source-list rejection looked like a valid empty state | Frontend | Resolved in `2e836ef` |

## Phase B Business Classification Gaps

Found by an Owner-reference-specification review (Price/Quantity/Stock Status/
Warning/Eligibility classification, `WORKSPACE_PHASE_B_CHANGE_BADGES_PLAN.md`)
of the badge/classification engine shipped through `feat/workspace-phase-b-completion`.
Reviewed against `main`@`0aaae4b`.

| ID | Severity | Current behavior | Target behavior | Disposition |
| --- | --- | --- | --- | --- |
| CLS-001 | P0 | `ChannelCache.status` (`_cache_payload`) fell back to `row.status` (provider publication: `publish`/`draft`/`private`) whenever `row.stock_status` was falsy-checked via `or`; `row.status` is truthy for virtually every product, so the cache's canonical-availability field silently held a publication string the precedence engine never recognizes. No Stock Status Manifest operation was ever proposed for a normal published product, and the same value corrupted Dry Run status verification. | `ChannelCache.status` holds only `row.stock_status` (provider-neutral `instock`/`outofstock`/`onbackorder`); publication state never enters it. | Resolved in `d46bde7` |
| CLS-002 | P0 | Identity resolution (`app/flowhub/source_workspace/service.py`, ~15 sites) and the shared `canonical_text` helper (`app/flowhub/unified_workspace/domain.py`) built Channel/Source identifiers with `str(value or "").strip()`, which collapses a literal identifier value of `0` to blank -- identical to a truly missing identifier -- so a Channel that legitimately uses `0` as a Product Identifier had that row silently excluded/blocked (`missing_mapping_identity`), contradicting the Owner rule that identifier sentinels `x`/`-`/`0` must reach the connector's identifier contract unchanged. | Only `None` (or a value that is itself blank after stripping) normalizes to `""`; a present `0`/`0.0` identifier is preserved and passed through. | Resolved in `d46bde7` |
| CLS-003 | P0 | `normalize_direct_price` had no `mapped` parameter (unlike `normalize_quantity`/`normalize_stock_status`, which both already had one); `_classify_channel_targets` substituted a bare `None` for an unmapped Price field, and `resolve_availability` crashed with `AttributeError: 'NoneType' object has no attribute 'blocker_code'` for any classification where a Channel doesn't map Price. This crashed several pre-existing identity/classification tests (confirmed pre-existing via clean-`main` comparison). | `normalize_direct_price(..., mapped=False)` returns a proper `NO_INSTRUCTION` field, matching the Quantity/Status pattern. | Resolved in `d46bde7`; fixed 7 previously-failing tests as a result (`tests/flowhub/source_workspace/test_identity_authority_architecture.py`) |
| CLS-004 | P1 | `Review.status` was gated on `eligible_count`, which requires an item to be both safe *and* actionable (changed). A Draft whose changes were all no-ops (target equals current) produced `Review.status: "blocked"` with an "Eligible" count of zero, even though nothing was unsafe -- contradicting the Owner rule that an unchanged row remains `ELIGIBLE`, merely not actionable. | A distinct `safe_count` (items with no `errors`, regardless of unchanged) gates `Review.status`; an all-unchanged Review is `ready`, not `blocked`. | Resolved in `d46bde7` for `Review.status`. `ReviewItem.eligible` itself still means "safe AND actionable" for its original, correct purpose (auto-selection defaults, Apply-selection gating at `select_review_items`/`apply_selected`) -- splitting that into two persisted/exposed concepts touches ~8 interdependent call sites and needs dedicated test coverage; deferred, see CLS-006. |
| CLS-005 | P1 | The Review dialog (`ReviewScopePresentation` in `DensePricingWorkspace.tsx`) rendered the Owner-facing per-item and per-row Eligible/Blocked badge directly from `item.eligible`, so a merely-unchanged (safe, no-op) field displayed as "Blocked" with no actual defect. | Badge treats `validationState === 'unchanged'` as safe/Eligible, matching backend `ReviewItem.validation_state`'s existing three-way distinction (error/unchanged/warning-or-ready). | Resolved in `d46bde7` |
| CLS-006 | P2 | `ReviewItem.eligible` (backend) conflates row safety with actionability by design (see CLS-004). No first-class distinction exists between "safe" and "safe AND actionable" for the persisted/API-exposed value; the frontend fix (CLS-005) works around it via `validationState` instead. | Introduce a genuinely separate `actionable` concept (derivable at read time via `values_equal(field, current_value, target_value)` without a schema migration) and audit each of `services.py`'s ~8 `item.eligible`/`item["eligible"]` call sites for which concept it actually wants. | Deferred -- Owner decision on scope/timing recommended before touching Apply-selection gating logic |
| CLS-007 | P1 | Badge staleness is unimplemented: an unsaved local grid edit does not clear or mark the neighboring server-computed change badge as stale; it keeps asserting the pre-edit classification until the Draft is saved and reclassified. | Per the Owner spec: "the UI must clear or visibly mark the old badges as stale until the edited Draft is saved and reclassified." | Deferred |
| CLS-008 | P1 | The Review dialog cannot render the four-dimension change classification (Price/Quantity/Status/Warning) an Owner already saw in the grid, because `ReviewItemResource` carries only raw `field`/`current`/`target`, not `changeClassification` -- a DTO gap, not a rendering oversight. | Review read model carries the same immutable classification shown in Preview. | Deferred |
| CLS-009 | P1 | Percentage price delta is never computed (`_change_badge_shape`) or rendered, despite being a named, repeated element of the Price badge across the Owner spec (e.g. "Price ↑ 50,000 · 4.2%"). | Compute and expose `percentage_delta` alongside the existing absolute `delta`. | Deferred |
| CLS-010 | P2 | `ChangeBadges` renders no badge for `UNCHANGED`/`NOT_EVALUATED` Price or Quantity states (Stock Status already renders all four of its states), so neutral rows compose incompletely versus the Owner's example presentation ("Price unchanged · No quantity instruction · In stock · Eligible"). | Render a neutral badge for every dimension's unchanged/not-evaluated state, matching Stock Status's existing pattern. | Deferred |
| CLS-011 | P2 | Grid inline price/stock editors show the raw unformatted value (no thousands grouping) when not actively being edited; `Dashboard.tsx`'s USD formatter bypasses the shared `formatMoney` (uses a JS `number`, a precision-loss risk above `2^53`); badge text embeds numeric/Latin runs with no RTL bidi isolation. | Route every Owner-facing financial value through the one shared grouped formatter; isolate embedded LTR numerics inside RTL badge text. | Deferred |
| CLS-012 | P2 | Warning badges are i18n-templated, but the interpolated `{code}` is always the raw English enum with underscores replaced by spaces (e.g. "LARGE PRICE CHANGE"), never a per-code localized message -- a Persian-locale Owner sees embedded English. | Per-warning-code localized message keys. | Deferred |
| CLS-013 | P2 | Canonical Decimal/exact-text values are used correctly through classification and comparison (`domain.py`), but downstream write-path contracts still type price/stock as `float`: `WorkspaceWriteIntent` (`write_pipeline/workspace_contracts.py`), `ChannelProduct`/`ChannelProductUpdate` (`channels/contracts.py`), `WriteItemContract` (`write_pipeline/adapters.py`); the WooCommerce REST client formats price with Python `.2f` after a float boundary. For realistic RIAL/TOMAN magnitudes this does not currently produce a wrong value (float is exact well past real-world price magnitudes), but it is latent precision debt against the "no binary float may cross into ... governed write intent" invariant. | Plumb exact Decimal/canonical-integer text through the write pipeline to the connector boundary. | Deferred -- recommend a dedicated pass, not a incidental fix |
| CLS-014 | P2 | `SnappShopWorkspaceConnector`/`TapsiShopWorkspaceConnector`/`TechnolifeWorkspaceConnector` still declare `write_status=False` (WooCommerce alone was upgraded to `write_status=True` in `8bb1e51`). | Per Owner policy this is a legitimate "fail safely through the canonical model" posture, not a defect, until each connector's provider-neutral availability write contract is declared and tested. | Not a gap -- recorded as a known, intentional scope boundary |
| CLS-015 | P2 | Legacy `POST /api/v2/workspace/preview` (backend route, `price_workflow.py`) remains mounted/importable and still float-based/pre-badge; the frontend `/workspace` route redirects to `/products` (`d49d0e4`) so no UI reaches it, but `frontend/src/pages/Workspace.tsx` and its `product_name_mismatch` translations/tests are dead code left in place rather than deleted. | Remove the legacy backend route and dead frontend page/translations/tests once WS-001's route-consolidation timeline is decided. | Confirms WS-001's scope also covers the backend route, not only the frontend page |

The full backend suite (3,955 collected) was run before and after this
change: 3,942 passed both times, with the identical 13 pre-existing failures
present in both runs (confirmed via clean-`main` comparison, none newly
introduced) -- left untouched as out of this review's scope:
`tests/flowhub/source_workspace/test_worksheet_rules.py::test_per_worksheet_rules_replay_local_evidence_with_different_layouts`,
`test_source_preview_business_summary_uses_source_keys_not_duplicate_names`,
`test_cost_only_row_participates_in_identity_validation_but_blank_row_is_ignored`;
`tests/flowhub/source_workspace/test_workspace_integration.py::test_source_product_workspace_groups_listings_and_auto_selects_ready_changes`;
`tests/flowhub/unified_workspace/test_connectors.py::test_woocommerce_adapter_validates_verifies_and_redacts_provider_failures`;
and eight in the legacy Commerce Hub suite (`test_commerce_hub.py`) (`test_nextcloud_manual_read_now_uses_mapping_and_never_writes`,
`test_explicit_source_profile_read_retains_dataset_when_legacy_parser_finds_no_rows`,
`test_detect_worksheets_reuses_the_new_snapshot_without_double_counting`,
`test_failed_outbound_source_read_consumes_reserved_quota`,
`test_concurrent_source_reads_cannot_exceed_atomic_quota`,
`test_source_profile_read_quotas_are_independent_and_shared`,
`test_source_read_allowance_resets_after_24_hours`,
`test_duplicate_rows_are_errors_and_manual_read_counts_reconcile`).
CLS-003's `normalize_direct_price` fix additionally turned 7 previously
crashing/failing tests green (counted in the 3,942 passed above), which is
why the net pass count improved even though this change targeted different
files.

## Integration Audit Status

The authorization-contract HOLD is resolved. The page-by-page audit is
complete and all non-architectural findings above are committed. WS-001
through WS-003 are no longer HOLD: OD-004/OD-005 record the Owner's
architecture decisions, and WS-002/WS-003 are being implemented as the Apply
Manifest feature. WS-001's route-consolidation mechanics remain future work.
WS-004 and WS-005 remain open.
