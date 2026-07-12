from __future__ import annotations

import pytest

from app.flowhub.workspace.preview_store import PreviewValidationError, _row_hashes


def test_row_hashes_accept_valid_unique_ids():
    hashes = _row_hashes([
        {"id": "wpr_a", "source": {"worksheet": "Sheet1", "rowNumber": 3}, "value": "same"},
        {"id": "wpr_b", "source": {"worksheet": "Sheet1", "rowNumber": 4}, "value": "same"},
    ])

    assert set(hashes) == {"wpr_a", "wpr_b"}
    assert hashes["wpr_a"] != hashes["wpr_b"]


@pytest.mark.parametrize("row_id", [None, ""])
def test_row_hashes_reject_missing_or_empty_ids(row_id):
    with pytest.raises(PreviewValidationError) as exc_info:
        _row_hashes([{"id": row_id, "source": {"worksheet": "Sheet1", "rowNumber": 3}}])

    assert exc_info.value.code == "PREVIEW_ROW_ID_INVALID"
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["row_index"] == 0


def test_row_hashes_reject_duplicate_ids_with_row_index():
    with pytest.raises(PreviewValidationError) as exc_info:
        _row_hashes([
            {"id": "wpr_duplicate", "source": {"worksheet": "Sheet1", "rowNumber": 3}},
            {"id": "wpr_duplicate", "source": {"worksheet": "Sheet1", "rowNumber": 4}},
        ])

    assert exc_info.value.code == "PREVIEW_ROW_ID_DUPLICATE"
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["row_index"] == 1
