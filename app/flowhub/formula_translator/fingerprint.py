"""Deterministic checksum helpers for formula translator contracts and results."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.flowhub.formula_translator.contracts import FORMULA_SHAPE_REGISTRY_VERSION
from app.flowhub.unified_workspace.domain import checksum


def compute_shape_registry_checksum(
    *,
    shapes: Sequence[Mapping[str, object]],
    registry_version: str = FORMULA_SHAPE_REGISTRY_VERSION,
) -> str:
    payload = {
        "registry_version": registry_version,
        "shapes": tuple(
            {
                key: shape[key]
                for key in sorted(shape.keys())
                if shape[key] is not None
            }
            for shape in sorted(shapes, key=lambda item: str(item.get("shape_id", "")))
        ),
    }
    return checksum(payload)


def compute_translation_result_checksum(
    *,
    formula_rule_identity: str,
    translator_version: str,
    formula_shape_id: str | None,
    translation_status: str,
    reason_code: str,
    registry_version: str,
    registry_checksum: str,
    translation_input_payload: Mapping[str, object],
    translation_output_payload: Mapping[str, object],
    package_fingerprint: str | None = None,
    reviewed_by: str | None = None,
) -> str:
    payload = {
        "formula_rule_identity": formula_rule_identity,
        "translator_version": translator_version,
        "formula_shape_id": formula_shape_id,
        "translation_status": translation_status,
        "reason_code": reason_code,
        "registry_version": registry_version,
        "registry_checksum": registry_checksum,
        "translation_input_payload": dict(translation_input_payload),
        "translation_output_payload": dict(translation_output_payload),
        "package_fingerprint": package_fingerprint,
        "reviewed_by": reviewed_by,
    }
    return checksum(payload)
