"""Deterministic translator checksum helpers (Phase D2)."""

from __future__ import annotations

from app.flowhub.formula_translator.fingerprint import (
    compute_shape_registry_checksum,
    compute_translation_result_checksum,
)
from app.flowhub.formula_translator.registry import (
    FORMULA_SHAPE_REGISTRY_CHECKSUM,
    formula_shape_registry_payload,
)
from app.flowhub.formula_translator.contracts import FORMULA_SHAPE_REGISTRY_VERSION


def test_shape_registry_checksum_is_deterministic() -> None:
    base = compute_shape_registry_checksum(shapes=formula_shape_registry_payload())
    reverse = compute_shape_registry_checksum(
        shapes=tuple(reversed(formula_shape_registry_payload()))
    )
    assert base == reverse
    assert base == FORMULA_SHAPE_REGISTRY_CHECKSUM
    assert (
        base
        == compute_shape_registry_checksum(
            shapes=formula_shape_registry_payload(), registry_version=FORMULA_SHAPE_REGISTRY_VERSION
        )
    )


def test_shape_registry_checksum_changes_when_content_changes() -> None:
    base = compute_shape_registry_checksum(shapes=formula_shape_registry_payload())

    changed = compute_shape_registry_checksum(
        shapes=(
            *formula_shape_registry_payload()[:1],
            {
                "shape_id": "A1",
                "translation_status": "unsupported",
                "default_reason_code": "shape_unsupported",
                "is_price_target": True,
                "formula_cell_count": 2291,
                "topology_hint": "price_target_candidate",
                "notes": "mutated",
                "registry_version": FORMULA_SHAPE_REGISTRY_VERSION,
            },
            *formula_shape_registry_payload()[1:],
        )
    )
    assert changed != base


def test_translation_result_checksum_is_deterministic_and_sensitive() -> None:
    base = compute_translation_result_checksum(
        formula_rule_identity="A1:R1",
        translator_version="formula-translator-schema-v1",
        formula_shape_id="A1",
        translation_status="translated",
        reason_code="matched_supported",
        registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
        registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
        translation_input_payload={"a": 1, "b": 2},
        translation_output_payload={"x": [1, 2, 3], "y": "ok"},
        package_fingerprint=None,
        reviewed_by=None,
    )

    same = compute_translation_result_checksum(
        formula_rule_identity="A1:R1",
        translator_version="formula-translator-schema-v1",
        formula_shape_id="A1",
        translation_status="translated",
        reason_code="matched_supported",
        registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
        registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
        translation_input_payload={"b": 2, "a": 1},
        translation_output_payload={"y": "ok", "x": [1, 2, 3]},
        reviewed_by=None,
        package_fingerprint=None,
    )
    assert same == base

    changed = compute_translation_result_checksum(
        formula_rule_identity="A1:R1",
        translator_version="formula-translator-schema-v1",
        formula_shape_id="A1",
        translation_status="translated",
        reason_code="matched_supported",
        registry_version=FORMULA_SHAPE_REGISTRY_VERSION,
        registry_checksum=FORMULA_SHAPE_REGISTRY_CHECKSUM,
        translation_input_payload={"a": 1, "b": 2},
        translation_output_payload={"x": [1, 2, 4], "y": "ok"},
        package_fingerprint=None,
        reviewed_by=None,
    )
    assert changed != base
