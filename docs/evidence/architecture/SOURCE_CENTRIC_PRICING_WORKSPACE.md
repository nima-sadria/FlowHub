# Source-Centric Pricing Workspace

FlowHub v1.3 adds a seller-oriented Source Product view while preserving the
frozen v1.2 execution and safety architecture. A Source Product is the visible
parent. Its WooCommerce, SnappShop, TapsiShop, and future supported Listings are
independent children with stable Listing identities.

## Processing path

```text
Saved Source Mapping
    -> immutable Mapping revision (identity may be PENDING)
    -> local identity validation against an immutable Observation/Sheet revision
    -> durable Source Product Key bindings
    -> immutable Workspace Snapshot
    -> Source Product and Listing resolution
    -> independent per-Channel analysis
    -> immutable Draft revision
    -> deterministic Review / Dry Run
    -> checksum-bound selected Listings
    -> shared Write Pipeline
    -> exact provider verification or reconciliation
    -> verified Channel Cache update
    -> append-only Audit
```

The Source, Sheet, import, formula, and UI layers cannot call provider mutation
methods. Existing Workspace authentication, permissions, maintenance mode,
cache freshness, Mapping versions, currency profiles, Listing guards, durable
attempts, crash recovery, verification, and Audit behavior remain authoritative.
Saving Source configuration also performs no provider read. Acquisition and
worksheet discovery are explicit operations with separate allowances; local
Preview and validation consume neither allowance.

## Source and Channel mappings

Each immutable Mapping revision stores Source Product fields separately from
per-Channel fields. Supported references are an Excel-style column letter, an
exact header name, a managed Sheet column ID where available, or disabled.
Header detection may help an operator, but it never overrides the saved
Mapping. Every Channel also has an explicit participation flag; disabling a
Channel preserves its saved fields and excludes it from new analysis.

Source fields are required name and Source Product Key plus optional category,
brand, and cost. The Source Product Key is the provider-neutral, nonblank,
unique, stable identity within one Source namespace. Every Mapping revision
also records an Identity Authority: metadata naming the external system,
internal scheme, or custom source of truth that owns the key's meaning.

Identity Authority is not a Channel, does not enable a Channel, and does not
require Channel credentials. Historical mappings whose authority was never
recorded remain `unspecified`; FlowHub does not infer WooCommerce or another
provider from a column name or value. They remain identity-PENDING until the
Owner explicitly selects and saves an authority.

Each enabled, implemented Channel independently maps its connector-defined
Product Identifier, price, stock, and status fields. Only fields required by
that connector's capability contract block readiness. Coming Soon and disabled
Channels are excluded. Technical Channel IDs remain internal; the UI renders
friendly instance names.

Source Product Key and Channel Product Identifier are separate roles. They may
use the same Source column or different columns, and different Channels may use
different Product Identifier columns. The saved Mapping never imposes a
one-column-one-role restriction across these compatible roles.

Identity readiness is derived from revision-bound local evidence. `PASS` means
the complete participating dataset has valid keys and consistent Canonical
Product bindings; `BLOCKED` identifies key or binding conflicts; `PENDING`
means the Mapping is saved but no compatible local dataset exists. Only PASS
may make the Source Ready for a new Workspace decision.

New Mapping writes use identity policy v2. Historical v1 revisions remain
readable but project PENDING and require an explicit Owner upgrade before a new
Workspace can be opened. External readiness is scoped by a non-secret binding
fingerprint (normalized endpoint, account, workbook path, and connector), so a
connection change cannot reuse evidence from a different logical workbook.
Open Workspace pins the exact compatible retained dataset and performs no
provider read. It also pins one exact Listing evidence cohort: durable Source
key bindings are proposed only from complete enabled/resolved Listings, all
such Listings are locked and rechecked at commit, and the confirmed bindings
are persisted in Snapshot provenance. Managed Source Workspace creation
requires the persisted Source identity; it has no source-less acquisition
fallback.

The default value policy is conservative:

| Input | Default interpretation |
| --- | --- |
| blank | no target change |
| `x` | Listing unavailable |
| `-` | no target change |
| zero | explicit zero where the field permits it |
| formula | use the deterministic calculated value |
| invalid text | blocked Data Quality issue |

FlowHub never infers IRR or Toman. The existing versioned currency profile and
Channel-native unit rules still decide whether a target is valid.

## Daily Workspace

The default view emphasizes Ready, Blocked, Changed, and Unchanged counts.
Eligible changed Review items are selected automatically. Unchanged,
unsupported, and blocked items are not selected. A blocked child Listing does
not prevent another valid Listing from reaching Review.

One Source Product may have one WooCommerce Listing and multiple marketplace
Listings. Every child remains independently selectable. Inline target editing
uses immutable Canonical Product, Listing, Channel, and field identities rather
than visual row indexes. Saving creates a new Draft revision; selection changes
invalidate the v1.2 selection checksum.

## Data Quality

Data Quality is a separate operator surface. Issues are grouped by severity,
category, and Channel and include a plain-language explanation, recommended
action, Source row identity, and optional technical details. Categories include
missing mappings, duplicate Listing rows, Mapping conflicts, invalid values,
currency problems, unavailable cache, stale cache, and unsupported capability.

## FlowHub Sheet

FlowHub Sheet is a managed product and pricing sheet, not an Excel replacement.
Rows, columns, and cells are normalized database records. Every save produces
an immutable revision; revisions referenced by Snapshots are never overwritten.
Bulk imports and edits use batched persistence and identity-based optimistic
concurrency. The browser requests at most 500 rows and virtualizes the visible
window, so a 10,000-row Sheet is not loaded or rendered in full.

The Sheet editor is a FlowHub-owned React UI. It does not depend on Handsontable
commercial functionality. The stable v1.2 manual Workspace still uses
Handsontable until a future explicitly approved parity replacement; its existing
commercial-deployment license requirement is unchanged.

## Formula grammar and limits

Formula expressions begin with `=` and accept cell references, ranges,
parentheses, numeric constants, arithmetic (`+ - * /`), comparisons, and these
functions: `ROUND`, `IF`, `MIN`, `MAX`, and `SUM`.

Examples:

```text
=B2
=B2+C2
=B2*(1+C2/100)
=ROUND(B2,0)
=IF(B2>0,B2,0)
=MIN(B2:C2)
=MAX(B2:C2)
=SUM(B2:C2)
```

The `flowhub-formula-1` engine parses a restricted grammar and interprets the
validated syntax tree. It does not use `eval` and cannot execute JavaScript,
Python, SQL, macros, files, network calls, attributes, imports, or external
functions. Formula length, dependency count, evaluation steps, Sheet rows, and
Sheet columns are bounded. Circular references, division by zero, invalid
functions, and resource-limit violations are persisted as calculation errors.

## Import and external compatibility

CSV and XLSX imports are previewed before persistence. The user selects a
worksheet and data start row, then applies explicit Source and Channel mappings.
The uploaded bytes are checksummed and are never modified. Import metadata keeps
the source filename, type, worksheet, timestamp, row count, Mapping version, and
checksum.

Existing external Sources are retained as the advanced workflow. The connector
downloads and parses the workbook only through an explicit acquisition action.
That action creates an immutable Source Observation with a retained normalized
dataset. Mapping Save, local Preview, and identity validation reuse that local
evidence without provider I/O. Workspace creation then resolves all enabled
Channel mappings from the validated Observation. Each Channel's Product
Identifier, price, stock, and status are read only from that Channel's saved
mapping and compared only with its own Listing cache.

If no compatible local dataset exists, the Mapping remains saved with identity
status PENDING and the operator is offered an explicit Read Source/Create
Snapshot action. Acquisition quota errors belong to that action, never to Save.

The legacy Nextcloud `Product ID / Price / Stock` configuration is exposed as a
WooCommerce-primary compatibility prefill only. It is not copied to other
Channels and becomes active only after the operator explicitly saves a new
per-Channel Mapping revision.

## Persistence and migration

`FLOWHUB_018` is an additive, forward-only migration. It creates normalized
Source, Mapping revision, Sheet revision, column, row, cell, import, and Data
Quality tables with foreign keys, indexes, uniqueness constraints, optimistic
version fields, and immutable revision triggers. It does not alter v1.2
Snapshot or historical Workspace data and does not rewrite older migrations.

The provider-neutral identity and local-validation decision is defined by
`ADR_SOURCE_PRODUCT_IDENTITY_AUTHORITY_ADDENDUM.md`. Its implementation is also
additive and preserves existing keys with Authority `unspecified`; it adds no
provider-specific Source identity columns.

## Third-party licenses

- XLSX parsing uses the already-declared `openpyxl` dependency (MIT license).
- The internal Sheet UI adds no grid dependency and uses React and browser DOM
  primitives already present in FlowHub.
- No Handsontable source or proprietary implementation detail is copied.
