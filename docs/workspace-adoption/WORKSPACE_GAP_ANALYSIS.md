# FlowHub Workspace Gap Analysis

## Severity Definitions

- **P0:** safety, authorization, or write-integrity defect.
- **P1:** core workflow, recovery, or contract defect.
- **P2:** explainability, consistency, or maintainability gap.

## Authorization Gaps

| ID | Severity | Current behavior | Target behavior | Disposition |
| --- | --- | --- | --- | --- |
| AUTH-001 | P0 | `/api/auth/me` returned legacy `can_*` permissions only | Return canonical Workspace permissions plus compatibility aliases | Resolved in `d0caca5` |
| AUTH-002 | P0 | Source and Workspace routes used `can_access_site` or `can_fetch` | Route guards use `workspace.read`, `workspace.create`, and related capabilities | Resolved in `d0caca5` |
| AUTH-003 | P0 | Viewer could reach Source creation/import/edit controls | Mutating controls require their exact capability; viewer remains read-only | Resolved in `d0caca5` |
| AUTH-004 | P1 | Any API 403 changed the whole app to `permission_denied` | Action-level 403 remains local; only `/auth/me` defines global access state | Resolved in `d0caca5` |
| AUTH-005 | P0 | Maintenance write guard allowed admin roles only, while role policy granted operators `apply.execute` | Enforce `apply.execute`; retain owner/super-admin maintenance bypass | Resolved in `d0caca5` |
| AUTH-006 | P2 | Permission strings were repeated in frontend code | Use typed/shared frontend constants without introducing a new framework | Resolved in `d0caca5` |

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
| SRC-001 | P1 | Source Configuration rendered editable controls for all readers | `workspace.read` can inspect; `workspace.edit` enables mapping mutation | Resolved in `d0caca5` |
| SRC-002 | P1 | FlowHub Sheet rendered editable cells/actions for all route users | `workspace.read` can inspect; `draft.save` enables revision mutation | Resolved in `d0caca5` |
| SRC-003 | P1 | Add Source and import entry points were visible without `workspace.create` | Creation paths require `workspace.create` in route and component | Resolved in `d0caca5` |
| SRC-004 | P2 | External connector setup appeared to non-admin Source creators | Preserve Sources/Channels separation and backend admin policy | Resolved in `727ab5e` |
| SRC-005 | P1 | Total Source-list failure rendered an empty state with no recovery | Preserve partial results; show retry when both authoritative lists fail | Resolved in `d3eec97` |

## Contract and Recovery Gaps

| ID | Severity | Current behavior | Target behavior | Disposition |
| --- | --- | --- | --- | --- |
| CON-001 | P1 | Browser could not distinguish all backend Workspace capabilities | `/api/auth/me` is the canonical frontend capability contract | Resolved in `d0caca5` |
| CON-002 | P1 | Action-level permission denial could destroy authenticated UI state | Preserve session and render local error | Resolved in `d0caca5` |
| CON-003 | P2 | Permission model is role-derived in code | Role-derived policy is acceptable until custom grants are approved | No schema change |
| CON-004 | P2 | Reference specification is present only in the Owner working tree during this audit | Adoption docs record reviewed filenames; reference publication remains Owner-controlled | Documented risk |

## Page Integration Findings

| ID | Page | Severity | Root cause | Layer | Disposition |
| --- | --- | --- | --- | --- | --- |
| UI-001 | Channels | P1 | Primary list rejection had no error/retry state | Frontend | Resolved in `727ab5e` |
| UI-002 | Channels | P1 | Add/Configure controls were visible to readers although backend requires admin | Frontend/contract | Resolved in `727ab5e` |
| UI-003 | Channels | P2 | KPI numbers used host locale instead of FlowHub locale | Frontend | Resolved in `727ab5e` |
| UI-004 | Sources | P1 | Sheet creation rejection escaped without user feedback | Frontend | Resolved in `727ab5e` |
| UI-005 | Orders | P1 | Detail rejection was swallowed and left no recovery message | Frontend | Resolved in `727ab5e` |
| UI-006 | Activity | P1 | Primary history rejection escaped its async handler | Frontend | Resolved in `e3955ee` |
| UI-007 | Sources | P1 | Total Source-list rejection looked like a valid empty state | Frontend | Resolved in `d3eec97` |

## Integration Audit Status

The authorization-contract HOLD is resolved. The page-by-page audit is
complete and all non-architectural findings above are committed. Overall
Workspace adoption remains HOLD on WS-001 through WS-003 and must not be
silently patched as UI-only behavior.
