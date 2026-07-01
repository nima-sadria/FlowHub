"""FlowHub /api/v2/config router.

Read-only configuration view backed by Integration Platform connector settings.
Runtime writes through this generic config endpoint are blocked in this release.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.beta.auth.dependencies import get_current_user
from app.beta.auth.models import BetaUser
from app.beta.database import get_db
from app.beta.integration_platform.service import IntegrationPlatformService

router = APIRouter(prefix="/config", tags=["config"])


class ConfigRecordShape(BaseModel):
    field_name: str
    current_value: str
    is_editable: bool
    is_secret: bool
    is_installer_only: bool
    description: str


class ConfigSetRequest(BaseModel):
    value: str


class ConfigSetResponse(BaseModel):
    success: bool
    field_name: str
    new_value: str
    error: Optional[str]


def _integration_config_records(db: Session) -> list[ConfigRecordShape]:
    records: list[ConfigRecordShape] = []
    for connector in IntegrationPlatformService(db).settings_summary():
        for setting in connector.settings:
            records.append(
                ConfigRecordShape(
                    field_name=f"connector.{connector.connector_id}.{setting.key}",
                    current_value="configured" if setting.secret and setting.configured else str(setting.value or ""),
                    is_editable=False,
                    is_secret=setting.secret,
                    is_installer_only=False,
                    description=f"{connector.name} connector setting",
                )
            )
    return records


@router.get("", response_model=list[ConfigRecordShape])
async def list_editable_config(
    _: BetaUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ConfigRecordShape]:
    return _integration_config_records(db)


@router.get("/{field_name}", response_model=ConfigRecordShape)
async def get_config_field(
    field_name: str,
    _: BetaUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConfigRecordShape:
    records = _integration_config_records(db)
    for record in records:
        if record.field_name == field_name:
            return record
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Configuration field not found.")


@router.put("/{field_name}", response_model=ConfigSetResponse)
async def set_config_field(
    field_name: str,
    body: ConfigSetRequest,
    _: BetaUser = Depends(get_current_user),
) -> ConfigSetResponse:
    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        "Runtime connector settings writes are disabled in FlowHub.",
    )
