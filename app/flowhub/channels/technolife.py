"""Technolife seller API connector.

Implements the documented v1 products, price, inventory, visibility, and
seller-delivery order reads. Provider-specific authentication remains inside
this adapter while FlowHub consumes normalized channel contracts.
"""

from __future__ import annotations

import asyncio
import base64
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.connectors.common.current_state import (
    CurrentStateError,
    CurrentStateRecord,
    CurrentStateRequest,
    CurrentStateResult,
    CurrentStateStrategy,
    TransportRecorder,
    failed_current_state,
)
from app.flowhub.channels.contracts import (
    ChannelCapability,
    ChannelHealth,
    ChannelIdentifierSet,
    ChannelOrder,
    ChannelOrderItem,
    ChannelProduct,
    ChannelProductUpdate,
    ChannelProductUpdateResult,
    ConnectorError,
    ConnectorErrorCategory,
    CursorPagination,
    PageNumberPagination,
    PaginatedResult,
    RetryMetadata,
)
from app.flowhub.channels.marketplace import BaseMarketplaceConnector, UnsupportedCapabilityError

TECHNOLIFE_BASE_URL = "https://seller-api.technolife.com"
TECHNOLIFE_MAX_PAGE_SIZE = 100
_ALLOWED_HOSTS = frozenset({"seller-api.technolife.com"})


class TechnolifeConnectorError(Exception):
    def __init__(self, error: ConnectorError) -> None:
        self.error = error
        super().__init__(error.message)


@dataclass(frozen=True)
class TechnolifeConfig:
    api_key: str
    encryption_secret: str
    base_url: str = TECHNOLIFE_BASE_URL
    timeout_seconds: int = 30
    enabled: bool = True

    @classmethod
    def from_values(cls, *, settings: dict[str, Any], secrets: dict[str, Any]) -> TechnolifeConfig:
        api_key = str(secrets.get("api_key") or settings.get("api_key") or "").strip()
        encryption_secret = str(
            secrets.get("encryption_secret") or settings.get("encryption_secret") or ""
        ).strip()
        base_url = str(settings.get("base_url") or TECHNOLIFE_BASE_URL).strip().rstrip("/")
        timeout = _timeout_seconds(settings.get("request_timeout") or 30)
        if not api_key:
            raise ValueError("Technolife API key is required.")
        if not encryption_secret:
            raise ValueError("Technolife encryption secret is required.")
        _decode_encryption_key(encryption_secret)
        _validate_base_url(base_url)
        return cls(
            api_key=api_key,
            encryption_secret=encryption_secret,
            base_url=base_url,
            timeout_seconds=timeout,
            enabled=bool(settings.get("enabled", True)),
        )


class TechnolifeConnector(BaseMarketplaceConnector):
    def __init__(self, *, channel_id: str, config: TechnolifeConfig) -> None:
        super().__init__(
            connector_type="technolife",
            channel_id=channel_id,
            capabilities={
                ChannelCapability.PRODUCTS_READ,
                ChannelCapability.PRODUCTS_WRITE_PRICE,
                ChannelCapability.PRODUCTS_WRITE_STOCK,
                ChannelCapability.ORDERS_READ,
            },
        )
        self.config = config

    async def test_connection(self) -> ChannelHealth:
        started = _utcnow()
        try:
            await self._request(
                "GET", "/v1/products", params={"page": 1, "limit": 1}, safe_to_retry=True
            )
            elapsed = (_utcnow() - started).total_seconds() * 1000
            return ChannelHealth(
                status="healthy", checked_at=_iso(_utcnow()), latency_ms=round(elapsed, 2)
            )
        except TechnolifeConnectorError as exc:
            return ChannelHealth(status="unhealthy", checked_at=_iso(_utcnow()), error=exc.error)

    async def get_vendor_information(self):
        raise UnsupportedCapabilityError(
            ChannelCapability.PRODUCTS_READ, self.channel_id, self.connector_type
        )

    async def list_products(
        self,
        pagination: PageNumberPagination | CursorPagination | None = None,
    ) -> PaginatedResult:
        page = pagination.page if isinstance(pagination, PageNumberPagination) else 1
        requested_size = (
            pagination.page_size if isinstance(pagination, PageNumberPagination) else 20
        )
        page_size = min(max(int(requested_size), 1), TECHNOLIFE_MAX_PAGE_SIZE)
        payload = await self._request(
            "GET",
            "/v1/products",
            params={"page": page, "limit": page_size},
            safe_to_retry=True,
        )
        root = _payload_root(payload)
        products = root.get("products")
        if not isinstance(products, list):
            raise TechnolifeConnectorError(self._unexpected("Malformed Technolife product list."))

        valid_products = [
            product
            for product in products
            if isinstance(product, dict) and _string(product.get("code"))
        ]
        groups = await self._fetch_product_item_groups(valid_products)
        normalized = [item for group in groups for item in group]

        total = _optional_int(root.get("count"))
        total_pages = ((total + page_size - 1) // page_size) if total is not None else None
        has_more = bool(total_pages is not None and page < total_pages)
        return PaginatedResult(
            items=normalized,
            pagination=PageNumberPagination(
                page=page,
                page_size=page_size,
                total=total,
                total_pages=total_pages,
                has_more=has_more,
                next_page=page + 1 if has_more else None,
            ),
        )

    async def get_product(self, identifiers: dict[str, str]) -> ChannelProduct:
        product_code = (
            identifiers.get("product_number")
            or identifiers.get("parent_product_number")
            or identifiers.get("productCode")
        )
        seller_item_code = (
            identifiers.get("external_product_id")
            or identifiers.get("sellerItemCode")
            or identifiers.get("id")
        )
        if not product_code or not seller_item_code:
            raise TechnolifeConnectorError(
                self._validation(
                    "Technolife product lookup requires productCode and sellerItemCode."
                )
            )
        product_payload = await self._request(
            "GET", "/v1/products", params={"search": product_code, "limit": 100}, safe_to_retry=True
        )
        products = _payload_root(product_payload).get("products")
        product = next(
            (
                item
                for item in products or []
                if isinstance(item, dict) and _string(item.get("code")) == product_code
            ),
            None,
        )
        if product is None:
            raise TechnolifeConnectorError(self._not_found("Technolife product was not found."))
        items_payload = await self._request(
            "GET", f"/v1/products/{product_code}/items", safe_to_retry=True
        )
        items = _payload_root(items_payload).get("data")
        item = next(
            (
                value
                for value in items or []
                if isinstance(value, dict) and _string(value.get("code")) == seller_item_code
            ),
            None,
        )
        if item is None:
            raise TechnolifeConnectorError(self._not_found("Technolife seller item was not found."))
        return _product_from_payload(self.channel_id, product, item)

    async def fetch_current_state(
        self, request: CurrentStateRequest
    ) -> CurrentStateResult:
        if request.channel_id != self.channel_id:
            return failed_current_state(
                request,
                strategy=CurrentStateStrategy.GROUPED_COLLECTION,
                category="validation",
                message="Current-state request channel does not match Technolife.",
            )
        recorder = TransportRecorder(
            strategy=CurrentStateStrategy.GROUPED_COLLECTION,
            purpose=request.purpose,
            entities_requested=len(request.entities),
        )
        records: dict[str, CurrentStateRecord] = {}
        errors: dict[str, CurrentStateError] = {}
        pending_by_parent: dict[str, list] = {}
        for entity in request.entities:
            parent_id = str(entity.parent_external_id or "").strip()
            if not parent_id:
                errors[entity.key] = CurrentStateError(
                    key=entity.key,
                    category="validation",
                    message="Technolife current-state lookup requires productCode.",
                )
                continue
            pending_by_parent.setdefault(parent_id, []).append(entity)

        # The mapped productCode is already the exact collection scope required
        # by Technolife's seller-item endpoint. Avoid scanning /v1/products.
        found_products = [{"code": code} for code in pending_by_parent]
        item_groups = await self._fetch_product_item_groups(
            found_products,
            transport=recorder,
            return_exceptions=True,
        )
        for product, group in zip(found_products, item_groups, strict=True):
            product_code = _string(product.get("code"))
            entities = pending_by_parent.get(product_code, [])
            if isinstance(group, Exception):
                for entity in entities:
                    errors[entity.key] = (
                        _technolife_state_error(entity.key, group)
                        if isinstance(group, TechnolifeConnectorError)
                        else CurrentStateError(
                            key=entity.key,
                            category="unexpected_response",
                            message="Technolife seller-item retrieval failed.",
                        )
                    )
                continue
            by_external_id = {
                str(item.identifiers.external_product_id or ""): item for item in group
            }
            for entity in entities:
                product_state = by_external_id.get(entity.external_id)
                if product_state is None:
                    errors[entity.key] = CurrentStateError(
                        key=entity.key,
                        category="not_found",
                        message="Technolife seller item was not found.",
                    )
                else:
                    records[entity.key] = _current_state_record(entity.key, product_state)

        return CurrentStateResult(
            records=records,
            errors=errors,
            transport=recorder.finish(entities_returned=len(records)),
        )

    async def _fetch_product_item_groups(
        self,
        products: list[dict[str, Any]],
        *,
        transport: TransportRecorder | None = None,
        return_exceptions: bool = False,
    ) -> list:
        semaphore = asyncio.Semaphore(8)

        async def fetch(product: dict[str, Any]) -> list[ChannelProduct]:
            product_code = _string(product.get("code"))
            async with semaphore:
                if transport is not None:
                    transport.record_batch()
                items_payload = await self._request(
                    "GET",
                    f"/v1/products/{product_code}/items",
                    safe_to_retry=True,
                    transport=transport,
                    stage="seller_item_collection",
                )
            seller_items = _payload_root(items_payload).get("data")
            if not isinstance(seller_items, list):
                raise TechnolifeConnectorError(
                    self._unexpected("Malformed Technolife seller item list.")
                )
            return [
                _product_from_payload(self.channel_id, product, item)
                for item in seller_items
                if isinstance(item, dict) and _string(item.get("code"))
            ]

        return list(
            await asyncio.gather(
                *(fetch(product) for product in products),
                return_exceptions=return_exceptions,
            )
        )

    async def update_products(
        self, updates: list[ChannelProductUpdate]
    ) -> list[ChannelProductUpdateResult]:
        results: list[ChannelProductUpdateResult] = []
        for update in updates:
            seller_item_code = update.identifiers.external_product_id
            if not seller_item_code:
                raise TechnolifeConnectorError(
                    self._validation("Technolife sellerItemCode is required.")
                )
            raw: dict[str, Any] = {}
            applied: list[ChannelCapability] = []
            try:
                if update.price is not None:
                    price = _rial_amount(
                        update.price, currency=update.currency, unit=update.price_unit
                    )
                    raw["price"] = await self._request(
                        "PATCH",
                        f"/v1/pricing/{seller_item_code}/info",
                        json={"cash": {"price": price}},
                        safe_to_retry=False,
                    )
                    applied.append(ChannelCapability.PRODUCTS_WRITE_PRICE)
                if update.stock_quantity is not None:
                    stock = _stock_amount(update.stock_quantity)
                    raw["stock"] = await self._request(
                        "PATCH",
                        f"/v1/products/{seller_item_code}/info",
                        json={"available": stock},
                        safe_to_retry=False,
                    )
                    applied.append(ChannelCapability.PRODUCTS_WRITE_STOCK)
                if not applied:
                    raise TechnolifeConnectorError(
                        self._validation("Technolife update requires price or stock.")
                    )
                results.append(
                    ChannelProductUpdateResult(
                        channel_id=self.channel_id,
                        identifiers=update.identifiers,
                        success=True,
                        applied_capabilities=applied,
                        raw=raw,
                    )
                )
            except TechnolifeConnectorError as exc:
                results.append(
                    ChannelProductUpdateResult(
                        channel_id=self.channel_id,
                        identifiers=update.identifiers,
                        success=False,
                        applied_capabilities=applied,
                        error=exc.error,
                        raw=raw,
                    )
                )
        return results

    async def set_product_visibility(self, seller_item_code: str, *, visible: bool) -> dict:
        action = "show" if visible else "hide"
        return await self._request(
            "PATCH", f"/v1/products/{seller_item_code}/{action}", safe_to_retry=False
        )

    async def list_orders(
        self,
        pagination: PageNumberPagination | CursorPagination | None = None,
    ) -> PaginatedResult:
        page = pagination.page if isinstance(pagination, PageNumberPagination) else 1
        requested_size = (
            pagination.page_size if isinstance(pagination, PageNumberPagination) else 20
        )
        page_size = min(max(int(requested_size), 1), TECHNOLIFE_MAX_PAGE_SIZE)
        payload = await self._request(
            "GET",
            "/v1/orders/sbs",
            params={"page": page, "limit": page_size},
            safe_to_retry=True,
        )
        root = _payload_root(payload)
        items = root.get("data")
        if not isinstance(items, list):
            raise TechnolifeConnectorError(self._unexpected("Malformed Technolife order list."))
        total = _optional_int(root.get("count"))
        total_pages = ((total + page_size - 1) // page_size) if total is not None else None
        has_more = bool(total_pages is not None and page < total_pages)
        return PaginatedResult(
            items=[
                _order_from_payload(self.channel_id, item)
                for item in items
                if isinstance(item, dict)
            ],
            pagination=PageNumberPagination(
                page=page,
                page_size=page_size,
                total=total,
                total_pages=total_pages,
                has_more=has_more,
                next_page=page + 1 if has_more else None,
            ),
        )

    async def get_order(self, identifiers: dict[str, str]) -> ChannelOrder:
        order_code = identifiers.get("orderCode") or identifiers.get("order_number")
        if not order_code:
            raise TechnolifeConnectorError(self._validation("Technolife orderCode is required."))
        payload = await self._request("GET", f"/v1/orders/sbs/{order_code}", safe_to_retry=True)
        return _order_detail_from_payload(self.channel_id, _payload_root(payload))

    async def list_order_events(self, pagination=None) -> PaginatedResult:
        del pagination
        raise UnsupportedCapabilityError(
            ChannelCapability.ORDERS_EVENTS_POLL, self.channel_id, self.connector_type
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        safe_to_retry: bool,
        transport: TransportRecorder | None = None,
        stage: str = "provider_request",
    ) -> dict[str, Any]:
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
            "encrypted-secret": encrypt_endpoint(self.config.encryption_secret, path),
        }
        started = time.perf_counter()
        failed = False
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.timeout_seconds)
            ) as client:
                response = await client.request(
                    method,
                    f"{self.config.base_url}{path}",
                    headers=headers,
                    params=params,
                    json=json,
                )
            return self._decode_response(response, safe_to_retry=safe_to_retry)
        except httpx.TimeoutException as exc:
            failed = True
            raise TechnolifeConnectorError(
                self._categorized(
                    ConnectorErrorCategory.TIMEOUT,
                    "Technolife request timed out.",
                    retryable=safe_to_retry,
                )
            ) from exc
        except httpx.HTTPError as exc:
            failed = True
            raise TechnolifeConnectorError(
                self._categorized(
                    ConnectorErrorCategory.UPSTREAM_UNAVAILABLE,
                    "Technolife request failed.",
                    retryable=safe_to_retry,
                )
            ) from exc
        except Exception:
            failed = True
            raise
        finally:
            if transport is not None:
                transport.record_request(
                    stage=stage,
                    duration_ms=(time.perf_counter() - started) * 1000,
                    failed=failed,
                )

    def _decode_response(self, response: httpx.Response, *, safe_to_retry: bool) -> dict[str, Any]:
        categories = {
            400: ConnectorErrorCategory.VALIDATION,
            401: ConnectorErrorCategory.AUTHENTICATION,
            403: ConnectorErrorCategory.AUTHORIZATION,
            404: ConnectorErrorCategory.NOT_FOUND,
            409: ConnectorErrorCategory.CONFLICT,
            422: ConnectorErrorCategory.VALIDATION,
            429: ConnectorErrorCategory.RATE_LIMIT,
        }
        if response.status_code >= 400:
            category = categories.get(
                response.status_code,
                ConnectorErrorCategory.UPSTREAM_UNAVAILABLE
                if response.status_code >= 500
                else ConnectorErrorCategory.UNEXPECTED_RESPONSE,
            )
            retryable = safe_to_retry and (
                category
                in {
                    ConnectorErrorCategory.RATE_LIMIT,
                    ConnectorErrorCategory.UPSTREAM_UNAVAILABLE,
                }
            )
            raise TechnolifeConnectorError(
                self._categorized(
                    category,
                    "Technolife rejected the request."
                    if response.status_code < 500
                    else "Technolife is unavailable.",
                    http_status=response.status_code,
                    retryable=retryable,
                )
            )
        if response.status_code == 204 or not response.content:
            return {}
        try:
            payload = response.json()
        except ValueError as exc:
            raise TechnolifeConnectorError(
                self._unexpected("Technolife returned malformed JSON.", response.status_code)
            ) from exc
        if not isinstance(payload, dict):
            raise TechnolifeConnectorError(
                self._unexpected("Technolife returned a malformed response.", response.status_code)
            )
        return payload

    def _validation(self, message: str) -> ConnectorError:
        return self._categorized(ConnectorErrorCategory.VALIDATION, message)

    def _not_found(self, message: str) -> ConnectorError:
        return self._categorized(ConnectorErrorCategory.NOT_FOUND, message, http_status=404)

    def _unexpected(self, message: str, http_status: int | None = None) -> ConnectorError:
        return self._categorized(
            ConnectorErrorCategory.UNEXPECTED_RESPONSE, message, http_status=http_status
        )

    def _categorized(
        self,
        category: ConnectorErrorCategory,
        message: str,
        *,
        http_status: int | None = None,
        retryable: bool = False,
    ) -> ConnectorError:
        return ConnectorError(
            category=category,
            message=message,
            connector_type=self.connector_type,
            channel_id=self.channel_id,
            http_status=http_status,
            retry=RetryMetadata(
                retryable=retryable,
                safe_to_retry=retryable,
            ),
        )


def encrypt_endpoint(secret_base64: str, endpoint: str, *, iv: bytes | None = None) -> str:
    """Create the documented iv:tag:ciphertext AES-128-GCM header value."""

    key = _decode_encryption_key(secret_base64)
    nonce = iv or os.urandom(12)
    if len(nonce) != 12:
        raise ValueError("Technolife AES-GCM IV must be 12 bytes.")
    encrypted = AESGCM(key).encrypt(nonce, endpoint.encode("utf-8"), None)
    ciphertext, tag = encrypted[:-16], encrypted[-16:]
    return ":".join(base64.b64encode(part).decode("ascii") for part in (nonce, tag, ciphertext))


def _decode_encryption_key(value: str) -> bytes:
    try:
        key = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("Technolife encryption secret must be valid Base64.") from exc
    if len(key) != 16:
        raise ValueError("Technolife encryption secret must decode to 16 bytes.")
    return key


def _validate_base_url(value: str) -> None:
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in _ALLOWED_HOSTS
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise ValueError("Technolife Base URL must use the official HTTPS seller API.")


def _payload_root(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    if isinstance(data, dict) and not any(
        key in payload for key in ("products", "count", "orderCode")
    ):
        return data
    return payload


def _product_from_payload(
    channel_id: str, product: dict[str, Any], item: dict[str, Any]
) -> ChannelProduct:
    product_code = _string(product.get("code"))
    seller_item_code = _string(item.get("code"))
    cash = item.get("cash") if isinstance(item.get("cash"), dict) else {}
    name_parts = [
        _string(product.get("title")),
        _string(item.get("variation")),
        _string(item.get("guarantee")),
    ]
    return ChannelProduct(
        channel_id=channel_id,
        connector_type="technolife",
        identifiers=ChannelIdentifierSet(
            external_product_id=seller_item_code,
            sku=_string(item.get("SalesCode")),
            product_number=product_code,
            parent_product_number=product_code,
        ),
        name=" - ".join(part for part in name_parts if part)
        or seller_item_code
        or "Technolife item",
        current_price=_optional_float(cash.get("price")),
        currency="IRR",
        price_unit="RIAL",
        stock_quantity=_optional_float(item.get("available")),
        status="hidden" if bool(item.get("hide")) else "active",
        raw={"product": product, "sellerItem": item},
    )


def _current_state_record(key: str, product: ChannelProduct) -> CurrentStateRecord:
    return CurrentStateRecord(
        key=key,
        provider=product.connector_type,
        external_id=str(product.identifiers.external_product_id or ""),
        parent_external_id=product.identifiers.parent_product_number,
        price=product.current_price,
        stock=product.stock_quantity,
        status=product.status,
        currency=product.currency,
        unit=product.price_unit,
        raw=product.raw,
    )


def _technolife_state_error(
    key: str, exc: TechnolifeConnectorError
) -> CurrentStateError:
    return CurrentStateError(
        key=key,
        category=exc.error.category.value,
        message=exc.error.message,
        retry_eligible=exc.error.retry.retryable,
    )


def _order_from_payload(channel_id: str, item: dict[str, Any]) -> ChannelOrder:
    code = _string(item.get("code")) or ""
    return ChannelOrder(
        channel_id=channel_id,
        connector_type="technolife",
        identifiers=ChannelIdentifierSet(order_number=code),
        status=_string(item.get("status")) or "unknown",
        created_at=_string(item.get("orderDate")),
        total=_optional_float(item.get("totalPrice")),
        currency="IRR",
        raw=item,
    )


def _order_detail_from_payload(channel_id: str, item: dict[str, Any]) -> ChannelOrder:
    products = item.get("products") if isinstance(item.get("products"), list) else []
    order_items = [
        ChannelOrderItem(
            identifiers=ChannelIdentifierSet(
                external_product_id=_string(product.get("sellerItemCode")),
                product_number=_string(product.get("productCode")),
            ),
            name=_string(product.get("title"))
            or _string(product.get("sellerItemCode"))
            or "Technolife item",
            quantity=_optional_float(product.get("count")) or 0,
            unit_price=_optional_float(product.get("discountedPrice") or product.get("price")),
            currency="IRR",
            raw=product,
        )
        for product in products
        if isinstance(product, dict)
    ]
    order = _order_from_payload(
        channel_id,
        {
            "code": item.get("orderCode"),
            "status": item.get("status") or "unknown",
            "orderDate": item.get("orderDate"),
            "totalPrice": sum((entry.unit_price or 0) * entry.quantity for entry in order_items),
            **item,
        },
    )
    return order.model_copy(update={"items": order_items})


def _rial_amount(amount: float, *, currency: str | None, unit: str | None) -> int:
    if str(currency or "").upper() != "IRR" or str(unit or "").upper() not in {
        "IRR",
        "RIAL",
    }:
        raise TechnolifeConnectorError(
            _standalone_error("Technolife prices require IRR currency and RIAL unit.")
        )
    value = float(amount)
    if value < 0 or not value.is_integer():
        raise TechnolifeConnectorError(
            _standalone_error("Technolife price must be a non-negative integer in RIAL.")
        )
    return int(value)


def _stock_amount(amount: float) -> int:
    value = float(amount)
    if value < 0 or not value.is_integer():
        raise TechnolifeConnectorError(
            _standalone_error("Technolife stock must be a non-negative integer.")
        )
    return int(value)


def _standalone_error(message: str) -> ConnectorError:
    return ConnectorError(
        category=ConnectorErrorCategory.VALIDATION,
        message=message,
        connector_type="technolife",
        channel_id="technolife:main",
        retry=RetryMetadata(retryable=False, safe_to_retry=False),
    )


def _timeout_seconds(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("Technolife request timeout must be an integer.")
    try:
        timeout = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Technolife request timeout must be an integer.") from exc
    if not timeout.is_integer() or timeout < 1 or timeout > 120:
        raise ValueError("Technolife request timeout must be between 1 and 120 seconds.")
    return int(timeout)


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
    text = str(value).strip() if value is not None else ""
    return text or None


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds") + "Z"
