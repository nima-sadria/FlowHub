# Appendix A Formula Classification

This classification is derived from the authoritative production workbook
snapshot, not from formula examples or design inference.

## Evidence source

| Field | Value |
| --- | --- |
| Workbook | `Price List.xlsx` |
| SHA-256 | `a529c3306d6db3923eb55451562c5a1eb4886861c45b390cddfdfc6f70db6a45` |
| Worksheets | 22 total; 20 contain formulas |
| Formula cells | 5,997 |
| Unique normalized formulas | 53 |
| Formula shapes | 13 |
| Formula cells containing `#REF!` | 255 |
| Other broken formula cells | 1 (`Surface Acc!I12`, cached `#VALUE!`) |

The cell-level evidence is stored in `formula_inventory/formula_cells.csv` and
`formula_inventory/formula_cells.json`. Shape aggregates are stored in
`formula_inventory/formula_shapes.json`; all broken formulas are listed in
`formula_inventory/broken_formulas.csv`.

## Verified shapes

| Shape | Cells | Role | Translation status | Verified workbook semantics |
| --- | ---: | --- | --- | --- |
| A1 | 2,291 | Price target candidate | Supported | Basis plus percentage and optional fixed addend; multiply by 1,000,000 and floor to 50,000. |
| A2 | 1,840 | Basis selection | Supported | Minimum non-zero value across a same-row vendor range. |
| A3 | 663 | Price target candidate | Supported | Basis plus percentage; multiply by 1,000 and floor to 100,000. |
| A4 | 90 | Price target candidate | Supported | A3 arithmetic with 500,000 added after rounding. |
| A5 | 7 | Price target candidate | Supported | Basis plus percentage, rounded upward with `ROUNDUP(...,-2)`. |
| A6 | 327 | Price target candidate | Unknown / quarantined | UGREEN source value multiplied by the manually stored, unlabeled `G2`, floored to 50,000, then divided by 10. Arithmetic is proven; business meaning is not. |
| A7 | 319 | Display metric | Unsupported as pricing | `consumer / purchase` ratio. It is not a Channel price target. |
| A8 | 25 | Metadata reference | Supported with review | Same-column copies of manually entered vendor/header text such as `=M2` and `=N2`. |
| A9 | 254 | Price target candidate | Broken | A1 syntax with missing percentage and addend references (`#REF!`). |
| A10 | 94 | Price target candidate | Supported | Parenthesized syntax variant of A3 with the same arithmetic. |
| A11 | 85 | Price target candidate | Supported | Basis plus percentage and 500,000 before floor-to-100,000. |
| A12 | 1 | Anomalous formula | Broken | `Surface Acc!I12` reads `E3:I3` from a Link column and is cached as `#VALUE!`; intended meaning is not inferred. |
| A13 | 1 | Price target candidate | Broken | `Beats!C34` has a missing price-basis reference (`#REF!`). |

## Classification rules

- `Supported` is an inventory classification, not proof that translator
  fixtures exist. Activation remains gated on fixture-backed translation.
- A6 remains quarantined. The workbook does not label `G2`, and `/10` after
  rounding is not silently interpreted as a Source scale or unit declaration.
- A7 and A8 are retained for provenance but are not counted as Channel price
  targets.
- A9 and A13 account for all 255 documented `#REF!` cells. A12 is a separate
  non-`#REF!` workbook defect, bringing the complete broken-formula total to
  256.
- Workbook presence and worksheet visibility do not prove whether a rule is
  operationally active. Every cell therefore remains `activity_status =
  unknown` until independent Channel evidence exists.
