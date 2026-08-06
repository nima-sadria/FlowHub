# Appendix A Formula Classification

This document records only the formula shapes that are explicitly evidenced in
the repository. It does **not** invent classifications for unseen shapes.

## Evidence source

- `docs/architecture/PRICING_MATRIX_DESIGN.md`

The design document is currently the authoritative inventory artifact checked
into the repository. No separate workbook-analysis export or translator
inventory file was found in the repository tree.

## Classified shapes

| Shape | Repository classification | Notes |
|---|---|---|
| A1 | Supported / translated | Exact policy parameterization for `percent_bp`, `fixed_addend`, `floor`, `quote_scale = 1000000`. |
| A2 | Supported / translated | Basis selection `min`, excluding zero values. |
| A3 | Supported / translated | Similar to A1 with `quote_scale = 1000` and no fixed addend. |
| A4 | Supported / translated | `surcharge_minor = 500000`, `round_then_surcharge`. |
| A5 | Supported / translated | `ROUNDUP(...,-2)` mapped to `ceil` with step from the negative digit argument. |
| A6 | Quarantined | `/10` occurs after rounding; plausible Rial/Toman outbound conversion, but unproven. |
| A7 | Not a price target | Derived display metric only. |
| A8 | Translated at migration time | Plain cross-reference, resolved during migration, not modeled as a pricing shape. |
| A9 | Quarantined / impossible | `#REF!` variants are structurally invalid and never translated. |

## Explicit notes from the repository

- The design states that shapes not present in Appendix A after the real
  inventory pass are to be quarantined rather than guessed.
- The design also states that `IFERROR(..., "x")` and `IFERROR(..., "â‌Œ")`
  are not single outcomes; each occurrence must be classified against the
  precedence table.
- A6 is explicitly marked as quarantined until a fixture with real workbook
  output proves it.

## What remains unproven in the repository

- The remaining 255 broken formulas are referenced in the ADR context, but the
  repository does not contain a separate workbook inventory file enumerating
  them one by one.
- The repository therefore does not yet provide a formula-by-formula proof
  beyond the Appendix A shapes above.

