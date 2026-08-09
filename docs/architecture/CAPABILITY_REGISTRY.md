# Capability Registry (Phase 4.2 — design only)

**Status:** Design only — not implemented, not wired to any code or CI
**Scope:** Phase 4.2 of Architecture Guard bring-up. Builds on the stable
Source Gateway ([`app/connectors/common/source_http.py`](../../app/connectors/common/source_http.py))
and Channel Gateway ([`app/flowhub/channels/gateway.py`](../../app/flowhub/channels/gateway.py))
boundaries and the target design drawn in
[`docs/draw/business-architecture.drawio`](../draw/business-architecture.drawio)
(`capability_registry`, `architecture_guard`, `parity_check` nodes).

This document is the schema and a small illustrative seed set. Nothing here
is imported by application code, referenced by any test, or run in CI. It
does not modify runtime behavior and does not merge with, replace, or extend
`MarketplaceConnectorRegistry` (`app/flowhub/channels/registry.py`), which
answers a different question — "can this connector do X at runtime" — not
"does this domain feature have Backend + API + UI + Tests."

## Principle

Quoting the `capability_principle` node in the target-architecture diagram:

> Every Owner/Admin/Operator-facing capability must maintain coherent
> Backend ↔ API ↔ UI ↔ Test coverage. Excludes internal-only transaction,
> locking, CAS, migration engine, and worker internals.

## Non-goals

- **No reflection, no auto-discovery.** The registry is never populated by
  scanning routes, walking the frontend router, or introspecting modules.
  Every entry is a hand-written line reviewed by a human.
- **Not a CI gate yet.** Phase 4.2 defines the shape only. A future phase
  may add a check that declared refs exist; this document does not.
- **Not a runtime capability system.** It does not gate behavior, does not
  get imported by `app/flowhub/`, and is not a dependency of any request
  path. It is closer in spirit to `ARCHITECTURE_STATE.md` than to code.
- **Small and enumerable, on purpose.** The set of Owner/Admin/Operator-
  facing capabilities in FlowHub today is finite and short. If this list
  grows into the hundreds, that is a signal the granularity is wrong, not
  a reason to automate population of it.

## Schema

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

## Status rules

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
to make that judgment mechanically (see [[Phase 4.3 design]] below on why
that stays a warning surface, not a CI-blocking one).

## Illustrative seed set

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
failure, a question for a human.

## Where this would live if promoted

Not decided here — that is an implementation question for a later phase,
not a design-only one. Candidates worth weighing then: a single file (keeps
the "small enumerable set" property visible in one diff) versus one entry
per domain module (keeps ownership local to the team that owns the domain).
This document takes no position beyond keeping the seed table above small
enough that the question doesn't matter yet.

---

## Phase 4.3 design (not implemented): Architecture Health

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

## Phase 4.4 design (not implemented): Diagnostics integration

- Wires the Phase 4.3 report into whatever Diagnostics already exposes to
  Owner/Admin (UI page, CLI, or existing report endpoint — to be determined
  by whoever plans 4.4, informed by how `diagnostics/report.py` and
  `diagnostics/runner.py` currently surface their output).
- No new UI framework, no new permission model: reuses existing
  Diagnostics access control as-is.
- Depends on 4.3 existing and on the registry (4.2) having been reviewed
  and populated beyond the four illustrative rows above — sequencing, not
  parallelizable with 4.2.
