from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "docs" / "architecture" / "formula_inventory"


def _documents() -> tuple[dict, dict]:
    cells = json.loads((INVENTORY / "formula_cells.json").read_text(encoding="utf-8"))
    shapes = json.loads((INVENTORY / "formula_shapes.json").read_text(encoding="utf-8"))
    return cells, shapes


def test_formula_inventory_reconciles_authoritative_totals() -> None:
    cells_document, shapes_document = _documents()
    cells = cells_document["cells"]
    metadata = cells_document["metadata"]

    assert len(cells) == metadata["formula_cell_count"] == 5_997
    assert sum(cell["contains_broken_ref"] for cell in cells) == 255
    assert len(shapes_document["shapes"]) == metadata["formula_shape_count"] == 13
    assert metadata["broken_formula_cell_count"] == 256


def test_formula_inventory_has_unique_ids_and_complete_provenance() -> None:
    cells_document, _ = _documents()
    cells = cells_document["cells"]
    ids = [cell["inventory_id"] for cell in cells]
    provenance = [
        (cell["workbook"], cell["worksheet"], cell["cell_address"]) for cell in cells
    ]

    assert len(ids) == len(set(ids))
    assert len(provenance) == len(set(provenance))
    assert all(all(item) for item in provenance)


def test_formula_inventory_shape_and_broken_exports_are_consistent() -> None:
    cells_document, shapes_document = _documents()
    cells = cells_document["cells"]
    shapes = shapes_document["shapes"]

    shape_counts = Counter(cell["detected_formula_shape"] for cell in cells)
    assert shape_counts == Counter(
        {shape["shape_id"]: shape["cell_count"] for shape in shapes}
    )

    with (INVENTORY / "formula_cells.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        csv_ids = [row["inventory_id"] for row in csv.DictReader(handle)]
    assert csv_ids == [cell["inventory_id"] for cell in cells]

    with (INVENTORY / "broken_formulas.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        broken_ids = [row["inventory_id"] for row in csv.DictReader(handle)]
    assert broken_ids == [
        cell["inventory_id"] for cell in cells if cell["translation_status"] == "broken"
    ]


def test_display_metrics_are_not_classified_as_price_targets() -> None:
    cells_document, _ = _documents()
    display_metrics = [
        cell for cell in cells_document["cells"] if cell["detected_formula_shape"] == "A7"
    ]

    assert len(display_metrics) == 319
    assert {cell["cell_role"] for cell in display_metrics} == {"display_metric"}
    assert {cell["translation_status"] for cell in display_metrics} == {"unsupported"}
