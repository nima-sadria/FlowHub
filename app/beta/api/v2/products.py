"""FlowHub Beta — /api/v2/products router (BU5).

Real read-only WooCommerce product browser.

Routes:
  GET /api/v2/products           — paginated product list with search/filter
  GET /api/v2/products/categories — WooCommerce category list for filter UI
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.beta.auth.dependencies import get_current_user
from app.beta.auth.models import BetaUser
from app.beta.database import get_db
from app.beta.integrations.errors import IntegrationError
from app.beta.integrations.woocommerce import WooCommerceClient
from app.beta.setup.service import AppConfigService

router = APIRouter(prefix="/products", tags=["products"])


def _build_wc_client(db: Session) -> WooCommerceClient:
    """Build WC client from config; raise 503 if not configured."""
    cfg = AppConfigService(db)
    client = WooCommerceClient.from_config(cfg)
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="WooCommerce is not configured. Go to Settings → WooCommerce Integration.",
        )
    return client


@router.get("")
async def list_products(
    page: int = 1,
    pageSize: int = 20,
    search: str = "",
    categoryId: int | None = None,
    productType: str | None = None,
    _: BetaUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return a paginated list of WooCommerce products.

    Configured flag allows the frontend to distinguish 'empty store' from
    'WooCommerce not configured yet'.
    """
    cfg = AppConfigService(db)
    wc = WooCommerceClient.from_config(cfg)
    if wc is None:
        return {
            "items": [],
            "total": 0,
            "page": page,
            "pageSize": pageSize,
            "configured": False,
        }

    # Clamp page size
    per_page = max(1, min(pageSize, 100))

    try:
        products, total = await wc.get_products_page(
            page=page,
            per_page=per_page,
            search=search,
            category_id=categoryId,
            product_type=productType if productType in ("simple", "variable") else None,
        )
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=exc.detail)

    # Fill currency from server config
    currency = cfg.get("server.currency") or "EUR"
    for p in products:
        p["currency"] = currency
        p["sourcePrice"] = None  # source prices are populated in Workspace, not here

    return {
        "items": products,
        "total": total,
        "page": page,
        "pageSize": per_page,
        "configured": True,
    }


@router.get("/categories")
async def list_categories(
    _: BetaUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return all WooCommerce product categories."""
    wc = _build_wc_client(db)
    try:
        categories = await wc.get_categories()
    except IntegrationError as exc:
        raise HTTPException(status_code=502, detail=exc.detail)
    return {"items": categories, "total": len(categories)}
