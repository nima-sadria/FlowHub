# ruff: noqa: B008
"""Versioned REST presentation layer for Unified Workspace."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import get_db
from app.flowhub.maintenance import require_write_operation_available
from app.flowhub.unified_workspace.authorization import require_workspace_permission
from app.flowhub.unified_workspace.services import UnifiedWorkspaceService

router = APIRouter(prefix="/unified-workspaces", tags=["unified-workspaces"])


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProductSelection(StrictModel):
    connector_id: str = Field(min_length=1, max_length=120)
    product_id: str = Field(min_length=1, max_length=255)


class ManualWorkspaceCreateRequest(StrictModel):
    name: str = Field(default="Manual Workspace", min_length=1, max_length=240)
    selections: list[ProductSelection] = Field(min_length=1, max_length=10_000)


class SourceWorkspaceCreateRequest(StrictModel):
    name: str = Field(default="Source Workspace", min_length=1, max_length=240)
    currency: str | None = Field(default=None, min_length=3, max_length=12)
    unit: str | None = Field(default=None, min_length=3, max_length=24)


class DraftChangeRequest(StrictModel):
    canonical_product_id: str = Field(min_length=1, max_length=36)
    listing_id: str = Field(min_length=1, max_length=36)
    channel_id: str = Field(min_length=1, max_length=120)
    field: Literal["price", "stock", "status"]
    target_value: str = Field(min_length=1, max_length=1000)
    currency: str | None = Field(default=None, max_length=12)
    unit: str | None = Field(default=None, max_length=24)


class DraftSaveRequest(StrictModel):
    expected_version: int = Field(ge=0)
    changes: list[DraftChangeRequest] = Field(max_length=30_000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DraftRestoreRequest(StrictModel):
    expected_version: int = Field(ge=0)


class ReviewCreateRequest(StrictModel):
    draft_revision_id: str = Field(min_length=1, max_length=36)


class ReviewSelectionRequest(StrictModel):
    review_item_ids: list[str] = Field(min_length=1, max_length=30_000)


class ApplyRequest(StrictModel):
    review_id: str = Field(min_length=1, max_length=36)
    confirmed: bool


class PreferenceRequest(StrictModel):
    expected_version: int = Field(ge=0)
    visibleChannelIds: list[str] = Field(max_length=20)
    channelOrder: list[str] = Field(max_length=20)
    visibleFields: dict[str, bool]
    displayNameSource: str = Field(max_length=120)


class MappingDecisionRequest(StrictModel):
    proposed_canonical_product_id: str = Field(min_length=1, max_length=36)
    decision: Literal["approved", "rejected"]
    reason: str = Field(min_length=1, max_length=2000)
    evidence: dict[str, Any] = Field(default_factory=dict)

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str) -> str:
        cleaned = " ".join(value.strip().split())
        if not cleaned:
            raise ValueError("Reason is required.")
        return cleaned


class WorkspaceResource(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    name: str
    entryPoint: str
    status: str
    version: int
    snapshot: dict[str, Any]
    draft: dict[str, Any]
    createdAt: datetime


def _service(db: Session = Depends(get_db)) -> UnifiedWorkspaceService:
    return UnifiedWorkspaceService(db)


def _correlation(value: str | None = Header(default=None, alias="X-Correlation-ID")) -> str:
    cleaned = (value or "").strip()
    return cleaned[:120] if cleaned else f"uw_{uuid.uuid4().hex}"


@router.post("/manual", response_model=WorkspaceResource, status_code=201)
def create_manual_workspace(
    body: ManualWorkspaceCreateRequest,
    user: FlowHubUser = Depends(require_workspace_permission("workspace.create")),
    service: UnifiedWorkspaceService = Depends(_service),
    correlation_id: str = Depends(_correlation),
):
    return service.create_manual_workspace(
        name=body.name,
        selections=[item.model_dump() for item in body.selections],
        user=user,
        correlation_id=correlation_id,
    )


@router.post("/source", response_model=WorkspaceResource, status_code=201)
async def create_source_workspace(
    body: SourceWorkspaceCreateRequest,
    user: FlowHubUser = Depends(require_workspace_permission("workspace.create")),
    service: UnifiedWorkspaceService = Depends(_service),
    correlation_id: str = Depends(_correlation),
):
    return await service.create_source_workspace(
        name=body.name,
        source_currency=body.currency,
        source_unit=body.unit,
        user=user,
        correlation_id=correlation_id,
    )


@router.get("/preferences/me")
def get_preferences(
    user: FlowHubUser = Depends(require_workspace_permission("workspace.read")),
    service: UnifiedWorkspaceService = Depends(_service),
):
    return service.preference(user)


@router.put("/preferences/me")
def save_preferences(
    body: PreferenceRequest,
    user: FlowHubUser = Depends(require_workspace_permission("workspace.read")),
    service: UnifiedWorkspaceService = Depends(_service),
):
    payload = body.model_dump(exclude={"expected_version"})
    return service.save_preference(payload, body.expected_version, user)


@router.post("/channels/{channel_id}/cache-refresh")
async def refresh_channel_cache(
    channel_id: str,
    user: FlowHubUser = Depends(require_workspace_permission("channel_cache.refresh")),
    service: UnifiedWorkspaceService = Depends(_service),
    correlation_id: str = Depends(_correlation),
):
    return await service.refresh_channel_cache(channel_id, user, correlation_id)


@router.get("/{workspace_id}", response_model=WorkspaceResource)
def get_workspace(
    workspace_id: str,
    user: FlowHubUser = Depends(require_workspace_permission("workspace.read")),
    service: UnifiedWorkspaceService = Depends(_service),
):
    return service.workspace_shape(workspace_id, user)


@router.get("/{workspace_id}/grid")
def get_grid(
    workspace_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, alias="pageSize", ge=1, le=500),
    search: str | None = Query(default=None, max_length=240),
    product_type: str | None = Query(default=None, alias="productType"),
    mapping_state: str | None = Query(default=None, alias="mappingState"),
    category: str | None = Query(default=None, max_length=240),
    brand: str | None = Query(default=None, max_length=240),
    channel_id: str | None = Query(default=None, alias="channelId", max_length=120),
    sku: str | None = Query(default=None, max_length=255),
    listing_id: str | None = Query(default=None, alias="listingId", max_length=36),
    channel_status: str | None = Query(default=None, alias="channelStatus", max_length=80),
    min_price: float | None = Query(default=None, alias="minPrice", ge=0),
    max_price: float | None = Query(default=None, alias="maxPrice", ge=0),
    stock_quantity: float | None = Query(default=None, alias="stockQuantity", ge=0),
    sort: str = Query(default="name:asc", max_length=300),
    user: FlowHubUser = Depends(require_workspace_permission("workspace.read")),
    service: UnifiedWorkspaceService = Depends(_service),
):
    sorts: list[tuple[str, str]] = []
    for raw in sort.split(","):
        field, _, direction = raw.partition(":")
        sorts.append((field, "desc" if direction == "desc" else "asc"))
    return service.grid(
        workspace_id,
        user,
        page=page,
        page_size=page_size,
        search=search,
        product_type=product_type,
        mapping_state=mapping_state,
        category=category,
        brand=brand,
        channel_id=channel_id,
        sku=sku,
        listing_id=listing_id,
        channel_status=channel_status,
        min_price=min_price,
        max_price=max_price,
        stock_quantity=stock_quantity,
        sorts=sorts,
    )


@router.post("/{workspace_id}/draft/revisions", status_code=201)
def save_draft(
    workspace_id: str,
    body: DraftSaveRequest,
    user: FlowHubUser = Depends(require_workspace_permission("draft.save")),
    service: UnifiedWorkspaceService = Depends(_service),
    correlation_id: str = Depends(_correlation),
):
    return service.save_draft(
        workspace_id,
        expected_version=body.expected_version,
        raw_changes=[item.model_dump() for item in body.changes],
        metadata=body.metadata,
        user=user,
        correlation_id=correlation_id,
    )


@router.get("/{workspace_id}/draft/revisions")
def list_revisions(
    workspace_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, alias="pageSize", ge=1, le=100),
    user: FlowHubUser = Depends(require_workspace_permission("workspace.read")),
    service: UnifiedWorkspaceService = Depends(_service),
):
    return service.revisions(workspace_id, user, page=page, page_size=page_size)


@router.post("/{workspace_id}/draft/revisions/{revision_id}/restore", status_code=201)
def restore_revision(
    workspace_id: str,
    revision_id: str,
    body: DraftRestoreRequest,
    user: FlowHubUser = Depends(require_workspace_permission("draft.save")),
    service: UnifiedWorkspaceService = Depends(_service),
    correlation_id: str = Depends(_correlation),
):
    return service.restore_revision(
        workspace_id,
        revision_id,
        expected_version=body.expected_version,
        user=user,
        correlation_id=correlation_id,
    )


@router.post("/{workspace_id}/reviews", status_code=201)
def create_review(
    workspace_id: str,
    body: ReviewCreateRequest,
    user: FlowHubUser = Depends(require_workspace_permission("review.generate")),
    service: UnifiedWorkspaceService = Depends(_service),
    correlation_id: str = Depends(_correlation),
):
    return service.generate_review(workspace_id, body.draft_revision_id, user, correlation_id)


@router.get("/{workspace_id}/reviews/{review_id}")
def get_review(
    workspace_id: str,
    review_id: str,
    user: FlowHubUser = Depends(require_workspace_permission("workspace.read")),
    service: UnifiedWorkspaceService = Depends(_service),
):
    result = service.review_shape(review_id, user)
    if result["workspaceId"] != workspace_id:
        from fastapi import HTTPException

        raise HTTPException(404, {"code": "REVIEW_NOT_FOUND", "message": "Review not found."})
    return result


@router.put("/{workspace_id}/reviews/{review_id}/selection")
def save_review_selection(
    workspace_id: str,
    review_id: str,
    body: ReviewSelectionRequest,
    user: FlowHubUser = Depends(require_workspace_permission("workspace.edit")),
    service: UnifiedWorkspaceService = Depends(_service),
    correlation_id: str = Depends(_correlation),
):
    return service.select_review_items(
        workspace_id, review_id, body.review_item_ids, user, correlation_id
    )


@router.post("/{workspace_id}/apply", status_code=202)
async def apply_selected(
    workspace_id: str,
    body: ApplyRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=255),
    user: FlowHubUser = Depends(require_write_operation_available),
    service: UnifiedWorkspaceService = Depends(_service),
    correlation_id: str = Depends(_correlation),
):
    return await service.apply_selected(
        workspace_id,
        body.review_id,
        idempotency_key=idempotency_key,
        confirmed=body.confirmed,
        user=user,
        correlation_id=correlation_id,
    )


@router.get("/{workspace_id}/apply/{job_id}")
def get_apply(
    workspace_id: str,
    job_id: str,
    user: FlowHubUser = Depends(require_workspace_permission("workspace.read")),
    service: UnifiedWorkspaceService = Depends(_service),
):
    result = service.apply_shape(job_id, user)
    if result["workspaceId"] != workspace_id:
        from fastapi import HTTPException

        raise HTTPException(404, {"code": "APPLY_NOT_FOUND", "message": "Apply job not found."})
    return result


@router.get("/{workspace_id}/audit")
def get_audit(
    workspace_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, alias="pageSize", ge=1, le=200),
    user: FlowHubUser = Depends(require_workspace_permission("audit.read")),
    service: UnifiedWorkspaceService = Depends(_service),
):
    return service.audit(workspace_id, user, page=page, page_size=page_size)


@router.post("/{workspace_id}/mappings/{listing_id}/decisions", status_code=201)
def decide_mapping(
    workspace_id: str,
    listing_id: str,
    body: MappingDecisionRequest,
    user: FlowHubUser = Depends(require_workspace_permission("mapping.approve")),
    service: UnifiedWorkspaceService = Depends(_service),
    correlation_id: str = Depends(_correlation),
):
    return service.approve_mapping(
        workspace_id,
        listing_id,
        body.proposed_canonical_product_id,
        body.decision,
        body.reason,
        body.evidence,
        user,
        correlation_id,
    )
