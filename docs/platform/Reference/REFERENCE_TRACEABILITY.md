# Reference Traceability

## Workspace Reference

| Reference document | Canonical destination |
| --- | --- |
| `WORKSPACE_BUSINESS_SPEC.md` | Workspace, Architecture, Authorization |
| `WORKSPACE_STATE_MACHINE.md` | State Machines |
| `WORKSPACE_DATA_CONTRACTS.md` | Data Contracts, API |
| `WORKSPACE_DECISION_TABLES.md` | Workspace, Testing |
| `WORKSPACE_REFERENCE_PSEUDOCODE.md` | Workspace, Operational Model |
| `WORKSPACE_MIGRATION_GUIDE.md` | Migration |
| `WORKSPACE_TEST_MATRIX.md` | Testing |
| `WORKSPACE_CODE_TRACEABILITY.md` | this traceability file and implementation docs |

## Operational Reference

| Reference document | Canonical destination |
| --- | --- |
| `OPERATIONAL_INTELLIGENCE_SPEC.md` | Operational Model |
| `CONNECTOR_LIFECYCLE.md` | Connectors |
| `DIAGNOSTICS_AND_HEALTH.md` | Diagnostics, Health |
| `API_CONTRACTS.md` | API |
| `DATA_CONTRACTS.md` | Data Contracts |
| `STATE_MACHINES.md` | State Machines |
| `AUDIT_ENGINE_SPEC.md` | Audit |
| `LOGGING_AND_EVENT_MODEL.md` | Logging |
| `METRICS_AND_ANALYTICS.md` | Metrics, Analytics |
| `REFERENCE_PSEUDOCODE.md` | domain contracts |
| `TEST_MATRIX.md` | Testing |
| `MIGRATION_GUIDE.md` | Migration |
| `PORTABILITY_GUIDE.md` | Architecture, Connectors |
| `CODE_TRACEABILITY.md` | this traceability file |

## Translation Rules

- WooCommerce becomes a Channel adapter where behavior is portable.
- Nextcloud/spreadsheets become Source adapters where behavior is portable.
- WooPrice jobs and manifests are not copied; only verified invariants are
  expressed through FlowHub Snapshot, Review, selection, and Write Pipeline.
- FastAPI, React, SQLAlchemy, route names, and model names are implementation
  evidence, not platform requirements.
- Product/variation and webhook topic rules remain adapter-specific.

## Implementation Evidence

Current code and detailed architecture remain documented in:

- `docs/architecture/CURRENT_ARCHITECTURE.md`
- `docs/architecture/INTEGRATION_PLATFORM.md`
- `docs/architecture/DATA_LAYER_ARCHITECTURE.md`
- `docs/architecture/UNIFIED_MULTI_CHANNEL_WORKSPACE.md`
- `docs/architecture/SOURCE_CENTRIC_PRICING_WORKSPACE.md`
- `docs/architecture/UNIFIED_LOGGING_PLATFORM.md`
- `docs/api/SOURCE_WORKSPACE_API.md`
- `docs/api/UNIFIED_WORKSPACE_API.md`

