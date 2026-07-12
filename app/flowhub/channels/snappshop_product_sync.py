"""Atomic SnappShop product-cache synchronization."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic
from typing import Any

from sqlalchemy.orm import Session

from app.flowhub.channels.contracts import (
    ChannelProduct,
    ConnectorErrorCategory,
    PageNumberPagination,
)
from app.flowhub.channels.snappshop import (
    SNAPPSHOP_PRODUCTS_PER_PAGE,
    SnappShopConnector,
    SnappShopConnectorError,
)
from app.flowhub.data_layer.models import DlInventoryCache, DlProductCache, DlRefreshJob
from app.flowhub.integration_platform.models import IntegrationConnectorEvent


_RETRYABLE_READ_ERRORS = frozenset(
    {
        ConnectorErrorCategory.RATE_LIMIT,
        ConnectorErrorCategory.TIMEOUT,
        ConnectorErrorCategory.UPSTREAM_UNAVAILABLE,
    }
)


class SnappShopProductFetchError(Exception):
    def __init__(self, cause: Exception, *, pages_read: int, products_received: int, products_skipped: int) -> None:
        self.cause = cause
        self.pages_read = pages_read
        self.products_received = products_received
        self.products_skipped = products_skipped
        super().__init__(str(cause))


@dataclass(frozen=True)
class SnappShopProductSyncResult:
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


class SnappShopProductSyncService:
    def __init__(self, db: Session) -> None:
        self.db = db

    async def run(
        self,
        connector: SnappShopConnector,
        *,
        actor: str,
        max_pages: int,
        retry_attempts: int = 2,
    ) -> SnappShopProductSyncResult:
        if not connector.config.vendor_id:
            raise ValueError("A selected SnappShop vendor is required before product synchronization.")
        if max_pages < 1:
            raise ValueError("SnappShop product synchronization page limit must be positive.")

        started = _utcnow()
        job = DlRefreshJob(
            job_type="manual",
            entity_type="products",
            connector_id=connector.channel_id,
            status="running",
            triggered_by=actor,
            started_at=started,
            created_at=started,
            meta={"provider": "snappshop", "vendor_id": connector.config.vendor_id},
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        started_clock = monotonic()
        try:
            products, pages_read, received, skipped = await self._fetch_all(
                connector,
                max_pages=max_pages,
                retry_attempts=retry_attempts,
            )
            completed = _utcnow()
            rows = [self._cache_row(connector, product, completed) for product in products]
            inventories = [self._inventory_row(connector, product, completed) for product in products]

            self.db.rollback()
            with self.db.begin():
                self.db.query(DlProductCache).filter_by(connector_id=connector.channel_id).delete(
                    synchronize_session=False
                )
                self.db.query(DlInventoryCache).filter_by(connector_id=connector.channel_id).delete(
                    synchronize_session=False
                )
                self.db.add_all(rows)
                self.db.add_all(inventories)
                durable_job = self.db.get(DlRefreshJob, job.id)
                if durable_job is None:
                    raise RuntimeError("SnappShop refresh job disappeared before cache commit.")
                durable_job.status = "completed"
                durable_job.completed_at = completed
                durable_job.duration_ms = round((monotonic() - started_clock) * 1000, 2)
                durable_job.meta = {
                    "provider": "snappshop",
                    "vendor_id": connector.config.vendor_id,
                    "pages_read": pages_read,
                    "products_received": received,
                    "products_stored": len(rows),
                    "products_skipped": skipped,
                    "error_category": None,
                }
                self.db.add(
                    IntegrationConnectorEvent(
                        connector_id=connector.channel_id,
                        event_name="product_cache_refresh_completed",
                        message="SnappShop product cache refresh completed.",
                        metadata_json={
                            "actor": actor,
                            "pages_read": pages_read,
                            "products_received": received,
                            "products_stored": len(rows),
                            "products_skipped": skipped,
                            "external_write": False,
                        },
                    )
                )
            return SnappShopProductSyncResult(
                pages_read=pages_read,
                products_received=received,
                products_stored=len(rows),
                products_skipped=skipped,
                failures=[],
                started_at=started,
                completed_at=completed,
            )
        except Exception as exc:
            self.db.rollback()
            completed = _utcnow()
            fetch_error = exc if isinstance(exc, SnappShopProductFetchError) else None
            category, message = _safe_error(fetch_error.cause if fetch_error else exc)
            pages_read = fetch_error.pages_read if fetch_error else 0
            products_received = fetch_error.products_received if fetch_error else 0
            products_skipped = fetch_error.products_skipped if fetch_error else 0
            failed_job = self.db.get(DlRefreshJob, job.id)
            if failed_job is not None:
                failed_job.status = "failed"
                failed_job.failed_at = completed
                failed_job.duration_ms = round((monotonic() - started_clock) * 1000, 2)
                failed_job.error_message = message
                failed_job.meta = {
                    **(failed_job.meta or {}),
                    "pages_read": pages_read,
                    "products_received": products_received,
                    "products_stored": 0,
                    "products_skipped": products_skipped,
                    "error_category": category,
                }
            self.db.add(
                IntegrationConnectorEvent(
                    connector_id=connector.channel_id,
                    event_name="product_cache_refresh_failed",
                    severity="error",
                    message="SnappShop product cache refresh failed.",
                    metadata_json={"actor": actor, "error_category": category, "external_write": False},
                )
            )
            self.db.commit()
            return SnappShopProductSyncResult(
                pages_read=pages_read,
                products_received=products_received,
                products_stored=0,
                products_skipped=products_skipped,
                failures=[message],
                started_at=started,
                completed_at=completed,
            )

    async def _fetch_all(
        self,
        connector: SnappShopConnector,
        *,
        max_pages: int,
        retry_attempts: int,
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
                raise ValueError("SnappShop product pagination repeated a page.")
            if pages_read >= max_pages:
                raise ValueError("SnappShop product synchronization exceeded the configured page limit.")
            visited_pages.add(page_number)
            try:
                page = await self._read_page(
                    connector,
                    page_number=page_number,
                    retry_attempts=retry_attempts,
                )
            except Exception as exc:
                raise SnappShopProductFetchError(
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
                    raise ValueError("SnappShop returned a duplicate external product identifier.")
                identifiers.add(product_id)
                products.append(item)

            pagination = page.pagination
            if not isinstance(pagination, PageNumberPagination) or not pagination.has_more:
                break
            page_number = pagination.next_page or (page_number + 1)

        return products, pages_read, received, skipped

    async def _read_page(
        self,
        connector: SnappShopConnector,
        *,
        page_number: int,
        retry_attempts: int,
    ):
        for attempt in range(retry_attempts + 1):
            try:
                return await connector.list_products(
                    PageNumberPagination(page=page_number, page_size=SNAPPSHOP_PRODUCTS_PER_PAGE)
                )
            except SnappShopConnectorError as exc:
                if exc.error.category not in _RETRYABLE_READ_ERRORS or attempt >= retry_attempts:
                    raise
                delay = exc.error.retry.retry_after_seconds or float(attempt + 1)
                await asyncio.sleep(min(max(delay, 0.0), 5.0))
        raise RuntimeError("SnappShop product read retry loop ended unexpectedly.")

    def _cache_row(
        self,
        connector: SnappShopConnector,
        product: ChannelProduct,
        synchronized_at: datetime,
    ) -> DlProductCache:
        raw = dict(product.raw)
        product_id = str(product.identifiers.external_product_id)
        discount = raw.get("discount") if isinstance(raw.get("discount"), dict) else {}
        thumbnail = raw.get("thumbnail")
        stock = _optional_int(raw.get("stock"))
        normalized_raw = {
            **raw,
            "external_product_id": product_id,
            "sku": product.identifiers.sku,
            "product_number": product.identifiers.product_number,
            "parent_product_number": product.identifiers.parent_product_number,
            "active": raw.get("active"),
            "capacity": raw.get("capacity"),
            "stock": raw.get("stock"),
            "warehouse_stock": raw.get("warehouse_stock"),
            "title": raw.get("title"),
            "title_en": raw.get("title_en"),
            "thumbnail": thumbnail,
            "price": raw.get("price"),
            "warranty": raw.get("warranty"),
            "discount": discount,
            "variation_attributes": raw.get("variation_attributes") or [],
            "source_channel": connector.channel_id,
            "vendor_id": connector.config.vendor_id,
            "synchronized_at": _iso(synchronized_at),
        }
        return DlProductCache(
            connector_id=connector.channel_id,
            product_id=product_id,
            external_id=_optional_int(product_id),
            sku=product.identifiers.sku,
            name=str(raw.get("title") or raw.get("title_en") or product.name or product_id),
            product_type="variation" if product.identifiers.parent_product_number else "simple",
            parent_id=product.identifiers.parent_product_number,
            status=product.status or "inactive",
            price=_text(raw.get("price") if raw.get("price") is not None else product.current_price),
            last_price=_text(raw.get("price") if raw.get("price") is not None else product.current_price),
            regular_price=_text(raw.get("price") if raw.get("price") is not None else product.current_price),
            sale_price=_text(discount.get("special_price")),
            stock_qty=stock,
            stock_status="instock" if (stock or 0) > 0 else "outofstock",
            manage_stock=True,
            backorders_allowed=False,
            categories=[],
            images=[{"src": str(thumbnail)}] if thumbnail else [],
            channel_id=connector.channel_id,
            freshness="fresh",
            last_fetched_at=synchronized_at,
            last_successful_read=synchronized_at,
            last_modified=_text(raw.get("updated_at")),
            exists=True,
            record_hash=hashlib.sha256(
                json.dumps(normalized_raw, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
            ).hexdigest(),
            raw_data=normalized_raw,
        )

    def _inventory_row(
        self,
        connector: SnappShopConnector,
        product: ChannelProduct,
        synchronized_at: datetime,
    ) -> DlInventoryCache:
        stock = _optional_int(product.raw.get("stock"))
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
    if isinstance(exc, SnappShopConnectorError):
        return exc.error.category.value, exc.error.message
    if isinstance(exc, ValueError):
        return "validation", str(exc)
    return "unexpected_response", "SnappShop product synchronization failed unexpectedly."


def _optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds") + "Z"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
