"""SnappShop marketplace channel connector.

The connector implements the documented Vendor Automation API v2.1.2 surface.
It does not embed SnappShop behavior in the Rule Engine; all currency conversion
and channel-native identifier handling stays at this adapter boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from sqlalchemy.orm import Session

from app.flowhub.channels.contracts import (
    ChannelCapability,
    ChannelHealth,
    ChannelIdentifierSet,
    ChannelOrder,
    ChannelOrderEvent,
    ChannelOrderItem,
    ChannelProduct,
    ChannelProductUpdate,
    ChannelProductUpdateResult,
    ChannelVendor,
    ConnectorError,
    ConnectorErrorCategory,
    CursorPagination,
    PageNumberPagination,
    PaginatedResult,
    RetryMetadata,
)
from app.flowhub.channels.marketplace import BaseMarketplaceConnector
from app.flowhub.integration_platform.models import IntegrationConnectorInstance, IntegrationConnectorSetting


SNAPPSHOP_BASE_URL = "https://apix.snappshop.ir/automation/v1"
SNAPPSHOP_DEFAULT_AGENT_HEADER = "User-Agent"
SNAPPSHOP_PRODUCTS_PER_PAGE = 20
SNAPPSHOP_MAX_UPDATE_BATCH = 50
SNAPPSHOP_ORDER_EVENT_TYPES = frozenset({"NEW_ORDER", "CANCELLATION", "CHANGE_STATUS"})


class SnappShopConnectorError(Exception):
    def __init__(self, error: ConnectorError) -> None:
        self.error = error
        super().__init__(error.message)


@dataclass(frozen=True)
class SnappShopConfig:
    token: str
    agent_identifier: str
    vendor_id: str | None = None
    base_url: str = SNAPPSHOP_BASE_URL
    agent_header_name: str = SNAPPSHOP_DEFAULT_AGENT_HEADER
    timeout_seconds: int = 30
    enabled: bool = True

    @classmethod
    def from_values(cls, *, settings: dict[str, Any], secrets: dict[str, Any]) -> "SnappShopConfig":
        token = str(secrets.get("token") or settings.get("token") or "").strip()
        agent_identifier = str(
            settings.get("agent_identifier")
            or settings.get("agent_user")
            or settings.get("user_agent")
            or ""
        ).strip()
        if not token:
            raise ValueError("SnappShop token is required.")
        if not agent_identifier:
            raise ValueError("SnappShop agent identifier is required.")
        return cls(
            token=token,
            agent_identifier=agent_identifier,
            vendor_id=_blank_to_none(settings.get("vendor_id") or settings.get("vendor_selection")),
            base_url=str(settings.get("base_url") or SNAPPSHOP_BASE_URL).rstrip("/"),
            agent_header_name=str(settings.get("agent_header_name") or SNAPPSHOP_DEFAULT_AGENT_HEADER).strip(),
            timeout_seconds=_timeout_seconds(
                settings.get("request_timeout") or settings.get("timeout_seconds") or 30
            ),
            enabled=bool(settings.get("enabled", True)),
        )


class OrderEventCursorStore(Protocol):
    def get_cursor(self, channel_id: str) -> str | None:
        ...

    def advance_cursor(self, channel_id: str, cursor: str | None, event_ids: list[str]) -> None:
        ...

    def seen_event_ids(self, channel_id: str) -> set[str]:
        ...


class InMemoryOrderEventCursorStore:
    def __init__(self) -> None:
        self._cursor: dict[str, str | None] = {}
        self._seen: dict[str, set[str]] = {}

    def get_cursor(self, channel_id: str) -> str | None:
        return self._cursor.get(channel_id)

    def advance_cursor(self, channel_id: str, cursor: str | None, event_ids: list[str]) -> None:
        self._cursor[channel_id] = cursor
        self._seen.setdefault(channel_id, set()).update(event_ids)

    def seen_event_ids(self, channel_id: str) -> set[str]:
        return set(self._seen.get(channel_id, set()))


class IntegrationSettingsOrderEventCursorStore:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_cursor(self, channel_id: str) -> str | None:
        return _setting_value(self.db.get(IntegrationConnectorInstance, channel_id), "orders_events_cursor")

    def advance_cursor(self, channel_id: str, cursor: str | None, event_ids: list[str]) -> None:
        row = self.db.get(IntegrationConnectorInstance, channel_id)
        if row is None:
            return
        seen = sorted(self.seen_event_ids(channel_id).union(event_ids))[-500:]
        _upsert_setting(self.db, row, "orders_events_cursor", cursor, configured=cursor is not None)
        _upsert_setting(self.db, row, "orders_events_seen_ids", seen, configured=bool(seen))
        self.db.commit()

    def seen_event_ids(self, channel_id: str) -> set[str]:
        row = self.db.get(IntegrationConnectorInstance, channel_id)
        value = _setting_value(row, "orders_events_seen_ids")
        return set(value if isinstance(value, list) else [])


class SnappShopConnector(BaseMarketplaceConnector):
    def __init__(
        self,
        *,
        channel_id: str,
        config: SnappShopConfig,
        cursor_store: OrderEventCursorStore | None = None,
    ) -> None:
        super().__init__(
            connector_type="snappshop",
            channel_id=channel_id,
            capabilities={
                ChannelCapability.PRODUCTS_READ,
                ChannelCapability.PRODUCTS_WRITE_PRICE,
                ChannelCapability.PRODUCTS_WRITE_STOCK,
                ChannelCapability.PRODUCTS_WRITE_DISCOUNT,
                ChannelCapability.PRODUCTS_WRITE_CAPACITY,
                ChannelCapability.ORDERS_READ,
                ChannelCapability.ORDERS_EVENTS_POLL,
            },
        )
        self.config = config
        self.cursor_store = cursor_store or InMemoryOrderEventCursorStore()

    async def test_connection(self) -> ChannelHealth:
        started = _utcnow()
        try:
            vendors = await self._request("GET", "/vendors")
            data = _expect_list(vendors, self._error("Malformed vendor list response."))
            if self.config.vendor_id:
                vendor = await self._request("GET", f"/vendors/{self.config.vendor_id}")
                _expect_dict(vendor.get("data"), self._error("Malformed selected vendor response."))
            elif not data:
                raise SnappShopConnectorError(self._error("No authorized SnappShop vendors were returned."))
            latency = (_utcnow() - started).total_seconds() * 1000
            return ChannelHealth(status="healthy", checked_at=_iso(_utcnow()), latency_ms=round(latency, 2))
        except SnappShopConnectorError as exc:
            return ChannelHealth(status="unhealthy", checked_at=_iso(_utcnow()), error=exc.error)

    async def list_vendors(self) -> list[ChannelVendor]:
        payload = await self._request("GET", "/vendors")
        data = _expect_list(payload, self._error("Malformed vendor list response."))
        return [_vendor_from_payload(self.channel_id, item) for item in data if isinstance(item, dict)]

    async def get_vendor_information(self) -> ChannelVendor:
        vendor_id = await self._selected_vendor_id()
        payload = await self._request("GET", f"/vendors/{vendor_id}")
        data = _expect_dict(payload.get("data"), self._error("Malformed vendor response."))
        return _vendor_from_payload(self.channel_id, data)

    async def list_products(
        self,
        pagination: PageNumberPagination | CursorPagination | None = None,
    ) -> PaginatedResult:
        vendor_id = await self._selected_vendor_id()
        page = pagination.page if isinstance(pagination, PageNumberPagination) else 1
        payload = await self._request("GET", f"/vendors/{vendor_id}/products", params={"page": page})
        data = _expect_list(payload, self._error("Malformed product list response."))
        page_meta = _page_meta(payload)
        next_page = _next_page_from_link(page_meta)
        current_page = int(page_meta.get("current_page") or page)
        total_pages = _optional_int(page_meta.get("total_pages"))
        return PaginatedResult(
            items=[_product_from_payload(self.channel_id, item) for item in data],
            pagination=PageNumberPagination(
                page=current_page,
                page_size=int(page_meta.get("per_page") or SNAPPSHOP_PRODUCTS_PER_PAGE),
                total=_optional_int(page_meta.get("total")),
                total_pages=total_pages,
                has_more=(next_page is not None) or (total_pages is not None and current_page < total_pages),
                next_page=next_page,
            ),
        )

    async def list_all_products(self, *, max_pages: int = 250) -> list[ChannelProduct]:
        page = 1
        products: list[ChannelProduct] = []
        while page <= max_pages:
            result = await self.list_products(PageNumberPagination(page=page, page_size=SNAPPSHOP_PRODUCTS_PER_PAGE))
            products.extend(result.items)
            pagination = result.pagination
            if not isinstance(pagination, PageNumberPagination) or not pagination.has_more:
                break
            page = pagination.next_page or (page + 1)
        return products

    async def get_product(self, identifiers: dict[str, str]) -> ChannelProduct:
        vendor_id = await self._selected_vendor_id()
        product_id = identifiers.get("id") or identifiers.get("external_product_id")
        if not product_id:
            raise SnappShopConnectorError(self._validation_error("SnappShop product id is required."))
        payload = await self._request("GET", f"/vendors/{vendor_id}/products/{product_id}")
        data = _expect_dict(payload.get("data"), self._error("Malformed product response."))
        return _product_from_payload(self.channel_id, data)

    async def update_products(self, updates: list[ChannelProductUpdate]) -> list[ChannelProductUpdateResult]:
        if len(updates) > SNAPPSHOP_MAX_UPDATE_BATCH:
            raise SnappShopConnectorError(self._validation_error("SnappShop product updates are limited to 50 items."))
        vendor_id = await self._selected_vendor_id()
        request_items = [_update_to_payload(update) for update in updates]
        try:
            payload = await self._request("PATCH", f"/vendors/{vendor_id}/products", json={"products": request_items})
        except SnappShopConnectorError as exc:
            if exc.error.category == ConnectorErrorCategory.VALIDATION:
                return [_failed_update(update, exc.error) for update in updates]
            raise
        data = _expect_list(payload, self._error("Malformed product update response."))
        return [_update_result_from_payload(self.channel_id, item) for item in data]

    async def list_order_events(
        self,
        pagination: PageNumberPagination | CursorPagination | None = None,
    ) -> PaginatedResult:
        vendor_id = await self._selected_vendor_id()
        cursor = pagination.cursor if isinstance(pagination, CursorPagination) else self.cursor_store.get_cursor(self.channel_id)
        params = {"cursor": cursor} if cursor else None
        payload = await self._request("GET", f"/vendors/{vendor_id}/orders/events", params=params)
        data = _expect_list(payload, self._error("Malformed order event response."))
        seen = self.cursor_store.seen_event_ids(self.channel_id)
        events = [_event_from_payload(self.channel_id, item) for item in data]
        unique = [event for event in events if event.event_id not in seen]
        cursor_meta = _cursor_meta(payload, cursor)
        return PaginatedResult(items=unique, pagination=cursor_meta)

    def acknowledge_order_events(self, page: PaginatedResult) -> None:
        pagination = page.pagination
        if not isinstance(pagination, CursorPagination):
            return
        event_ids = [item.event_id for item in page.items if isinstance(item, ChannelOrderEvent)]
        self.cursor_store.advance_cursor(self.channel_id, pagination.next_cursor, event_ids)

    async def list_orders(
        self,
        pagination: PageNumberPagination | CursorPagination | None = None,
    ) -> PaginatedResult:
        vendor_id = await self._selected_vendor_id()
        cursor = pagination.cursor if isinstance(pagination, CursorPagination) else None
        params = {"cursor": cursor} if cursor else None
        payload = await self._request("GET", f"/vendors/{vendor_id}/orders", params=params)
        data = _expect_list(payload, self._error("Malformed order list response."))
        return PaginatedResult(
            items=[_order_from_payload(self.channel_id, item) for item in data],
            pagination=_cursor_meta(payload, cursor),
        )

    async def list_order_history(
        self,
        *,
        date_start: str | None = None,
        date_end: str | None = None,
        cursor: str | None = None,
    ) -> PaginatedResult:
        vendor_id = await self._selected_vendor_id()
        params = {k: v for k, v in {"start_date": date_start, "end_date": date_end, "cursor": cursor}.items() if v}
        payload = await self._request("GET", f"/vendors/{vendor_id}/orders", params=params or None)
        data = _expect_list(payload, self._error("Malformed order history response."))
        return PaginatedResult(
            items=[_order_from_payload(self.channel_id, item) for item in data],
            pagination=_cursor_meta(payload, cursor),
        )

    async def get_order(self, identifiers: dict[str, str]) -> ChannelOrder:
        vendor_id = await self._selected_vendor_id()
        order_number = identifiers.get("order_number") or identifiers.get("id")
        if not order_number:
            raise SnappShopConnectorError(self._validation_error("SnappShop order_number is required."))
        payload = await self._request("GET", f"/vendors/{vendor_id}/orders/{order_number}")
        data = _expect_dict(payload.get("data"), self._error("Malformed order response."))
        return _order_from_payload(self.channel_id, data)

    async def _selected_vendor_id(self) -> str:
        if self.config.vendor_id:
            return self.config.vendor_id
        payload = await self._request("GET", "/vendors")
        data = _expect_list(payload, self._error("Malformed vendor list response."))
        if not data or not isinstance(data[0], dict) or not data[0].get("id"):
            raise SnappShopConnectorError(self._error("No authorized SnappShop vendor id was returned."))
        return str(data[0]["id"])

    async def _request(self, method: str, path: str, *, params: dict | None = None, json: dict | None = None) -> dict:
        url = urljoin(f"{self.config.base_url}/", path.lstrip("/"))
        headers = {
            "Authorization": f"Bearer {self.config.token}",
            self.config.agent_header_name: self.config.agent_identifier,
            "Accept": "application/json",
        }
        timeout = httpx.Timeout(self.config.timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(method, url, headers=headers, params=params, json=json)
        except httpx.TimeoutException as exc:
            raise SnappShopConnectorError(self._timeout_error()) from exc
        except httpx.HTTPError as exc:
            raise SnappShopConnectorError(self._upstream_error("SnappShop request failed.")) from exc
        return self._decode_response(response)

    def _decode_response(self, response: httpx.Response) -> dict:
        try:
            payload = response.json()
        except ValueError as exc:
            raise SnappShopConnectorError(self._error("SnappShop returned a malformed JSON response.", response.status_code)) from exc
        if not isinstance(payload, dict):
            raise SnappShopConnectorError(self._error("SnappShop returned a malformed response.", response.status_code))
        if response.status_code == 401:
            raise SnappShopConnectorError(self._auth_error(response.status_code))
        if response.status_code == 403:
            raise SnappShopConnectorError(self._authorization_error(response.status_code))
        if response.status_code == 404:
            raise SnappShopConnectorError(self._not_found_error(response.status_code))
        if response.status_code == 409:
            raise SnappShopConnectorError(self._conflict_error(response.status_code))
        if response.status_code == 422:
            raise SnappShopConnectorError(self._validation_error("SnappShop rejected the request validation.", response.status_code))
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise SnappShopConnectorError(self._rate_limit_error(response.status_code, retry_after))
        if response.status_code >= 500:
            raise SnappShopConnectorError(self._upstream_error("SnappShop is unavailable.", response.status_code))
        if response.status_code >= 400:
            raise SnappShopConnectorError(self._error("SnappShop request failed.", response.status_code))
        if payload.get("status") is False:
            raise SnappShopConnectorError(self._error("SnappShop returned an unsuccessful response.", response.status_code))
        return payload

    def _error(self, message: str, http_status: int | None = None) -> ConnectorError:
        return ConnectorError(
            category=ConnectorErrorCategory.UNEXPECTED_RESPONSE,
            message=message,
            connector_type=self.connector_type,
            channel_id=self.channel_id,
            http_status=http_status,
            retry=RetryMetadata(retryable=False, safe_to_retry=False),
        )

    def _validation_error(self, message: str, http_status: int | None = None) -> ConnectorError:
        return self._categorized_error(ConnectorErrorCategory.VALIDATION, message, http_status)

    def _auth_error(self, http_status: int | None = None) -> ConnectorError:
        return self._categorized_error(ConnectorErrorCategory.AUTHENTICATION, "SnappShop authentication failed.", http_status)

    def _authorization_error(self, http_status: int | None = None) -> ConnectorError:
        return self._categorized_error(ConnectorErrorCategory.AUTHORIZATION, "SnappShop authorization failed.", http_status)

    def _not_found_error(self, http_status: int | None = None) -> ConnectorError:
        return self._categorized_error(ConnectorErrorCategory.NOT_FOUND, "SnappShop resource was not found.", http_status)

    def _conflict_error(self, http_status: int | None = None) -> ConnectorError:
        return self._categorized_error(ConnectorErrorCategory.CONFLICT, "SnappShop reported a state conflict.", http_status)

    def _timeout_error(self) -> ConnectorError:
        return self._categorized_error(ConnectorErrorCategory.TIMEOUT, "SnappShop request timed out.", None, retryable=True)

    def _upstream_error(self, message: str, http_status: int | None = None) -> ConnectorError:
        return self._categorized_error(ConnectorErrorCategory.UPSTREAM_UNAVAILABLE, message, http_status, retryable=True)

    def _rate_limit_error(self, http_status: int | None, retry_after: str | None) -> ConnectorError:
        try:
            retry_after_seconds = float(retry_after) if retry_after is not None else None
        except ValueError:
            retry_after_seconds = None
        return ConnectorError(
            category=ConnectorErrorCategory.RATE_LIMIT,
            message="SnappShop rate limit was reached.",
            connector_type=self.connector_type,
            channel_id=self.channel_id,
            http_status=http_status,
            retry=RetryMetadata(retryable=True, retry_after_seconds=retry_after_seconds, safe_to_retry=False),
        )

    def _categorized_error(
        self,
        category: ConnectorErrorCategory,
        message: str,
        http_status: int | None,
        *,
        retryable: bool = False,
    ) -> ConnectorError:
        return ConnectorError(
            category=category,
            message=message,
            connector_type=self.connector_type,
            channel_id=self.channel_id,
            http_status=http_status,
            retry=RetryMetadata(retryable=retryable, safe_to_retry=False),
        )


def _vendor_from_payload(channel_id: str, item: dict[str, Any]) -> ChannelVendor:
    return ChannelVendor(
        channel_id=channel_id,
        connector_type="snappshop",
        vendor_id=_string(item.get("id")),
        name=_string(item.get("title_en") or item.get("title") or item.get("id")) or "SnappShop vendor",
        identifiers=ChannelIdentifierSet(channel_reference_code=_string(item.get("id"))),
        metadata={"status": item.get("status"), "title": item.get("title"), "title_en": item.get("title_en")},
    )


def _product_from_payload(channel_id: str, item: dict[str, Any]) -> ChannelProduct:
    return ChannelProduct(
        channel_id=channel_id,
        connector_type="snappshop",
        identifiers=ChannelIdentifierSet(
            external_product_id=_string(item.get("id")),
            sku=_string(item.get("sku")),
            product_number=_string(item.get("product_number")),
            parent_product_number=_string(item.get("parent_product_number")),
        ),
        name=_string(item.get("title_en") or item.get("title") or item.get("id")) or "",
        current_price=_optional_float(item.get("price")),
        currency="IRR",
        price_unit="toman",
        stock_quantity=_optional_float(item.get("stock")),
        status="active" if item.get("active") is True else "inactive" if item.get("active") is False else None,
        raw=item,
    )


def _order_from_payload(channel_id: str, item: dict[str, Any]) -> ChannelOrder:
    raw_items = item.get("items") if isinstance(item.get("items"), list) else []
    return ChannelOrder(
        channel_id=channel_id,
        connector_type="snappshop",
        identifiers=ChannelIdentifierSet(order_number=_string(item.get("order_number"))),
        status=_string(item.get("status") or item.get("new_status")) or "UNKNOWN",
        created_at=_string(item.get("created_at") or item.get("order_at")),
        updated_at=_string(item.get("updated_at") or item.get("event_at")),
        items=[_order_item_from_payload(order_item) for order_item in raw_items if isinstance(order_item, dict)],
        total=_optional_float(item.get("final_price") or item.get("total")),
        currency="IRR",
        raw=item,
    )


def _order_item_from_payload(item: dict[str, Any]) -> ChannelOrderItem:
    return ChannelOrderItem(
        identifiers=ChannelIdentifierSet(
            sku=_string(item.get("sku")),
            external_product_id=_string(item.get("vendor_product_info_id")),
            product_number=_string(item.get("product_number")),
            parent_product_number=_string(item.get("parent_product_number")),
        ),
        name=_string(item.get("title") or item.get("name")) or "",
        quantity=_optional_float(item.get("quantity") or item.get("deliverable_quantity")) or 0,
        unit_price=_optional_float(item.get("final_price")),
        currency="IRR",
        raw={
            "sku": item.get("sku"),
            "vendor_product_info_id": item.get("vendor_product_info_id"),
            "product_number": item.get("product_number"),
            "parent_product_number": item.get("parent_product_number"),
            "canceled_quantity": item.get("canceled_quantity"),
            "total_canceled_quantity": item.get("total_canceled_quantity"),
            "deliverable_quantity": item.get("deliverable_quantity"),
            "final_price": item.get("final_price"),
            "item_status": item.get("item_status"),
            **item,
        },
    )


def _event_from_payload(channel_id: str, item: dict[str, Any]) -> ChannelOrderEvent:
    event_type = _string(item.get("event_type")) or "UNKNOWN"
    if event_type not in SNAPPSHOP_ORDER_EVENT_TYPES:
        event_type = "UNKNOWN"
    order_number = _string(item.get("order_number"))
    occurred_at = _string(item.get("event_at"))
    event_id = _string(item.get("event_id")) or f"{event_type}:{order_number}:{occurred_at}"
    return ChannelOrderEvent(
        channel_id=channel_id,
        connector_type="snappshop",
        event_id=event_id,
        event_type=event_type,
        occurred_at=occurred_at,
        order_identifiers=ChannelIdentifierSet(order_number=order_number),
        raw=item,
    )


def _update_to_payload(update: ChannelProductUpdate) -> dict[str, Any]:
    identifiers = update.identifiers
    outbound: dict[str, Any] = {}
    if identifiers.sku:
        outbound["sku"] = identifiers.sku
    elif identifiers.external_product_id:
        outbound["id"] = identifiers.external_product_id
    else:
        raise SnappShopConnectorError(_standalone_validation_error(update.channel_id, "Update requires sku or external product id."))
    if update.stock_quantity is None or update.price is None:
        raise SnappShopConnectorError(_standalone_validation_error(update.channel_id, "Update requires stock and price."))
    outbound["stock"] = int(update.stock_quantity)
    outbound["price"] = toman_amount(update.price, currency=update.currency, unit=update.price_unit)
    if update.capacity is not None:
        outbound["capacity"] = int(update.capacity)
    if update.discount_price is not None:
        outbound["special_price"] = toman_amount(update.discount_price, currency=update.currency, unit=update.price_unit)
    if update.special_price_start_at:
        outbound["special_price_start_at"] = update.special_price_start_at
    if update.special_price_end_at:
        outbound["special_price_end_at"] = update.special_price_end_at
    if update.special_price_stock is not None:
        outbound["special_price_stock"] = int(update.special_price_stock)
    return outbound


def _update_result_from_payload(channel_id: str, item: dict[str, Any]) -> ChannelProductUpdateResult:
    success = bool(item.get("status"))
    error = None if success else ConnectorError(
        category=ConnectorErrorCategory.VALIDATION,
        message="; ".join(str(message) for message in item.get("messages") or []) or "SnappShop rejected this product update.",
        connector_type="snappshop",
        channel_id=channel_id,
        retry=RetryMetadata(retryable=False, safe_to_retry=False),
    )
    return ChannelProductUpdateResult(
        channel_id=channel_id,
        identifiers=ChannelIdentifierSet(external_product_id=_string(item.get("id") or item.get("d")), sku=_string(item.get("sku"))),
        success=success,
        applied_capabilities=[
            ChannelCapability.PRODUCTS_WRITE_PRICE,
            ChannelCapability.PRODUCTS_WRITE_STOCK,
        ] if success else [],
        error=error,
        raw=item,
    )


def _failed_update(update: ChannelProductUpdate, error: ConnectorError) -> ChannelProductUpdateResult:
    return ChannelProductUpdateResult(channel_id=update.channel_id, identifiers=update.identifiers, success=False, error=error)


def toman_amount(amount: float, *, currency: str | None, unit: str | None) -> int:
    normalized_currency = (currency or "").strip().upper()
    normalized_unit = (unit or "").strip().lower()
    if normalized_unit in {"toman", "tmn"} or normalized_currency in {"TMN", "TOMAN"}:
        return int(round(amount))
    if normalized_unit in {"rial", "irr"} or normalized_currency == "IRR":
        if amount % 10:
            raise SnappShopConnectorError(_standalone_validation_error("snappshop:main", "IRR amounts must be divisible by 10 before SnappShop toman conversion."))
        return int(round(amount / 10))
    raise SnappShopConnectorError(_standalone_validation_error("snappshop:main", "Price currency/unit metadata is required for SnappShop writes."))


def _cursor_meta(payload: dict[str, Any], cursor: str | None) -> CursorPagination:
    pagination = payload.get("meta", {}).get("pagination", {}) if isinstance(payload.get("meta"), dict) else {}
    return CursorPagination(
        cursor=cursor,
        next_cursor=_string(pagination.get("next_cursor")) or _next_cursor_from_link(pagination),
        limit=int(pagination.get("per_page") or pagination.get("count") or SNAPPSHOP_PRODUCTS_PER_PAGE),
        has_more=bool(pagination.get("has_more")),
    )


def _page_meta(payload: dict[str, Any]) -> dict[str, Any]:
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    pagination = meta.get("pagination") if isinstance(meta.get("pagination"), dict) else {}
    return pagination


def _expect_list(payload: dict[str, Any], error: ConnectorError) -> list[dict[str, Any]]:
    data = payload.get("data")
    if not isinstance(data, list):
        raise SnappShopConnectorError(error)
    return [item for item in data if isinstance(item, dict)]


def _expect_dict(value: Any, error: ConnectorError) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SnappShopConnectorError(error)
    return value


def _standalone_validation_error(channel_id: str, message: str) -> ConnectorError:
    return ConnectorError(
        category=ConnectorErrorCategory.VALIDATION,
        message=message,
        connector_type="snappshop",
        channel_id=channel_id,
        retry=RetryMetadata(retryable=False, safe_to_retry=False),
    )


def _setting_value(row: IntegrationConnectorInstance | None, key: str) -> Any:
    if row is None:
        return None
    for item in row.settings:
        if item.key == key:
            return item.value_json
    return None


def _upsert_setting(db: Session, row: IntegrationConnectorInstance, key: str, value: Any, *, configured: bool) -> None:
    for item in row.settings:
        if item.key == key:
            item.value_json = value
            item.secret = False
            item.configured = configured
            return
    db.add(IntegrationConnectorSetting(connector_id=row.id, key=key, value_json=value, secret=False, configured=configured))


def _next_cursor_from_link(pagination: dict[str, Any]) -> str | None:
    links = pagination.get("links") if isinstance(pagination.get("links"), dict) else {}
    next_link = links.get("next")
    if not isinstance(next_link, str) or "cursor=" not in next_link:
        return None
    return next_link.split("cursor=", 1)[1].split("&", 1)[0] or None


def _next_page_from_link(pagination: dict[str, Any]) -> int | None:
    links = pagination.get("links") if isinstance(pagination.get("links"), dict) else {}
    next_link = links.get("next")
    if not isinstance(next_link, str) or not next_link.strip():
        return None
    values = parse_qs(urlparse(next_link).query).get("page") or []
    return _optional_int(values[0]) if values else None


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _blank_to_none(value: Any) -> str | None:
    return _string(value)


def _timeout_seconds(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("SnappShop request timeout must be a whole number of seconds.")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("SnappShop request timeout must be a whole number of seconds.") from exc
    if not parsed.is_integer() or parsed < 1 or parsed > 120:
        raise ValueError("SnappShop request timeout must be an integer between 1 and 120 seconds.")
    return int(parsed)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds") + "Z"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
