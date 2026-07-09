"""Canonical FlowHub Integration Platform API."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.flowhub.auth.dependencies import get_current_user
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import get_db
from app.flowhub.integration_platform.service import IntegrationPlatformService

router = APIRouter(prefix="/integration-platform", tags=["integration-platform"])


def _service(db: Session = Depends(get_db)) -> IntegrationPlatformService:
    return IntegrationPlatformService(db)


def _require_admin(user: FlowHubUser) -> None:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin permission required.")


@router.get("/registry")
async def list_registry(
    _: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> dict:
    return service.list_registry_contract()


@router.get("/registry/{connector_type}")
async def get_registry_detail(
    connector_type: str,
    _: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> dict:
    return service.get_registry_contract(connector_type)


@router.get("/connectors")
async def list_connectors(
    page: int = 1,
    page_size: int = 50,
    _: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> dict:
    return service.list_instances_contract(page=page, page_size=page_size)


@router.post("/connectors", status_code=201)
async def create_connector(
    body: dict,
    user: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> dict:
    _require_admin(user)
    return service.create_instance_contract(body)


@router.put("/connectors/{connector_id}")
async def update_connector(
    connector_id: str,
    body: dict,
    user: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> dict:
    _require_admin(user)
    return service.update_instance_contract(connector_id, body)


@router.patch("/connectors/{connector_id}/enable")
async def enable_connector(
    connector_id: str,
    user: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> dict:
    _require_admin(user)
    return service.set_enabled_contract(connector_id, True)


@router.patch("/connectors/{connector_id}/disable")
async def disable_connector(
    connector_id: str,
    user: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> dict:
    _require_admin(user)
    return service.set_enabled_contract(connector_id, False)


@router.delete("/connectors/{connector_id}")
async def delete_connector(
    connector_id: str,
    user: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> dict:
    _require_admin(user)
    return service.delete_instance_contract(connector_id)


@router.get("/connectors/{connector_id}/settings")
async def get_settings(
    connector_id: str,
    _: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> dict:
    return service.get_settings_contract(connector_id)


@router.put("/connectors/{connector_id}/settings")
async def update_settings(
    connector_id: str,
    body: dict,
    user: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> dict:
    _require_admin(user)
    return service.update_settings_contract(connector_id, body)


@router.post("/connectors/{connector_id}/test")
async def test_connection(
    connector_id: str,
    user: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> dict:
    _require_admin(user)
    instance = service.get_instance(connector_id)
    health = service.latest_health(connector_id)
    status_value = instance.connector.status.value
    return {
        "ok": status_value not in {"error", "authentication_failed"},
        "status": status_value,
        "latency_ms": health.latency_ms if health else None,
        "connector_version": instance.connector.identity.version,
        "detected_capabilities": instance.connector.capabilities.model_dump(),
        "authentication_valid": status_value != "authentication_failed",
        "error_code": None,
        "message": "Connection test used local Integration Platform/Data Layer records only.",
        "correlation_id": service._correlation_id(),
    }


@router.post("/connectors/{connector_id}/detect-capabilities")
async def detect_capabilities(
    connector_id: str,
    user: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> dict:
    _require_admin(user)
    instance = service.get_instance(connector_id)
    return {
        "canonical_capabilities": instance.connector.capabilities.model_dump(),
        "native_capabilities": {},
        "detected_at": instance.updated_at,
        "confidence": "registry",
        "warnings": ["Capability detection does not grant authorization."],
        "correlation_id": service._correlation_id(),
    }


@router.get("/connectors/{connector_id}/health")
async def get_connector_health(
    connector_id: str,
    _: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> dict:
    return service.health_contract(connector_id)


@router.get("/health")
async def get_health(
    _: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> dict:
    return service.health_contract()


@router.post("/connectors/{connector_id}/diagnostics/run")
async def run_connector_diagnostics(
    connector_id: str,
    user: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> dict:
    _require_admin(user)
    return service.diagnostics_contract(connector_id)


@router.post("/diagnostics/run")
async def run_all_diagnostics(
    user: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> dict:
    _require_admin(user)
    return service.diagnostics_contract()


@router.get("/connectors/{connector_id}/telemetry")
async def get_connector_telemetry(
    connector_id: str,
    _: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> dict:
    return service.telemetry_contract(connector_id=connector_id)


@router.get("/telemetry")
async def get_telemetry(
    _: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> dict:
    return service.telemetry_contract()


@router.get("/events")
async def get_events(
    limit: int = 100,
    _: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> dict:
    return service.list_events_contract(limit=limit)


@router.post("/webhooks/{connector_type}/{connector_id}")
async def receive_webhook(
    connector_type: str,
    connector_id: str,
    request: Request,
    x_flowhub_signature: str | None = Header(default=None),
    service: IntegrationPlatformService = Depends(_service),
) -> dict:
    raw_body = await request.body()
    payload = json.loads(raw_body.decode("utf-8") or "{}")
    return service.receive_webhook_contract(connector_type, connector_id, payload, raw_body, x_flowhub_signature)


@router.get("/connectors/{connector_id}/polling")
async def get_polling(
    connector_id: str,
    _: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> dict:
    return service.get_polling_contract(connector_id)


@router.put("/connectors/{connector_id}/polling")
async def update_polling(
    connector_id: str,
    body: dict,
    user: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> dict:
    _require_admin(user)
    return service.update_polling_contract(connector_id, body)


@router.post("/connectors/{connector_id}/write-test")
async def write_test(
    connector_id: str,
    body: dict,
    user: FlowHubUser = Depends(get_current_user),
    service: IntegrationPlatformService = Depends(_service),
) -> dict:
    _require_admin(user)
    return service.write_guard_contract(connector_id, str(body.get("operation") or "write_prices"))
