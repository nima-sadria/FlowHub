"""Incremental product read engine.

This service is explicitly manual. It records resumable state but does not
schedule, auto-sync, or retry in a loop.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any

from sqlalchemy.orm import Session

from app.flowhub.data_layer.models import DlProductCache, DlRefreshJob
from app.flowhub.data_layer.product_service import ProductReadModelService
from app.flowhub.rate_limit.service import RateLimitService
from app.flowhub.read_engine.contracts import ReadConnectorAdapter, ReadPage


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

    async def run_manual(self, adapter: ReadConnectorAdapter, *, triggered_by: str = "manual") -> ReadProgress:
        strategy = self.determine_strategy(adapter)
        job = self._resume_or_create_job(adapter.connector_id, strategy, triggered_by)
        job.status = "running"
        job.started_at = job.started_at or datetime.utcnow()
        self.db.commit()

        meta = dict(job.meta or {})
        strategy = str(meta.get("strategy") or strategy)
        cursor = meta.get("cursor")
        requests_completed = int(meta.get("requests_completed") or 0)
        requests_delayed = int(meta.get("requests_delayed") or 0)
        products_stored = int(meta.get("products_stored") or 0)
        modified_since = self._modified_since(adapter.connector_id) if strategy == "modified_since" else None
        product_ids = self.eligible_cached_product_ids(adapter.connector_id) if strategy == "metadata_filter" else None

        try:
            while True:
                limiter_result = await self.rate_limits.acquire(
                    adapter.connector_id,
                    "read",
                    connector_type=adapter.connector_type,
                )
                requests_completed += 1
                if limiter_result.delayed:
                    requests_delayed += 1

                page = await self._fetch_page(adapter, strategy, cursor, modified_since, product_ids)
                for item in page.items:
                    self._store_product(adapter.connector_id, item)
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

        job.status = "completed"
        job.completed_at = datetime.utcnow()
        if job.started_at:
            job.duration_ms = (job.completed_at - job.started_at).total_seconds() * 1000
        self.db.commit()

        estimated = None if requests_completed == 0 else max(0, (60.0 / self.rate_limits.get_settings().read_requests_per_minute) * (1 if cursor else 0))
        return ReadProgress(
            job_id=job.id,
            connector_id=adapter.connector_id,
            strategy=strategy,
            status=job.status,
            requests_completed=requests_completed,
            requests_delayed=requests_delayed,
            products_stored=products_stored,
            remaining_queue=0 if cursor is None else 1,
            estimated_completion_seconds=estimated,
        )

    def _fetch_page(
        self,
        adapter: ReadConnectorAdapter,
        strategy: str,
        cursor: str | None,
        modified_since: datetime | None,
        product_ids: list[str] | None,
    ):
        if strategy == "metadata_filter":
            return adapter.fetch_products(cursor=cursor, product_ids=product_ids or [])
        if strategy == "modified_since":
            return adapter.fetch_products(modified_since=modified_since, cursor=cursor)
        return adapter.fetch_products(cursor=cursor)

    def _resume_or_create_job(self, connector_id: str, strategy: str, triggered_by: str) -> DlRefreshJob:
        existing = (
            self.db.query(DlRefreshJob)
            .filter_by(connector_id=connector_id, entity_type="products", status="pending")
            .order_by(DlRefreshJob.created_at.desc())
            .first()
        )
        if existing and (existing.meta or {}).get("resumable"):
            return existing
        job = DlRefreshJob(
            job_type="manual",
            entity_type="products",
            connector_id=connector_id,
            status="pending",
            triggered_by=triggered_by,
            meta={"strategy": strategy, "scheduler_started": False, "automatic_sync": False},
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
        product_id = str(item.get("product_id") or item.get("id") or "")
        if not product_id:
            return
        now = datetime.utcnow()
        price = item.get("last_price", item.get("price"))
        raw_data = _safe_item(item)
        self.products.upsert(
            connector_id,
            product_id,
            {
                "sku": item.get("sku"),
                "name": item.get("name"),
                "price": str(price) if price is not None else None,
                "last_price": str(price) if price is not None else None,
                "last_successful_read": now,
                "last_modified": item.get("last_modified") or item.get("date_modified_gmt") or item.get("updated_at"),
                "exists": bool(item.get("exists", True)),
                "record_hash": _hash(raw_data),
                "raw_data": raw_data,
            },
            freshness="fresh",
        )


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


def _safe_item(item: dict[str, Any]) -> dict[str, Any]:
    blocked = {"key", "secret", "token", "authorization", "password"}
    return {key: value for key, value in item.items() if key.lower() not in blocked}


def _hash(item: dict[str, Any]) -> str:
    payload = json.dumps(item, sort_keys=True, default=str, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()
