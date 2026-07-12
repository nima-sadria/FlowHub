"""Immutable Workspace preview persistence and Dry Run selection validation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.data_layer.models import DlProductCache, DlSourceSnapshot, DlWorkspacePreview


PREVIEW_TTL_MINUTES = 30


@dataclass(frozen=True)
class PreviewValidationError(Exception):
    code: str
    status_code: int
    detail: dict | None = None


@dataclass(frozen=True)
class ValidatedPreviewSelection:
    preview: DlWorkspacePreview
    rows: list[dict]
    changes: list[dict]


class WorkspacePreviewStore:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        preview_id: str,
        source_id: str,
        source_snapshot: DlSourceSnapshot,
        owner: FlowHubUser,
        rows: list[dict],
        summary: dict,
        now: datetime | None = None,
    ) -> DlWorkspacePreview:
        created_at = now or datetime.utcnow()
        expires_at = created_at + timedelta(minutes=PREVIEW_TTL_MINUTES)
        immutable_rows = json.loads(_canonical_json(rows))
        immutable_summary = json.loads(_canonical_json(summary))
        row_hashes = _row_hashes(immutable_rows)
        source_hash = str(source_snapshot.integrity_hash or "")
        preview_hash = calculate_preview_hash(
            preview_id=preview_id,
            source_id=source_id,
            source_snapshot_id=int(source_snapshot.id),
            source_integrity_hash=source_hash,
            owner_user_id=int(owner.id),
            expires_at=expires_at,
            row_hashes=row_hashes,
            summary=immutable_summary,
        )
        record = DlWorkspacePreview(
            id=preview_id,
            source_id=source_id,
            source_snapshot_id=int(source_snapshot.id),
            source_integrity_hash=source_hash,
            owner_user_id=int(owner.id),
            owner_username=owner.username,
            preview_hash=preview_hash,
            rows_json=immutable_rows,
            row_hashes_json=row_hashes,
            summary_json=immutable_summary,
            created_at=created_at,
            expires_at=expires_at,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def latest_reusable(
        self,
        *,
        source_id: str,
        owner: FlowHubUser,
        source_config_hash: str,
        now: datetime | None = None,
    ) -> DlWorkspacePreview | None:
        current_time = now or datetime.utcnow()
        previews = (
            self.db.query(DlWorkspacePreview)
            .filter(DlWorkspacePreview.source_id == source_id)
            .filter(DlWorkspacePreview.expires_at > current_time)
            .order_by(
                (DlWorkspacePreview.owner_user_id == int(owner.id)).desc(),
                DlWorkspacePreview.created_at.desc(),
            )
            .limit(20)
            .all()
        )
        for preview in previews:
            rows = preview.rows_json if isinstance(preview.rows_json, list) else []
            if not rows or any(
                not isinstance(row.get("source"), dict)
                or row["source"].get("sourceConfigHash") != source_config_hash
                for row in rows
            ):
                continue
            try:
                calculated_hashes = _row_hashes(rows)
            except PreviewValidationError:
                continue
            source_snapshot = self.db.get(DlSourceSnapshot, preview.source_snapshot_id)
            expected_hash = calculate_preview_hash(
                preview_id=preview.id,
                source_id=preview.source_id,
                source_snapshot_id=preview.source_snapshot_id,
                source_integrity_hash=preview.source_integrity_hash,
                owner_user_id=preview.owner_user_id,
                expires_at=preview.expires_at,
                row_hashes=calculated_hashes,
                summary=preview.summary_json if isinstance(preview.summary_json, dict) else {},
            )
            if (
                source_snapshot is None
                or str(source_snapshot.integrity_hash or "") != preview.source_integrity_hash
                or calculated_hashes != preview.row_hashes_json
                or expected_hash != preview.preview_hash
            ):
                continue

            changes = [
                row.get("dry_run_change")
                for row in rows
                if row.get("eligible_for_dry_run") is True and isinstance(row.get("dry_run_change"), dict)
            ]
            product_ids = {str(change.get("productId") or "") for change in changes if change}
            products = (
                self.db.query(DlProductCache)
                .filter(DlProductCache.connector_id == "woocommerce:primary")
                .filter(DlProductCache.product_id.in_(product_ids))
                .all()
                if product_ids
                else []
            )
            by_id = {row.product_id: row for row in products}
            valid = True
            for change in changes:
                product_id = str(change.get("productId") or "")
                current_price = _cached_price(by_id.get(product_id))
                try:
                    expected_price = float(change.get("currentPrice"))
                except (TypeError, ValueError):
                    valid = False
                    break
                if current_price is None or current_price != expected_price:
                    valid = False
                    break
            if valid:
                return preview
        return None

    def validate_selection(
        self,
        *,
        preview_id: str,
        selected_row_ids: list[str],
        user: FlowHubUser,
        now: datetime | None = None,
    ) -> ValidatedPreviewSelection:
        preview = self.db.get(DlWorkspacePreview, preview_id)
        if preview is None:
            raise PreviewValidationError("PREVIEW_NOT_FOUND", 404)
        if int(preview.owner_user_id) != int(user.id):
            raise PreviewValidationError("PREVIEW_OWNERSHIP_MISMATCH", 403)
        if preview.expires_at <= (now or datetime.utcnow()):
            raise PreviewValidationError("PREVIEW_EXPIRED", 409)
        if not selected_row_ids:
            raise PreviewValidationError("PREVIEW_ROW_NOT_ELIGIBLE", 422)
        if len(selected_row_ids) != len(set(selected_row_ids)):
            raise PreviewValidationError("PREVIEW_ROW_NOT_ELIGIBLE", 422)

        rows = preview.rows_json if isinstance(preview.rows_json, list) else []
        stored_hashes = preview.row_hashes_json if isinstance(preview.row_hashes_json, dict) else {}
        calculated_hashes = _row_hashes(rows)
        expected_preview_hash = calculate_preview_hash(
            preview_id=preview.id,
            source_id=preview.source_id,
            source_snapshot_id=preview.source_snapshot_id,
            source_integrity_hash=preview.source_integrity_hash,
            owner_user_id=preview.owner_user_id,
            expires_at=preview.expires_at,
            row_hashes=calculated_hashes,
            summary=preview.summary_json if isinstance(preview.summary_json, dict) else {},
        )
        source_snapshot = self.db.get(DlSourceSnapshot, preview.source_snapshot_id)
        if (
            stored_hashes != calculated_hashes
            or preview.preview_hash != expected_preview_hash
            or source_snapshot is None
            or str(source_snapshot.integrity_hash or "") != preview.source_integrity_hash
        ):
            raise PreviewValidationError("PREVIEW_HASH_MISMATCH", 409)

        by_id = {str(row.get("id")): row for row in rows if row.get("id")}
        selected_rows: list[dict] = []
        selected_changes: list[dict] = []
        for row_id in selected_row_ids:
            row = by_id.get(str(row_id))
            if row is None:
                raise PreviewValidationError("PREVIEW_ROW_NOT_FOUND", 422)
            if row.get("eligible_for_dry_run") is not True or row.get("errors"):
                raise PreviewValidationError("PREVIEW_ROW_NOT_ELIGIBLE", 422)
            change = row.get("dry_run_change")
            if not isinstance(change, dict) or change.get("eligible_for_dry_run") is not True:
                raise PreviewValidationError("PREVIEW_ROW_NOT_ELIGIBLE", 422)
            product_id = str(change.get("productId") or "")
            product = (
                self.db.query(DlProductCache)
                .filter(DlProductCache.connector_id == "woocommerce:primary")
                .filter(DlProductCache.product_id == product_id)
                .filter(DlProductCache.exists.is_(True))
                .one_or_none()
            )
            current_price = _cached_price(product)
            if current_price is None or current_price != float(change.get("currentPrice")):
                raise PreviewValidationError("PREVIEW_HASH_MISMATCH", 409)
            selected_rows.append(row)
            selected_changes.append(change)
        return ValidatedPreviewSelection(preview=preview, rows=selected_rows, changes=selected_changes)


def calculate_preview_hash(
    *,
    preview_id: str,
    source_id: str,
    source_snapshot_id: int,
    source_integrity_hash: str,
    owner_user_id: int,
    expires_at: datetime,
    row_hashes: dict[str, str],
    summary: dict,
) -> str:
    payload = {
        "preview_id": preview_id,
        "source_id": source_id,
        "source_snapshot_id": source_snapshot_id,
        "source_integrity_hash": source_integrity_hash,
        "owner_user_id": owner_user_id,
        "expires_at": expires_at.isoformat(),
        "row_hashes": row_hashes,
        "summary": summary,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _row_hashes(rows: list[dict]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for index, row in enumerate(rows):
        row_id = str(row.get("id") or "")
        if not row_id:
            raise PreviewValidationError(
                "PREVIEW_ROW_ID_INVALID",
                422,
                {"message": "Workspace preview row ID is missing.", "row_index": index},
            )
        if row_id in hashes:
            raise PreviewValidationError(
                "PREVIEW_ROW_ID_DUPLICATE",
                422,
                {"message": "Workspace preview row ID is duplicated.", "row_index": index, "row_id": row_id},
            )
        hashes[row_id] = hashlib.sha256(_canonical_json(row).encode("utf-8")).hexdigest()
    return hashes


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _cached_price(product: DlProductCache | None) -> float | None:
    if product is None:
        return None
    for value in (product.sale_price, product.regular_price, product.price, product.last_price):
        if value in (None, ""):
            continue
        try:
            return float(str(value).replace(",", "").strip())
        except (TypeError, ValueError):
            continue
    return None
