"""Source and destination snapshot metadata services."""

from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.flowhub.data_layer.models import DlDestinationSnapshot, DlSourceSnapshot


class SourceSnapshotService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_status(self) -> dict:
        """Return source snapshot status summary."""
        total = self._db.query(DlSourceSnapshot).count()
        last = (
            self._db.query(DlSourceSnapshot)
            .order_by(DlSourceSnapshot.snapshotted_at.desc())
            .first()
        )
        return {
            "initialized": total > 0,
            "total": total,
            "last_snapshot_at": _iso(last.snapshotted_at) if last else None,
        }

    def get_all(self) -> list[dict]:
        """Return all source snapshot records, most recent first."""
        rows = (
            self._db.query(DlSourceSnapshot)
            .order_by(DlSourceSnapshot.snapshotted_at.desc())
            .all()
        )
        return [_src_to_dict(r) for r in rows]

    def upsert(
        self,
        connector_id: str,
        file_path: str,
        *,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
        parsed_row_count: Optional[int] = None,
        duplicate_count: Optional[int] = None,
        invalid_row_count: Optional[int] = None,
        integrity_hash: Optional[str] = None,
        sheet_names: Optional[list] = None,
    ) -> DlSourceSnapshot:
        """Insert or update a source snapshot record. Increments version_seq on update."""
        now = datetime.datetime.utcnow()
        row = (
            self._db.query(DlSourceSnapshot)
            .filter_by(connector_id=connector_id, file_path=file_path)
            .first()
        )
        if row is None:
            row = DlSourceSnapshot(
                connector_id=connector_id,
                file_path=file_path,
                snapshotted_at=now,
                version_seq=1,
            )
            self._db.add(row)
        else:
            row.version_seq = (row.version_seq or 1) + 1
            row.snapshotted_at = now
        row.etag = etag
        row.last_modified = last_modified
        row.parsed_row_count = parsed_row_count
        row.duplicate_count = duplicate_count
        row.invalid_row_count = invalid_row_count
        row.integrity_hash = integrity_hash
        row.sheet_names = sheet_names
        self._db.commit()
        self._db.refresh(row)
        return row


class DestinationSnapshotService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_status(self) -> dict:
        """Return destination snapshot status summary."""
        total = self._db.query(DlDestinationSnapshot).count()
        last = (
            self._db.query(DlDestinationSnapshot)
            .order_by(DlDestinationSnapshot.snapshotted_at.desc())
            .first()
        )
        return {
            "initialized": total > 0,
            "total": total,
            "last_snapshot_at": _iso(last.snapshotted_at) if last else None,
        }

    def get_all(self, connector_id: Optional[str] = None) -> list[dict]:
        """Return all destination snapshot records."""
        q = self._db.query(DlDestinationSnapshot)
        if connector_id:
            q = q.filter_by(connector_id=connector_id)
        rows = q.order_by(DlDestinationSnapshot.snapshotted_at.desc()).all()
        return [_dst_to_dict(r) for r in rows]

    def upsert(
        self,
        connector_id: str,
        product_id: str,
        *,
        price: Optional[str] = None,
        regular_price: Optional[str] = None,
        sale_price: Optional[str] = None,
        stock_status: Optional[str] = None,
        response_hash: Optional[str] = None,
        source_connector_id: Optional[str] = None,
    ) -> DlDestinationSnapshot:
        """Insert or update a destination snapshot record."""
        now = datetime.datetime.utcnow()
        row = (
            self._db.query(DlDestinationSnapshot)
            .filter_by(connector_id=connector_id, product_id=product_id)
            .first()
        )
        if row is None:
            row = DlDestinationSnapshot(
                connector_id=connector_id,
                product_id=product_id,
                snapshotted_at=now,
            )
            self._db.add(row)
        row.price = price
        row.regular_price = regular_price
        row.sale_price = sale_price
        row.stock_status = stock_status
        row.response_hash = response_hash
        row.source_connector_id = source_connector_id
        row.snapshotted_at = now
        self._db.commit()
        self._db.refresh(row)
        return row


def _src_to_dict(r: DlSourceSnapshot) -> dict:
    return {
        "id": r.id,
        "connector_id": r.connector_id,
        "file_path": r.file_path,
        "etag": r.etag,
        "last_modified": r.last_modified,
        "parsed_row_count": r.parsed_row_count,
        "duplicate_count": r.duplicate_count,
        "invalid_row_count": r.invalid_row_count,
        "integrity_hash": r.integrity_hash,
        "sheet_names": r.sheet_names,
        "version_seq": r.version_seq,
        "snapshotted_at": _iso(r.snapshotted_at),
    }


def _dst_to_dict(r: DlDestinationSnapshot) -> dict:
    return {
        "id": r.id,
        "connector_id": r.connector_id,
        "product_id": r.product_id,
        "price": r.price,
        "regular_price": r.regular_price,
        "sale_price": r.sale_price,
        "stock_status": r.stock_status,
        "response_hash": r.response_hash,
        "source_connector_id": r.source_connector_id,
        "snapshotted_at": _iso(r.snapshotted_at),
    }


def _iso(dt: Optional[datetime.datetime]) -> Optional[str]:
    return dt.isoformat() + "Z" if dt is not None else None
