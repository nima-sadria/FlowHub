"""Deterministic checksum helpers for D6 preview outputs."""

from __future__ import annotations

from collections.abc import Sequence

from app.flowhub.unified_workspace.domain import checksum, stable_json


def compute_preview_row_checksum(*, row_payload: dict[str, object]) -> str:
    """Checksum for one preview row (canonical payload)."""

    return checksum(
        {
            "row": stable_json({k: row_payload[k] for k in sorted(row_payload)}),
        }
    )


def compute_preview_batch_checksum(*, batch_payload: dict[str, object], cell_payloads: Sequence[dict[str, object]]) -> str:
    """Deterministic aggregate checksum for one preview batch."""

    rows = []
    for payload in sorted(cell_payloads, key=lambda item: stable_json({k: item[k] for k in sorted(item)})):
        rows.append(stable_json({k: payload[k] for k in sorted(payload)}))

    return checksum(
        {
            "batch": stable_json({k: batch_payload[k] for k in sorted(batch_payload)}),
            "rows": rows,
        }
    )
