"""Deterministic Pricing Matrix domain primitives."""

from app.flowhub.pricing_matrix.arithmetic import (
    PRICING_ARITHMETIC_VERSION,
    PricingArithmeticResult,
    calculate_price,
    round_to_step,
)
from app.flowhub.pricing_matrix.contracts import (
    PricingGuardSet,
    PricingRule,
    RateMode,
    RoundingMode,
    RoundOrder,
)
from app.flowhub.pricing_matrix.errors import PricingMatrixError
from app.flowhub.pricing_matrix.evaluator import (
    PricingTargetResult,
    QuoteAssessment,
    QuoteEvidence,
    evaluate_pricing_target,
)
from app.flowhub.pricing_matrix.guards import GuardEvaluation, evaluate_guards

__all__ = [
    "PRICING_ARITHMETIC_VERSION",
    "PricingArithmeticResult",
    "GuardEvaluation",
    "PricingGuardSet",
    "PricingMatrixError",
    "PricingRule",
    "PricingTargetResult",
    "QuoteAssessment",
    "QuoteEvidence",
    "RateMode",
    "RoundingMode",
    "RoundOrder",
    "calculate_price",
    "evaluate_guards",
    "evaluate_pricing_target",
    "round_to_step",
]
