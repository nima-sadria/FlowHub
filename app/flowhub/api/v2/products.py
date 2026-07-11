"""FlowHub /api/v2/products router.

Read-only product browser backed by Integration Platform/Data Layer records.
This router never calls WooCommerce, Nextcloud, or httpx directly.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.flowhub.auth.dependencies import get_current_user
from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import get_db
from app.flowhub.integration_platform.contracts import (
    ConnectorCategoryListResponse,
    ConnectorProductListResponse,
)
from app.flowhub.integration_platform.service import IntegrationPlatformService
from app.flowhub.maintenance import require_write_operation_available
from app.flowhub.product_pricing.service import ProductPricingService

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=ConnectorProductListResponse)
async def list_products(
    page: int = 1,
    pageSize: int = 20,
    search: str = "",
    categoryId: int | None = None,
    productType: str | None = None,
    channelId: str | None = None,
    _: FlowHubUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConnectorProductListResponse:
    return IntegrationPlatformService(db).list_products(
        search=search,
        page=page,
        page_size=pageSize,
        category_id=categoryId,
        product_type=productType,
        connector_id=channelId,
    )


@router.get("/categories", response_model=ConnectorCategoryListResponse)
async def list_categories(
    _: FlowHubUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConnectorCategoryListResponse:
    return IntegrationPlatformService(db).list_categories()


@router.get("/channel-price-operations/{operation_id}")
async def get_channel_price_operation(
    operation_id: str,
    _: FlowHubUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return ProductPricingService(db).operation(operation_id)


@router.post("/channel-price-operations/{operation_id}/approve")
async def approve_channel_price_operation(
    operation_id: str,
    body: dict,
    user: FlowHubUser = Depends(require_write_operation_available),
    db: Session = Depends(get_db),
) -> dict:
    return ProductPricingService(db).approve(operation_id, body, user)


@router.post("/channel-price-operations/{operation_id}/apply")
async def apply_channel_price_operation(
    operation_id: str,
    user: FlowHubUser = Depends(require_write_operation_available),
    db: Session = Depends(get_db),
) -> dict:
    return await ProductPricingService(db).apply(operation_id, user)


@router.get("/{product_id}")
async def get_product(
    product_id: str,
    _: FlowHubUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    page = IntegrationPlatformService(db).list_products(search=product_id, page=1, page_size=200)
    for item in page.items:
        if item.id == product_id:
            return item.model_dump()
    from fastapi import HTTPException, status
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found.")


@router.get("/{product_id}/channel-prices")
async def get_channel_prices(
    product_id: str,
    _: FlowHubUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return ProductPricingService(db).load(product_id)


@router.post("/{product_id}/channel-prices/validate")
async def validate_channel_prices(
    product_id: str,
    body: dict,
    _: FlowHubUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return ProductPricingService(db).validate(product_id, body)


@router.post("/{product_id}/channel-prices/dry-run", status_code=201)
async def create_channel_price_dry_run(
    product_id: str,
    body: dict,
    user: FlowHubUser = Depends(require_write_operation_available),
    db: Session = Depends(get_db),
) -> dict:
    return ProductPricingService(db).dry_run(product_id, body, user)
