# Authoritative Formula Inventory Summary

## Source snapshot

| Field | Value |
| --- | --- |
| Workbook | `Price List.xlsx` |
| SHA-256 | `a529c3306d6db3923eb55451562c5a1eb4886861c45b390cddfdfc6f70db6a45` |
| Worksheets | 22 |
| Formula-bearing worksheets | 20 |
| Formula cells | 5997 |
| Normalization | `flowhub-formula-r1c1-v1` |

The inventory uses the workbook's stored cached result. It does not recalculate or repair any formula. Shared formulas are expanded to their exact cell-relative A1 formula before inventorying.

## Documented-total reconciliation

| Measure | Documented | Observed | Result |
| --- | --- | --- | --- |
| Formula cells | 5997 | 5997 | match |
| Formula shapes | 13 | 13 | match |
| Formula cells containing `#REF!` | 255 | 255 | match |

The workbook also contains one non-`#REF!` broken formula: `Surface Acc!I12` is cached as `#VALUE!`. Therefore the authoritative total is **256 broken formula cells**, comprising **255 documented `#REF!` cells plus one additional cached error**.

## Formula duplication

| Measure | Count |
| --- | --- |
| Unique exact formula texts | 3783 |
| Exact duplicate groups | 1071 |
| Cells belonging to exact duplicate groups | 3285 |
| Unique normalized R1C1 formulas | 53 |
| Normalized duplicate groups | 43 |
| Cells belonging to normalized duplicate groups | 5987 |
| Semantic/syntax shapes | 13 |

Normalized formulas preserve constants and reference geometry while replacing cell location with deterministic R1C1 offsets. Shape identity is a separate syntax skeleton that replaces valid references with `<REF>` and preserves broken `#REF!` tokens.

## Confirmed shapes

| Shape | Cells | Role | Translation | Semantics |
| --- | --- | --- | --- | --- |
| A1 | 2291 | price_target_candidate | supported | Price target from one basis, a percentage parameter, an optional fixed addend, and floor-to-50000 after scaling by 1000000. |
| A2 | 1840 | basis_selection | supported | Minimum non-zero quote across a same-row vendor range. |
| A3 | 663 | price_target_candidate | supported | Price target from a basis and percentage, scaled by 1000 and floored to 100000. |
| A4 | 90 | price_target_candidate | supported | A3 price target with a fixed 500000 surcharge applied after rounding. |
| A5 | 7 | price_target_candidate | supported | Price target rounded upward to two negative decimal places after percentage markup. |
| A6 | 327 | price_target_candidate | unknown | UGREEN price candidate from one source value and the manually stored G2 multiplier, followed by division by 10 after rounding. |
| A7 | 319 | display_metric | unsupported | Derived purchase-to-consumer ratio used as a display metric, not a Channel price target. |
| A8 | 25 | metadata_reference | supported_with_review | Same-column copy of manually entered header/vendor metadata. |
| A9 | 254 | price_target_candidate | broken | A1 variant with missing percentage and addend references. |
| A10 | 94 | price_target_candidate | supported | Parenthesized syntax variant of A3 with the same evidenced arithmetic. |
| A11 | 85 | price_target_candidate | supported | Price target with a fixed 500000 amount added before floor-to-100000. |
| A12 | 1 | anomalous_formula | broken | One anomalous cross-row minimum formula in Surface Acc!I12, located in a Link column and cached as #VALUE!. |
| A13 | 1 | price_target_candidate | broken | A10 variant with a missing price-basis reference. |

## Classification totals

| Input topology | Cells |
| --- | --- |
| single_source | 1020 |
| multi_source | 1841 |
| external_market | 0 |
| manual_reference | 352 |
| derived_reference | 2784 |

| Translation status | Cells |
| --- | --- |
| broken | 256 |
| supported | 5070 |
| supported_with_review | 25 |
| unknown | 327 |
| unsupported | 319 |

| Validation feasibility | Cells |
| --- | --- |
| comparison_not_possible | 256 |
| provenance_partial | 327 |
| replayable | 5414 |

| Cell role | Cells |
| --- | --- |
| anomalous_formula | 1 |
| basis_selection | 1840 |
| display_metric | 319 |
| metadata_reference | 25 |
| price_target_candidate | 3812 |

No formula cell is marked active or inactive: workbook presence and worksheet visibility do not prove operational Channel authority. Every record therefore has `activity_status = unknown`.

## Worksheet coverage

| Worksheet | Formula cells |
| --- | --- |
| Surface | 595 |
| Surface Acc | 127 |
| Mac | 407 |
| iPad | 266 |
| Apple Acc | 223 |
| iPhone | 480 |
| Apple Watch | 78 |
| PS5 | 46 |
| Beats | 181 |
| WHOOP+FITBIT | 11 |
| SandDisk | 150 |
| Logitech | 764 |
| Rapoo | 89 |
| Speaker | 360 |
| Belkin | 128 |
| Mophie | 165 |
| UGREEN | 655 |
| JCPAL | 958 |
| POWEROLOGY | 234 |
| Porodo | 80 |

## Evidence-backed anomalies and gates

- `A9`: 254 Logitech price cells contain broken percentage/addend references.
- `A13`: `Beats!C34` contains a broken price-basis reference.
- `A12`: `Surface Acc!I12` is in a Link column, reads row 3 instead of row 12, and is cached as `#VALUE!`; its intended meaning is not inferred.
- `A6`: 327 UGREEN price candidates use the manually stored, unlabeled `G2` multiplier and divide by 10 after rounding. The arithmetic is proven, but the business meaning and output-unit semantics remain unproven, so the shape stays quarantined as `unknown`.
- `A7` is a display ratio and is explicitly not a Channel price target.
- `A8` copies vendor/header metadata and is explicitly not a Channel price target.

## Inventory closure

The cell-level inventory is complete for the exact workbook hash above: all 5,997 formula cells have workbook, worksheet, cell, exact formula, cached result, references, normalized formula, shape, topology, translation status, and validation classification. Translator implementation and migration activation remain blocked by the quarantined/broken shapes and fixture work; this inventory does not activate or repair anything.
