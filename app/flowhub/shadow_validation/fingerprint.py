"""Checksum helpers for Shadow Validation immutable identities."""

from __future__ import annotations

from app.flowhub.unified_workspace.domain import checksum


def compute_window_checksum(
    *,
    channel_id: str,
    scope_manifest_checksum: str,
    pricing_policy_activation_id: str | None,
    pricing_authority_event_id: str,
    pricing_authority_head_version: int,
    formula_inventory_checksum: str,
    acceptance_policy_version: str,
) -> str:
    return checksum(
        {
            "channel_id": channel_id,
            "scope_manifest_checksum": scope_manifest_checksum,
            "pricing_policy_activation_id": pricing_policy_activation_id,
            "pricing_authority_event_id": pricing_authority_event_id,
            "pricing_authority_head_version": pricing_authority_head_version,
            "formula_inventory_checksum": formula_inventory_checksum,
            "acceptance_policy_version": acceptance_policy_version,
        }
    )


def compute_contract_checksum(
    *,
    shape_id: str,
    contract_revision: str,
    contract_version: str,
    target_kind: str,
    stable_rule_identity: str,
    required_input_identity: object,
    required_output_lanes: object,
    acceptance_effect: str,
    required_trace_components: object,
    classification_mapping: object,
) -> str:
    return checksum(
        {
            "shape_id": shape_id,
            "contract_revision": contract_revision,
            "contract_version": contract_version,
            "target_kind": target_kind,
            "stable_rule_identity": stable_rule_identity,
            "required_input_identity": required_input_identity,
            "required_output_lanes": required_output_lanes,
            "acceptance_effect": acceptance_effect,
            "required_trace_components": required_trace_components,
            "classification_mapping": classification_mapping,
        }
    )


def compute_legacy_capture_checksum(
    *,
    channel_id: str,
    frozen_evaluation_package_id: str,
    legacy_formula_engine: str,
    legacy_formula_engine_version: str,
    formula_rule_identity: str,
    formula_shape_id: str,
    workbook_identity: str | None,
    input_manifest_checksum: str,
    captured_candidate_numerator: int,
    captured_candidate_denominator: int,
    captured_effective_numerator: int,
    captured_effective_denominator: int,
    candidate_currency: str | None,
    candidate_unit: str | None,
    effective_currency: str | None,
    effective_unit: str | None,
) -> str:
    return checksum(
        {
            "channel_id": channel_id,
            "frozen_evaluation_package_id": frozen_evaluation_package_id,
            "legacy_formula_engine": legacy_formula_engine,
            "legacy_formula_engine_version": legacy_formula_engine_version,
            "formula_rule_identity": formula_rule_identity,
            "formula_shape_id": formula_shape_id,
            "workbook_identity": workbook_identity,
            "input_manifest_checksum": input_manifest_checksum,
            "captured_candidate_numerator": captured_candidate_numerator,
            "captured_candidate_denominator": captured_candidate_denominator,
            "captured_effective_numerator": captured_effective_numerator,
            "captured_effective_denominator": captured_effective_denominator,
            "candidate_currency": candidate_currency,
            "candidate_unit": candidate_unit,
            "effective_currency": effective_currency,
            "effective_unit": effective_unit,
        }
    )


def compute_comparison_identity_checksum(
    *,
    channel_id: str,
    stable_rule_identity: str,
    frozen_evaluation_package_id: str,
    frozen_evaluation_package_checksum: str,
    legacy_formula_capture_id: str,
    legacy_formula_capture_checksum: str,
    comparison_contract_id: str,
    comparison_contract_checksum: str,
    comparison_algorithm_version: str,
) -> str:
    return checksum(
        {
            "channel_id": channel_id,
            "stable_rule_identity": stable_rule_identity,
            "frozen_evaluation_package_id": frozen_evaluation_package_id,
            "frozen_evaluation_package_checksum": frozen_evaluation_package_checksum,
            "legacy_formula_capture_id": legacy_formula_capture_id,
            "legacy_formula_capture_checksum": legacy_formula_capture_checksum,
            "comparison_contract_id": comparison_contract_id,
            "comparison_contract_checksum": comparison_contract_checksum,
            "comparison_algorithm_version": comparison_algorithm_version,
        }
    )


def compute_readiness_checksum(
    *,
    validation_window_id: str,
    decision: str,
    reason_code: str | None,
    comparison_count: int,
    readiness_payload: object,
) -> str:
    return checksum(
        {
            "validation_window_id": validation_window_id,
            "decision": decision,
            "reason_code": reason_code,
            "comparison_count": comparison_count,
            "readiness_payload": readiness_payload,
        }
    )
