# Unified Workspace REST API

All resources are under `/api/v2/unified-workspaces`, use bearer authentication, and enforce server-side role-compatible permissions. Mutations accept strict DTOs (`extra=forbid`). Errors use an explicit code/message inside the existing FlowHub HTTP error envelope.

| Method | Path | Purpose |
|---|---|---|
| POST | `/manual` | Create Manual Workspace and immutable internal Snapshot from selected cache identities |
| POST | `/source` | Read the available source once and create a unified immutable Snapshot |
| GET | `/{workspace_id}` | Workspace, Snapshot and Draft pointers |
| GET | `/{workspace_id}/grid` | Deterministically paginated/filterable/sortable Listing rows and dynamic Channel capabilities |
| POST | `/{workspace_id}/draft/revisions` | Optimistic, transactional Save Draft |
| GET | `/{workspace_id}/draft/revisions` | Paginated immutable history |
| POST | `/{workspace_id}/draft/revisions/{revision_id}/restore` | Create a new revision from history |
| POST | `/{workspace_id}/reviews` | Generate deterministic mandatory Review |
| GET | `/{workspace_id}/reviews/{review_id}` | Read Review issues and eligibility |
| PUT | `/{workspace_id}/reviews/{review_id}/selection` | Persist a versioned canonical selected-only scope and return its SHA-256 checksum |
| POST | `/{workspace_id}/apply` | Submit confirmed selected Review items through the shared Write Pipeline |
| GET | `/{workspace_id}/apply/{job_id}` | Per-change Apply and cache-sync results |
| POST | `/{workspace_id}/apply/{job_id}/reconcile` | Read back an uncertain durable attempt without blind redispatch |
| POST | `/apply-jobs/recover-stale` | Classify stale running jobs from immutable attempt evidence without dispatch |
| GET | `/{workspace_id}/audit` | Paginated append-only Workspace audit |
| POST | `/{workspace_id}/mappings/{listing_id}/decisions` | Approve/reject identity conflict with new Mapping revision |
| GET/PUT | `/preferences/me` | Presentation-only Channel visibility/order/fields/name-source preferences |
| POST | `/channels/{channel_id}/cache-refresh` | Explicit authorized cache refresh, blocked by overlapping Apply locks |

`POST /manual` selections use `{connector_id, product_id}`. These are Channel cache identities, not SKU matches. `POST /apply` requires `expected_selection_checksum`, `confirmed=true`, and an `Idempotency-Key` of at most 255 characters. The server reconstructs the persisted scope and returns `409 APPLY_SELECTION_CHECKSUM_MISMATCH` with zero provider calls if it differs. The frontend key is a fixed 64-character SHA-256 digest, independent of selection size. The logical operation identity also deduplicates the same confirmed scope when a client changes its HTTP header.

Apply may return per-item `applied`, `failed`, or `reconciliation_required`. Provider acceptance is an intermediate evidence state, never success. Only an exact verified read-back produces `applied` and permits cache mutation or success audit. A stale ruleset, mapping, capability, currency profile, cache version/checksum, or cache older than the configured maximum returns `409 STALE_REVIEW`; clients must discard the Review and generate another without rereading the source.

Apply and Product Pricing use the same provider-neutral durable attempt/event model. Repeating a logical request with existing dispatch evidence performs verification only. `POST /apply-jobs/recover-stale` requires Apply permission, classifies stale workers from their latest immutable attempt outcome, and issues no provider writes. `POST /{workspace_id}/apply/{job_id}/reconcile` selects uncertain items only and rebuilds verification requests exclusively from the persisted attempt payload.

Production Grid builds require `VITE_HANDSONTABLE_LICENSE_KEY`. Development/test may use the vendor evaluation mode. A Production build without a non-evaluation configured value renders the Grid unavailable with an explicit configuration error; no license key is stored by this API or committed to source control. Commercial deployment remains blocked until the Owner supplies and configures a valid purchased license.

Grid query fields include `page`, `pageSize` (maximum 500), `search`, `productType`, `mappingState`, Channel/Listing filters, price/stock filters, and `sort`. `sort` accepts up to five comma-separated `field:direction` values. Supported sort fields are canonical name, brand, category, product type, Mapping state, Channel, Listing ID, price, stock, status, and SKU; every query adds a stable Snapshot-row tie-breaker.
