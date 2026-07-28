# FlowHub Platform Specification

## Status

This directory is the canonical specification for FlowHub platform behavior.
It supersedes reference material, phase plans, and legacy compatibility
documents where they conflict. Existing architecture documents remain useful
implementation evidence but are not independently normative.

Normative terms use **MUST**, **MUST NOT**, **SHOULD**, and **MAY**.

## Product Boundary

FlowHub connects Sources to Channels through an explicit, reviewable Workspace.
Sources provide proposed data. Channels provide observed external state.
FlowHub owns normalization, immutable snapshots, Drafts, Review, selected
scope, write intent, verification, reconciliation, audit, and reporting.

The platform is provider-neutral. WooCommerce, Nextcloud, spreadsheets, and
marketplaces are adapters, not business architecture.

## Canonical Workflow

```text
Source acquisition
  -> normalized source records
  -> immutable Workspace Snapshot
  -> Draft changes
  -> deterministic Review
  -> explicit selected scope and checksum
  -> confirmation
  -> durable write intents
  -> Channel dispatch
  -> verification or reconciliation
  -> verified cache update
  -> append-only audit and confirmed history
```

## Safety Invariants

1. Preview and Review MUST NOT write to a Source or Channel.
2. Apply MUST use persisted selected scope, not visible rows or current filters.
3. Scope identity and checksum changes MUST invalidate approval.
4. A Channel write is successful only after authoritative confirmation.
5. An ambiguous write outcome MUST become `reconciliation_required`; it MUST
   NOT be reported as success or blindly retried.
6. Cache state MUST change only after verified Channel state.
7. Connector candidates MUST be verified before becoming active runtime
   configuration. Failed verification MUST preserve the active configuration.
8. Normal health reads MUST summarize recorded facts and MUST NOT probe
   external systems.
9. Secrets MUST be write-only or redacted on every read, log, diagnostic, and
   audit surface.
10. Every mutation MUST be attributable to an authenticated actor and checked
    against a named capability.
11. Sources and Channels MUST remain separate identities and lifecycles.
12. Audit activity, operation attempts, and confirmed business history MUST
    remain distinct records.

## Specification Map

| Domain | Canonical document |
| --- | --- |
| Architecture | [Architecture/PLATFORM_ARCHITECTURE.md](Architecture/PLATFORM_ARCHITECTURE.md) |
| Workspace | [Workspace/WORKSPACE_MODEL.md](Workspace/WORKSPACE_MODEL.md) |
| Authorization | [Authorization/AUTHORIZATION_MODEL.md](Authorization/AUTHORIZATION_MODEL.md) |
| API | [API/API_CONTRACTS.md](API/API_CONTRACTS.md) |
| Connectors | [Connectors/CONNECTOR_LIFECYCLE.md](Connectors/CONNECTOR_LIFECYCLE.md) |
| Data contracts | [Data Contracts/PLATFORM_DATA_CONTRACTS.md](Data%20Contracts/PLATFORM_DATA_CONTRACTS.md) |
| State machines | [State Machines/PLATFORM_STATE_MACHINES.md](State%20Machines/PLATFORM_STATE_MACHINES.md) |
| Operational model | [Operational Model/OPERATIONAL_MODEL.md](Operational%20Model/OPERATIONAL_MODEL.md) |
| Audit | [Audit/AUDIT_MODEL.md](Audit/AUDIT_MODEL.md) |
| Logging | [Logging/LOGGING_EVENT_MODEL.md](Logging/LOGGING_EVENT_MODEL.md) |
| Diagnostics | [Diagnostics/DIAGNOSTICS_MODEL.md](Diagnostics/DIAGNOSTICS_MODEL.md) |
| Health | [Health/HEALTH_MODEL.md](Health/HEALTH_MODEL.md) |
| Metrics | [Metrics/METRICS_MODEL.md](Metrics/METRICS_MODEL.md) |
| Analytics | [Analytics/ANALYTICS_MODEL.md](Analytics/ANALYTICS_MODEL.md) |
| Testing | [Testing/PLATFORM_TEST_MATRIX.md](Testing/PLATFORM_TEST_MATRIX.md) |
| Migration | [Migration/PLATFORM_MIGRATION.md](Migration/PLATFORM_MIGRATION.md) |
| Owner decisions | [Owner Decisions/OWNER_DECISIONS.md](Owner%20Decisions/OWNER_DECISIONS.md) |
| Traceability | [Reference/REFERENCE_TRACEABILITY.md](Reference/REFERENCE_TRACEABILITY.md) |
| Compliance evidence | [PLATFORM_COMPLIANCE_REPORT.md](PLATFORM_COMPLIANCE_REPORT.md) |

## Document Governance

- A new durable platform rule belongs in the relevant canonical domain file.
- Implementation documents MAY describe modules, schemas, and routes but MUST
  link back to the governing platform contract.
- Release notes, reports, phase plans, and adoption assessments are evidence,
  not normative specifications.
- Historical reference material MUST NOT silently override this index.
- Any intentional exception MUST be recorded in Owner Decisions with scope,
  compatibility impact, migration, tests, and rollout gate.

## Current Compliance

The granular authorization contract and audited application integrations are
implemented. Current sampled compliance is 84%. Full convergence is on HOLD
for the decisions listed in `PLATFORM_COMPLIANCE_REPORT.md`, including the
canonical Workspace route, exact-operation confirmation, Connector activation,
operational read scope, retention, diagnostics history, alerts, and report
artifacts.
