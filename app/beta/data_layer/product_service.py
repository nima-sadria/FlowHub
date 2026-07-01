"""Product read model service â€” reads and writes dl_product_cache."""

from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.beta.data_layer.models import DlProductCache


class ProductReadModelService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_status(self) -> dict:
        """Return product cache status summary."""
        total = self._db.query(DlProductCache).count()
        fresh = self._db.query(DlProductCache).filter(DlProductCache.freshness == "fresh").count()
        stale = self._db.query(DlProductCache).filter(DlProductCache.freshness == "stale").count()
        error = self._db.query(DlProductCache).filter(DlProductCache.freshness == "error").count()

        last_record = (
            self._db.query(DlProductCache)
            .filter(DlProductCache.last_fetched_at.isnot(None))
            .order_by(DlProductCache.last_fetched_at.desc())
            .first()
        )

        return {
            "initialized": total > 0,
            "total": total,
            "fresh": fresh,
            "stale": stale,
            "error": error,
            "last_fetched_at": _iso(last_record.last_fetched_at) if last_record else None,
        }

    def list(
        self,
        connector_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        """Return paginated product cache entries."""
        q = self._db.query(DlProductCache)
        if connector_id:
            q = q.filter(DlProductCache.connector_id == connector_id)
        total = q.count()
        offset = (page - 1) * page_size
        items = q.order_by(DlProductCache.id.desc()).offset(offset).limit(page_size).all()
        return {
            "items": [_product_to_dict(p) for p in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def upsert(
        self,
        connector_id: str,
        product_id: str,
        data: dict,
        freshness: str = "fresh",
        expires_at: Optional[datetime.datetime] = None,
    ) -> DlProductCache:
        """Insert or update a product cache entry."""
        row = (
            self._db.query(DlProductCache)
            .filter_by(connector_id=connector_id, product_id=product_id)
            .first()
        )
        now = datetime.datetime.utcnow()
        if row is None:
            row = DlProductCache(connector_id=connector_id, product_id=product_id)
            self._db.add(row)
        for k, v in data.items():
            if hasattr(row, k) and k not in ("id", "connector_id", "product_id"):
                setattr(row, k, v)
        row.freshness = freshness
        row.last_fetched_at = now
        if expires_at is not None:
            row.expires_at = expires_at
        self._db.commit()
        self._db.refresh(row)
        return row

    def mark_stale(self, connector_id: Optional[str] = None) -> int:
        """Mark product cache entries as stale. Returns count updated."""
        q = self._db.query(DlProductCache)
        if connector_id:
            q = q.filter(DlProductCache.connector_id == connector_id)
        count = q.update({"freshness": "stale"})
        self._db.commit()
        return count


def _product_to_dict(p: DlProductCache) -> dict:
    return {
        "id": p.id,
        "connector_id": p.connector_id,
        "product_id": p.product_id,
        "external_id": p.external_id,
        "sku": p.sku,
        "name": p.name,
        "product_type": p.product_type,
        "status": p.status,
        "price": p.price,
        "stock_status": p.stock_status,
        "freshness": p.freshness,
        "channel_id": p.channel_id,
        "last_fetched_at": _iso(p.last_fetched_at),
        "expires_at": _iso(p.expires_at),
    }


def _iso(dt: Optional[datetime.datetime]) -> Optional[str]:
    return dt.isoformat() + "Z" if dt is not None else None
