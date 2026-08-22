# Source Workspace API

All routes use the existing authenticated `/api/v2` API, typed request models,
workspace permissions, optimistic version checks, and consistent FlowHub error
responses. UI row indexes are never accepted as resource identities.

## Sources and mappings

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/source-profiles` | List Sources owned by the current user |
| `GET` | `/source-profiles/channels` | List Channel capabilities and participation availability |
| `POST` | `/sources` | Create a managed or explicitly linked Source |
| `GET` | `/sources/{source_id}/configuration` | Read the active immutable Mapping |
| `PUT` | `/sources/{source_id}/mappings` | Create the next Mapping revision |
| `GET` | `/sources/{source_id}/preview` | Preview recognized and ignored Source rows |

Mapping writes require `expected_source_version`. A mismatch returns `409` and
does not overwrite either configuration. Each Channel mapping contains an
explicit `enabled` flag plus independent `external_id`, `price`, `stock`, and
`status` references. Disabled Channel mappings and field references are
preserved but excluded from new Source processing. Coming Soon and unavailable
Channels cannot be enabled.

## FlowHub Sheet

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/sheets` | Create an internal FlowHub Sheet |
| `GET` | `/sheets/{sheet_id}` | Page Sheet rows (maximum 500) |
| `POST` | `/sheets/{sheet_id}/revisions` | Save a complete immutable revision |
| `PATCH` | `/sheets/{sheet_id}/revisions` | Save an identity-based cell patch as a new revision |
| `POST` | `/sheets/{sheet_id}/rows` | Append a bounded batch of rows in a new revision |
| `POST` | `/sheets/calculate` | Calculate a bounded, sandboxed Sheet payload |

Revision writes require `expected_version`. Cells are addressed by stable
`row_key` and `column_key`; page and visual row numbers are display metadata.

## Import and Data Quality

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/sheet-imports/preview` | Preview CSV/XLSX worksheets and rows |
| `POST` | `/sheets/import` | Import checksum-bound bytes into a managed Sheet |
| `GET` | `/data-quality` | Filter issues by Source, Channel, category, severity, and page |

Import requests are limited to 20 MB, 10,000 rows, and 200 columns. The import
request must repeat the preview checksum; mismatched bytes fail closed.

## Source Workspace

`POST /unified-workspaces/source` accepts an optional `source_id`. A Source ID
selects the v1.3 path for either an internal FlowHub Sheet or a linked external
Source; omitting it preserves the v1.2 compatibility behavior. Internal Sources
snapshot the exact Sheet and Mapping revision. External Sources acquire the
workbook once, snapshot its integrity checksum, and resolve every Channel from
that same acquisition. Both paths resolve Channel Listings, create an immutable
Draft and Review, and automatically save only eligible Review items into the
existing selection checksum model.

`GET /unified-workspaces/{workspace_id}/grouped-grid` returns Source Product
parents and stable Listing children. It supports `page`, `pageSize`, `search`,
and `view=changed|ready|blocked|unchanged|all`. Paging is by parent product so
multiple Listings are never split or collapsed.

Review, selection, Dry Run, and Apply continue to use the existing Unified
Workspace endpoints documented in [Unified Workspace API](UNIFIED_WORKSPACE_API.md).
There is no Source-specific provider write endpoint.
