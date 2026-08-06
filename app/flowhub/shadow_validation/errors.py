"""Stable failures for shadow validation comparison assembly."""

from __future__ import annotations


class ShadowValidationError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


REASON_WINDOW_NOT_FOUND = "shadow_validation_window_not_found"
REASON_WINDOW_CHANNEL_MISMATCH = "shadow_validation_window_channel_mismatch"
REASON_FEP_NOT_FOUND = "shadow_validation_fep_not_found"
REASON_CAPTURE_NOT_FOUND = "shadow_validation_capture_not_found"
REASON_CAPTURE_CHANNEL_MISMATCH = "shadow_validation_capture_channel_mismatch"
REASON_CONTRACT_NOT_FOUND = "shadow_validation_contract_not_found"
REASON_CONTRACT_UNAPPROVED = "shadow_validation_contract_unapproved"
REASON_UNSUPPORTED_SHAPE = "shadow_validation_unsupported_shape"
REASON_FEP_CAPTURE_MISMATCH = "shadow_validation_fep_capture_mismatch"
REASON_AUTHORITY_MISMATCH = "shadow_validation_authority_mismatch"
REASON_POLICY_MISMATCH = "shadow_validation_policy_mismatch"
REASON_OUTPUT_LANES_UNSUPPORTED = "shadow_validation_output_lanes_invalid"
REASON_PACKAGE_OUTPUT_MISSING = "shadow_validation_package_output_missing"
REASON_PACKAGE_OUTPUT_INVALID = "shadow_validation_package_output_invalid"
