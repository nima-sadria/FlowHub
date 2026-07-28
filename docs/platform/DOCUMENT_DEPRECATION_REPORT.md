# Document Deprecation Report

## Superseded Sources

The 22 Workspace and Operational reference documents are superseded for
FlowHub product behavior by the canonical domain contracts. They remain useful
provenance but MUST NOT be treated as live FlowHub API or architecture
requirements.

## Deprecated Adoption Documents

The four files under `docs/workspace-adoption/` are frozen audit evidence.
New gaps, phases, and decisions belong in:

- `Owner Decisions/OWNER_DECISIONS.md`
- `Migration/PLATFORM_MIGRATION.md`
- `DOCUMENT_MERGE_REPORT.md`

## Deprecated Compatibility Stubs

All files identified as historical in `DOCUMENT_MERGE_REPORT.md` are
deprecated. Their pointers to `docs/architecture/CURRENT_ARCHITECTURE.md`
remain valid, but the platform entry point is now
`docs/platform/PLATFORM_SPECIFICATION_INDEX.md`.

## Terminology Deprecated in Canonical Rules

- WooCommerce as the universal destination model;
- Nextcloud or spreadsheet as the universal Source model;
- Preview-table rows as Apply scope;
- attempted HTTP write as confirmed success;
- one generic log as audit, operation ledger, and business history;
- health GET as an implicit external probe;
- role-name checks where a named capability exists.

Provider-specific terminology remains valid inside adapter documentation.

## Runtime Deprecations Requiring Owner Approval

- legacy Workspace route and workflow;
- legacy `can_*` permission aliases;
- unversioned confirmation behavior without an exact approved operation object.

No runtime deprecation was executed by this documentation consolidation.

