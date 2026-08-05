# ruff: noqa: B008
"""Strict REST API for Pricing Matrix configuration and activation."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import get_db
from app.flowhub.pricing_matrix.errors import PricingMatrixError
from app.flowhub.pricing_matrix.service import PricingMatrixService
from app.flowhub.unified_workspace.authorization import require_workspace_permission

router = APIRouter(prefix="/pricing-matrix", tags=["pricing-matrix"])


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GuardInput(StrictModel):
    min_price_minor: int | None = Field(default=None, ge=0)
    max_price_minor: int | None = Field(default=None, ge=0)
    max_increase_bp: int | None = Field(default=None, ge=0)
    max_decrease_bp: int | None = Field(default=None, ge=0)
    min_markup_bp: int | None = Field(default=None, ge=0)
    min_markup_worst_case_bp: int | None = Field(default=None, ge=0)
    max_basis_spread_bp: int | None = Field(default=None, ge=0)


class RuleInput(StrictModel):
    channel_id: str | None = Field(default=None, max_length=120)
    product_ref: str | None = Field(default=None, max_length=120)
    product_group_revision_id: str | None = Field(default=None, max_length=36)
    rate_mode: Literal["percent_bp", "multiplier_ppm"]
    rate_value: int
    fixed_addend_minor: int = 0
    round_mode: Literal["floor", "ceil", "nearest"] = "floor"
    round_step_minor: int = Field(default=1, ge=1)
    surcharge_minor: int = 0
    guards: GuardInput = Field(default_factory=GuardInput)

    @model_validator(mode="after")
    def one_product_scope(self) -> RuleInput:
        if self.product_ref and self.product_group_revision_id:
            raise ValueError("A rule cannot target both a product and a product group.")
        return self


class PolicyRevisionCreate(StrictModel):
    policy_id: str | None = Field(default=None, max_length=36)
    name: str = Field(min_length=1, max_length=240)
    computation_currency: str = Field(min_length=3, max_length=12)
    round_order: Literal["round_then_surcharge", "surcharge_then_round"] = (
        "round_then_surcharge"
    )
    max_quote_age_days: int = Field(ge=0, le=3650)
    min_quote_count: int = Field(ge=1, le=1000)
    evaluation_timezone: str = Field(default="UTC", min_length=1, max_length=64)
    rules: list[RuleInput] = Field(min_length=1, max_length=10_000)


class ProductGroupRevisionCreate(StrictModel):
    product_group_id: str | None = Field(default=None, max_length=36)
    name: str = Field(min_length=1, max_length=240)
    canonical_product_ids: list[str] = Field(min_length=1, max_length=10_000)


class UnitDeclaration(StrictModel):
    currency: str = Field(min_length=3, max_length=12)
    unit: str = Field(min_length=1, max_length=24)
    connector_config_version: str = Field(default="unversioned", min_length=1, max_length=80)


class ActivationRequest(StrictModel):
    policy_revision_id: str = Field(min_length=36, max_length=36)
    expected_head_version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=2000)


class DeactivationRequest(StrictModel):
    expected_head_version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=2000)


def _service(db: Session = Depends(get_db)) -> PricingMatrixService:
    return PricingMatrixService(db)


@router.get("/policies")
def list_policies(
    _: FlowHubUser = Depends(require_workspace_permission("workspace.read")),
    service: PricingMatrixService = Depends(_service),
) -> dict:
    return {"items": service.policies()}


@router.get("/policies/{revision_id}")
def get_policy(
    revision_id: str,
    _: FlowHubUser = Depends(require_workspace_permission("workspace.read")),
    service: PricingMatrixService = Depends(_service),
) -> dict:
    return _call(service.policy, revision_id)


@router.get("/product-groups")
def list_product_groups(
    _: FlowHubUser = Depends(require_workspace_permission("workspace.read")),
    service: PricingMatrixService = Depends(_service),
) -> dict:
    return {"items": service.product_groups()}


@router.get("/product-groups/{revision_id}")
def get_product_group(
    revision_id: str,
    _: FlowHubUser = Depends(require_workspace_permission("workspace.read")),
    service: PricingMatrixService = Depends(_service),
) -> dict:
    return _call(service.product_group, revision_id)


@router.post("/product-groups", status_code=201)
def create_product_group(
    body: ProductGroupRevisionCreate,
    user: FlowHubUser = Depends(require_workspace_permission("workspace.admin")),
    service: PricingMatrixService = Depends(_service),
) -> dict:
    return _call(service.create_product_group_revision, payload=body.model_dump(), user=user)


@router.post("/policies", status_code=201)
def create_policy(
    body: PolicyRevisionCreate,
    user: FlowHubUser = Depends(require_workspace_permission("workspace.admin")),
    service: PricingMatrixService = Depends(_service),
) -> dict:
    return _call(
        service.create_policy_revision,
        payload=body.model_dump(),
        user=user,
    )


@router.get("/units/{scope}/{scope_reference}")
def get_unit_declaration(
    scope: Literal["global", "source", "channel"],
    scope_reference: str,
    _: FlowHubUser = Depends(require_workspace_permission("workspace.read")),
    service: PricingMatrixService = Depends(_service),
) -> dict:
    return _call(service.unit_declaration, scope, scope_reference)


@router.put("/units/{scope}/{scope_reference}")
def put_unit_declaration(
    scope: Literal["global", "source", "channel"],
    scope_reference: str,
    body: UnitDeclaration,
    user: FlowHubUser = Depends(require_workspace_permission("workspace.admin")),
    service: PricingMatrixService = Depends(_service),
) -> dict:
    return _call(
        service.declare_unit,
        scope=scope,
        scope_reference=scope_reference,
        currency=body.currency,
        unit=body.unit,
        user=user,
        connector_config_version=body.connector_config_version,
    )


@router.get("/channels/{channel_id}/head")
def get_channel_policy_head(
    channel_id: str,
    _: FlowHubUser = Depends(require_workspace_permission("workspace.read")),
    service: PricingMatrixService = Depends(_service),
) -> dict:
    return _call(service.head, channel_id)


@router.get("/channels/{channel_id}/lifecycle-events")
def list_channel_lifecycle_events(
    channel_id: str,
    _: FlowHubUser = Depends(require_workspace_permission("workspace.read")),
    service: PricingMatrixService = Depends(_service),
) -> dict:
    return {"items": _call(service.lifecycle_events, channel_id)}


@router.post("/channels/{channel_id}/activate")
def activate_channel_policy(
    channel_id: str,
    body: ActivationRequest,
    user: FlowHubUser = Depends(require_workspace_permission("workspace.admin")),
    service: PricingMatrixService = Depends(_service),
) -> dict:
    return _call(
        service.activate,
        channel_id=channel_id,
        policy_revision_id=body.policy_revision_id,
        expected_head_version=body.expected_head_version,
        reason=body.reason,
        user=user,
    )


@router.post("/channels/{channel_id}/deactivate")
def deactivate_channel_policy(
    channel_id: str,
    body: DeactivationRequest,
    user: FlowHubUser = Depends(require_workspace_permission("workspace.admin")),
    service: PricingMatrixService = Depends(_service),
) -> dict:
    return _call(
        service.deactivate,
        channel_id=channel_id,
        expected_head_version=body.expected_head_version,
        reason=body.reason,
        user=user,
    )


def _call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except PricingMatrixError as exc:
        if exc.code.endswith("_not_found") or exc.code == "channel_not_found":
            http_status = status.HTTP_404_NOT_FOUND
        elif exc.code.endswith("_conflict"):
            http_status = status.HTTP_409_CONFLICT
        else:
            http_status = status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(
            http_status,
            {"code": exc.code, "message": str(exc)},
        ) from exc
