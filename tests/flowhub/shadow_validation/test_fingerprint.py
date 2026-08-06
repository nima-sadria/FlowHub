"""Checksum helpers for Shadow Validation persistence identities."""

from __future__ import annotations

from app.flowhub.shadow_validation.fingerprint import (
    compute_legacy_capture_checksum,
    compute_comparison_identity_checksum,
    compute_contract_checksum,
    compute_readiness_checksum,
    compute_window_checksum,
)


def test_window_checksum_is_deterministic() -> None:
    first = compute_window_checksum(
        channel_id="channel-1",
        scope_manifest_checksum="s" * 64,
        pricing_policy_activation_id="activation-1",
        pricing_authority_event_id="event-1",
        pricing_authority_head_version=4,
        formula_inventory_checksum="f" * 64,
        acceptance_policy_version="policy-1",
    )
    second = compute_window_checksum(
        channel_id="channel-1",
        scope_manifest_checksum="s" * 64,
        pricing_policy_activation_id="activation-1",
        pricing_authority_event_id="event-1",
        pricing_authority_head_version=4,
        formula_inventory_checksum="f" * 64,
        acceptance_policy_version="policy-1",
    )
    assert first == second


def test_window_checksum_changes_when_authority_head_changes() -> None:
    a = compute_window_checksum(
        channel_id="channel-1",
        scope_manifest_checksum="s" * 64,
        pricing_policy_activation_id=None,
        pricing_authority_event_id="event-1",
        pricing_authority_head_version=1,
        formula_inventory_checksum="f" * 64,
        acceptance_policy_version="policy-1",
    )
    b = compute_window_checksum(
        channel_id="channel-1",
        scope_manifest_checksum="s" * 64,
        pricing_policy_activation_id=None,
        pricing_authority_event_id="event-1",
        pricing_authority_head_version=2,
        formula_inventory_checksum="f" * 64,
        acceptance_policy_version="policy-1",
    )
    assert a != b


def test_contract_checksum_responds_to_stable_rule_identity() -> None:
    base = compute_contract_checksum(
        shape_id="A1",
        contract_revision="rev-1",
        contract_version="v1",
        target_kind="price_target",
        stable_rule_identity={"rule": "u-1"},
        required_input_identity={"input": "x"},
        required_output_lanes={"lanes": ["candidate"]},
        acceptance_effect="may_count",
        required_trace_components=[],
        classification_mapping={},
    )
    changed = compute_contract_checksum(
        shape_id="A1",
        contract_revision="rev-1",
        contract_version="v1",
        target_kind="price_target",
        stable_rule_identity={"rule": "u-1"},
        required_input_identity={"input": "x"},
        required_output_lanes={"lanes": ["effective"]},
        acceptance_effect="may_count",
        required_trace_components=[],
        classification_mapping={},
    )
    assert base != changed


def test_legacy_capture_checksum_is_stable_and_sensitive() -> None:
    base = compute_legacy_capture_checksum(
        channel_id="channel-1",
        frozen_evaluation_package_id="fep-1",
        legacy_formula_engine="engine",
        legacy_formula_engine_version="1.0",
        formula_rule_identity="rule-1",
        formula_shape_id="A1",
        workbook_identity=None,
        input_manifest_checksum="i" * 64,
        captured_candidate_numerator=100,
        captured_candidate_denominator=10,
        captured_effective_numerator=90,
        captured_effective_denominator=10,
        candidate_currency="USD",
        candidate_unit="USD",
        effective_currency="USD",
        effective_unit="USD",
    )
    changed = compute_legacy_capture_checksum(
        channel_id="channel-1",
        frozen_evaluation_package_id="fep-1",
        legacy_formula_engine="engine",
        legacy_formula_engine_version="1.0",
        formula_rule_identity="rule-1",
        formula_shape_id="A1",
        workbook_identity=None,
        input_manifest_checksum="i" * 64,
        captured_candidate_numerator=100,
        captured_candidate_denominator=10,
        captured_effective_numerator=90,
        captured_effective_denominator=12,
        candidate_currency="USD",
        candidate_unit="USD",
        effective_currency="USD",
        effective_unit="USD",
    )
    assert base != changed


def test_comparison_identity_checksum_is_sensitive_to_contract_pin() -> None:
    base = compute_comparison_identity_checksum(
        channel_id="channel-1",
        stable_rule_identity="rule-1",
        frozen_evaluation_package_id="fep-1",
        frozen_evaluation_package_checksum="c" * 64,
        legacy_formula_capture_id="cap-1",
        legacy_formula_capture_checksum="x" * 64,
        comparison_contract_id="contract-1",
        comparison_contract_checksum="y" * 64,
        comparison_algorithm_version="translator-1",
    )
    changed = compute_comparison_identity_checksum(
        channel_id="channel-1",
        stable_rule_identity="rule-1",
        frozen_evaluation_package_id="fep-1",
        frozen_evaluation_package_checksum="c" * 64,
        legacy_formula_capture_id="cap-1",
        legacy_formula_capture_checksum="x" * 64,
        comparison_contract_id="contract-2",
        comparison_contract_checksum="y" * 64,
        comparison_algorithm_version="translator-1",
    )
    assert base != changed


def test_readiness_checksum_is_sensitive_to_decision_payload() -> None:
    base = compute_readiness_checksum(
        validation_window_id="window-1",
        decision="ready",
        reason_code=None,
        comparison_count=3,
        readiness_payload={"match": True, "rules": 2},
    )
    changed = compute_readiness_checksum(
        validation_window_id="window-1",
        decision="not_ready",
        reason_code="comparison_scope_invalidated",
        comparison_count=3,
        readiness_payload={"match": True, "rules": 2},
    )
    assert base != changed
