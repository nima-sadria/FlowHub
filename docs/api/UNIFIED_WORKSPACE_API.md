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
| GET | `/{workspace_id}/audit` | Paginated append-only Workspace audit |
| POST | `/{workspace_id}/mappings/{listing_id}/decisions` | Approve/reject identity conflict with new Mapping revision |
| GET/PUT | `/preferences/me` | Presentation-only Channel visibility/order/fields/name-source preferences |
| POST | `/channels/{channel_id}/cache-refresh` | Explicit authorized cache refresh, blocked by overlapping Apply locks |

`POST /manual` selections use `{connector_id, product_id}`. These are Channel cache identities, not SKU matches. `POST /apply` requires `expected_selection_checksum`, `confirmed=true`, and an `Idempotency-Key` of at most 255 characters. The server reconstructs the persisted scope and returns `409 APPLY_SELECTION_CHECKSUM_MISMATCH` with zero provider calls if it differs. The frontend key is a fixed 64-character SHA-256 digest, independent of selection size. The logical operation identity also deduplicates the same confirmed scope when a client changes its HTTP header.

Apply may return per-item `applied`, `failed`, or `reconciliation_required`. Only an exact verified read-back produces `applied`. A stale ruleset, mapping, capability, currency profile, cache version/checksum, or cache older than the configured maximum returns `409 STALE_REVIEW`; clients must discard the Review and generate another without rereading the source.

Grid query fields include `page`, `pageSize` (maximum 500), `search`, `productType`, `mappingState`, Channel/Listing filters, price/stock filters, and `sort`. `sort` accepts up to five comma-separated `field:direction` values. Supported sort fields are canonical name, brand, category, product type, Mapping state, Channel, Listing ID, price, stock, status, and SKU; every query adds a stable Snapshot-row tie-breaker.
