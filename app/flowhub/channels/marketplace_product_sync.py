"""Provider-independent atomic product-cache synchronization."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from typing import Any, Callable, Protocol

from sqlalchemy.orm import Session

from app.flowhub.channels.contracts import (
    ChannelProduct,
    ConnectorErrorCategory,
    PageNumberPagination,
    PaginatedResult,
)
from app.flowhub.data_layer.models import DlInventoryCache, DlProductCache, DlRefreshJob
from app.flowhub.data_layer.job_lifecycle import RefreshJobLifecycle
from app.flowhub.integration_platform.models import IntegrationConnectorEvent

_RETRYABLE_READ_ERRORS = frozenset(
    {
        ConnectorErrorCategory.RATE_LIMIT,
        ConnectorErrorCategory.TIMEOUT,
        ConnectorErrorCategory.UPSTREAM_UNAVAILABLE,
    }
)


class PaginatedProductConnector(Protocol):
    channel_id: str
    connector_type: str

    async def list_products(
        self,
        pagination: PageNumberPagination,
    ) -> PaginatedResult: ...


class MarketplaceProductFetchError(Exception):
    def __init__(
        self,
        cause: Exception,
        *,
        pages_read: int,
        products_received: int,
        products_skipped: int,
    ) -> None:
        self.cause = cause
        self.pages_read = pages_read
        self.products_received = products_received
        self.products_skipped = products_skipped
        super().__init__(str(cause))


@dataclass(frozen=True)
class MarketplaceProductSyncResult:
    pages_read: int
    products_received: int
    products_stored: int
    products_skipped: int
    failures: list[str]
    started_at: datetime
    completed_at: datetime

    @property
    def duration_ms(self) -> float:
        return round((self.completed_at - self.started_at).total_seconds() * 1000, 2)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": not self.failures,
            "status": "completed" if not self.failures else "failed",
            "pages_read": self.pages_read,
            "products_received": self.products_received,
            "products_stored": self.products_stored,
            "products_skipped": self.products_skipped,
            "failures": list(self.failures),
            "duration_ms": self.duration_ms,
            "started_at": _iso(self.started_at),
            "completed_at": _iso(self.completed_at),
            "read_only": True,
            "external_write": False,
            "stock_write": False,
            "source_write": False,
            "dry_run_created": False,
            "approval_created": False,
            "apply_executed": False,
            "credentials_returned": False,
        }


class MarketplaceProductSyncService:
    """Read every provider page, then replace only that channel's local cache."""

    def __init__(self, db: Session) -> None:
        self.db = db

    async def run(
        self,
        connector: PaginatedProductConnector,
        *,
        actor: str,
        page_size: int,
        max_pages: int,
        retry_attempts: int = 2,
        page_delay_seconds: float = 1.0,
        rate_limit_backoff_seconds: float = 30.0,
        job_type: str = "manual",
    ) -> MarketplaceProductSyncResult:
        if page_size < 1 or max_pages < 1:
            raise ValueError("Marketplace product synchronization limits must be positive.")
        if retry_attempts < 0 or page_delay_seconds < 0 or rate_limit_backoff_seconds <= 0:
            raise ValueError("Marketplace product synchronization retry settings are invalid.")

        started = _utcnow()
        provider = connector.connector_type
        job = DlRefreshJob(
            job_type=job_type,
            entity_type="products",
            connector_id=connector.channel_id,
            status="pending",
            triggered_by=actor,
            started_at=started,
            created_at=started,
            meta={"provider": provider, "automatic_sync": job_type == "scheduled"},
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        lifecycle = RefreshJobLifecycle(self.db)
        lifecycle.start(job)
        started_clock = monotonic()

        try:
            products, pages_read, received, skipped = await self._fetch_all(
                connector,
                page_size=page_size,
                max_pages=max_pages,
                retry_attempts=retry_attempts,
                page_delay_seconds=page_delay_seconds,
                rate_limit_backoff_seconds=rate_limit_backoff_seconds,
                on_page_progress=lambda: lifecycle.heartbeat(job),
            )
            completed = _utcnow()
            product_rows = [
                self._product_row(connector, product, completed) for product in products
            ]
            inventory_rows = [
                self._inventory_row(connector, product, completed) for product in products
            ]

            self.db.rollback()
            with self.db.begin():
                from app.flowhub.unified_workspace.listing_guard import (
                    acquire_channel_listing_guards,
                )

                acquire_channel_listing_guards(self.db, connector.channel_id)
                self.db.query(DlProductCache).filter_by(
                    connector_id=connector.channel_id
                ).delete(synchronize_session=False)
                self.db.query(DlInventoryCache).filter_by(
                    connector_id=connector.channel_id
                ).delete(synchronize_session=False)
                self.db.add_all(product_rows)
                self.db.add_all(inventory_rows)
                durable_job = self.db.get(DlRefreshJob, job.id)
                if durable_job is None:
                    raise RuntimeError("Marketplace refresh job disappeared before cache commit.")
                lifecycle.finish(durable_job, now=completed, commit=False)
                durable_job.duration_ms = round((monotonic() - started_clock) * 1000, 2)
                durable_job.meta = {
                    "provider": provider,
                    "pages_read": pages_read,
                    "products_received": received,
                    "products_stored": len(product_rows),
                    "products_skipped": skipped,
                    "error_category": None,
                }
                self.db.add(
                    IntegrationConnectorEvent(
                        connector_id=connector.channel_id,
                        event_name="product_cache_refresh_completed",
                        message="Marketplace product cache refresh completed.",
                        metadata_json={
                            "provider": provider,
                            "actor": actor,
                            "pages_read": pages_read,
                            "products_received": received,
                            "products_stored": len(product_rows),
                            "products_skipped": skipped,
                            "external_write": False,
                        },
                    )
                )
            return MarketplaceProductSyncResult(
                pages_read=pages_read,
                products_received=received,
                products_stored=len(product_rows),
                products_skipped=skipped,
                failures=[],
                started_at=started,
                completed_at=completed,
            )
        except Exception as exc:
            self.db.rollback()
            completed = _utcnow()
            fetch_error = exc if isinstance(exc, MarketplaceProductFetchError) else None
            category, message = _safe_error(fetch_error.cause if fetch_error else exc)
            pages_read = fetch_error.pages_read if fetch_error else 0
            received = fetch_error.products_received if fetch_error else 0
            skipped = fetch_error.products_skipped if fetch_error else 0
            failed_job = self.db.get(DlRefreshJob, job.id)
            if failed_job is not None:
                lifecycle.finish(failed_job, status="failed", now=completed, commit=False)
                failed_job.failed_at = completed
                failed_job.duration_ms = round((monotonic() - started_clock) * 1000, 2)
                failed_job.error_message = message
                failed_job.meta = {
                    **(failed_job.meta or {}),
                    "pages_read": pages_read,
                    "products_received": received,
                    "products_stored": 0,
                    "products_skipped": skipped,
                    "error_category": category,
                }
            self.db.add(
                IntegrationConnectorEvent(
                    connector_id=connector.channel_id,
                    event_name="product_cache_refresh_failed",
                    severity="error",
                    message="Marketplace product cache refresh failed.",
                    metadata_json={
                        "provider": provider,
                        "actor": actor,
                        "error_category": category,
                        "external_write": False,
                    },
                )
            )
            self.db.commit()
            return MarketplaceProductSyncResult(
                pages_read=pages_read,
                products_received=received,
                products_stored=0,
                products_skipped=skipped,
                failures=[message],
                started_at=started,
                completed_at=completed,
            )

    async def _fetch_all(
        self,
        connector: PaginatedProductConnector,
        *,
        page_size: int,
        max_pages: int,
        retry_attempts: int,
        page_delay_seconds: float,
        rate_limit_backoff_seconds: float,
        on_page_progress: Callable[[], None] | None = None,
    ) -> tuple[list[ChannelProduct], int, int, int]:
        page_number = 1
        pages_read = 0
        received = 0
        skipped = 0
        products: list[ChannelProduct] = []
        identifiers: set[str] = set()
        visited_pages: set[int] = set()

        while True:
            if page_number in visited_pages:
                raise ValueError("Marketplace product pagination repeated a page.")
            if pages_read >= max_pages:
                raise ValueError(
                    "Marketplace product synchronization exceeded the configured page limit."
                )
            visited_pages.add(page_number)
            try:
                page = await self._read_page(
                    connector,
                    page_number=page_number,
                    page_size=page_size,
                    retry_attempts=retry_attempts,
                    rate_limit_backoff_seconds=rate_limit_backoff_seconds,
                )
            except Exception as exc:
                raise MarketplaceProductFetchError(
                    exc,
                    pages_read=pages_read,
                    products_received=received,
                    products_skipped=skipped,
                ) from exc
            pages_read += 1
            received += len(page.items)
            for item in page.items:
                if not isinstance(item, ChannelProduct):
                    skipped += 1
                    continue
                product_id = item.identifiers.external_product_id
                if not product_id:
                    skipped += 1
                    continue
                if product_id in identifiers:
                    raise ValueError(
                        "Marketplace returned a duplicate external product identifier."
                    )
                identifiers.add(product_id)
                products.append(item)

            if on_page_progress is not None:
                on_page_progress()

            pagination = page.pagination
            if not isinstance(pagination, PageNumberPagination) or not pagination.has_more:
                break
            page_number = pagination.next_page or (page_number + 1)
            if page_delay_seconds:
                await asyncio.sleep(page_delay_seconds)

        return products, pages_read, received, skipped

    async def _read_page(
        self,
        connector: PaginatedProductConnector,
        *,
        page_number: int,
        page_size: int,
        retry_attempts: int,
        rate_limit_backoff_seconds: float,
    ) -> PaginatedResult:
        for attempt in range(retry_attempts + 1):
            try:
                return await connector.list_products(
                    PageNumberPagination(page=page_number, page_size=page_size)
                )
            except Exception as exc:
                error = getattr(exc, "error", None)
                category = getattr(error, "category", None)
                if category not in _RETRYABLE_READ_ERRORS or attempt >= retry_attempts:
                    raise
                retry = getattr(error, "retry", None)
                retry_after = getattr(retry, "retry_after_seconds", None)
                delay = (
                    retry_after
                    or (
                        rate_limit_backoff_seconds
                        if category == ConnectorErrorCategory.RATE_LIMIT
                        else float(attempt + 1)
                    )
                )
                await asyncio.sleep(min(max(float(delay), 0.0), 60.0))
        raise RuntimeError("Marketplace product read retry loop ended unexpectedly.")

    def _product_row(
        self,
        connector: PaginatedProductConnector,
        product: ChannelProduct,
        synchronized_at: datetime,
    ) -> DlProductCache:
        product_id = str(product.identifiers.external_product_id)
        stock = _optional_int(product.stock_quantity)
        normalized_raw = {
            **dict(product.raw),
            "external_product_id": product_id,
            "sku": product.identifiers.sku,
            "product_number": product.identifiers.product_number,
            "parent_product_number": product.identifiers.parent_product_number,
            "currency": product.currency,
            "price_unit": product.price_unit,
            "source_channel": connector.channel_id,
            "synchronized_at": _iso(synchronized_at),
        }
        price = _number_text(product.current_price)
        return DlProductCache(
            connector_id=connector.channel_id,
            product_id=product_id,
            external_id=_optional_int(product_id),
            sku=product.identifiers.sku,
            name=product.name or product.identifiers.sku or product_id,
            product_type=(
                "variation" if product.identifiers.parent_product_number else "simple"
            ),
            parent_id=product.identifiers.parent_product_number,
            status=product.status or "active",
            price=price,
            last_price=price,
            regular_price=price,
            sale_price=None,
            stock_qty=stock,
            stock_status="instock" if (stock or 0) > 0 else "outofstock",
            manage_stock=True,
            backorders_allowed=False,
            categories=[],
            images=[],
            channel_id=connector.channel_id,
            freshness="fresh",
            last_fetched_at=synchronized_at,
            last_successful_read=synchronized_at,
            exists=True,
            record_hash=hashlib.sha256(
                json.dumps(
                    normalized_raw,
                    sort_keys=True,
                    ensure_ascii=False,
                    default=str,
                ).encode("utf-8")
            ).hexdigest(),
            raw_data=normalized_raw,
        )

    def _inventory_row(
        self,
        connector: PaginatedProductConnector,
        product: ChannelProduct,
        synchronized_at: datetime,
    ) -> DlInventoryCache:
        stock = _optional_int(product.stock_quantity)
        return DlInventoryCache(
            connector_id=connector.channel_id,
            product_id=str(product.identifiers.external_product_id),
            stock_qty=stock,
            stock_status="instock" if (stock or 0) > 0 else "outofstock",
            manage_stock=True,
            backorders="no",
            channel_id=connector.channel_id,
            last_fetched_at=synchronized_at,
        )


def _safe_error(exc: Exception) -> tuple[str, str]:
    error = getattr(exc, "error", None)
    category = getattr(error, "category", None)
    message = getattr(error, "message", None)
    if category is not None and message:
        return str(getattr(category, "value", category)), str(message)
    if isinstance(exc, ValueError):
        return "validation", str(exc)
    return "unexpected_response", "Marketplace product synchronization failed unexpectedly."


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _number_text(value: Any) -> str | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(parsed)) if parsed.is_integer() else format(parsed, "f").rstrip("0").rstrip(".")


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds") + "Z"


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
