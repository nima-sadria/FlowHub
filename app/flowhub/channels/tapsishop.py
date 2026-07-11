"""TapsiShop marketplace channel connector."""

from __future__ import annotations

import asyncio
import json as jsonlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

import httpx

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
from app.flowhub.channels.marketplace import BaseMarketplaceConnector, UnsupportedCapabilityError


TAPSISHOP_BASE_URL = "https://vendorgw.tapsi.shop/Web/Hub/vendors/v1"
TAPSISHOP_AUTH_HEADER = "TapsiShop.Hub.Authorization"
TAPSISHOP_WEBHOOK_AUTH_HEADER = "TapsiShop.Hub.Webhook-Authorization"
TAPSISHOP_REFRESH_PATH = "/refresh-token"
TAPSISHOP_COURIER_REVIEW_METHOD = "PUT"
TAPSISHOP_COURIER_REVIEW_PATH = "/review-courier"


class TapsiShopConnectorError(Exception):
    def __init__(self, error: ConnectorError) -> None:
        self.error = error
        super().__init__(error.message)


@dataclass(frozen=True)
class TapsiShopConfig:
    token: str
    webhook_token: str | None = None
    base_url: str = TAPSISHOP_BASE_URL
    timeout_seconds: float = 30.0
    enabled: bool = True
    refresh_enabled: bool = False
    refresh_token_name: str = "FlowHub"
    refresh_revoke_current_token: bool = False
    refresh_expired_at: str | None = None
    selected_vendor_id: str | None = None

    @classmethod
    def from_values(cls, *, settings: dict[str, Any], secrets: dict[str, Any]) -> "TapsiShopConfig":
        token = str(secrets.get("token") or settings.get("token") or "").strip()
        if not token:
            raise ValueError("TapsiShop authorization token is required.")
        return cls(
            token=token,
            webhook_token=_blank_to_none(secrets.get("webhook_token") or settings.get("webhook_token")),
            base_url=str(settings.get("base_url") or TAPSISHOP_BASE_URL).strip().rstrip("/"),
            timeout_seconds=float(settings.get("request_timeout") or settings.get("timeout_seconds") or 30.0),
            enabled=bool(settings.get("enabled", True)),
            refresh_enabled=_to_bool(settings.get("token_refresh_enabled") or settings.get("refresh_enabled")),
            refresh_token_name=str(settings.get("token_refresh_name") or "FlowHub").strip() or "FlowHub",
            refresh_revoke_current_token=_to_bool(settings.get("revoke_current_token")),
            refresh_expired_at=_blank_to_none(settings.get("token_refresh_expired_at") or settings.get("expired_at")),
            selected_vendor_id=_blank_to_none(settings.get("selected_vendor_id") or settings.get("vendor_id")),
        )


class TapsiShopConnector(BaseMarketplaceConnector):
    def __init__(
        self,
        *,
        channel_id: str,
        config: TapsiShopConfig,
        token_updater: Callable[[str], None] | None = None,
        refresh_lock: asyncio.Lock | None = None,
    ) -> None:
        super().__init__(
            connector_type="tapsishop",
            channel_id=channel_id,
            capabilities={
                ChannelCapability.PRODUCTS_READ,
                ChannelCapability.PRODUCTS_WRITE_PRICE,
                ChannelCapability.PRODUCTS_WRITE_STOCK,
                ChannelCapability.ORDERS_READ,
                ChannelCapability.ORDERS_WEBHOOK_RECEIVE,
                ChannelCapability.CREDENTIALS_REFRESH,
                ChannelCapability.COURIER_READ,
            },
        )
        self.config = config
        self._token = config.token
        self._token_updater = token_updater
        self._refresh_lock = refresh_lock or asyncio.Lock()

    async def test_connection(self) -> ChannelHealth:
        started = _utcnow()
        try:
            payload = await self._request("GET", "/vendor-information", safe_to_retry=True)
            data = _expect_dict(payload.get("data"), self._error("Malformed vendor information response."))
            self._validate_selected_vendor(data)
            latency = (_utcnow() - started).total_seconds() * 1000
            return ChannelHealth(status="healthy", checked_at=_iso(_utcnow()), latency_ms=round(latency, 2))
        except TapsiShopConnectorError as exc:
            return ChannelHealth(status="unhealthy", checked_at=_iso(_utcnow()), error=exc.error)

    async def get_vendor_information(self) -> ChannelVendor:
        payload = await self._request("GET", "/vendor-information", safe_to_retry=True)
        data = _expect_dict(payload.get("data"), self._error("Malformed vendor information response."))
        return ChannelVendor(
            channel_id=self.channel_id,
            connector_type=self.connector_type,
            vendor_id=_string(data.get("vendorId")),
            name=_string(data.get("storeName") or data.get("vendorName") or data.get("vendorId")) or "TapsiShop vendor",
            display_url=_string(data.get("storeLink")),
            identifiers=ChannelIdentifierSet(channel_reference_code=_string(data.get("storeNumber"))),
            metadata={
                "vendorId": data.get("vendorId"),
                "vendorName": data.get("vendorName"),
                "storeName": data.get("storeName"),
                "storeLink": data.get("storeLink"),
                "storeNumber": data.get("storeNumber"),
            },
        )

    async def list_products(
        self,
        pagination: PageNumberPagination | CursorPagination | None = None,
    ) -> PaginatedResult:
        page = pagination.page if isinstance(pagination, PageNumberPagination) else 1
        page_size = pagination.page_size if isinstance(pagination, PageNumberPagination) else 20
        payload = await self._request("GET", f"/products/{page}/{page_size}", safe_to_retry=True)
        data = _expect_dict(payload.get("data"), self._error("Malformed product list response."))
        items = data.get("items")
        if not isinstance(items, list):
            raise TapsiShopConnectorError(self._error("Malformed product list items."))
        total = _optional_int(data.get("totalCount"))
        size = int(data.get("pageSize") or page_size or 20)
        total_pages = ((total + size - 1) // size) if total is not None and size else None
        return PaginatedResult(
            items=[_product_from_payload(self.channel_id, item) for item in items if isinstance(item, dict)],
            pagination=PageNumberPagination(
                page=int(data.get("page") or page),
                page_size=size,
                total=total,
                total_pages=total_pages,
            ),
        )

    async def get_product(self, identifiers: dict[str, str]) -> ChannelProduct:
        # The document only defines paginated product listing. Keep lookup explicit and testable.
        raise UnsupportedCapabilityError(ChannelCapability.PRODUCTS_READ, self.channel_id, self.connector_type)

    async def update_products(self, updates: list[ChannelProductUpdate]) -> list[ChannelProductUpdateResult]:
        body = {"products": [_update_to_payload(update) for update in updates]}
        payload = await self._request("PUT", "/products", json=body, safe_to_retry=False)
        data = _expect_dict(payload.get("data"), self._error("Malformed product update response."))
        items = data.get("data")
        if not isinstance(items, list):
            raise TapsiShopConnectorError(self._error("Malformed product update item results."))
        return [_update_result_from_payload(self.channel_id, item) for item in items if isinstance(item, dict)]

    async def list_orders(
        self,
        pagination: PageNumberPagination | CursorPagination | None = None,
        *,
        filters: dict[str, Any] | None = None,
    ) -> PaginatedResult:
        page = pagination.page if isinstance(pagination, PageNumberPagination) else 0
        page_size = pagination.page_size if isinstance(pagination, PageNumberPagination) else 20
        request_body = {"pageNumber": page, "pageSize": page_size, **(filters or {})}
        payload = await self._request("POST", "/orders", json=request_body, safe_to_retry=True)
        data = _expect_dict(payload.get("data"), self._error("Malformed order list response."))
        items = data.get("items")
        if not isinstance(items, list):
            raise TapsiShopConnectorError(self._error("Malformed order list items."))
        total = _optional_int(data.get("totalItems"))
        size = int(data.get("pageSize") or page_size or 20)
        total_pages = ((total + size - 1) // size) if total is not None and size else None
        return PaginatedResult(
            items=[_order_summary_from_payload(self.channel_id, item) for item in items if isinstance(item, dict)],
            pagination=PageNumberPagination(
                page=int(data.get("pageNumber") or page),
                page_size=size,
                total=total,
                total_pages=total_pages,
            ),
        )

    async def get_order(self, identifiers: dict[str, str]) -> ChannelOrder:
        order_id = identifiers.get("orderId") or identifiers.get("id") or identifiers.get("order_number")
        if not order_id:
            raise TapsiShopConnectorError(self._validation_error("TapsiShop order id is required."))
        payload = await self._request("GET", f"/orders/{order_id}", safe_to_retry=True)
        data = _expect_dict(payload.get("data"), self._error("Malformed order detail response."))
        return _order_detail_from_payload(self.channel_id, data)

    async def list_order_events(
        self,
        pagination: PageNumberPagination | CursorPagination | None = None,
    ) -> PaginatedResult:
        raise UnsupportedCapabilityError(ChannelCapability.ORDERS_EVENTS_POLL, self.channel_id, self.connector_type)

    async def receive_webhook(self, payload: bytes, headers: dict[str, str]) -> ChannelOrderEvent:
        expected = self.config.webhook_token
        supplied = _header_value(headers, TAPSISHOP_WEBHOOK_AUTH_HEADER)
        if not expected or supplied != expected:
            raise TapsiShopConnectorError(self._categorized_error(ConnectorErrorCategory.AUTHENTICATION, "TapsiShop webhook authentication failed.", 401))
        try:
            body = jsonlib.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise TapsiShopConnectorError(self._validation_error("Malformed TapsiShop webhook payload.")) from exc
        if not isinstance(body, dict):
            raise TapsiShopConnectorError(self._validation_error("Malformed TapsiShop webhook payload."))
        order_detail = body.get("orderDetail") if isinstance(body.get("orderDetail"), dict) else {}
        order_id = _string(order_detail.get("orderId"))
        order_number = _string(order_detail.get("orderNumber"))
        change_type = _string(order_detail.get("changeType"))
        event_id = _string(order_detail.get("requestId")) or f"tapsishop:{order_id}:{change_type}:{order_detail.get('createdOnTimestamp')}"
        return ChannelOrderEvent(
            channel_id=self.channel_id,
            connector_type=self.connector_type,
            event_id=event_id,
            event_type=change_type or "UNKNOWN",
            occurred_at=_string(order_detail.get("createdOnTimestamp")),
            order_identifiers=ChannelIdentifierSet(order_number=order_number, external_product_id=order_id),
            raw=body,
        )

    def webhook_success_response(self, message: str = "Processed") -> dict[str, Any]:
        return {"message": message, "succeed": True}

    async def get_courier(self, pickup_code: str) -> dict[str, Any]:
        payload = await self._request("GET", f"/courier/{pickup_code}", safe_to_retry=True)
        return _expect_dict(payload.get("data"), self._error("Malformed courier response."))

    async def review_courier(self, *, pickup_code: str, is_acceptable: bool, include_details: bool) -> dict[str, Any]:
        raise UnsupportedCapabilityError(ChannelCapability.COURIER_REVIEW, self.channel_id, self.connector_type)

    async def refresh_credentials(self) -> ChannelHealth:
        if not self.config.refresh_enabled:
            return ChannelHealth(status="degraded", error=self._validation_error("TapsiShop token refresh is disabled."))
        try:
            await self._refresh_token()
            return ChannelHealth(status="healthy", checked_at=_iso(_utcnow()))
        except TapsiShopConnectorError as exc:
            return ChannelHealth(status="unhealthy", checked_at=_iso(_utcnow()), error=exc.error)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        safe_to_retry: bool,
        retry_after_refresh: bool = True,
    ) -> dict:
        try:
            response = await self._send(method, path, token=self._token, json=json)
            return self._decode_response(response)
        except TapsiShopConnectorError as exc:
            if (
                retry_after_refresh
                and safe_to_retry
                and exc.error.category == ConnectorErrorCategory.AUTHENTICATION
                and self.config.refresh_enabled
            ):
                await self._refresh_token()
                response = await self._send(method, path, token=self._token, json=json)
                return self._decode_response(response)
            raise

    async def _send(self, method: str, path: str, *, token: str, json: dict | None = None) -> httpx.Response:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            TAPSISHOP_AUTH_HEADER: token,
        }
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.config.timeout_seconds)) as client:
                return await client.request(method, self._url(path), headers=headers, json=json)
        except httpx.TimeoutException as exc:
            raise TapsiShopConnectorError(self._categorized_error(ConnectorErrorCategory.TIMEOUT, "TapsiShop request timed out.", None, retryable=True)) from exc
        except httpx.HTTPError as exc:
            raise TapsiShopConnectorError(self._categorized_error(ConnectorErrorCategory.UPSTREAM_UNAVAILABLE, "TapsiShop request failed.", None, retryable=True)) from exc

    async def _refresh_token(self) -> str:
        async with self._refresh_lock:
            request_body = {
                "token": self._token,
                "name": self.config.refresh_token_name,
                "revokeCurrentToken": self.config.refresh_revoke_current_token,
                "expiredAt": self.config.refresh_expired_at,
            }
            response = await self._send_without_auth("POST", TAPSISHOP_REFRESH_PATH, json=request_body)
            payload = self._decode_response(response)
            data = _expect_dict(payload.get("data"), self._error("Malformed TapsiShop token refresh response."))
            new_token = _string(data.get("token"))
            if not new_token:
                raise TapsiShopConnectorError(self._error("TapsiShop token refresh did not return a token."))
            self._token = new_token
            if self._token_updater:
                self._token_updater(new_token)
            return new_token

    async def _send_without_auth(self, method: str, path: str, *, json: dict | None = None) -> httpx.Response:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self.config.timeout_seconds)) as client:
                return await client.request(method, self._url(path), headers={"Accept": "application/json", "Content-Type": "application/json"}, json=json)
        except httpx.TimeoutException as exc:
            raise TapsiShopConnectorError(self._categorized_error(ConnectorErrorCategory.TIMEOUT, "TapsiShop token refresh timed out.", None, retryable=True)) from exc
        except httpx.HTTPError as exc:
            raise TapsiShopConnectorError(self._categorized_error(ConnectorErrorCategory.UPSTREAM_UNAVAILABLE, "TapsiShop token refresh failed.", None, retryable=True)) from exc

    def _url(self, path: str) -> str:
        return f"{self.config.base_url.rstrip('/')}/{path.strip('/')}"

    def _validate_selected_vendor(self, data: dict[str, Any]) -> None:
        selected = self.config.selected_vendor_id
        if not selected:
            return
        documented_ids = {
            _string(data.get("vendorId")),
            _string(data.get("storeNumber")),
        }
        if selected not in {item for item in documented_ids if item}:
            raise TapsiShopConnectorError(self._categorized_error(
                ConnectorErrorCategory.NOT_FOUND,
                "Configured TapsiShop vendor/store identity was not returned by vendor-information.",
                404,
            ))

    def _decode_response(self, response: httpx.Response) -> dict:
        try:
            payload = response.json()
        except ValueError as exc:
            raise TapsiShopConnectorError(self._error("TapsiShop returned malformed JSON.", response.status_code)) from exc
        if not isinstance(payload, dict):
            raise TapsiShopConnectorError(self._error("TapsiShop returned a malformed response.", response.status_code))
        if response.status_code == 401:
            raise TapsiShopConnectorError(self._categorized_error(ConnectorErrorCategory.AUTHENTICATION, "TapsiShop authentication failed.", response.status_code))
        if response.status_code == 403:
            raise TapsiShopConnectorError(self._categorized_error(ConnectorErrorCategory.AUTHORIZATION, "TapsiShop authorization failed.", response.status_code))
        if response.status_code == 404:
            raise TapsiShopConnectorError(self._categorized_error(ConnectorErrorCategory.NOT_FOUND, "TapsiShop resource was not found.", response.status_code))
        if response.status_code == 422:
            raise TapsiShopConnectorError(self._categorized_error(ConnectorErrorCategory.VALIDATION, "TapsiShop rejected request validation.", response.status_code))
        if response.status_code == 429:
            raise TapsiShopConnectorError(self._categorized_error(ConnectorErrorCategory.RATE_LIMIT, "TapsiShop rate limit was reached.", response.status_code, retryable=True))
        if response.status_code >= 500:
            raise TapsiShopConnectorError(self._categorized_error(ConnectorErrorCategory.UPSTREAM_UNAVAILABLE, "TapsiShop is unavailable.", response.status_code, retryable=True))
        if response.status_code >= 400:
            raise TapsiShopConnectorError(self._error("TapsiShop request failed.", response.status_code))
        if payload.get("success") is False:
            raise TapsiShopConnectorError(self._error("TapsiShop returned an unsuccessful response.", response.status_code))
        return payload

    def _validation_error(self, message: str) -> ConnectorError:
        return self._categorized_error(ConnectorErrorCategory.VALIDATION, message, None)

    def _error(self, message: str, http_status: int | None = None) -> ConnectorError:
        return ConnectorError(
            category=ConnectorErrorCategory.UNEXPECTED_RESPONSE,
            message=message,
            connector_type=self.connector_type,
            channel_id=self.channel_id,
            http_status=http_status,
            retry=RetryMetadata(retryable=False, safe_to_retry=False),
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


def _product_from_payload(channel_id: str, item: dict[str, Any]) -> ChannelProduct:
    return ChannelProduct(
        channel_id=channel_id,
        connector_type="tapsishop",
        identifiers=ChannelIdentifierSet(
            external_product_id=_string(item.get("id")),
            sku=_string(item.get("sku")),
            product_number=_string(item.get("hsin")),
        ),
        name=_string(item.get("sku") or item.get("id")) or "",
        current_price=_optional_float(item.get("finalPrice") or item.get("originalPrice")),
        currency="IRR",
        price_unit="rial",
        stock_quantity=_optional_float(item.get("onHandQuantity")),
        raw=item,
    )


def _update_to_payload(update: ChannelProductUpdate) -> dict[str, Any]:
    identifier = update.identifiers.sku or update.identifiers.external_product_id
    if not identifier:
        raise TapsiShopConnectorError(_standalone_validation_error(update.channel_id, "TapsiShop update requires sku or external product id."))
    if update.stock_quantity is None or update.price is None:
        raise TapsiShopConnectorError(_standalone_validation_error(update.channel_id, "TapsiShop update requires stock and price."))
    price = rial_amount(update.price, currency=update.currency, unit=update.price_unit)
    body = {
        "id": identifier,
        "stock": int(update.stock_quantity),
        "price": price,
        "referenceCode": update.idempotency_key or f"fh-{uuid4().hex}",
    }
    if update.discount_price is not None:
        body["specialPrice"] = rial_amount(update.discount_price, currency=update.currency, unit=update.price_unit)
    return body


def _update_result_from_payload(channel_id: str, item: dict[str, Any]) -> ChannelProductUpdateResult:
    success = bool(item.get("status"))
    error = None if success else ConnectorError(
        category=ConnectorErrorCategory.VALIDATION,
        message="; ".join(str(message) for message in item.get("messages") or []) or "TapsiShop rejected this product update.",
        connector_type="tapsishop",
        channel_id=channel_id,
        retry=RetryMetadata(retryable=False, safe_to_retry=False),
    )
    return ChannelProductUpdateResult(
        channel_id=channel_id,
        identifiers=ChannelIdentifierSet(external_product_id=_string(item.get("id")), sku=_string(item.get("sku"))),
        success=success,
        applied_capabilities=[ChannelCapability.PRODUCTS_WRITE_PRICE, ChannelCapability.PRODUCTS_WRITE_STOCK] if success else [],
        error=error,
        raw={
            "id": item.get("id"),
            "sku": item.get("sku"),
            "status": item.get("status"),
            "messages": item.get("messages"),
            "currentOriginalPrice": item.get("currentOriginalPrice"),
            "currentFinalPrice": item.get("currentFinalPrice"),
            "currentOnHandQuantity": item.get("currentOnHandQuantity"),
            "referenceCode": item.get("referenceCode"),
            **item,
        },
    )


def _order_summary_from_payload(channel_id: str, item: dict[str, Any]) -> ChannelOrder:
    return ChannelOrder(
        channel_id=channel_id,
        connector_type="tapsishop",
        identifiers=ChannelIdentifierSet(order_number=_string(item.get("orderNumber")), external_product_id=_string(item.get("id"))),
        status=_string(item.get("stateCode") or item.get("stateTitle")) or "UNKNOWN",
        created_at=_string(item.get("createdOn")),
        total=_optional_float(item.get("finalPrice")),
        currency="IRR",
        raw=item,
    )


def _order_detail_from_payload(channel_id: str, data: dict[str, Any]) -> ChannelOrder:
    order = data.get("order") if isinstance(data.get("order"), dict) else {}
    raw_items = data.get("items") if isinstance(data.get("items"), list) else []
    return ChannelOrder(
        channel_id=channel_id,
        connector_type="tapsishop",
        identifiers=ChannelIdentifierSet(order_number=_string(order.get("orderNumber"))),
        status=_string(order.get("status")) or "UNKNOWN",
        created_at=_string(order.get("orderDate")),
        items=[_order_item_from_payload(item) for item in raw_items if isinstance(item, dict)],
        total=_optional_float(order.get("amountAfterDiscount") or order.get("originalAmount")),
        currency="IRR",
        raw=data,
    )


def _order_item_from_payload(item: dict[str, Any]) -> ChannelOrderItem:
    return ChannelOrderItem(
        identifiers=ChannelIdentifierSet(sku=_string(item.get("sku"))),
        name=_string(item.get("name") or item.get("sku")) or "",
        quantity=1,
        unit_price=_optional_float(item.get("finalPrice") or item.get("price")),
        currency="IRR",
        raw=item,
    )


def rial_amount(amount: float, *, currency: str | None, unit: str | None) -> int:
    normalized_currency = (currency or "").strip().upper()
    normalized_unit = (unit or "").strip().lower()
    if normalized_currency != "IRR" and normalized_unit not in {"rial", "irr"}:
        raise TapsiShopConnectorError(_standalone_validation_error("tapsishop:main", "TapsiShop prices must be explicit rial/IRR values."))
    if int(amount) != amount:
        raise TapsiShopConnectorError(_standalone_validation_error("tapsishop:main", "TapsiShop prices must be integer rial values."))
    value = int(amount)
    if value < 10:
        raise TapsiShopConnectorError(_standalone_validation_error("tapsishop:main", "TapsiShop prices must be at least 10 rial."))
    if value % 10 != 0:
        raise TapsiShopConnectorError(_standalone_validation_error("tapsishop:main", "TapsiShop prices must be a multiple of 10 rial."))
    return value


def _expect_dict(value: Any, error: ConnectorError) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TapsiShopConnectorError(error)
    return value


def _standalone_validation_error(channel_id: str, message: str) -> ConnectorError:
    return ConnectorError(
        category=ConnectorErrorCategory.VALIDATION,
        message=message,
        connector_type="tapsishop",
        channel_id=channel_id,
        retry=RetryMetadata(retryable=False, safe_to_retry=False),
    )


def _header_value(headers: dict[str, str], name: str) -> str | None:
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return None


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _optional_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _blank_to_none(value: Any) -> str | None:
    return _string(value)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds") + "Z"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
