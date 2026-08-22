"""Frozen Evaluation Package foundation for legacy pricing migration evidence.

This package implements Pricing Migration Phase B only: an immutable evidence
package that pins every upstream dependency (Source Observations, manual
inputs, derived values, FX/unit/config/formula/translator versions) behind one
deterministic fingerprint. It does not translate formulas, run Shadow
Validation, or expose any callable API. See ``docs/archive/handoffs/RESUME.md`` and
``docs/evidence/architecture/ADR_PRICING_MATRIX.md``.
"""

from __future__ import annotations
