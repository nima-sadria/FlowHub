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
from collections.abc import Awaitable, Callable, Sequence

from app.connectors.common.auth import AuthConfig
from app.connectors.common.base import DestinationConnector
from app.connectors.common.current_state import (
    CurrentStateError,
    CurrentStateIdentity,
    CurrentStateRecord,
    CurrentStateRequest,
    CurrentStateResult,
    CurrentStateStrategy,
    TransportRecorder,
    canonical_decimal,
    failed_current_state,
)
from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
from app.connectors.common.health import HealthResult, HealthStatus
from app.connectors.common.test_result import ConnectionTestResult
from app.connectors.common.types import ConnectorCapabilities, ConnectorID

from .auth import WooCommerceCredentials, extract_credentials
from .rest_client import (
    get_product,
    list_products,
    list_products_paged,
    list_variations_by_ids,
    ping,
    update_product_fields,
)


class WooCommerceConnector(DestinationConnector):
    """WooCommerce destination connector.

    Lifecycle:
      1. test_connection(auth)  - probe without storing state
      2. connect(auth)          - store credentials + verify connectivity
      3. health()               - lightweight ping
      4. list_products(page, per_page)  - paginated product list
      5. read_inventory(product_id)     - stock data for one product
      6. update_price(product_id, price)- Write Pipeline price-only adapter
      7. fetch_current_state(request)   - grouped post-write verification
      8. disconnect()                   - clears stored credentials
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

    async def connect(
        self,
        auth: AuthConfig,
        *,
        verify_connection: bool = True,
        transport: TransportRecorder | None = None,
    ) -> None:
        """Store credentials and verify the WooCommerce API is reachable."""
        creds = extract_credentials(auth)
        if verify_connection:
            await ping(creds, transport=transport)
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
        except ConnectorError:
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
        except ConnectorError:
            latency = (time.monotonic() - t0) * 1000
            return ConnectionTestResult(
                ok=False,
                message="WooCommerce connection failed.",
                latency_ms=round(latency, 1),
            )
        except Exception:
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

    async def update_fields(
        self,
        product_id: int,
        *,
        price: float | None = None,
        stock_quantity: int | None = None,
        stock_status: str | None = None,
        parent_product_id: int | None = None,
    ) -> dict:
        """Apply the selected governed price/inventory fields only."""
        creds = self._require_connected()
        return await update_product_fields(
            creds,
            product_id,
            price=price,
            stock_quantity=stock_quantity,
            stock_status=stock_status,
            parent_product_id=parent_product_id,
        )

    async def update_price(self, product_id: int, price: float, *, parent_product_id: int | None = None) -> dict:
        """Compatibility wrapper for legacy price-only callers."""
        return await self.update_fields(product_id, price=price, parent_product_id=parent_product_id)

    async def fetch_current_state(
        self,
        request: CurrentStateRequest,
        *,
        transport: TransportRecorder | None = None,
    ) -> CurrentStateResult:
        if request.channel_id != "woocommerce:primary":
            return failed_current_state(
                request,
                strategy=CurrentStateStrategy.BATCH_BY_ID,
                category="validation",
                message="Current-state request channel does not match WooCommerce.",
            )
        creds = self._require_connected()
        recorder = transport or TransportRecorder(
            strategy=CurrentStateStrategy.BATCH_BY_ID,
            purpose=request.purpose,
            entities_requested=len(request.entities),
        )
        records: dict[str, CurrentStateRecord] = {}
        errors: dict[str, CurrentStateError] = {}
        simple: list[CurrentStateIdentity] = []
        variations: dict[int, list[CurrentStateIdentity]] = {}
        for entity in request.entities:
            if not entity.external_id.isdigit():
                errors[entity.key] = CurrentStateError(
                    key=entity.key,
                    category="validation",
                    message="WooCommerce product ID must be numeric.",
                )
                continue
            if entity.parent_external_id is None:
                simple.append(entity)
                continue
            if not entity.parent_external_id.isdigit():
                errors[entity.key] = CurrentStateError(
                    key=entity.key,
                    category="validation",
                    message="WooCommerce parent product ID must be numeric.",
                )
                continue
            variations.setdefault(int(entity.parent_external_id), []).append(entity)

        async def load_simple(batch: Sequence[CurrentStateIdentity]) -> list[dict]:
            payload, _, _ = await list_products_paged(
                creds,
                per_page=len(batch),
                fields="id,type,regular_price,price,sale_price,stock_quantity,stock_status,manage_stock",
                status="any",
                product_ids=[int(entity.external_id) for entity in batch],
                transport=recorder,
            )
            return payload

        await self._fetch_state_batches(
            simple,
            loader=load_simple,
            recorder=recorder,
            records=records,
            errors=errors,
            parent_id=None,
        )
        for parent_id, entities in variations.items():
            async def load_variations(
                batch: Sequence[CurrentStateIdentity],
                *,
                parent: int = parent_id,
            ) -> list[dict]:
                return await list_variations_by_ids(
                    creds,
                    parent,
                    [int(entity.external_id) for entity in batch],
                    transport=recorder,
                )

            await self._fetch_state_batches(
                entities,
                loader=load_variations,
                recorder=recorder,
                records=records,
                errors=errors,
                parent_id=parent_id,
            )
        return CurrentStateResult(
            records=records,
            errors=errors,
            transport=recorder.finish(entities_returned=len(records)),
        )

    async def _fetch_state_batches(
        self,
        entities: Sequence[CurrentStateIdentity],
        *,
        loader: Callable[[Sequence[CurrentStateIdentity]], Awaitable[list[dict]]],
        recorder: TransportRecorder,
        records: dict[str, CurrentStateRecord],
        errors: dict[str, CurrentStateError],
        parent_id: int | None,
    ) -> None:
        for offset in range(0, len(entities), 100):
            await self._fetch_state_batch_isolated(
                entities[offset : offset + 100],
                loader=loader,
                recorder=recorder,
                records=records,
                errors=errors,
                parent_id=parent_id,
            )

    async def _fetch_state_batch_isolated(
        self,
        entities: Sequence[CurrentStateIdentity],
        *,
        loader: Callable[[Sequence[CurrentStateIdentity]], Awaitable[list[dict]]],
        recorder: TransportRecorder,
        records: dict[str, CurrentStateRecord],
        errors: dict[str, CurrentStateError],
        parent_id: int | None,
    ) -> None:
        if not entities:
            return
        recorder.record_batch()
        try:
            payload = await loader(entities)
        except ConnectorError as exc:
            # Split only a deterministic item-scope failure. Retrying a
            # provider-wide 5xx as a binary tree would recreate N+1 traffic.
            isolatable = (
                exc.code is ConnectorErrorCode.PROVIDER_ERROR
                and exc.http_status is not None
                and 400 <= exc.http_status < 500
            )
            if isolatable and len(entities) > 1:
                middle = len(entities) // 2
                await self._fetch_state_batch_isolated(
                    entities[:middle],
                    loader=loader,
                    recorder=recorder,
                    records=records,
                    errors=errors,
                    parent_id=parent_id,
                )
                await self._fetch_state_batch_isolated(
                    entities[middle:],
                    loader=loader,
                    recorder=recorder,
                    records=records,
                    errors=errors,
                    parent_id=parent_id,
                )
                return
            for entity in entities:
                errors[entity.key] = CurrentStateError(
                    key=entity.key,
                    category=exc.code.value,
                    message=exc.message,
                    retry_eligible=exc.retryable,
                )
            return

        by_id = {str(item.get("id")): item for item in payload if item.get("id") is not None}
        for entity in entities:
            item = by_id.get(entity.external_id)
            if item is None:
                errors[entity.key] = CurrentStateError(
                    key=entity.key,
                    category="not_found",
                    message="WooCommerce product was not returned by the current-state batch.",
                )
                continue
            records[entity.key] = CurrentStateRecord(
                key=entity.key,
                provider="woocommerce",
                external_id=str(item.get("id") or ""),
                parent_external_id=(
                    str(parent_id) if parent_id is not None else None
                ),
                price=canonical_decimal(item.get("regular_price")),
                stock=(
                    float(item["stock_quantity"])
                    if item.get("stock_quantity") is not None
                    else None
                ),
                status=str(item.get("stock_status") or "") or None,
                product_type=("variation" if parent_id is not None else _product_type(item)),
                raw=item,
            )


def _product_type(item: dict[str, object]) -> str | None:
    value = str(item.get("type") or "").strip().lower()
    return value or None
