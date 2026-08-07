"""Closed offline workflow for formula migration preview assembly.

Phase D6 is evidence-only, review-only, and immutable by construction.
"""

from .contracts import (
    DependencyManifest,
    FormulaInventoryCell,
    FormulaMigrationCellDecision,
    FormulaMigrationInputCell,
    FormulaMigrationPreviewBatch,
    FormulaMigrationReviewAction,
    PreviewBatchState,
)
from .service import FormulaMigrationPreviewService, PreviewInput, ReviewDecisionRecord
from .models import (
    FormulaMigrationPreviewBatch as PreviewBatchModel,
    FormulaMigrationPreviewCell as PreviewCellModel,
    FormulaMigrationReviewDecision as ReviewDecisionModel,
)
from .fingerprint import compute_preview_batch_checksum, compute_preview_row_checksum

__all__ = [
    "DependencyManifest",
    "FormulaInventoryCell",
    "FormulaMigrationCellDecision",
    "FormulaMigrationInputCell",
    "FormulaMigrationPreviewBatch",
    "FormulaMigrationPreviewService",
    "PreviewInput",
    "ReviewDecisionRecord",
    "FormulaMigrationReviewAction",
    "PreviewBatchModel",
    "PreviewCellModel",
    "PreviewBatchState",
    "ReviewDecisionModel",
    "compute_preview_batch_checksum",
    "compute_preview_row_checksum",
]
