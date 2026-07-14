# Source-Centric Pricing Workspace

FlowHub v1.3 adds a seller-oriented Source Product view while preserving the
frozen v1.2 execution and safety architecture. A Source Product is the visible
parent. Its WooCommerce, SnappShop, TapsiShop, and future supported Listings are
independent children with stable Listing identities.

## Processing path

```text
Saved Source Mapping
    -> immutable Source/Sheet revision
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

## Source and Channel mappings

Each immutable Mapping revision stores Source Product fields separately from
per-Channel fields. Supported references are an Excel-style column letter, an
exact header name, a managed Sheet column ID, or disabled. Header detection may
help an operator, but it never overrides the saved Mapping.

Source fields are name, optional Source key, category, brand, and cost. Each
enabled, implemented Channel may independently map an external Listing ID,
price, stock, and status. Coming Soon and disabled Channels are excluded.
Technical Channel IDs remain internal; the UI renders friendly instance names.

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

Existing external Sources are retained as the advanced workflow and continue to
use their established read-once connector and immutable Snapshot path. The
legacy Nextcloud `Product ID / Price / Stock` configuration is not silently
reinterpreted as a marketplace mapping. Operators explicitly adopt a new
per-Channel Mapping when they move that Source into the v1.3 managed model.

## Persistence and migration

`FLOWHUB_018` is an additive, forward-only migration. It creates normalized
Source, Mapping revision, Sheet revision, column, row, cell, import, and Data
Quality tables with foreign keys, indexes, uniqueness constraints, optimistic
version fields, and immutable revision triggers. It does not alter v1.2
Snapshot or historical Workspace data and does not rewrite older migrations.

## Third-party licenses

- XLSX parsing uses the already-declared `openpyxl` dependency (MIT license).
- The internal Sheet UI adds no grid dependency and uses React and browser DOM
  primitives already present in FlowHub.
- No Handsontable source or proprietary implementation detail is copied.
