"""Pydantic contracts for the FlowHub Write Pipeline."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WritePipelinePriceChange(BaseModel):
    model_config = ConfigDict(extra="allow")

    productId: str
    productName: str = ""
    sku: str = ""
    currentPrice: float
    proposedPrice: float
    currency: str = "EUR"
    changePct: float | None = None


class WritePipelineDryRunRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    previewId: str | None = None
    channelId: str = "woocommerce:primary"
    operationType: str = "price_update"
    changes: list[WritePipelinePriceChange] = Field(default_factory=list, max_length=100)


class WritePipelineApprovalRequest(BaseModel):
    reason: str | None = None


class WritePipelineItemShape(BaseModel):
    id: int | None = None
    productId: str
    productName: str
    sku: str
    currentPrice: float
    proposedPrice: float
    difference: float
    changePct: float
    currency: str
    status: str
    errorCode: str | None = None
    errorMessage: str | None = None


class WritePipelineBatchShape(BaseModel):
    id: str
    channelId: str
    channelType: str
    operationType: str
    status: str
    sourcePreviewId: str | None = None
    batchHash: str
    itemCount: int
    currency: str
    safetySummary: dict
    createdBy: str
    approvedBy: str | None = None
    approvalReason: str | None = None
    createdAt: datetime
    approvedAt: datetime | None = None
    executedAt: datetime | None = None
    items: list[WritePipelineItemShape] = Field(default_factory=list)


class WritePipelineEventShape(BaseModel):
    id: int
    batchId: str
    itemId: int | None = None
    eventType: str
    severity: str
    message: str
    metadata: dict
    correlationId: str
    createdAt: datetime
