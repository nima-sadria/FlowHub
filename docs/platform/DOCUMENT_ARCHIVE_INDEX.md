# Document Archive Index

## Archive Policy

Archive means non-normative historical evidence. Archived material may explain
why the current system exists but cannot override
`PLATFORM_SPECIFICATION_INDEX.md`.

## Logical Archive Groups

| Group | Documents | Reason |
| --- | --- | --- |
| Legacy compatibility records | root `ARCHITECTURE`, `MASTER_SPEC`, `PLATFORM_MAP`, `A2_ARCHITECTURE`, `AI_OPERATING_MANUAL`, `PHASE_5_CUTOVER_PLAN`, `RELEASE_STRATEGY` | Content already replaced by current release docs |
| Agent/audit instructions | `docs/agents/*` | Time-bound development evidence |
| Control-plane records | `docs/control-plane/*` | Pre-release drafts, not current contracts |
| Phase records | `docs/phases/*` | Completed implementation history |
| Legacy platform records | all prior nine-line `docs/platform/*.md` compatibility files | Superseded drafts |
| Workspace adoption | `docs/workspace-adoption/*` after Owner approval | Rules merged into canonical platform docs |
| External references | Owner-provided `workspace-spec/*` and `operational-spec/*` | Source evidence; not FlowHub canonical architecture |

`docs/platform/INSTALLER_ARCHITECTURE.md` is excluded from the archive because
it is a current installer contract.

## Physical Archive

No file was moved. A future archival commit must:

1. scan inbound links;
2. preserve Git history;
3. update current navigation;
4. avoid moving active operator/release guides;
5. receive Owner approval.

## Deletion

No archive entry is approved for deletion in this pass.
