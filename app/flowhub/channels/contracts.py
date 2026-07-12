"""Normalized marketplace/channel connector contracts.

The DTOs in this module are internal FlowHub contracts. They preserve
channel-native identifiers separately from Data Layer canonical IDs so future
marketplace connectors do not become the product source of truth.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ChannelCapability(str, Enum):
    PRODUCTS_READ = "products.read"
    PRODUCTS_WRITE_PRICE = "products.write_price"
    PRODUCTS_WRITE_STOCK = "products.write_stock"
    PRODUCTS_WRITE_DISCOUNT = "products.write_discount"
    PRODUCTS_WRITE_CAPACITY = "products.write_capacity"
    ORDERS_READ = "orders.read"
    ORDERS_EVENTS_POLL = "orders.events.poll"
    ORDERS_WEBHOOK_RECEIVE = "orders.webhook.receive"
    CREDENTIALS_REFRESH = "credentials.refresh"
    COURIER_READ = "courier.read"
    COURIER_REVIEW = "courier.review"


class ConnectorErrorCategory(str, Enum):
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    VALIDATION = "validation"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    UNEXPECTED_RESPONSE = "unexpected_response"


class ChannelIdentifierSet(BaseModel):
    canonical_product_id: str | None = None
    external_product_id: str | None = None
    sku: str | None = None
    product_number: str | None = None
    parent_product_number: str | None = None
    order_number: str | None = None
    channel_reference_code: str | None = None


class RetryMetadata(BaseModel):
    retryable: bool = False
    retry_after_seconds: float | None = None
    attempt: int = 0
    max_attempts: int = 0
    safe_to_retry: bool = False


class ConnectorError(BaseModel):
    category: ConnectorErrorCategory
    message: str
    connector_type: str
    channel_id: str
    http_status: int | None = None
    provider_code: str | None = None
    retry: RetryMetadata = Field(default_factory=RetryMetadata)


class ChannelHealth(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy", "disabled"]
    checked_at: str | None = None
    latency_ms: float | None = None
    error: ConnectorError | None = None


class ChannelVendor(BaseModel):
    channel_id: str
    connector_type: str
    name: str
    vendor_id: str | None = None
    display_url: str | None = None
    identifiers: ChannelIdentifierSet = Field(default_factory=ChannelIdentifierSet)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChannelProduct(BaseModel):
    channel_id: str
    connector_type: str
    identifiers: ChannelIdentifierSet
    name: str
    current_price: float | None = None
    currency: str | None = None
    price_unit: str | None = None
    stock_quantity: float | None = None
    status: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class ChannelProductUpdate(BaseModel):
    channel_id: str
    identifiers: ChannelIdentifierSet
    price: float | None = None
    stock_quantity: float | None = None
    discount_price: float | None = None
    capacity: int | None = None
    currency: str | None = None
    price_unit: str | None = None
    special_price_start_at: str | None = None
    special_price_end_at: str | None = None
    special_price_stock: int | None = None
    idempotency_key: str | None = None


class ChannelProductUpdateResult(BaseModel):
    channel_id: str
    identifiers: ChannelIdentifierSet
    success: bool
    applied_capabilities: list[ChannelCapability] = Field(default_factory=list)
    error: ConnectorError | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class ChannelOrderItem(BaseModel):
    identifiers: ChannelIdentifierSet
    name: str
    quantity: float
    unit_price: float | None = None
    currency: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class ChannelOrder(BaseModel):
    channel_id: str
    connector_type: str
    identifiers: ChannelIdentifierSet
    status: str
    created_at: str | None = None
    updated_at: str | None = None
    items: list[ChannelOrderItem] = Field(default_factory=list)
    total: float | None = None
    currency: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class ChannelOrderEvent(BaseModel):
    channel_id: str
    connector_type: str
    event_id: str
    event_type: str
    occurred_at: str | None = None
    order_identifiers: ChannelIdentifierSet = Field(default_factory=ChannelIdentifierSet)
    raw: dict[str, Any] = Field(default_factory=dict)


class PageNumberPagination(BaseModel):
    kind: Literal["page"] = "page"
    page: int = 1
    page_size: int = 50
    total: int | None = None
    total_pages: int | None = None
    has_more: bool = False
    next_page: int | None = None


class CursorPagination(BaseModel):
    kind: Literal["cursor"] = "cursor"
    cursor: str | None = None
    next_cursor: str | None = None
    limit: int = 50
    has_more: bool = False


Pagination = PageNumberPagination | CursorPagination


class PaginatedResult(BaseModel):
    items: list[Any] = Field(default_factory=list)
    pagination: Pagination


class ChannelTimeouts(BaseModel):
    connect_seconds: float = 10.0
    read_seconds: float = 30.0
    write_seconds: float = 10.0
    page_seconds: float = 45.0


class ChannelConnectorConfig(BaseModel):
    channel_id: str
    connector_type: str
    settings: dict[str, Any] = Field(default_factory=dict)
    secrets_configured: dict[str, bool] = Field(default_factory=dict)
    timeouts: ChannelTimeouts = Field(default_factory=ChannelTimeouts)
    default_page_size: int = 50
    max_page_size: int = 200
