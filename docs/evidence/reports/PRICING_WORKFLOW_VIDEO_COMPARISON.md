# Product Pricing Workflow — Video Comparison

## Reference recordings

The complete recordings were reviewed from start to finish using a two-second storyboard and targeted frame inspection.

| Recording | Duration | Visual source |
| --- | ---: | --- |
| Wanted Model.mp4 | 31.57 s | `C:/Users/nimas/Downloads/Wanted Model.mp4` |
| Present Model.mp4 | 24.53 s | `C:/Users/nimas/Downloads/Present Model.mp4` |

## Present Model timeline

The present recording is the current product-first workflow:

| Time | Interaction | Result |
| ---: | --- | --- |
| 00:00–00:04 | Products page is visible with search, Channel/category/type filters, pagination, and one `Edit prices` action per product row. | The user sees a paginated product list; only one product is opened at a time. |
| 00:04–00:10 | The user enters a product search and waits for the list to refresh. | Filtering happens on the Products page, but there is no batch editing surface. |
| 00:10–00:18 | The user chooses a row-level `Edit prices` action. | A large in-page Channel prices panel opens above the list. |
| 00:18–00:24.53 | The panel shows one product, one Channel section per destination, Current/Proposed/Validation/Freshness/Pending state, and Validate / Preview-Dry Run / Approve / Apply actions. | Editing and review are scoped to one product; the user must close the panel and repeat for another product. |

**Observed interaction cost:** at least one row action plus panel context switch per product, one open panel at a time, and repeated return-to-list transitions. The recording does not show a continuous multi-product editing session.

## Wanted Model timeline

The wanted recording is a dense, spreadsheet-style bulk pricing surface:

| Time | Interaction | Result |
| ---: | --- | --- |
| 00:00–00:08 | A compact filter/criteria view is configured (many product attributes are available without opening a product). | The user defines a result set before editing. |
| 00:08–00:10 | The filter operation is submitted and the grid enters a loading state. | One transition loads the matching products. |
| 00:10–00:12 | A wide editable table appears with selection, product identity, current/target price-related columns, stock/status fields, and a horizontal scrollbar. | Many products are visible simultaneously; the page remains a single work surface. |
| 00:12–00:24 | The user works directly in the grid: selection checkboxes, horizontal scrolling, dense rows, and visible current/target values are used without a product modal. | Changes can be made across many products in one continuous session. |
| 00:24–00:31.57 | The grid remains the operational context while changed/selected values and bulk actions are available. | Review and eventual batch execution are conceived as one operation, not one operation per product. |

**Observed interaction model:** one filter action, one result grid, direct cell-level work, stable selection across rows, horizontal channel fields, and a single batch-oriented follow-up path.

## Gap and root cause

Three prior revisions improved individual product inspection and safety messaging, but kept the old Product list as the primary editing surface. The route still renders a row-level `Edit prices` affordance and the existing Channel prices panel is the only place where proposed values can be edited. Consequently the implementation remains modal-centric and cannot satisfy the wanted bulk workflow even though the underlying Draft/Review/Dry Run/Apply safeguards are present.

The correction in this change is intentionally limited to the presentation and interaction layer: the existing safe Draft, Review, Dry Run, Apply, Write Pipeline, verification, cache, and Audit services remain authoritative.

## Exact implementation contract

The redesigned workflow must provide:

1. A compact filter toolbar that stays on the pricing workspace page.
2. A dense, virtualized, product-grouped result grid with Channel listings in the same context.
3. Inline Target Price, Target Stock, and Target Status editing; Product identity and provider Current values remain read-only.
4. Enter/Tab keyboard movement, Escape cancellation, clipboard paste, and stable Listing/Product identity resolution.
5. Automatic local Draft/change tracking and automatic selection of valid changed fields only.
6. Field-level and Listing-level deselection without reconstructing scope from row indexes.
7. A live summary for changed, selected, ready, blocked, and hidden-pending changes.
8. One batch Review, one Dry Run, and one explicitly confirmed selected-only Apply using the existing safe pipeline.
9. Draft and selection persistence across pagination and filtering.
10. No product-edit modal for normal pricing edits; the existing details panel may remain secondary.

## Acceptance comparison

| Measure | Present Model | Wanted/target implementation |
| --- | --- | --- |
| Products edited continuously | 1 | 10+ (and 20 in the acceptance scenario) |
| Product editing modals | 1 per product | 0 for normal edits |
| Route changes | Product list → panel context and back | 0; filter and grid stay on one page |
| Review operations | Per product context | 1 batch operation |
| Dry Run operations | Per product context | 1 batch operation |
| Apply operations | Per product context | 1 selected-only operation |
| Main editing method | Panel inputs | Inline grid cells + keyboard/paste |
| Selection | Row/product context | Product, Listing, and changed-field scope |

## Final acceptance evidence

The completed browser run uses one dense virtualized table with grouped Channel
columns. Product identity remains frozen, all sellable rows are directly
editable, and variable parents remain read-only. Changes are keyed by the
immutable Product, Listing, Channel, and field tuple; no visual row index is
used as business identity.

At 1440×900 the acceptance run recorded:

| Measure | Result |
| --- | ---: |
| Visible sellable rows | 23 |
| Products edited inline | 10 |
| Product edit panels opened | 0 |
| Route changes | 0 |
| Review operations | 1 |
| Dry Run operations | 1 |
| Apply operations | 1 |
| Time to first editable cell | 4,686 ms |
| Time for ten direct edits | 10,458 ms |

The 10,000-product browser run used five visible Channels and a maximum
100-product server window. It rendered 23 rows and 2,997 DOM nodes, with an
observed JavaScript heap of 62,062,961 bytes. The measured readiness, scroll,
edit, paste, filter, sort, and page-return values are stored in
`docs/screenshots/v1.3/pricing-workflow-redesign/pricing-10000-benchmark-metrics.json`.

The final interaction recording is
`docs/videos/v1.3/pricing-workflow-redesign/wanted-model-final-remediation.webm`.
It shows filtering, ten direct cell edits, multiline paste, immediate automatic
field selection, a percentage transformation preview, one field deselection,
page/filter return with the Draft overlay intact, one Review, one Dry Run, and
one selected-only Apply.
