# Pricing Formula Migration Decisions

This document records the currently approved decisions for Pricing Formula
Migration and the exact places where the repository still does not implement
the target architecture.

## Status

Discovery complete from repository evidence. Implementation remains gated.

## Approved decisions

1. Migration and cutover are per Channel.
2. Each Channel has exactly one authoritative pricing engine at a time.
3. There is no rule-level hybrid authority after cutover.
4. Both legacy and new pricing paths must write through `WritePipelineService`.
5. RC1 already converges production writes onto a shared write pipeline.
6. RC1 does **not** yet persist a per-Channel pricing-authority state.
7. Required authority states include at least:
   - `legacy_formula_engine`
   - `migration_locked`
   - `pricing_matrix`
8. Shadow Validation is temporary and evidence-only.
9. Pricing Matrix must never write during Shadow Validation.
10. Comparisons require a Frozen Evaluation Package.
11. Timing proximity alone does not prove identical inputs.
12. `comparison_confidence` values are:
   - `verified`
   - `partial`
   - `unavailable`
13. Unproven input identity must resolve to `comparison_not_possible`.
14. Divergence contracts must be formula-shape-aware, not merely Channel-wide.
15. Channel policy may make acceptance stricter, but may not weaken shape
    invariants.
16. Rule-level evidence feeds Channel-level cutover eligibility.
17. Every active blocking rule must be resolved before Channel cutover.
18. Manual prices, overrides, external API values, and vendor inputs are
    immutable/versioned target-architecture inputs.
19. Active override does not stop candidate calculation; it controls final
    output.
20. Legacy calculation may remain temporarily after cutover for rollback
    safety, but legacy write authority remains disabled.
21. Normal rollback requires verified evidence.
22. Emergency rollback uses a separate `emergency_safety` basis.
23. Current legacy replay capability is not assumed.
24. Full deterministic Legacy Replay Adapter is a GA requirement.
25. Multi-source formula dependencies are possible, including vendor ranking,
    vendor availability, manual market values, forced price, and ERP/API
    inputs.
26. Pricing formula migration/activation remains disabled in RC1.
27. The unresolved 255 formulas require formal classification.

## Confirmed current implementation

- `WritePipelineService` is the active production write boundary for the
  unified Workspace and product-pricing flows.
- Pricing Matrix persistence already models immutable policy revisions,
  append-only lifecycle events, mutable Channel heads, and workspace bindings.
- Pricing Matrix activation enforces policy activation and configuration
  freshness, not a persisted pricing-engine authority enum.
- The legacy direct write path still exists in `app/main.py` and
  `app/services/woocommerce.py`, but it is not the RC1 production entrypoint.

## Missing target-architecture pieces

- No persisted per-Channel pricing-authority state exists.
- `WritePipelineService` does not receive a pricing-engine identity that could
  distinguish legacy formula output from Pricing Matrix output as an authority
  state.
- No `migration_locked` state exists in the RC1 data model.
- No explicit pre-dispatch or post-lock authority rejection exists beyond
  configuration/version freshness checks.
- No audit trail exists specifically for rejecting non-authoritative pricing
  writes.

## Explicit invariants

- One Channel may be controlled by only one authoritative pricing engine at a
  time.
- Authorization and version consistency are not the same thing.
- Workspace / head / activation / CAS checks protect state freshness, not
  engine authority.
- A write path that bypasses `WritePipelineService` is out of policy for the
  target architecture, even if it remains present as legacy compatibility code.
- The migration is not activated until the formula inventory, fixtures, and
  cutover evidence are complete.

