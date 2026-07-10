"""WooCommerceConnector - concrete DestinationConnector for WooCommerce REST API.

The only concrete class in this package. Business logic (adapters, rule engine)
must import only this class - never rest_client.py directly.

FlowHub 1.0.0 permits one explicit Write Pipeline adapter method:
WooCommerce price update only. No stock, scheduler, automatic apply, or generic
connector write API is implemented.

Capabilities:
  can_list_products  = True
  can_read_inventory = True
"""
from __future__ import annotations

import time

from app.connectors.common.auth import AuthConfig
from app.connectors.common.base import DestinationConnector
from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
from app.connectors.common.health import HealthResult, HealthStatus
from app.connectors.common.test_result import ConnectionTestResult
from app.connectors.common.types import ConnectorCapabilities, ConnectorID

from .auth import WooCommerceCredentials, extract_credentials
from .rest_client import get_product, get_variation, list_products, ping, update_product_price


class WooCommerceConnector(DestinationConnector):
    """WooCommerce destination connector.

    Lifecycle:
      1. test_connection(auth)  - probe without storing state
      2. connect(auth)          - store credentials + verify connectivity
      3. health()               - lightweight ping
      4. list_products(page, per_page)  - paginated product list
      5. read_inventory(product_id)     - stock data for one product
      6. update_price(product_id, price)- Write Pipeline price-only adapter
      7. read_product_price(product_id) - read-back verification after write
      8. disconnect()           - clears stored credentials
    """

    connector_id: ConnectorID = "woocommerce"

    def __init__(self) -> None:
        self._creds: WooCommerceCredentials | None = None

    def capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            can_list_products=True,
            can_read_inventory=True,
        )

    # -- Lifecycle -------------------------------------------------------------

    async def connect(self, auth: AuthConfig) -> None:
        """Store credentials and verify the WooCommerce API is reachable."""
        creds = extract_credentials(auth)
        await ping(creds)
        self._creds = creds

    async def disconnect(self) -> None:
        self._creds = None

    # -- Health ----------------------------------------------------------------

    async def health(self) -> HealthResult:
        if self._creds is None:
            return HealthResult(
                status=HealthStatus.UNHEALTHY,
                detail="Not connected - call connect() first",
            )
        t0 = time.monotonic()
        try:
            await ping(self._creds)
            latency = (time.monotonic() - t0) * 1000
            return HealthResult(status=HealthStatus.HEALTHY, latency_ms=round(latency, 1))
        except ConnectorError as exc:
            latency = (time.monotonic() - t0) * 1000
            return HealthResult(
                status=HealthStatus.UNHEALTHY,
                latency_ms=round(latency, 1),
                detail="WooCommerce connection failed.",
            )

    # -- Connection test -------------------------------------------------------

    async def test_connection(self, auth: AuthConfig) -> ConnectionTestResult:
        """Probe the WooCommerce REST API without storing state."""
        t0 = time.monotonic()
        try:
            creds = extract_credentials(auth)
            result = await ping(creds)
            latency = (time.monotonic() - t0) * 1000
            count = result.get("records_checked", 0)
            return ConnectionTestResult(
                ok=True,
                message=f"Connected to WooCommerce store ({count} product(s) found)",
                latency_ms=round(latency, 1),
            )
        except ConnectorError as exc:
            latency = (time.monotonic() - t0) * 1000
            return ConnectionTestResult(
                ok=False,
                message="WooCommerce connection failed.",
                latency_ms=round(latency, 1),
            )
        except Exception as exc:
            latency = (time.monotonic() - t0) * 1000
            return ConnectionTestResult(
                ok=False,
                message="WooCommerce returned an invalid or unavailable response.",
                latency_ms=round(latency, 1),
            )

    # -- Destination operations -------------------------------------------------

    def _require_connected(self) -> WooCommerceCredentials:
        if self._creds is None:
            raise ConnectorError(
                code=ConnectorErrorCode.UNKNOWN,
                message="WooCommerceConnector is not connected - call connect() first",
                provider="woocommerce",
            )
        return self._creds

    async def list_products(self, page: int = 1, per_page: int = 100) -> list[dict]:
        """Return a page of published products (read-only)."""
        creds = self._require_connected()
        return await list_products(creds, page=page, per_page=per_page)

    async def read_inventory(self, product_id: int) -> dict:
        """Return stock data for a single product (read-only).

        Returns a dict with at minimum: id, name, stock_quantity, stock_status,
        manage_stock. All values are sourced from the WooCommerce REST response.
        """
        creds = self._require_connected()
        product = await get_product(creds, product_id)
        return {
            "id": product.get("id"),
            "name": product.get("name"),
            "sku": product.get("sku"),
            "stock_quantity": product.get("stock_quantity"),
            "stock_status": product.get("stock_status"),
            "manage_stock": product.get("manage_stock"),
            "backorders": product.get("backorders"),
            "price": product.get("price"),
            "regular_price": product.get("regular_price"),
            "sale_price": product.get("sale_price"),
        }

    async def update_price(self, product_id: int, price: float, *, parent_product_id: int | None = None) -> dict:
        """Apply a price-only update through the approved Write Pipeline.

        This method deliberately accepts no stock or inventory fields.
        """
        creds = self._require_connected()
        return await update_product_price(creds, product_id, price, parent_product_id=parent_product_id)

    async def read_product_price(self, product_id: int, *, parent_product_id: int | None = None) -> dict:
        """Read price fields for post-apply verification."""
        creds = self._require_connected()
        if parent_product_id is None:
            product = await get_product(creds, product_id)
        else:
            product = await get_variation(creds, parent_product_id, product_id)
        return {
            "provider": "woocommerce",
            "product_id": product.get("id", product_id),
            "parent_product_id": parent_product_id,
            "variation_id": product_id if parent_product_id is not None else None,
            "regular_price": product.get("regular_price"),
            "price": product.get("price"),
            "sale_price": product.get("sale_price"),
        }
