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
| PUT | `/{workspace_id}/reviews/{review_id}/selection` | Persist explicit selected-only scope outside immutable Review content |
| POST | `/{workspace_id}/apply` | Apply selected Review items; requires `Idempotency-Key` and confirmation |
| GET | `/{workspace_id}/apply/{job_id}` | Per-change Apply and cache-sync results |
| GET | `/{workspace_id}/audit` | Paginated append-only Workspace audit |
| POST | `/{workspace_id}/mappings/{listing_id}/decisions` | Approve/reject identity conflict with new Mapping revision |
| GET/PUT | `/preferences/me` | Presentation-only Channel visibility/order/fields/name-source preferences |
| POST | `/channels/{channel_id}/cache-refresh` | Explicit authorized cache refresh, blocked by overlapping Apply locks |

`POST /manual` selections use `{connector_id, product_id}`. These are Channel cache identities, not SKU matches. Apply sends no request for any unselected Review item. Reusing an idempotency key returns the original Apply resource.

Grid query fields include `page`, `pageSize`, `search`, `productType`, `mappingState`, `sortField`, and `sortDirection`. Supported sort fields are canonical name, product type, Channel, Listing ID, price, stock, status, and SKU; every query adds a stable row-ID tie-breaker.
