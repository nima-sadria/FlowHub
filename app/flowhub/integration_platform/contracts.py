"""Integration Platform API contracts and canonical capability schema."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ConnectorHealthStatus(str, Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    ERROR = "error"
    DISABLED = "disabled"
    DEGRADED = "degraded"
    AUTHENTICATION_FAILED = "authentication_failed"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"


class ConnectorIdentity(BaseModel):
    id: str
    name: str
    type: str
    version: str = "1.0.0"
    enabled: bool = False
    read_only: bool = True


class ConnectorCapabilities(BaseModel):
    read_products: bool = False
    read_categories: bool = False
    read_inventory: bool = False
    read_orders: bool = False
    write_prices: bool = False
    write_inventory: bool = False
    webhook: bool = False
    polling: bool = False
    oauth: bool = False
    api_key: bool = False
    supports_modified_since: bool = False
    supports_delta_sync: bool = False
    supports_updated_after: bool = False
    supports_pagination: bool = False
    supports_batch_read: bool = False


class ConnectorDescriptor(BaseModel):
    identity: ConnectorIdentity
    capabilities: ConnectorCapabilities
    status: ConnectorHealthStatus = ConnectorHealthStatus.DISABLED
    runtime_write_blocked: bool = True
    capability_authorizes_write: Literal[False] = False


class ConnectorSettingDefinition(BaseModel):
    key: str
    label: str
    required: bool = False
    secret: bool = False
    default: str | int | float | bool | None = None


class ConnectorSettingValue(BaseModel):
    key: str
    value: str | int | float | bool | dict | list | None = None
    secret: bool = False
    configured: bool = False


class DiagnosticCheckContract(BaseModel):
    name: str
    category: str


class ConnectorDiagnosticsContract(BaseModel):
    checks: list[DiagnosticCheckContract] = Field(default_factory=list)


class ConnectorDefinition(BaseModel):
    connector: ConnectorDescriptor
    settings_schema: list[ConnectorSettingDefinition] = Field(default_factory=list)
    diagnostics_contract: ConnectorDiagnosticsContract = Field(default_factory=ConnectorDiagnosticsContract)


class ConnectorRegistryResponse(BaseModel):
    items: list[ConnectorDefinition]
    runtime_write_blocked: bool = True


class ConnectorCreateRequest(BaseModel):
    connector_type: str
    id: str
    name: str
    enabled: bool = True
    read_only: bool = True


class ConnectorSettingsUpdateRequest(BaseModel):
    settings: list[ConnectorSettingValue]


class ConnectorInstanceShape(BaseModel):
    connector: ConnectorDescriptor
    settings: list[ConnectorSettingValue] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


class ConnectorListResponse(BaseModel):
    items: list[ConnectorInstanceShape]
    runtime_write_blocked: bool = True


class ConnectorProductShape(BaseModel):
    id: str
    wcId: int | None = None
    connectorId: str
    productId: str
    name: str
    sku: str = ""
    currentPrice: float = 0.0
    sourcePrice: float | None = None
    currency: str = "EUR"
    categoryNames: list[str] = Field(default_factory=list)
    imageUrl: str | None = None
    productType: str = "simple"
    status: str = "pending"
    lastSynced: str | None = None


class ConnectorProductListResponse(BaseModel):
    items: list[ConnectorProductShape]
    total: int
    page: int
    pageSize: int
    page_size: int
    configured: bool = True
    runtime_write_blocked: bool = True


class ConnectorCategoryShape(BaseModel):
    id: int
    name: str
    parent: int = 0
    count: int = 0


class ConnectorCategoryListResponse(BaseModel):
    items: list[ConnectorCategoryShape]
    total: int
    runtime_write_blocked: bool = True


class ConnectorSourceShape(BaseModel):
    id: str
    connector_id: str
    name: str
    type: str
    displayUrl: str
    status: str
    lastSynced: str | None = None
    productCount: int = 0


class ConnectorSourceListResponse(BaseModel):
    items: list[ConnectorSourceShape]
    runtime_write_blocked: bool = True


class WorkspaceIntegrationSummary(BaseModel):
    state: str = "idle"
    source_count: int
    product_count: int
    connector_count: int
    runtime_write_blocked: bool = True
    apply_available: bool = False
    scheduler_available: bool = False
    pricing_automation_available: bool = False


class WorkspacePreviewResponse(BaseModel):
    id: str
    sourceId: str
    sourceName: str
    state: str
    totalChanges: int
    changes: list[dict] = Field(default_factory=list)
    startedAt: str
    duplicateWarnings: list[str] = Field(default_factory=list)
    runtime_write_blocked: bool = True
    external_call_performed: bool = False


class IntegrationSettingsSummary(BaseModel):
    connector_id: str
    connector_type: str
    name: str
    settings: list[ConnectorSettingValue]
    runtime_write_blocked: bool = True


class ConnectorTelemetryShape(BaseModel):
    id: int
    connector_id: str
    event_name: str
    severity: str
    message: str
    created_at: str
    metadata: dict = Field(default_factory=dict)


class ConnectorTelemetryResponse(BaseModel):
    items: list[ConnectorTelemetryShape]
    total: int
    aggregate: dict = Field(default_factory=dict)
    runtime_write_blocked: bool = True
