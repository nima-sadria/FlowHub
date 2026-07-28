# Document Merge Report

## Method

All Markdown documents in the feature checkout and all Owner-provided
Workspace and Operational reference documents were classified. Video artifacts
are not specification documents and are retained unchanged.

Classifications mean:

- **Keep:** current implementation, operator, release, or canonical evidence.
- **Merge:** useful rules moved into the canonical platform specification.
- **Archive:** historical/non-normative; retained in place pending link review.
- **Delete:** safe to remove only after content and inbound links are verified.

No document was deleted or physically moved in this pass.

## Canonical Documents

All files under the following new domain paths are **Keep** and canonical:

- `docs/platform/PLATFORM_SPECIFICATION_INDEX.md`
- `docs/platform/Architecture/PLATFORM_ARCHITECTURE.md`
- `docs/platform/Workspace/WORKSPACE_MODEL.md`
- `docs/platform/Authorization/AUTHORIZATION_MODEL.md`
- `docs/platform/API/API_CONTRACTS.md`
- `docs/platform/Connectors/CONNECTOR_LIFECYCLE.md`
- `docs/platform/Data Contracts/PLATFORM_DATA_CONTRACTS.md`
- `docs/platform/State Machines/PLATFORM_STATE_MACHINES.md`
- `docs/platform/Operational Model/OPERATIONAL_MODEL.md`
- `docs/platform/Audit/AUDIT_MODEL.md`
- `docs/platform/Logging/LOGGING_EVENT_MODEL.md`
- `docs/platform/Diagnostics/DIAGNOSTICS_MODEL.md`
- `docs/platform/Health/HEALTH_MODEL.md`
- `docs/platform/Metrics/METRICS_MODEL.md`
- `docs/platform/Analytics/ANALYTICS_MODEL.md`
- `docs/platform/Testing/PLATFORM_TEST_MATRIX.md`
- `docs/platform/Migration/PLATFORM_MIGRATION.md`
- `docs/platform/Owner Decisions/OWNER_DECISIONS.md`
- `docs/platform/Reference/REFERENCE_TRACEABILITY.md`
- `docs/platform/Archive/README.md`
- `docs/platform/DOCUMENT_MERGE_REPORT.md`
- `docs/platform/DOCUMENT_ARCHIVE_INDEX.md`
- `docs/platform/DOCUMENT_DEPRECATION_REPORT.md`

## Reference Specification Classification

| Source document | Classification | Destination |
| --- | --- | --- |
| `workspace-spec/WORKSPACE_BUSINESS_SPEC.md` | Merge | Workspace, Architecture, Authorization |
| `workspace-spec/WORKSPACE_STATE_MACHINE.md` | Merge | State Machines |
| `workspace-spec/WORKSPACE_DATA_CONTRACTS.md` | Merge | Data Contracts, API |
| `workspace-spec/WORKSPACE_DECISION_TABLES.md` | Merge | Workspace, Testing |
| `workspace-spec/WORKSPACE_REFERENCE_PSEUDOCODE.md` | Merge | Workspace, Operational Model |
| `workspace-spec/WORKSPACE_MIGRATION_GUIDE.md` | Merge | Migration |
| `workspace-spec/WORKSPACE_TEST_MATRIX.md` | Merge | Testing |
| `workspace-spec/WORKSPACE_CODE_TRACEABILITY.md` | Merge | Reference traceability |
| `operational-spec/OPERATIONAL_INTELLIGENCE_SPEC.md` | Merge | Operational Model |
| `operational-spec/CONNECTOR_LIFECYCLE.md` | Merge | Connectors |
| `operational-spec/DIAGNOSTICS_AND_HEALTH.md` | Merge | Diagnostics, Health |
| `operational-spec/API_CONTRACTS.md` | Merge | API |
| `operational-spec/DATA_CONTRACTS.md` | Merge | Data Contracts |
| `operational-spec/STATE_MACHINES.md` | Merge | State Machines |
| `operational-spec/AUDIT_ENGINE_SPEC.md` | Merge | Audit |
| `operational-spec/LOGGING_AND_EVENT_MODEL.md` | Merge | Logging |
| `operational-spec/METRICS_AND_ANALYTICS.md` | Merge | Metrics, Analytics |
| `operational-spec/REFERENCE_PSEUDOCODE.md` | Merge | Domain contracts |
| `operational-spec/TEST_MATRIX.md` | Merge | Testing |
| `operational-spec/MIGRATION_GUIDE.md` | Merge | Migration |
| `operational-spec/PORTABILITY_GUIDE.md` | Merge | Architecture, Connectors |
| `operational-spec/CODE_TRACEABILITY.md` | Merge | Reference traceability |

The reference files remain Owner-controlled, untracked evidence. They were not
copied into this checkout. All portable rules are represented in canonical
FlowHub terminology.

## Current Documents Kept

| Document | Reason |
| --- | --- |
| `docs/api/SOURCE_WORKSPACE_API.md` | Current route-level API evidence |
| `docs/api/UNIFIED_WORKSPACE_API.md` | Current route-level API evidence |
| `docs/architecture/BU5_INTEGRATIONS.md` | Current integration architecture evidence |
| `docs/architecture/CURRENT_ARCHITECTURE.md` | Current runtime topology |
| `docs/architecture/DATA_LAYER_ARCHITECTURE.md` | Detailed Data Layer implementation |
| `docs/architecture/INTEGRATION_PLATFORM.md` | Detailed Integration Platform implementation |
| `docs/architecture/MARKETPLACE_CHANNELS.md` | Channel adapter implementation |
| `docs/architecture/ORDER_SYNCHRONIZATION.md` | Order synchronization implementation |
| `docs/architecture/SOURCE_CENTRIC_PRICING_WORKSPACE.md` | Source Workspace implementation |
| `docs/architecture/UNIFIED_LOGGING_PLATFORM.md` | Logging implementation and open decisions |
| `docs/architecture/UNIFIED_MULTI_CHANNEL_WORKSPACE.md` | Unified Workspace implementation |
| `docs/BACKUP_RESTORE.md` | Current operator guide |
| `docs/FAQ.md` | Current user/operator guide |
| `docs/i18n/INTERNATIONALIZATION.md` | Current localization contract |
| `docs/i18n/TRANSLATOR_GUIDE.md` | Current translation guide |
| `docs/INSTALLATION.md` | Current installation guide |
| `docs/MIGRATION_STATUS.md` | Current migration head and procedure |
| `docs/platform/INSTALLER_ARCHITECTURE.md` | Current installer contract |
| `docs/release/ROLLBACK.md` | Current rollback procedure |
| `docs/RELEASE_CHECKLIST.md` | Current release validation |
| `docs/releases/FLOWHUB_V1.2_STABLE.md` | Historical release evidence |
| `docs/releases/FLOWHUB_V1.3_BETA.md` | Current beta release evidence |
| `docs/reports/FLOWHUB_V1.3_PDF_BUG_REMEDIATION.md` | Historical remediation evidence |
| `docs/reports/PRICING_WORKFLOW_VIDEO_COMPARISON.md` | UX research evidence |
| `docs/ROADMAP.md` | Current repository roadmap pointer |
| `docs/roadmap/NEXT.md` | Current high-level priorities |
| `docs/TROUBLESHOOTING.md` | Current operator guide |
| `docs/UPGRADE.md` | Current upgrade guide |
| `docs/WORKFLOW.md` | Current contribution workflow |
| `docs/MORNING_HANDOFF.md` | Current-state handoff; review on next release |

Kept implementation documents are subordinate to the canonical platform
contracts for business behavior.

## Adoption Documents Merged and Deprecated

| Document | Classification | Destination |
| --- | --- | --- |
| `docs/workspace-adoption/WORKSPACE_ADOPTION_ASSESSMENT.md` | Merge, then Archive | Index, Architecture, Migration |
| `docs/workspace-adoption/WORKSPACE_GAP_ANALYSIS.md` | Merge, then Archive | Owner Decisions, deprecation report |
| `docs/workspace-adoption/WORKSPACE_IMPLEMENTATION_PHASES.md` | Merge, then Archive | Migration |
| `docs/workspace-adoption/WORKSPACE_OWNER_DECISIONS.md` | Merge, then Archive | Canonical Owner Decisions |

They remain in place as audit evidence until Owner-approved archival.

## Historical Documents Archived

The following are already legacy compatibility stubs or phase/audit artifacts
and are classified **Archive**:

- `docs/A2_ARCHITECTURE.md`
- `docs/AI_OPERATING_MANUAL.md`
- `docs/ARCHITECTURE.md`
- `docs/MASTER_SPEC.md`
- `docs/PHASE_5_CUTOVER_PLAN.md`
- `docs/PLATFORM_MAP.md`
- `docs/RELEASE_STRATEGY.md`
- `docs/agents/AUDIT_REMEDIATION.md`
- `docs/agents/CLAUDE_DEVELOPER.md`
- `docs/agents/CODEX_AUDITOR.md`
- `docs/agents/PHASE_6_CLAUDE_ROADMAP.md`
- `docs/agents/README.md`
- `docs/agents/REAUDIT.md`
- `docs/agents/STABILIZATION_COMMIT.md`
- `docs/control-plane/CONNECTION_MANAGER.md`
- `docs/control-plane/CONTROL_PLANE_ARCHITECTURE.md`
- `docs/control-plane/CONTROL_PLANE_SECURITY.md`
- `docs/control-plane/DIAGNOSTICS_ARCHITECTURE.md`
- `docs/control-plane/HEALTH_ENGINE.md`
- `docs/control-plane/IMPLEMENTATION_PLAN.md`
- `docs/control-plane/OFFLINE_MODE.md`
- `docs/control-plane/RUNTIME_CONFIGURATION.md`
- `docs/phases/A2.1.md`
- `docs/phases/A2.2.md`
- `docs/phases/A2.3.md`
- `docs/phases/A2.3-R2-reconciliation-report.md`
- `docs/phases/A2.4.md`
- `docs/phases/A2.5.md`
- `docs/phases/A2.5-completion-report.md`
- `docs/phases/A2.6.md`
- `docs/phases/A2.6-completion-report.md`
- `docs/phases/A2.7.md`
- `docs/phases/A2.7-completion-report.md`
- `docs/phases/A2.8.md`
- `docs/phases/A2.8-completion-report.md`
- `docs/phases/A2.9.md`
- `docs/phases/A2.9-completion-report.md`
- `docs/platform/BU2_AUTH_ARCHITECTURE.md`
- `docs/platform/CLI_ARCHITECTURE.md`
- `docs/platform/CONFIGURATION_ARCHITECTURE.md`
- `docs/platform/DEPLOYMENT_ARCHITECTURE.md`
- `docs/platform/DEVELOPMENT_GUIDE.md`
- `docs/platform/FEATURE_FLAG_ARCHITECTURE.md`
- `docs/platform/IMPLEMENTATION_ROADMAP.md`
- `docs/platform/INSTALLATION_PROFILE.md`
- `docs/platform/PLUGIN_ARCHITECTURE.md`
- `docs/platform/REPOSITORY_LAYOUT.md`
- `docs/platform/SECURITY_ARCHITECTURE.md`
- `docs/platform/SERVER_INSTALL.md`
- `docs/platform/SYSTEM_ARCHITECTURE.md`
- `docs/platform/UI_ARCHITECTURE.md`

## Delete Classification

**None.** Deletion was intentionally deferred because link/reference analysis
and Owner approval are required. The canonical specification contains the
useful platform rules without destructive documentation cleanup.

