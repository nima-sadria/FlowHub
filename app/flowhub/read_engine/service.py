"""Incremental product read engine.

This service is explicitly manual. It records resumable state but does not
schedule, auto-sync, or retry in a loop.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any

from sqlalchemy.orm import Session

from app.flowhub.data_layer.models import DlProductCache, DlRefreshJob
from app.flowhub.data_layer.product_service import ProductReadModelService
from app.flowhub.rate_limit.service import RateLimitService
from app.flowhub.read_engine.contracts import ReadConnectorAdapter, ReadPage
from app.flowhub.read_engine.exceptions import IncrementalReadUnsupported
from app.flowhub.security.redaction import redact_sensitive


@dataclass(frozen=True)
class ReadProgress:
    job_id: int
    connector_id: str
    strategy: str
    status: str
    requests_completed: int
    requests_delayed: int
    products_stored: int
    remaining_queue: int
    estimated_completion_seconds: float | None
    # Number of rows is intentionally not the authoritative cache state; this
    # optional staging hook is invoked immediately before each upsert so callers
    # can hold their Listing guard through the transaction commit.


class IncrementalReadEngine:
    def __init__(self, db: Session, rate_limits: RateLimitService | None = None) -> None:
        self.db = db
        self.products = ProductReadModelService(db)
        self.rate_limits = rate_limits or RateLimitService(db)

    def determine_strategy(self, adapter: ReadConnectorAdapter) -> str:
        has_cache = self.db.query(DlProductCache).filter_by(connector_id=adapter.connector_id).first() is not None
        if not has_cache:
            return "initial_full_read"
        if adapter.capabilities.supports_modified_since or adapter.capabilities.supports_updated_after:
            return "modified_since"
        return "metadata_filter"

    def eligible_cached_product_ids(self, connector_id: str, *, now: datetime | None = None) -> list[str]:
        now = now or datetime.utcnow()
        cutoff = now - timedelta(days=365)
        rows = self.db.query(DlProductCache).filter_by(connector_id=connector_id).all()
        eligible: list[str] = []
        for row in rows:
            if _has_valid_price(row):
                eligible.append(row.product_id)
                continue
            if _parse_modified(row.last_modified) and _parse_modified(row.last_modified) >= cutoff:
                eligible.append(row.product_id)
        return eligible

    async def run_manual(
        self,
        adapter: ReadConnectorAdapter,
        *,
        triggered_by: str = "manual",
        force_full: bool = False,
        before_cache_write: Callable[[str, str], None] | None = None,
    ) -> ReadProgress:
        strategy = "initial_full_read" if force_full else self.determine_strategy(adapter)
        job = self._resume_or_create_job(
            adapter.connector_id,
            strategy,
            triggered_by,
            resume_pending=not force_full,
        )
        job.status = "running"
        job.started_at = job.started_at or datetime.utcnow()
        self.db.commit()

        meta = dict(job.meta or {})
        strategy = str(meta.get("strategy") or strategy)
        cursor = meta.get("cursor")
        requests_completed = int(meta.get("requests_completed") or 0)
        requests_delayed = int(meta.get("requests_delayed") or 0)
        products_stored = int(meta.get("products_stored") or 0)
        seen_product_ids = {str(item) for item in (meta.get("seen_product_ids") or [])}
        modified_since = self._modified_since(adapter.connector_id) if strategy == "modified_since" else None
        product_ids = meta.get("product_ids") if strategy == "metadata_filter" else None
        if strategy == "metadata_filter" and product_ids is None:
            product_ids = await self._metadata_filtered_product_ids(adapter)

        try:
            while True:
                if strategy == "metadata_filter" and not product_ids:
                    break
                limiter_result = await self._acquire_read_limit_if_needed(adapter)
                requests_completed += 1
                if limiter_result is not None and limiter_result.delayed:
                    requests_delayed += 1

                page = await self._fetch_page(adapter, strategy, cursor, modified_since, product_ids)
                for item in page.items:
                    product_id = self._product_id(item)
                    if not product_id or product_id in seen_product_ids:
                        continue
                    if before_cache_write is not None:
                        before_cache_write(adapter.connector_id, product_id)
                    self._store_product(adapter.connector_id, item)
                    seen_product_ids.add(product_id)
                    products_stored += 1

                cursor = page.next_cursor
                self._save_job_meta(
                    job,
                    {
                        "strategy": strategy,
                        "cursor": cursor,
                        "requests_completed": requests_completed,
                        "requests_delayed": requests_delayed,
                        "products_stored": products_stored,
                        "seen_product_ids": sorted(seen_product_ids),
                        "product_ids": product_ids if strategy == "metadata_filter" else None,
                        "queue_survives_interruption": True,
                        "scheduler_started": False,
                        "automatic_sync": False,
                    },
                )
                if not cursor:
                    break
        except Exception as exc:
            job.status = "pending"
            job.error_message = str(exc)[:500]
            job.meta = {
                **(job.meta or {}),
                "cursor": cursor,
                "resumable": True,
                "queue_survives_interruption": True,
                "scheduler_started": False,
                "automatic_sync": False,
            }
            self.db.commit()
            raise

        if force_full:
            unseen = self.db.query(DlProductCache).filter(DlProductCache.connector_id == adapter.connector_id)
            if seen_product_ids:
                unseen = unseen.filter(DlProductCache.product_id.notin_(seen_product_ids))
            unseen.update({"exists": False, "freshness": "stale"}, synchronize_session=False)

        job.status = "completed"
        job.completed_at = datetime.utcnow()
        if job.started_at:
            job.duration_ms = (job.completed_at - job.started_at).total_seconds() * 1000
        self.db.commit()

        remaining_queue = 0 if cursor is None else 1
        estimated = (
            (60.0 / self.rate_limits.get_settings().read_requests_per_minute) * remaining_queue
            if remaining_queue
            else None
        )
        return ReadProgress(
            job_id=job.id,
            connector_id=adapter.connector_id,
            strategy=strategy,
            status=job.status,
            requests_completed=requests_completed,
            requests_delayed=requests_delayed,
            products_stored=products_stored,
            remaining_queue=remaining_queue,
            estimated_completion_seconds=estimated,
        )

    async def _fetch_page(
        self,
        adapter: ReadConnectorAdapter,
        strategy: str,
        cursor: str | None,
        modified_since: datetime | None,
        product_ids: list[str] | None,
    ) -> ReadPage:
        if strategy == "metadata_filter":
            if not adapter.capabilities.supports_batch_read:
                raise IncrementalReadUnsupported("incremental_read_unsupported: connector cannot batch read product IDs")
            return await adapter.fetch_products(cursor=cursor, product_ids=product_ids or [])
        if strategy == "modified_since":
            return await adapter.fetch_products(modified_since=modified_since, cursor=cursor)
        return await adapter.fetch_products(cursor=cursor)

    async def _metadata_filtered_product_ids(self, adapter: ReadConnectorAdapter) -> list[str]:
        if not adapter.capabilities.supports_batch_read:
            raise IncrementalReadUnsupported("incremental_read_unsupported: connector cannot batch read product IDs")

        eligible_cache = set(self.eligible_cached_product_ids(adapter.connector_id))
        cutoff = datetime.utcnow() - timedelta(days=365)
        selected: list[str] = []
        seen: set[str] = set()
        cursor: str | None = None

        while True:
            await self._acquire_read_limit_if_needed(adapter)
            page = await adapter.fetch_metadata(cursor=cursor)
            for item in page.items:
                product_id = self._product_id(item)
                if not product_id or product_id in seen:
                    continue
                modified = _parse_modified(
                    item.get("last_modified")
                    or item.get("date_modified_gmt")
                    or item.get("updated_at")
                    or item.get("modified")
                )
                if product_id in eligible_cache or (modified is not None and modified >= cutoff):
                    selected.append(product_id)
                    seen.add(product_id)
            cursor = page.next_cursor
            if not cursor:
                break
        return selected

    async def _acquire_read_limit_if_needed(self, adapter: ReadConnectorAdapter):
        if bool(getattr(adapter, "uses_http_boundary_limiter", False)):
            return None
        return await self.rate_limits.acquire(
            adapter.connector_id,
            "read",
            connector_type=adapter.connector_type,
        )

    def _resume_or_create_job(
        self,
        connector_id: str,
        strategy: str,
        triggered_by: str,
        *,
        resume_pending: bool = True,
    ) -> DlRefreshJob:
        existing = (
            self.db.query(DlRefreshJob)
            .filter_by(connector_id=connector_id, entity_type="products", status="pending")
            .order_by(DlRefreshJob.created_at.desc())
            .first()
        )
        if existing and resume_pending and (existing.meta or {}).get("resumable"):
            return existing
        if existing and not resume_pending:
            existing.status = "failed"
            existing.error_message = "Superseded by a new full manual refresh."
            existing.completed_at = datetime.utcnow()
            self.db.commit()
        job = DlRefreshJob(
            job_type="manual",
            entity_type="products",
            connector_id=connector_id,
            status="pending",
            triggered_by=triggered_by,
            meta={
                "strategy": strategy,
                "force_full": not resume_pending,
                "scheduler_started": False,
                "automatic_sync": False,
            },
            created_at=datetime.utcnow(),
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def _save_job_meta(self, job: DlRefreshJob, meta: dict) -> None:
        job.meta = meta
        self.db.commit()

    def _modified_since(self, connector_id: str) -> datetime | None:
        row = (
            self.db.query(DlProductCache)
            .filter(DlProductCache.connector_id == connector_id, DlProductCache.last_successful_read.isnot(None))
            .order_by(DlProductCache.last_successful_read.desc())
            .first()
        )
        return row.last_successful_read if row else None

    def _store_product(self, connector_id: str, item: dict[str, Any]) -> None:
        product_id = self._product_id(item)
        if not product_id:
            return
        now = datetime.utcnow()
        price = item.get("last_price", item.get("price"))
        if price in (None, ""):
            price = item.get("sale_price") or item.get("regular_price")
        raw_data = _safe_item(item)
        self.products.upsert(
            connector_id,
            product_id,
            {
                "sku": item.get("sku"),
                "name": item.get("name"),
                "external_id": _int_or_none(item.get("external_id", item.get("id"))),
                "product_type": item.get("product_type") or item.get("type"),
                "parent_id": str(item.get("parent_id")) if item.get("parent_id") not in (None, "") else None,
                "status": item.get("status"),
                "price": str(price) if price is not None else None,
                "last_price": str(price) if price is not None else None,
                "regular_price": _text_or_none(item.get("regular_price")),
                "sale_price": _text_or_none(item.get("sale_price")),
                "stock_qty": _int_or_none(item.get("stock_quantity", item.get("stock_qty"))),
                "stock_status": item.get("stock_status"),
                "manage_stock": _bool_or_none(item.get("manage_stock")),
                "backorders_allowed": str(item.get("backorders") or "").lower() in {"yes", "notify", "true", "1"},
                "categories": item.get("categories") if isinstance(item.get("categories"), list) else [],
                "images": item.get("images") if isinstance(item.get("images"), list) else [],
                "channel_id": connector_id,
                "last_successful_read": now,
                "last_modified": item.get("last_modified") or item.get("date_modified_gmt") or item.get("updated_at"),
                "exists": bool(item.get("exists", True)),
                "record_hash": _hash(raw_data),
                "raw_data": raw_data,
            },
            freshness="fresh",
        )

    def _product_id(self, item: dict[str, Any]) -> str:
        return str(item.get("product_id") or item.get("id") or "").strip()


def _has_valid_price(row: DlProductCache) -> bool:
    price = row.last_price if row.last_price not in (None, "") else row.price
    return price not in (None, "")


def _parse_modified(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.replace(tzinfo=None)


def _int_or_none(value: Any) -> int | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _text_or_none(value: Any) -> str | None:
    return None if value in (None, "") else str(value)


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    return None


def _safe_item(item: dict[str, Any]) -> dict[str, Any]:
    return redact_sensitive(item)


def _hash(item: dict[str, Any]) -> str:
    payload = json.dumps(item, sort_keys=True, default=str, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()
