"""Fingerprint stability/change and package-order independence."""

from __future__ import annotations

from app.flowhub.pricing_evaluation.fingerprint import (
    compute_dependency_fingerprint,
    compute_package_checksum,
)

_BASE_KWARGS = dict(
    channel_id="woocommerce:primary",
    product_ref="SKU-1",
    formula_shape_id="A1",
    translator_version="translator-not-active-v0",
    fx_snapshot_id="fx-1",
    currency_unit_registry_version="unit-registry-v1",
    channel_config_revision_id="ccr-1",
    mapping_revision_id="map-1",
    product_metadata_fingerprint="pmf-1",
    arithmetic_version="pricing-evaluation-arithmetic-v1",
    pricing_policy_revision_id=None,
)


def test_fingerprint_is_stable_for_identical_inputs_regardless_of_pin_ordering():
    a = compute_dependency_fingerprint(
        **_BASE_KWARGS,
        source_pins=[("vendor_a", "obs-1", "cs-1"), ("vendor_b", "obs-2", "cs-2")],
        manual_input_pins=[("mir-1", "mid-1")],
        derived_definition_ids=["def-1", "def-2"],
    )
    b = compute_dependency_fingerprint(
        **_BASE_KWARGS,
        source_pins=[("vendor_b", "obs-2", "cs-2"), ("vendor_a", "obs-1", "cs-1")],
        manual_input_pins=[("mir-1", "mid-1")],
        derived_definition_ids=["def-2", "def-1"],
    )
    assert a == b


def test_fingerprint_changes_when_an_observation_pin_changes():
    a = compute_dependency_fingerprint(
        **_BASE_KWARGS,
        source_pins=[("vendor_a", "obs-1", "cs-1")],
        manual_input_pins=[],
        derived_definition_ids=[],
    )
    b = compute_dependency_fingerprint(
        **_BASE_KWARGS,
        source_pins=[("vendor_a", "obs-1", "cs-1-different-checksum")],
        manual_input_pins=[],
        derived_definition_ids=[],
    )
    assert a != b


def test_fingerprint_changes_when_a_pinned_version_changes():
    a = compute_dependency_fingerprint(
        **_BASE_KWARGS, source_pins=[], manual_input_pins=[], derived_definition_ids=[]
    )
    changed_kwargs = dict(_BASE_KWARGS, currency_unit_registry_version="unit-registry-v2")
    b = compute_dependency_fingerprint(
        **changed_kwargs, source_pins=[], manual_input_pins=[], derived_definition_ids=[]
    )
    assert a != b


def test_fingerprint_changes_when_the_formula_shape_changes():
    a = compute_dependency_fingerprint(
        **_BASE_KWARGS, source_pins=[], manual_input_pins=[], derived_definition_ids=[]
    )
    changed_kwargs = dict(_BASE_KWARGS, formula_shape_id="A3")
    b = compute_dependency_fingerprint(
        **changed_kwargs, source_pins=[], manual_input_pins=[], derived_definition_ids=[]
    )
    assert a != b


def test_package_checksum_binds_the_dependency_fingerprint():
    checksum_a = compute_package_checksum(
        channel_id="woocommerce:primary",
        product_ref="SKU-1",
        workspace_id=None,
        workspace_pricing_evaluated_at="2026-08-07T00:00:00",
        dependency_fingerprint="fingerprint-a",
    )
    checksum_b = compute_package_checksum(
        channel_id="woocommerce:primary",
        product_ref="SKU-1",
        workspace_id=None,
        workspace_pricing_evaluated_at="2026-08-07T00:00:00",
        dependency_fingerprint="fingerprint-b",
    )
    assert checksum_a != checksum_b
