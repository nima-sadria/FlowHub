"""FlowHub /api/v2/products router.

Read-only product browser backed by Integration Platform/Data Layer records.
This router never calls WooCommerce, Nextcloud, or httpx directly.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.beta.auth.dependencies import get_current_user
from app.beta.auth.models import BetaUser
from app.beta.database import get_db
from app.beta.integration_platform.contracts import (
    ConnectorCategoryListResponse,
    ConnectorProductListResponse,
)
from app.beta.integration_platform.service import IntegrationPlatformService

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=ConnectorProductListResponse)
async def list_products(
    page: int = 1,
    pageSize: int = 20,
    search: str = "",
    categoryId: int | None = None,
    productType: str | None = None,
    _: BetaUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConnectorProductListResponse:
    return IntegrationPlatformService(db).list_products(
        search=search,
        page=page,
        page_size=pageSize,
        category_id=categoryId,
        product_type=productType,
    )


@router.get("/categories", response_model=ConnectorCategoryListResponse)
async def list_categories(
    _: BetaUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConnectorCategoryListResponse:
    return IntegrationPlatformService(db).list_categories()
