# FlowHub Workspace Gap Analysis

## Severity Definitions

- **P0:** safety, authorization, or write-integrity defect.
- **P1:** core workflow, recovery, or contract defect.
- **P2:** explainability, consistency, or maintainability gap.

## Authorization Gaps

| ID | Severity | Current behavior | Target behavior | Disposition |
| --- | --- | --- | --- | --- |
| AUTH-001 | P0 | `/api/auth/me` returns legacy `can_*` permissions only | Return canonical Workspace permissions plus compatibility aliases | Implement now |
| AUTH-002 | P0 | Source and Workspace routes use `can_access_site` or `can_fetch` | Route guards use `workspace.read`, `workspace.create`, and related capabilities | Implement now |
| AUTH-003 | P0 | Viewer can reach Source creation/import/edit controls | Mutating controls require their exact capability; viewer remains read-only | Implement now |
| AUTH-004 | P1 | Any API 403 changes the whole app to `permission_denied` | Action-level 403 remains local; only `/auth/me` defines global access state | Implement now |
| AUTH-005 | P0 | Maintenance write guard allows admin roles only, while role policy grants operators `apply.execute` | Enforce `apply.execute`; retain owner/super-admin maintenance bypass | Implement now |
| AUTH-006 | P2 | Permission strings are repeated in frontend code | Use typed/shared frontend constants without introducing a new framework | Implement now |

## Workflow Gaps

| ID | Severity | Current behavior | Target behavior | Disposition |
| --- | --- | --- | --- | --- |
| WS-001 | P1 | Legacy `/workspace` and unified `/workspace/:id` coexist as separate user workflows | One canonical Workspace entry and lifecycle | Owner decision required |
| WS-002 | P0 | Unified Apply button saves selection and immediately sends `confirmed: true` | Separate confirmation bound to exact approved Review/operation scope | Owner decision required |
| WS-003 | P1 | Unified Review is the approval boundary, but no presentation contract identifies an exact operation manifest for confirmation | Persist or expose exact intended operations and checksum before confirmation | Owner decision required |
| WS-004 | P1 | Legacy Workspace uses a separate Preview/Dry Run/Approval/Write Pipeline facade | Canonical state names and recovery behavior across entry points | Owner decision required |
| WS-005 | P2 | Presentation preferences use `workspace.read` for writes | Decide whether preferences are presentation-only read capability or need a dedicated permission | Keep current behavior pending evidence |

## Source and Sheet Gaps

| ID | Severity | Current behavior | Target behavior | Disposition |
| --- | --- | --- | --- | --- |
| SRC-001 | P1 | Source Configuration renders editable controls for all readers | `workspace.read` can inspect; `workspace.edit` enables mapping mutation | Implement now |
| SRC-002 | P1 | FlowHub Sheet renders editable cells/actions for all route users | `workspace.read` can inspect; `draft.save` enables revision mutation | Implement now |
| SRC-003 | P1 | Add Source and import entry points are visible without `workspace.create` | Creation paths require `workspace.create` in route and component | Implement now |
| SRC-004 | P2 | External Commerce Source controls use separate admin role checks | Preserve Sources/Channels separation; audit later for capability alignment | Continue audit |

## Contract and Recovery Gaps

| ID | Severity | Current behavior | Target behavior | Disposition |
| --- | --- | --- | --- | --- |
| CON-001 | P1 | Browser cannot distinguish all backend Workspace capabilities | `/api/auth/me` is the canonical frontend capability contract | Implement now |
| CON-002 | P1 | Action-level permission denial can destroy authenticated UI state | Preserve session and render local error | Implement now |
| CON-003 | P2 | Permission model is role-derived in code | Role-derived policy is acceptable until custom grants are approved | No schema change |
| CON-004 | P2 | Reference specification is present only in the Owner working tree during this audit | Adoption docs record reviewed filenames; reference publication remains Owner-controlled | Documented risk |

## Integration Audit Status

The prior Integration Audit HOLD is resolved only after AUTH-001 through
AUTH-005 and SRC-001 through SRC-003 are validated. The audit then resumes
page-by-page for Dashboard, Sources, Channels, Products, Orders, Settings, and
both Workspace surfaces. WS-001 through WS-003 remain explicit architecture
holds and must not be silently patched as UI-only changes.

