"""FlowHub Integration Platform API.

These endpoints expose connector registry, connector instances, settings,
status, and telemetry. They are read-only with respect to external systems.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.flowhub.auth.dependencies import get_current_user
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import get_db
from app.flowhub.integration_platform.contracts import (
    ConnectorCreateRequest,
    ConnectorDefinition,
    ConnectorInstanceShape,
    ConnectorListResponse,
    ConnectorRegistryResponse,
    ConnectorSettingValue,
    ConnectorSettingsUpdateRequest,
    ConnectorTelemetryResponse,
)
from app.flowhub.integration_platform.service import IntegrationPlatformService

router = APIRouter(prefix="/integrations", tags=["integrations"])


def _service(db: Session = Depends(get_db)) -> IntegrationPlatformService:
    return IntegrationPlatformService(db)


@router.get("/registry", response_model=ConnectorRegistryResponse)
async def list_connector_registry(
    _: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> ConnectorRegistryResponse:
    return service.list_registry()


@router.get("/registry/{connector_type}", response_model=ConnectorDefinition)
async def get_connector_definition(
    connector_type: str,
    _: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> ConnectorDefinition:
    return service.get_registry_definition(connector_type)


@router.get("/connectors", response_model=ConnectorListResponse)
async def list_connectors(
    _: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> ConnectorListResponse:
    return service.list_instances()


@router.post("/connectors", response_model=ConnectorInstanceShape, status_code=201)
async def create_connector(
    body: ConnectorCreateRequest,
    _: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> ConnectorInstanceShape:
    return service.create_instance(body)


@router.get("/connectors/{connector_id}", response_model=ConnectorInstanceShape)
async def get_connector(
    connector_id: str,
    _: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> ConnectorInstanceShape:
    return service.get_instance(connector_id)


@router.get("/connectors/{connector_id}/status", response_model=ConnectorInstanceShape)
async def get_connector_status(
    connector_id: str,
    _: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> ConnectorInstanceShape:
    return service.get_instance(connector_id)


@router.get("/connectors/{connector_id}/settings", response_model=list[ConnectorSettingValue])
async def get_connector_settings(
    connector_id: str,
    _: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> list[ConnectorSettingValue]:
    return service.get_settings(connector_id)


@router.patch("/connectors/{connector_id}/settings", response_model=ConnectorInstanceShape)
async def update_connector_settings(
    connector_id: str,
    body: ConnectorSettingsUpdateRequest,
    _: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> ConnectorInstanceShape:
    return service.update_settings(connector_id, body.settings)


@router.get("/telemetry", response_model=ConnectorTelemetryResponse)
async def list_connector_telemetry(
    connector_id: str | None = None,
    limit: int = 100,
    _: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> ConnectorTelemetryResponse:
    return service.telemetry(connector_id=connector_id, limit=limit)
