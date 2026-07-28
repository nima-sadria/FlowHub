# Platform Compliance Report

## Audit Boundary

Static implementation review covered backend, frontend, API, authentication,
authorization, Workspace, Sources, Channels, Connector lifecycle, health,
diagnostics, logging, audit, metrics, analytics, and tests.

No provider write, Production access, merge, release, or deployment occurred.

## Compliance Score

**84%: 64 of 76 sampled platform controls are compliant.**

This is an evidence-weighted adoption score, not test coverage. A control is
compliant only when code or existing tests demonstrate the canonical behavior.
Owner-decision items and unavailable backend execution validation are not
counted as compliant.

| Domain | Compliant | Sampled | Status |
| --- | ---: | ---: | --- |
| Architecture | 4 | 4 | Already compliant |
| Workspace | 8 | 10 | Architecture decisions required |
| Authorization | 6 | 7 | Capability aligned; scope decision required |
| API | 5 | 6 | Confirmation contract decision required |
| Sources | 5 | 5 | Already compliant |
| Channels and Connectors | 5 | 6 | Activation transaction decision required |
| Data and Write Pipeline | 7 | 7 | Already compliant |
| Health | 5 | 5 | Already compliant |
| Diagnostics | 4 | 5 | Durable history decision required |
| Audit and Logging | 6 | 8 | Bounds fixed; scope/retention decisions required |
| Metrics and Analytics | 4 | 6 | Scope/provenance/artifact decisions required |
| Testing and Operations | 5 | 7 | Backend runtime unavailable; retention/alerts open |

## Already Compliant

- Sources and Channels remain separate adapter and identity domains.
- Source Workspace acquires one logical Source version and records provenance.
- Unified Workspace persists immutable Snapshot rows and content checksums.
- Draft and Review are deterministic, revision-bound records.
- Selection uses explicit Review item identities and checksum.
- Write Pipeline persists idempotent intents and attempts.
- Prior uncertain attempts are verified/reconciled rather than blindly
  retransmitted.
- Channel cache updates follow verification state.
- Health and diagnostics GET paths read local facts; explicit refresh is
  separate and reports external-call behavior.
- Connector secrets are write-only/masked and structured data is recursively
  redacted.
- Public `/api/health` is minimal liveness.
- Connector telemetry and refresh/job facts are durable.
- Frontend route actions, forms, loading, and recovery behavior were covered by
  the completed Integration Audit.

## Gaps Fixed During Adoption

| Gap | Classification | Resolution |
| --- | --- | --- |
| `/api/auth/me` exposed legacy permissions only | P0 contract | Canonical Workspace permissions plus compatibility aliases |
| Source/Workspace UI and API capability mismatch | P0 authorization | Exact named capability guards |
| Action-level 403 invalidated global UI | P1 recovery | Local action handling |
| Channels, Sources, Orders, Activity recovery gaps | P1 frontend | Explicit error/retry states |
| Activity and Logging reads used `can_view_logs` | P1 contract | Canonical `audit.read` at backend and frontend boundaries |
| Frontend log ingestion was unbounded | P1 operational | 100-entry batch limit and 64 KiB entry rejection |

## Architecture Decisions Required

| Decision | Affected behavior | Why implementation stopped |
| --- | --- | --- |
| OD-004 | Canonical Workspace route | Routing, saved links, compatibility, and test ownership |
| OD-005 | Exact-operation confirmation object | API/persistence and Apply safety boundary |
| OD-006 | Legacy permission retirement | Client compatibility release |
| OD-007 | Reference publication | Owner-controlled untracked evidence |
| OD-008 | Retention and archival | Legal, storage, deletion, restore, and enforcement |
| OD-009 | Durable diagnostic history | New persistence and retention contract |
| OD-010 | Alert transport | Delivery, deduplication, acknowledgement, and secrets |
| OD-011 | Immutable report artifacts | New report authority and retention |
| OD-012 | Connector activation transaction | Candidate/active persistence and runtime activation |
| OD-013 | Operational read scope | Instance-wide versus owner scope and admin override |

## Important Static Findings

- Activity, Unified Logging, Dashboard, diagnostics, metrics, and analytics
  include instance-wide projections. `audit.read` now protects audit/log reads,
  but owner filtering and reason-required administrative override await OD-013.
- Integration Platform metadata CRUD is local/read-only and does not activate
  a runtime Connector. A generic local "test" response must not be treated as
  verified activation; OD-012 defines the final transaction.
- Diagnostic history currently returns an empty read model.
- Application-log retention defaults exist, but automated enforcement and
  authoritative audit/history retention are not a unified policy.
- Analytics return truthful current aggregates but do not yet provide a
  canonical immutable report artifact or complete provenance envelope.

## Validation

- Focused frontend authorization: 85 tests passed.
- Focused Workspace/Diagnostics/Channels: 47 tests passed.
- Frontend production build: passed after each implementation commit.
- `git diff --check`: passed.
- Backend tests and Python compilation could not run because this checkout has
  no Python interpreter, Docker engine, or installed WSL distribution.
- Known non-blocking build warning: Unified Workspace output chunk exceeds
  500 KiB after minification.

## Decision

**HOLD.** The canonical documentation and all safe minor/medium findings found
in this pass are implemented. Further alignment crosses Owner-level
architecture boundaries, primarily OD-004, OD-005, OD-012, and OD-013.

