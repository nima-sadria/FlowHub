# ruff: noqa: B008
"""Versioned REST API for Source mappings and internal FlowHub Sheets."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import get_db
from app.flowhub.source_workspace.service import SourceWorkspaceService
from app.flowhub.unified_workspace.authorization import require_workspace_permission

router = APIRouter(tags=["source workspace"])


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ColumnReference(StrictModel):
    field: str = Field(min_length=1, max_length=30)
    reference_type: Literal["column_letter", "header_name", "column_id", "disabled"]
    reference_value: str | None = Field(default=None, max_length=240)
    required: bool = False


class ChannelMappingInput(StrictModel):
    channel_id: str = Field(min_length=1, max_length=120)
    worksheet_name: str | None = Field(default=None, max_length=240)
    enabled: bool = True
    fields: list[ColumnReference] = Field(min_length=1, max_length=4)


class WorksheetRuleInput(StrictModel):
    worksheet_name: str = Field(min_length=1, max_length=240)
    enabled: bool = True
    data_start_row: int = Field(default=1, ge=1, le=1_000_000)
    source_fields: list[ColumnReference] = Field(default_factory=list, max_length=5)
    channel_mappings: list[ChannelMappingInput] = Field(default_factory=list, max_length=20)
    value_policy: dict[str, str] = Field(default_factory=dict)


class WorksheetSummary(StrictModel):
    name: str
    rowCount: int = Field(ge=0)


class WorksheetListResponse(StrictModel):
    sourceId: str
    items: list[WorksheetSummary]
    sourceRevisionId: str | None = None


class SourcePreviewChannel(StrictModel):
    channelId: str
    fields: dict[str, str | int | float | bool | None]


class SourcePreviewItemIssue(StrictModel):
    category: str
    severity: str
    channelId: str | None = None
    message: str


class SourcePreviewItem(StrictModel):
    rowKey: str
    rowNumber: int = Field(ge=1)
    worksheetName: str
    recognized: bool
    hasIssues: bool
    ready: bool
    sourceProduct: dict[str, str | int | float | bool | None]
    channels: list[SourcePreviewChannel]
    valuePolicy: dict[str, str]
    issues: list[SourcePreviewItemIssue]


class SourcePreviewIssueSummary(StrictModel):
    category: str
    severity: str
    channelId: str | None = None
    count: int = Field(ge=0)


class SourcePreviewBusinessSummary(StrictModel):
    productsFound: int = Field(ge=0)
    productsReady: int = Field(ge=0)
    priceChanges: int | None = Field(default=None, ge=0)
    stockChanges: int | None = Field(default=None, ge=0)
    unchanged: int | None = Field(default=None, ge=0)
    needsAttention: int = Field(ge=0)
    channelsReady: int = Field(ge=0)
    channelsNotConfigured: int = Field(ge=0)


class SourcePreviewResponse(StrictModel):
    items: list[SourcePreviewItem]
    total: int = Field(ge=0)
    recognized: int = Field(ge=0)
    ignored: int = Field(ge=0)
    issues: list[SourcePreviewIssueSummary]
    businessSummary: SourcePreviewBusinessSummary
    sheetRevisionId: str | None = None
    mappingRevisionId: str | None = None


class SourceCreateRequest(StrictModel):
    name: str = Field(min_length=1, max_length=240)
    source_kind: Literal["flowhub_sheet", "imported_sheet", "external"]
    external_source_id: str | None = Field(default=None, max_length=120)
    worksheet_mode: Literal["all", "selected"] = "selected"
    worksheet_name: str | None = Field(default="Sheet1", max_length=240)
    data_start_row: int = Field(default=1, ge=1, le=1_000_000)


class SourceLifecycleRequest(StrictModel):
    expected_source_version: int = Field(ge=1)
    confirmation_name: str = Field(min_length=1, max_length=240)


class MappingSaveRequest(StrictModel):
    expected_source_version: int = Field(ge=1)
    worksheet_mode: Literal["all", "selected"]
    worksheet_name: str | None = Field(default=None, max_length=240)
    data_start_row: int = Field(ge=1, le=1_000_000)
    source_fields: list[ColumnReference] = Field(default_factory=list, max_length=5)
    channel_mappings: list[ChannelMappingInput] = Field(default_factory=list, max_length=20)
    value_policy: dict[str, str] = Field(default_factory=dict)
    worksheet_rule_mode: Literal["shared", "per_worksheet"] = "shared"
    selected_worksheet_names: list[str] = Field(default_factory=list, max_length=100)
    duplicate_product_policy: Literal["block", "last_sheet_wins"] = "block"
    worksheet_rules: list[WorksheetRuleInput] = Field(default_factory=list, max_length=100)


class SheetColumnInput(StrictModel):
    column_key: str | None = Field(default=None, max_length=36)
    name: str = Field(min_length=1, max_length=240)
    position: int = Field(ge=1, le=200)
    data_type: str = Field(default="text", max_length=30)


class SheetRowInput(StrictModel):
    row_key: str | None = Field(default=None, max_length=36)
    position: int = Field(ge=1, le=1_000_000)
    values: dict[str, str | int | float | None] = Field(default_factory=dict)


class SheetCreateRequest(StrictModel):
    name: str = Field(min_length=1, max_length=240)
    columns: list[SheetColumnInput] = Field(min_length=1, max_length=200)


class SheetRevisionRequest(StrictModel):
    expected_version: int = Field(ge=0)
    columns: list[SheetColumnInput] = Field(min_length=1, max_length=200)
    rows: list[SheetRowInput] = Field(max_length=10_000)


class SheetCalculateRequest(StrictModel):
    columns: list[SheetColumnInput] = Field(min_length=1, max_length=200)
    rows: list[SheetRowInput] = Field(max_length=10_000)


class SheetCellPatch(StrictModel):
    row_key: str = Field(min_length=1, max_length=36)
    column_key: str = Field(min_length=1, max_length=36)
    value: str | int | float | None = Field(default=None)


class SheetPatchRequest(StrictModel):
    expected_version: int = Field(ge=1)
    changes: list[SheetCellPatch] = Field(default_factory=list, max_length=30_000)
    column_names: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_a_change(self) -> SheetPatchRequest:
        if not self.changes and not self.column_names:
            raise ValueError("At least one cell or column name change is required.")
        if len(self.column_names) > 200 or any(
            not key or len(key) > 36 or not value.strip() or len(value) > 240
            for key, value in self.column_names.items()
        ):
            raise ValueError("Column name changes must use valid column identities and names.")
        return self


class SheetAppendRowsRequest(StrictModel):
    expected_version: int = Field(ge=1)
    count: int = Field(default=20, ge=1, le=500)


class DataQualityScanRequest(StrictModel):
    source_id: str | None = Field(default=None, max_length=36)


class DataQualityCategorySummary(StrictModel):
    category: str
    count: int = Field(ge=0)


class DataQualitySummaryResponse(StrictModel):
    state: Literal[
        "never_checked",
        "checking",
        "healthy",
        "issues_found",
        "failed",
        "permission_denied",
    ]
    totalIssues: int = Field(ge=0)
    blockingIssues: int = Field(ge=0)
    warnings: int = Field(ge=0)
    affectedProducts: int = Field(ge=0)
    affectedChannels: int = Field(ge=0)
    affectedSources: int = Field(ge=0)
    resolvedSinceLastRead: int = Field(ge=0)
    trendSinceLastRead: int | None = None
    productsChecked: int = Field(ge=0)
    sourcesChecked: int = Field(ge=0)
    checkedAt: datetime | None = None
    scanId: str | None = None
    errorCode: str | None = None
    categories: list[DataQualityCategorySummary]


class DataQualityIssueResponse(StrictModel):
    id: str
    scanId: str | None = None
    sourceId: str
    sourceRowKey: str | None = None
    worksheet: str | None = None
    sourceProductName: str | None = None
    mappingState: str | None = None
    channelId: str | None = None
    category: str
    severity: str
    code: str
    summary: str
    recommendedAction: str
    technicalDetails: dict[str, Any]


class DataQualityListResponse(StrictModel):
    items: list[DataQualityIssueResponse]
    counts: dict[str, int]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    pageSize: int = Field(ge=1, le=200)
    summary: DataQualitySummaryResponse


class DataQualityScanResponse(StrictModel):
    summary: DataQualitySummaryResponse


class ImportPreviewRequest(StrictModel):
    filename: str = Field(min_length=1, max_length=500)
    content_base64: str = Field(min_length=1)
    worksheet_name: str | None = Field(default=None, max_length=240)


class SheetImportRequest(ImportPreviewRequest):
    name: str = Field(min_length=1, max_length=240)
    worksheet_name: str = Field(min_length=1, max_length=240)
    expected_checksum: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    data_start_row: int = Field(default=2, ge=1, le=1_000_000)


def _service(db: Session = Depends(get_db)) -> SourceWorkspaceService:
    return SourceWorkspaceService(db)


@router.get("/source-profiles")
def list_source_profiles(
    user: FlowHubUser = Depends(require_workspace_permission("workspace.read")),
    service: SourceWorkspaceService = Depends(_service),
) -> dict[str, Any]:
    return service.list_sources(user)


@router.get("/source-profiles/channels")
def list_source_channels(
    _: FlowHubUser = Depends(require_workspace_permission("workspace.read")),
    service: SourceWorkspaceService = Depends(_service),
) -> dict[str, Any]:
    return service.available_channels()


@router.post("/sources", status_code=201)
def create_source_profile(
    body: SourceCreateRequest,
    user: FlowHubUser = Depends(require_workspace_permission("workspace.create")),
    service: SourceWorkspaceService = Depends(_service),
) -> dict[str, Any]:
    return service.create_source(**body.model_dump(), user=user)


@router.get("/sources/{source_id}/configuration")
def get_source_configuration(
    source_id: str,
    user: FlowHubUser = Depends(require_workspace_permission("workspace.read")),
    service: SourceWorkspaceService = Depends(_service),
) -> dict[str, Any]:
    return service.get_source(source_id, user)


@router.get("/sources/{source_id}/lifecycle")
def get_source_lifecycle(
    source_id: str,
    user: FlowHubUser = Depends(require_workspace_permission("workspace.admin")),
    service: SourceWorkspaceService = Depends(_service),
) -> dict[str, Any]:
    return service.source_lifecycle(source_id, user)


@router.delete("/sources/{source_id}")
def delete_or_archive_source(
    source_id: str,
    body: SourceLifecycleRequest,
    user: FlowHubUser = Depends(require_workspace_permission("workspace.admin")),
    service: SourceWorkspaceService = Depends(_service),
) -> dict[str, Any]:
    return service.delete_or_archive_source(
        source_id=source_id,
        expected_source_version=body.expected_source_version,
        confirmation_name=body.confirmation_name,
        user=user,
    )


@router.get("/sources/{source_id}/worksheets", response_model=WorksheetListResponse)
async def list_source_worksheets(
    source_id: str,
    user: FlowHubUser = Depends(require_workspace_permission("workspace.read")),
    service: SourceWorkspaceService = Depends(_service),
) -> WorksheetListResponse:
    return WorksheetListResponse.model_validate(
        await service.list_source_worksheets(source_id, user)
    )


@router.put("/sources/{source_id}/mappings")
def save_source_mapping(
    source_id: str,
    body: MappingSaveRequest,
    user: FlowHubUser = Depends(require_workspace_permission("workspace.edit")),
    service: SourceWorkspaceService = Depends(_service),
) -> dict[str, Any]:
    payload = body.model_dump()
    payload["source_fields"] = [item.model_dump() for item in body.source_fields]
    payload["channel_mappings"] = [
        {**item.model_dump(exclude={"fields"}), "fields": [field.model_dump() for field in item.fields]}
        for item in body.channel_mappings
    ]
    return service.save_mapping(source_id=source_id, user=user, **payload)


@router.get("/sources/{source_id}/preview", response_model=SourcePreviewResponse)
async def preview_source_rows(
    source_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, alias="pageSize", ge=1, le=500),
    user: FlowHubUser = Depends(require_workspace_permission("workspace.read")),
    service: SourceWorkspaceService = Depends(_service),
) -> SourcePreviewResponse:
    return SourcePreviewResponse.model_validate(
        await service.source_preview(source_id, user, page=page, page_size=page_size)
    )


@router.post("/sources/{source_id}/preview", response_model=SourcePreviewResponse)
async def preview_unsaved_source_mapping(
    source_id: str,
    body: MappingSaveRequest,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, alias="pageSize", ge=1, le=500),
    user: FlowHubUser = Depends(require_workspace_permission("workspace.edit")),
    service: SourceWorkspaceService = Depends(_service),
) -> SourcePreviewResponse:
    payload = body.model_dump()
    payload["source_fields"] = [item.model_dump() for item in body.source_fields]
    payload["channel_mappings"] = [
        {
            **item.model_dump(exclude={"fields"}),
            "fields": [field.model_dump() for field in item.fields],
        }
        for item in body.channel_mappings
    ]
    return SourcePreviewResponse.model_validate(
        await service.preview_unsaved_mapping(
            source_id=source_id,
            user=user,
            page=page,
            page_size=page_size,
            **payload,
        )
    )


@router.post("/sheets", status_code=201)
def create_sheet(
    body: SheetCreateRequest,
    user: FlowHubUser = Depends(require_workspace_permission("workspace.create")),
    service: SourceWorkspaceService = Depends(_service),
) -> dict[str, Any]:
    return service.create_sheet(
        name=body.name,
        columns=[item.model_dump() for item in body.columns],
        user=user,
    )


@router.get("/sheets/{sheet_id}")
def get_sheet(
    sheet_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=200, alias="pageSize", ge=1, le=500),
    search: str | None = Query(default=None, max_length=240),
    sort_column: str | None = Query(default=None, alias="sortColumn", max_length=36),
    sort_direction: Literal["asc", "desc"] = Query(default="asc", alias="sortDirection"),
    user: FlowHubUser = Depends(require_workspace_permission("workspace.read")),
    service: SourceWorkspaceService = Depends(_service),
) -> dict[str, Any]:
    return service.get_sheet(
        sheet_id,
        user,
        page=page,
        page_size=page_size,
        search=search,
        sort_column=sort_column,
        sort_direction=sort_direction,
    )


@router.post("/sheets/{sheet_id}/revisions", status_code=201)
def save_sheet_revision(
    sheet_id: str,
    body: SheetRevisionRequest,
    user: FlowHubUser = Depends(require_workspace_permission("draft.save")),
    service: SourceWorkspaceService = Depends(_service),
) -> dict[str, Any]:
    return service.save_sheet_revision(
        sheet_id=sheet_id,
        expected_version=body.expected_version,
        columns=[item.model_dump() for item in body.columns],
        rows=[item.model_dump() for item in body.rows],
        user=user,
    )


@router.patch("/sheets/{sheet_id}/revisions", status_code=201)
def patch_sheet_revision(
    sheet_id: str,
    body: SheetPatchRequest,
    user: FlowHubUser = Depends(require_workspace_permission("draft.save")),
    service: SourceWorkspaceService = Depends(_service),
) -> dict[str, Any]:
    return service.patch_sheet_revision(
        sheet_id=sheet_id,
        expected_version=body.expected_version,
        changes=[item.model_dump() for item in body.changes],
        column_names=body.column_names,
        user=user,
    )


@router.post("/sheets/{sheet_id}/rows", status_code=201)
def append_sheet_rows(
    sheet_id: str,
    body: SheetAppendRowsRequest,
    user: FlowHubUser = Depends(require_workspace_permission("draft.save")),
    service: SourceWorkspaceService = Depends(_service),
) -> dict[str, Any]:
    return service.append_sheet_rows(
        sheet_id=sheet_id,
        expected_version=body.expected_version,
        count=body.count,
        user=user,
    )


@router.post("/sheets/calculate")
def calculate_sheet(
    body: SheetCalculateRequest,
    _: FlowHubUser = Depends(require_workspace_permission("workspace.read")),
    service: SourceWorkspaceService = Depends(_service),
) -> dict[str, Any]:
    return service.calculate(
        columns=[item.model_dump() for item in body.columns],
        rows=[item.model_dump() for item in body.rows],
    )


@router.post("/sheet-imports/preview")
def preview_sheet_import(
    body: ImportPreviewRequest,
    _: FlowHubUser = Depends(require_workspace_permission("workspace.create")),
    service: SourceWorkspaceService = Depends(_service),
) -> dict[str, Any]:
    return service.preview_import(**body.model_dump())


@router.post("/sheets/import", status_code=201)
def import_sheet(
    body: SheetImportRequest,
    user: FlowHubUser = Depends(require_workspace_permission("workspace.create")),
    service: SourceWorkspaceService = Depends(_service),
) -> dict[str, Any]:
    return service.import_sheet(**body.model_dump(), user=user)


@router.get("/data-quality")
def data_quality(
    source_id: str | None = Query(default=None, alias="sourceId"),
    channel_id: str | None = Query(default=None, alias="channelId"),
    worksheet: str | None = Query(default=None),
    category: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    product: str | None = Query(default=None),
    mapping_state: str | None = Query(default=None, alias="mappingState"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, alias="pageSize", ge=1, le=200),
    user: FlowHubUser = Depends(require_workspace_permission("workspace.read")),
    service: SourceWorkspaceService = Depends(_service),
) -> DataQualityListResponse:
    result = service.data_quality(
        user=user,
        source_id=source_id,
        channel_id=channel_id,
        worksheet=worksheet,
        category=category,
        severity=severity,
        product=product,
        mapping_state=mapping_state,
        page=page,
        page_size=page_size,
    )
    return DataQualityListResponse.model_validate(result)


@router.post("/data-quality/scans", status_code=201)
async def scan_data_quality(
    body: DataQualityScanRequest,
    user: FlowHubUser = Depends(require_workspace_permission("workspace.read")),
    service: SourceWorkspaceService = Depends(_service),
) -> DataQualityScanResponse:
    result = await service.scan_data_quality(user=user, source_id=body.source_id)
    return DataQualityScanResponse.model_validate(result)
