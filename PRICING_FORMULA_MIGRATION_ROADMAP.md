# Pricing Formula Migration Roadmap

This roadmap breaks the remaining Pricing Formula Migration work into small,
release-grade phases. It is intentionally conservative and assumes no new
business decisions beyond the approved ones already captured in the
architecture docs.

## Phase 1 — Inventory closure

- **Scope:** complete Appendix A from the real workbook inventory pass and
  classify every remaining production formula shape.
- **Dependencies:** workbook analysis artifact, formula translator pass, owner
  confirmation of any ambiguous shape.
- **Recommended model:** GPT-5.6 Sol High if the inventory is large or the
  workbook analysis is still being inferred; otherwise GPT-5.6 Terra Medium.
- **Estimated token range:** 12k–25k.
- **Tests:** inventory validation, shape allowlist checks, quarantined-shape
  proof tests.
- **Stop condition:** every production formula shape is either fixture-proven
  or quarantined with evidence.

## Phase 2 — Fixture-backed translation

- **Scope:** add fixtures for every supported formula shape and prove exact
  workbook-to-FlowHub output parity where required.
- **Dependencies:** completed inventory closure.
- **Recommended model:** GPT-5.6 Sol High.
- **Estimated token range:** 15k–30k.
- **Tests:** translator fixtures, exact-value parity tests, quarantine tests,
  legacy-formula block tests.
- **Stop condition:** every supported shape has a deterministic fixture and the
  unsupported remainder is explicitly blocked.

## Phase 3 — Cutover authority model

- **Scope:** implement persisted per-Channel pricing authority state, explicit
  migration lock semantics, and authority-aware write-command checks.
- **Dependencies:** complete inventory and fixture evidence.
- **Recommended model:** GPT-5.6 Sol High.
- **Estimated token range:** 18k–35k.
- **Tests:** authority-state persistence, transition CAS, pre-dispatch rejection,
  rejected-write audit tests, channel isolation tests.
- **Stop condition:** one Channel can be legacy or matrix-authoritative, and
  WritePipelineService rejects non-authoritative writes deterministically.

## Phase 4 — Shadow validation and frozen evaluation package

- **Scope:** formalize the frozen evaluation package, comparison confidence,
  divergence classification, and evidence-only shadow validation.
- **Dependencies:** authority model in place.
- **Recommended model:** GPT-5.6 Sol High or equivalent.
- **Estimated token range:** 15k–25k.
- **Tests:** frozen-package assembly, comparison confidence, divergence
  classification, multi-source evidence tests.
- **Stop condition:** comparison evidence is persistent, reviewable, and
  channel-scoped.

## Phase 5 — Legacy replay and rollback safety

- **Scope:** implement deterministic legacy replay for rollback and emergency
  safety handling without re-enabling legacy write authority.
- **Dependencies:** authority model and frozen evaluation package.
- **Recommended model:** GPT-5.6 Sol High.
- **Estimated token range:** 15k–25k.
- **Tests:** replay determinism, rollback evidence, emergency safety basis,
  fallback calculation tests.
- **Stop condition:** rollback is evidence-backed and does not restore legacy
  direct writes.

## Phase 6 — Activation gate

- **Scope:** enable Pricing Matrix migration activation only after Appendix A,
  fixtures, legacy replay, and cutover evidence are complete.
- **Dependencies:** Phases 1–5 complete.
- **Recommended model:** GPT-5.6 Terra Medium for verification; Sol High only
  if a structural blocker remains.
- **Estimated token range:** 8k–15k.
- **Tests:** activation gating, release-term guard, backend regression, targeted
  source/workspace regressions.
- **Stop condition:** pricing migration activation is intentionally approved
  and release-ready.

## Practical recommendation

Start with **Phase 1: Inventory closure**. That is the smallest phase that
unblocks all later work and removes the largest remaining ambiguity.

