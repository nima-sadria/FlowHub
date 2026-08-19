"""Product read model service - reads and writes dl_product_cache."""

from __future__ import annotations

import datetime

from sqlalchemy.orm import Session

from app.flowhub.data_layer.models import DlProductCache

_UPSERTABLE_COLUMNS = {
    column.name for column in DlProductCache.__table__.columns if column.name not in ("id", "connector_id", "product_id")
}


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
        connector_id: str | None = None,
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
        expires_at: datetime.datetime | None = None,
    ) -> DlProductCache:
        """Insert or update a product cache entry."""
        # Cache mutation participates in the same stable Listing-row protocol
        # as Apply and Mapping. If Apply owns the Listing this raises before any
        # authoritative cache value is changed.
        from app.flowhub.unified_workspace.listing_guard import (
            acquire_external_listing_guard,
        )

        acquire_external_listing_guard(self._db, connector_id, product_id)
        row = (
            self._db.query(DlProductCache)
            .filter_by(connector_id=connector_id, product_id=product_id)
            .first()
        )
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
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

    def bulk_upsert(
        self,
        connector_id: str,
        items: list[tuple[str, dict]],
        *,
        freshness: str = "fresh",
    ) -> int:
        """Batch upsert for FULL/CHANNEL-scope page writes: one INSERT ...
        ON CONFLICT DO UPDATE per page on PostgreSQL, instead of N per-row
        commits. Fences on provider_observed_at (see model docstring) so a
        slow FULL page can never overwrite a newer targeted observation.
        Skips -- rather than aborting the whole page for -- any row whose
        Listing is currently owned by an in-flight Apply job; the row is
        simply left for a later pass instead of losing the rest of the
        batch to one contended product.
        """
        from app.flowhub.unified_workspace.listing_guard import (
            ListingGuardConflict,
            acquire_external_listing_guard,
        )

        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        rows: list[dict] = []
        for product_id, data in items:
            try:
                acquire_external_listing_guard(self._db, connector_id, product_id)
            except ListingGuardConflict:
                continue
            row = {key: value for key, value in data.items() if key in _UPSERTABLE_COLUMNS}
            row["connector_id"] = connector_id
            row["product_id"] = product_id
            row["freshness"] = freshness
            row["last_fetched_at"] = now
            rows.append(row)
        if not rows:
            return 0
        if self._db.bind is not None and self._db.bind.dialect.name == "postgresql":
            self._bulk_upsert_postgresql(rows)
        else:
            self._bulk_upsert_fallback(rows)
        self._db.commit()
        return len(rows)

    def _bulk_upsert_postgresql(self, rows: list[dict]) -> None:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        columns = [key for key in rows[0] if key not in ("connector_id", "product_id")]
        statement = pg_insert(DlProductCache).values(rows)
        statement = statement.on_conflict_do_update(
            index_elements=["connector_id", "product_id"],
            set_={column: getattr(statement.excluded, column) for column in columns},
            # Newest external observation wins, regardless of which write
            # commits last -- the FULL-vs-LIGHT fencing rule.
            where=(
                DlProductCache.provider_observed_at.is_(None)
                | (statement.excluded.provider_observed_at >= DlProductCache.provider_observed_at)
            ),
        )
        self._db.execute(statement)

    def _bulk_upsert_fallback(self, rows: list[dict]) -> None:
        # Correctness-preserving path for SQLite (unit tests) and any other
        # non-PostgreSQL dialect. Not the performance path -- production
        # runs PostgreSQL, where _bulk_upsert_postgresql does one statement
        # instead of N per-row round trips.
        for row in rows:
            existing = (
                self._db.query(DlProductCache)
                .filter_by(connector_id=row["connector_id"], product_id=row["product_id"])
                .first()
            )
            if existing is None:
                self._db.add(DlProductCache(**row))
                continue
            if existing.provider_observed_at is not None:
                incoming_observed = row.get("provider_observed_at")
                if incoming_observed is None or incoming_observed < existing.provider_observed_at:
                    continue  # a newer observation already exists; do not overwrite
            for key, value in row.items():
                setattr(existing, key, value)

    def mark_not_found(self, connector_id: str, product_id: str) -> None:
        """Narrow update for a targeted read that found the entity gone
        upstream (404). Mirrors FULL's unseen-sweep semantics: only
        exists/freshness/last_fetched_at change. Previously observed values
        (name, price, ...) are preserved for audit/display rather than
        clobbered with nulls. A no-op if the row was never cached."""
        from app.flowhub.unified_workspace.listing_guard import (
            acquire_external_listing_guard,
        )

        acquire_external_listing_guard(self._db, connector_id, product_id)
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        self._db.query(DlProductCache).filter_by(
            connector_id=connector_id, product_id=product_id
        ).update({"exists": False, "freshness": "stale", "last_fetched_at": now}, synchronize_session=False)
        self._db.commit()

    def mark_stale(self, connector_id: str | None = None) -> int:
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
        "last_price": p.last_price,
        "stock_status": p.stock_status,
        "freshness": p.freshness,
        "channel_id": p.channel_id,
        "last_fetched_at": _iso(p.last_fetched_at),
        "last_successful_read": _iso(p.last_successful_read),
        "last_modified": p.last_modified,
        "exists": p.exists,
        "hash": p.record_hash,
        "expires_at": _iso(p.expires_at),
    }


def _iso(dt: datetime.datetime | None) -> str | None:
    return dt.isoformat() + "Z" if dt is not None else None
