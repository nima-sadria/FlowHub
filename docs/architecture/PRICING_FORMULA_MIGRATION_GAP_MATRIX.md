# Pricing Formula Migration Gap Matrix

This matrix compares the approved target architecture against the current RC1
repository state.

## Legend

- **Implemented**: present and enforced in RC1.
- **Partial**: present, but only as a compatibility or freshness boundary.
- **Missing**: not implemented in RC1.

## Gap matrix

| Capability | State | Evidence files | Risk | Prerequisite / dependency |
|---|---|---|---|---|
| Per-Channel authority state (`legacy_formula_engine` / `migration_locked` / `pricing_matrix`) | Missing | `app/flowhub/pricing_matrix/models.py`, `app/flowhub/write_pipeline/service.py`, `app/flowhub/product_pricing/service.py` | Legacy writes and new writes are distinguishable only by workflow labels, not by persisted authority state. | Add a persisted Channel authority model and lifecycle transitions. |
| Shared production write boundary | Implemented | `app/flowhub/write_pipeline/service.py`, `app/flowhub/unified_workspace/services.py`, `app/flowhub/product_pricing/service.py` | Low | None. |
| Legacy direct write path still present | Partial | `app/main.py`, `app/services/woocommerce.py` | Reachable only through the legacy compatibility app, but still a direct WooCommerce path in code. | Cutover or decommission legacy runtime routes. |
| Originating engine identity on write command | Missing | `app/flowhub/write_pipeline/workspace_contracts.py`, `app/flowhub/write_pipeline/service.py` | Pipeline cannot reject based on source engine authority. | Add authority identity to the write command and persist it. |
| Authority rejection before dispatch | Missing | `app/flowhub/write_pipeline/service.py`, `app/flowhub/unified_workspace/services.py` | Non-authoritative candidates are not rejected as such; only freshness/config failures are. | Authority model plus pre-dispatch guard. |
| Authority rejection after Review but before dispatch | Missing | `app/flowhub/unified_workspace/services.py`, `app/flowhub/write_pipeline/service.py` | Review can become stale, but that is not the same as a pricing-authority lock. | Persisted Channel authority state and review-time snapshot. |
| Workspace fence / lease / CAS enforcement | Implemented | `app/flowhub/unified_workspace/services.py`, `app/flowhub/write_pipeline/service.py` | Protects concurrency and consistency, not authority. | None. |
| Channel head / activation enforcement | Implemented | `app/flowhub/pricing_matrix/models.py`, `app/flowhub/pricing_matrix/service.py` | Ensures policy activation freshness, not engine ownership. | None. |
| Frozen Evaluation Package | Partial | `app/flowhub/pricing_matrix/models.py`, `docs/architecture/PRICING_MATRIX_DESIGN.md` | Some required pieces exist as bindings and snapshots, but there is no dedicated cutover authority package model. | Formal package model for source observation, FX snapshot, revision pins, and quote fingerprints. |
| Shadow Validation | Partial | `docs/architecture/PRICING_MATRIX_DESIGN.md`, `app/flowhub/pricing_matrix/service.py` | Evidence-only comparison is specified, but the migration activation gate is still intentionally disabled. | Real inventory, fixtures, and explicit cutover approval. |
| Comparison confidence / divergence classification | Partial | `docs/architecture/PRICING_MATRIX_DESIGN.md` | The design is documented; repo evidence for complete persistent comparison records is still incomplete. | Comparison record model and evidence-backed fixtures. |
| Legacy replay adapter | Missing | `docs/architecture/PRICING_MATRIX_DESIGN.md`, `app/main.py` | Current legacy replay capability is not assumed; rollback safety depends on evidence. | Deterministic legacy replay implementation. |
| Formula inventory completion | Missing | `docs/architecture/PRICING_MATRIX_DESIGN.md`, `docs/architecture/ADR_PRICING_MATRIX.md` | Appendix A is still a checked-in allowlist, not a completed inventory artifact. | Real inventory pass over the production workbook. |
| Fixture-backed translation for all supported shapes | Partial | `docs/architecture/PRICING_MATRIX_DESIGN.md`, `tests/flowhub/pricing_matrix/*` | Appendix A covers only shapes explicitly confirmed in the design; remaining shapes are unresolved. | Fixtures for every supported formula shape. |
| 255 broken formulas classified | Missing | `docs/architecture/ADR_PRICING_MATRIX.md`, `docs/architecture/PRICING_MATRIX_DESIGN.md` | Unknown formulas remain feature-activation blockers. | Translation/quarantine classification of every broken formula. |
| Manual / external pricing inputs immutable and versioned | Partial | `docs/architecture/PRICING_MATRIX_DESIGN.md`, `app/flowhub/source_workspace/service.py` | Some inputs are already revisioned, but the target architecture still needs full cutover semantics. | Explicit source-of-truth records for manual, vendor, API, and override inputs. |
| Legacy write authority disabled after cutover | Missing | `app/main.py`, `app/services/woocommerce.py`, `app/flowhub/write_pipeline/service.py` | Legacy compatibility code still exists and is not authority-gated by the new model. | Authority-state enforcement and route deprecation/cutover. |

## Summary

RC1 already has:

- a unified shared write boundary;
- append-only pricing lifecycle and binding state;
- CAS and freshness checks; and
- explicit unit handling for the Pricing Matrix path.

RC1 does **not** yet have:

- a persisted per-Channel pricing-authority state machine;
- authority-aware write-command routing; or
- formal cutover enforcement from legacy formula authority to Pricing Matrix
  authority.

Those missing pieces are the remaining migration work.

