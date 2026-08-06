"""Deterministic fingerprint and checksum for a Frozen Evaluation Package.

``dependency_fingerprint`` covers only the authoritative dependency identities
and versions (Section G): it must change whenever any of them changes and
stay stable for identical packages. ``package_checksum`` covers the package's
own full identity payload (the same "self-checksum" pattern used by
``PricingPolicyRevision`` and other revisioned records elsewhere in the
codebase) and additionally binds in the fingerprint itself.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.flowhub.unified_workspace.domain import checksum


def compute_dependency_fingerprint(
    *,
    channel_id: str,
    product_ref: str,
    formula_shape_id: str,
    translator_version: str,
    fx_snapshot_id: str | None,
    currency_unit_registry_version: str,
    channel_config_revision_id: str | None,
    mapping_revision_id: str | None,
    product_metadata_fingerprint: str | None,
    arithmetic_version: str,
    pricing_policy_revision_id: str | None,
    source_pins: Sequence[tuple[str, str, str]],
    manual_input_pins: Sequence[tuple[str, str]],
    derived_definition_ids: Sequence[str],
) -> str:
    """``source_pins`` items are ``(source_role, observation_id, observation_checksum)``.
    ``manual_input_pins`` items are ``(manual_input_revision_id, manual_input_decision_id)``.
    Both are sorted internally so caller ordering never affects the result."""

    payload = {
        "channel_id": channel_id,
        "product_ref": product_ref,
        "formula_shape_id": formula_shape_id,
        "translator_version": translator_version,
        "fx_snapshot_id": fx_snapshot_id,
        "currency_unit_registry_version": currency_unit_registry_version,
        "channel_config_revision_id": channel_config_revision_id,
        "mapping_revision_id": mapping_revision_id,
        "product_metadata_fingerprint": product_metadata_fingerprint,
        "arithmetic_version": arithmetic_version,
        "pricing_policy_revision_id": pricing_policy_revision_id,
        "source_pins": sorted(source_pins),
        "manual_input_pins": sorted(manual_input_pins),
        "derived_definition_ids": sorted(derived_definition_ids),
    }
    return checksum(payload)


def compute_package_checksum(
    *,
    channel_id: str,
    product_ref: str,
    workspace_id: str | None,
    workspace_pricing_evaluated_at: str,
    dependency_fingerprint: str,
) -> str:
    payload = {
        "channel_id": channel_id,
        "product_ref": product_ref,
        "workspace_id": workspace_id,
        "workspace_pricing_evaluated_at": workspace_pricing_evaluated_at,
        "dependency_fingerprint": dependency_fingerprint,
    }
    return checksum(payload)
