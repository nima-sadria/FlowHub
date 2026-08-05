# ADR-PRICING-001: Replace Runtime Formulas with a Declarative Pricing Matrix

**Status:** Proposed
**Date:** 2026-08-05
**Decider:** FlowHub Owner
**Related:** `ADR-SOURCE-001`, `PRICING_MATRIX_DESIGN.md`,
`SOURCE_CENTRIC_PRICING_WORKSPACE.md`, `UNIFIED_MULTI_CHANNEL_WORKSPACE.md`
**Detailed design:** `PRICING_MATRIX_DESIGN.md`

## Context

`SOURCE_CENTRIC_PRICING_WORKSPACE.md` permits pricing cells to contain formulas
evaluated by the bounded `flowhub-formula-1` runtime engine. A production workbook
audit found 5,997 formula cells, 13 formula shapes, 255 broken `#REF!` formulas,
and incompatible unit conventions. The formulas combine quote selection, unit
scaling, pricing, rounding, fallback markers, and display calculations.

Even a restricted evaluator preserves the wrong abstraction for FlowHub pricing:
business policy remains encoded as executable cell expressions, formula meaning
is difficult to audit, malformed references can fail silently, and reproducing
identical results across Preview and server Apply becomes harder than necessary.

## Decision

FlowHub will replace runtime pricing-formula evaluation with immutable,
declarative `PricingPolicyRevision` matrices as specified by
`PRICING_MATRIX_DESIGN.md`.

The pricing runtime accepts typed parameters only. It performs exact rational and
integer arithmetic, values quotes before comparison, rounds exactly once, emits
typed outcomes, and records the resolved policy entry and all immutable inputs in
the Workspace Snapshot.

Upon acceptance, this ADR supersedes only these parts of
`SOURCE_CENTRIC_PRICING_WORKSPACE.md`:

- the `formula` row in the default value-policy table when used for pricing; and
- the `Formula grammar and limits` section and its `flowhub-formula-1` runtime.

All other Source-centric Workspace decisions remain in force unless another ADR
explicitly supersedes them.

## Migration Boundary

Formula parsing is allowed only in a bounded offline migration translator:

1. Inventory every production formula shape.
2. Accept only shapes listed in the checked-in allowlist with verified fixtures.
3. Translate a proven shape into declarative policy parameters, never executable
   state.
4. Quarantine unsupported, ambiguous, broken, or unproven formulas with
   `legacy_formula_unmigrated`; they produce no price target.
5. Require a migration preview and explicit activation before a translated
   Policy Revision can affect a Channel.
6. Remove the translator and formula evaluator from the runtime bundle after the
   migration release.

Historical formula text remains readable as audit evidence but is never
re-evaluated after migration.

## Invariants

1. No runtime pricing path evaluates formula text or an abstract syntax tree.
2. No formula meaning, currency unit, scale, or broken reference is inferred.
3. Pricing uses no floating-point arithmetic and no wall-clock input.
4. Pricing failures block only price targets; they never change stock or
   availability.
5. Policy creation is inert. Only per-Channel activation changes the effective
   policy and can make prior decisions outdated.
6. Workspace, Dry Run, and Apply remain bound to the exact Policy Activation,
   Source Observation, Mapping Revision, Product Group Revision, Channel
   configuration, FX snapshot, frozen `workspace_pricing_evaluated_at`, and
   arithmetic version reviewed by the operator.
7. Every external price write goes through `WritePipelineService`; this decision
   creates no alternate write or retry path.
8. Unsupported migration inputs fail closed with durable, visible diagnostics.
9. IRR has one canonical computation unit. Source, Channel, and display units are
   declared explicitly and never inferred from magnitude. FlowHub performs every
   conversion. A Policy binds only to Channels sharing its
   `computation_currency`, so no second conversion and no second rounding exist.
10. Apply is per Channel. A blocked Channel never blocks a healthy one, and
    partial application is always explicit in Workspace status.

## Options Considered

### Keep the restricted formula engine

Rejected. Sandboxing limits code execution but does not solve hidden business
semantics, broken references, unit ambiguity, migration auditability, or exact
cross-platform reproducibility.

### Hard-code pricing logic per Source or Channel

Rejected. It would duplicate business rules across connectors, couple policy to
transport, and require code releases for ordinary pricing changes.

### Use a declarative, revisioned pricing matrix

Chosen. It separates quote acquisition, valuation, rule resolution, arithmetic,
guards, approval, and transport while preserving deterministic replay and
per-Channel policy control.

## Consequences

Positive consequences:

- pricing policy becomes reviewable, versioned, and explainable per product and
  Channel;
- Preview and Apply can share one exact arithmetic contract;
- broken or unknown spreadsheet behavior cannot silently enter production; and
- connectors remain transport adapters rather than policy engines.

Costs and limitations:

- arbitrary user formulas are no longer supported for runtime pricing;
- migration requires a complete formula inventory and fixture-backed translator;
- unproven formulas remain blocked until corrected or explicitly modelled; and
- the Formula Engine cannot be removed until migration evidence and activation
gates are complete.

## Acceptance Criteria

- Every production formula is either fixture-proven and translated or visibly
  quarantined with a typed outcome.
- Translated fixtures match the workbook output, or an intentional difference is
  documented and approved before activation.
- Runtime application packages contain no pricing formula evaluator or migration
  translator after the migration release.
- Replaying a historical Workspace with its recorded revisions reproduces the
  same price targets exactly.
- Formula migration cannot write to a Channel, bypass Review, or bypass
  `WritePipelineService`.
- Existing non-formula Source Workspace behavior remains unchanged unless another
  accepted ADR supersedes it.

## Follow-up

1. Complete Appendix A in `PRICING_MATRIX_DESIGN.md` from the real inventory pass.
2. Produce fixtures for every supported formula shape and quarantine the rest.
3. Resolve the known broken production formulas before migration activation.
4. Implement and review the migration preview and Policy Activation gate.
