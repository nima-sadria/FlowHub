"""Read-only spreadsheet Source mapping, read policy, and import helpers."""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.flowhub.config.nextcloud_url import NextcloudUrlValidationError, normalize_nextcloud_url
from app.flowhub.data_layer.models import (
    DlSourceReadLock,
    DlSourceReadReservation,
    DlSourceSnapshot,
)
from app.flowhub.integration_platform.service import IntegrationPlatformService
from app.flowhub.integrations.errors import IntegrationError
from app.flowhub.integrations.nextcloud import NextcloudClient
from app.flowhub.integrations.spreadsheet import load_workbook_bytes, parse_source_price_rows
from app.flowhub.security.upstream_errors import UpstreamServiceError, normalize_upstream_error
from app.flowhub.setup.service import AppConfigService

SOURCE_ID = "nextcloud:primary"
SOURCE_TYPE = "nextcloud_spreadsheet"

DEFAULT_SOURCE_MAPPING: dict[str, dict[str, object]] = {
    "id": {"enabled": True, "column": "B"},
    "price": {"enabled": True, "column": "C"},
    "stock": {"enabled": False, "column": "D"},
}

DEFAULT_READ_POLICY: dict[str, object] = {
    "enabled": True,
    "max_reads_per_24h": 10,
    "manual_read_allowed": True,
}

_COLUMN_REF_RE = re.compile(r"^[A-Za-z]{1,3}$")
_HEADER_REF_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 _./()-]{0,63}$")
_HISTORY_KEY = "nextcloud.source_read_history"
_LAST_READ_AT_KEY = "nextcloud.last_read_at"
_LAST_READ_STATUS_KEY = "nextcloud.last_read_status"
_LAST_READ_ROWS_KEY = "nextcloud.last_read_row_count"
_LAST_READ_WARNINGS_KEY = "nextcloud.last_read_warning_count"
_LAST_READ_ERRORS_KEY = "nextcloud.last_read_error_count"


@dataclass(frozen=True)
class SourceImportResult:
    source_id: str
    source_type: str
    spreadsheet_path: str
    rows: list[dict]
    duplicate_info: dict
    snapshot: DlSourceSnapshot
    read_policy: dict
    stats: dict
    worksheets: dict[str, list[list[Any]]] | None = None


class SpreadsheetSourceReadService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.config = AppConfigService(db)
        self.integration = IntegrationPlatformService(db)

    async def read_nextcloud_spreadsheet(
        self,
        *,
        triggered_by: str,
        triggered_by_id: str | int | None = None,
        manual: bool,
        capture_raw_worksheets: bool = False,
    ) -> SourceImportResult:
        spreadsheet_path = self._required_config("nextcloud.spreadsheet_path")
        mapping = None if capture_raw_worksheets else self.mapping()
        worksheet = self.worksheet_selection()
        try:
            normalize_nextcloud_url(
                self.config.get("nextcloud.url") or "",
                self.config.get("nextcloud.username") or "",
            )
        except NextcloudUrlValidationError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {"code": exc.code, "message": str(exc)},
            ) from exc
        client = NextcloudClient.from_config(self.config)
        if client is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Nextcloud source credentials are incomplete.")
        reservation_user_id = str(triggered_by_id if triggered_by_id is not None else triggered_by)
        reservation = self.reserve_read_slot(reservation_user_id, manual=manual)
        policy_state = self.read_policy_state()

        self._record_event(
            "source_read_started",
            "Source read started.",
            triggered_by,
            {
                "source_id": SOURCE_ID,
                "source_type": SOURCE_TYPE,
                "spreadsheet_path": spreadsheet_path,
                "worksheet_mode": worksheet["mode"],
                "worksheet_name": worksheet["name"],
                "reservation_id": reservation.id if reservation else None,
                "reservation_status": reservation.status if reservation else None,
                "read_only": True,
                "source_write": False,
            },
        )
        try:
            content, file_meta = await client.download_file(spreadsheet_path)
            workbook = load_workbook_bytes(content)
            raw_worksheets = (
                {
                    sheet.title: [list(row) for row in sheet.iter_rows(values_only=True)]
                    for sheet in workbook.worksheets
                }
                if capture_raw_worksheets
                else None
            )
            if capture_raw_worksheets:
                rows = []
                duplicate_info: dict[str, Any] = {
                    "duplicate_product_ids": [],
                    "duplicate_skus": [],
                }
            else:
                if mapping is None:
                    raise RuntimeError("Legacy Source mapping was not loaded.")
                rows, duplicate_info = parse_source_price_rows(
                    workbook,
                    mapping=mapping,
                    worksheet_mode=worksheet["mode"],
                    worksheet_name=worksheet["name"],
                )
            if not rows and not capture_raw_worksheets:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Spreadsheet contains no importable source rows.")
            persisted_row_count = (
                sum(len(sheet_rows) for sheet_rows in raw_worksheets.values())
                if raw_worksheets is not None
                else len(rows)
            )
            stats = source_row_stats(rows, duplicate_info)
            if capture_raw_worksheets:
                stats["total_rows"] = persisted_row_count
                stats["valid_rows"] = persisted_row_count
            snapshot = self._upsert_source_snapshot(
                file_path=spreadsheet_path,
                content=content,
                file_meta=file_meta,
                sheet_names=list(workbook.sheetnames),
                row_count=persisted_row_count,
                duplicate_count=len(duplicate_info["duplicate_product_ids"]) + len(duplicate_info["duplicate_skus"]),
                invalid_row_count=stats["error_rows"],
            )
            self._record_event(
                "source_read_completed",
                "Source read completed.",
                triggered_by,
                {
                    "source_id": SOURCE_ID,
                    "source_type": SOURCE_TYPE,
                    "spreadsheet_path": spreadsheet_path,
                    "worksheets": list(workbook.sheetnames),
                    "row_count": persisted_row_count,
                    "valid_rows": stats["valid_rows"],
                    "warning_rows": stats["warning_rows"],
                    "error_rows": stats["error_rows"],
                    "duplicate_rows": stats["duplicate_rows"],
                    "reservation_id": reservation.id if reservation else None,
                    "read_only": True,
                    "source_write": False,
                },
            )
            if reservation:
                policy_state = self.finalize_read_reservation(reservation.id, "succeeded", stats=stats)
            return SourceImportResult(
                source_id=SOURCE_ID,
                source_type=SOURCE_TYPE,
                spreadsheet_path=spreadsheet_path,
                rows=rows,
                duplicate_info=duplicate_info,
                snapshot=snapshot,
                read_policy=policy_state,
                stats=stats,
                worksheets=raw_worksheets,
            )
        except IntegrationError as exc:
            safe_error = normalize_upstream_error(exc, source="nextcloud")
            if reservation:
                self.finalize_read_reservation(reservation.id, "failed", error_code="INTEGRATION_ERROR")
            self.config.set_many(
                {
                    _LAST_READ_AT_KEY: _iso(datetime.utcnow()),
                    _LAST_READ_STATUS_KEY: "failed",
                },
                updated_by="source_read",
            )
            self._record_event(
                "source_read_failed",
                "Source read failed.",
                triggered_by,
                {
                    "source_id": SOURCE_ID,
                    "source_type": SOURCE_TYPE,
                    "spreadsheet_path": spreadsheet_path,
                    "error": safe_error["message"],
                    "error_code": safe_error["code"],
                    "reservation_id": reservation.id if reservation else None,
                    "read_only": True,
                    "source_write": False,
                },
                severity="error",
            )
            raise UpstreamServiceError(exc, source="nextcloud") from exc
        except ValueError as exc:
            safe_message = str(exc)
            if reservation:
                self.finalize_read_reservation(reservation.id, "failed", error_code="SOURCE_VALIDATION_ERROR")
            self.config.set_many(
                {
                    _LAST_READ_AT_KEY: _iso(datetime.utcnow()),
                    _LAST_READ_STATUS_KEY: "failed",
                },
                updated_by="source_read",
            )
            self._record_event(
                "source_read_failed",
                "Source read failed.",
                triggered_by,
                {
                    "source_id": SOURCE_ID,
                    "source_type": SOURCE_TYPE,
                    "spreadsheet_path": spreadsheet_path,
                    "error": safe_message,
                    "reservation_id": reservation.id if reservation else None,
                    "read_only": True,
                    "source_write": False,
                },
                severity="error",
            )
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, safe_message) from exc
        except Exception as exc:
            if reservation:
                self.finalize_read_reservation(reservation.id, "failed", error_code=type(exc).__name__[:120])
            self.config.set_many(
                {
                    _LAST_READ_AT_KEY: _iso(datetime.utcnow()),
                    _LAST_READ_STATUS_KEY: "failed",
                },
                updated_by="source_read",
            )
            self._record_event(
                "source_read_failed",
                "Source read failed.",
                triggered_by,
                {
                    "source_id": SOURCE_ID,
                    "source_type": SOURCE_TYPE,
                    "spreadsheet_path": spreadsheet_path,
                    "error": _safe_error_message(exc),
                    "reservation_id": reservation.id if reservation else None,
                    "read_only": True,
                    "source_write": False,
                },
                severity="error",
            )
            raise

    def manual_read_response(self, result: SourceImportResult) -> dict:
        return {
            "ok": True,
            "rows_read": result.stats["total_rows"],
            "valid_rows": result.stats["valid_rows"],
            "warning_rows": result.stats["warning_rows"],
            "error_rows": result.stats["error_rows"],
            "duplicate_rows": result.stats["duplicate_rows"],
            "last_read_at": result.read_policy["last_read_at"],
            "remaining_reads_today": result.read_policy["reads_remaining"],
            "reads_used_last_24h": result.read_policy["reads_used_last_24h"],
            "reads_remaining": result.read_policy["reads_remaining"],
            "reset_at": result.read_policy["reset_at"],
            "warnings": result.stats["warnings"],
            "errors": result.stats["errors"],
            "error_details": result.stats["error_details"],
            "source_id": result.source_id,
            "source_type": result.source_type,
            "spreadsheet_path": result.spreadsheet_path,
            "external_call_performed": True,
            "read_only": True,
            "source_write": False,
            "write_blocked": True,
        }

    def mapping(self) -> dict[str, dict[str, object]]:
        raw = _json_config(self.config.get("nextcloud.source_mapping"))
        return normalize_source_mapping(raw)

    def read_policy(self) -> dict[str, object]:
        raw = _json_config(self.config.get("nextcloud.source_read_policy"))
        return normalize_read_policy(raw)

    def worksheet_selection(self) -> dict[str, str]:
        mode = str(self.config.get("nextcloud.worksheet_mode") or "all").strip().lower()
        if mode not in {"all", "selected"}:
            mode = "all"
        return {
            "mode": mode,
            "name": str(self.config.get("nextcloud.worksheet_name") or "").strip(),
        }

    def read_status(self) -> dict:
        return {
            **self.read_policy_state(),
            "last_read_status": self.config.get(_LAST_READ_STATUS_KEY),
            "last_row_count": _int_or_none(self.config.get(_LAST_READ_ROWS_KEY)),
            "last_warning_count": _int_or_none(self.config.get(_LAST_READ_WARNINGS_KEY)),
            "last_error_count": _int_or_none(self.config.get(_LAST_READ_ERRORS_KEY)),
        }

    def read_policy_state(self, *, now: datetime | None = None) -> dict:
        now = now or datetime.utcnow()
        policy = self.read_policy()
        legacy_history = _recent_history(self.config.get(_HISTORY_KEY), now)
        reservations = (
            self.db.query(DlSourceReadReservation)
            .filter(DlSourceReadReservation.source_id == SOURCE_ID)
            .filter(DlSourceReadReservation.reserved_at >= now - timedelta(hours=24))
            .all()
        )
        max_reads = int(policy["max_reads_per_24h"])
        used = len(legacy_history) + len(reservations) if policy["enabled"] else 0
        reset_at = None
        timestamps = legacy_history + [row.reserved_at for row in reservations]
        if timestamps:
            reset_at = _iso(min(timestamps) + timedelta(hours=24))
        return {
            "enabled": bool(policy["enabled"]),
            "max_reads_per_24h": max_reads,
            "manual_read_allowed": bool(policy["manual_read_allowed"]),
            "reads_used_last_24h": used,
            "reads_remaining": max(max_reads - used, 0) if policy["enabled"] else max_reads,
            "reset_at": reset_at,
            "last_read_at": self.config.get(_LAST_READ_AT_KEY),
        }

    def check_read_allowed(self, *, manual: bool) -> dict:
        state = self.read_policy_state()
        if manual and not state["manual_read_allowed"]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Manual source read is disabled by source read policy.")
        if state["enabled"] and state["reads_remaining"] <= 0:
            raise _source_read_limit_exception(state)
        return state

    def reserve_read_slot(self, user_id: str, *, manual: bool) -> DlSourceReadReservation:
        """Reserve atomically before outbound access.

        Every committed reservation consumes the rolling quota, including a
        failed outbound attempt. Configuration validation happens before this
        method, so local validation failures do not consume a slot.
        """
        policy = self.read_policy()
        if manual and not policy["manual_read_allowed"]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Manual source read is disabled by source read policy.")

        now = datetime.utcnow()
        self.db.commit()
        dialect = self.db.get_bind().dialect.name
        if dialect == "sqlite":
            self.db.execute(text("BEGIN IMMEDIATE"))
            self.db.execute(
                text("INSERT OR IGNORE INTO dl_source_read_locks (source_id, updated_at) VALUES (:source_id, :updated_at)"),
                {"source_id": SOURCE_ID, "updated_at": now},
            )
        elif dialect == "postgresql":
            self.db.execute(
                text(
                    "INSERT INTO dl_source_read_locks (source_id, updated_at) VALUES (:source_id, :updated_at) "
                    "ON CONFLICT (source_id) DO NOTHING"
                ),
                {"source_id": SOURCE_ID, "updated_at": now},
            )
        elif dialect in {"mysql", "mariadb"}:
            self.db.execute(
                text("INSERT IGNORE INTO dl_source_read_locks (source_id, updated_at) VALUES (:source_id, :updated_at)"),
                {"source_id": SOURCE_ID, "updated_at": now},
            )
        else:
            if self.db.get(DlSourceReadLock, SOURCE_ID) is None:
                self.db.add(DlSourceReadLock(source_id=SOURCE_ID, updated_at=now))
                self.db.flush()

        lock = (
            self.db.query(DlSourceReadLock)
            .filter(DlSourceReadLock.source_id == SOURCE_ID)
            .with_for_update()
            .one()
        )
        lock.updated_at = now
        self.db.flush()

        state = self.read_policy_state(now=now)
        if state["enabled"] and state["reads_remaining"] <= 0:
            error = _source_read_limit_exception(state, now=now)
            self.db.rollback()
            raise error

        reservation = DlSourceReadReservation(
            id=f"srr_{uuid.uuid4().hex[:20]}",
            source_id=SOURCE_ID,
            user_id=str(user_id),
            reserved_at=now,
            status="reserved",
        )
        self.db.add(reservation)
        self.db.commit()
        self.db.refresh(reservation)
        self._record_event(
            "source_read_reserved",
            "Source read quota slot reserved before outbound access.",
            str(user_id),
            {"source_id": SOURCE_ID, "reservation_id": reservation.id, "reservation_status": "reserved"},
        )
        return reservation

    def finalize_read_reservation(
        self,
        reservation_id: str,
        final_status: str,
        *,
        stats: dict | None = None,
        error_code: str | None = None,
    ) -> dict:
        self.db.rollback()
        reservation = self.db.get(DlSourceReadReservation, reservation_id)
        if reservation is None:
            raise RuntimeError("Source read reservation is missing.")
        if reservation.status == "reserved":
            reservation.status = final_status
            reservation.completed_at = datetime.utcnow()
            reservation.error_code = error_code
            self.db.commit()

        values = {
            _LAST_READ_AT_KEY: _iso(reservation.completed_at or datetime.utcnow()),
            _LAST_READ_STATUS_KEY: (
                "failed" if final_status == "failed" else "completed_with_errors" if stats and stats["error_rows"] else "completed"
            ),
        }
        if stats:
            values.update({
                _LAST_READ_ROWS_KEY: str(stats["total_rows"]),
                _LAST_READ_WARNINGS_KEY: str(stats["warning_rows"]),
                _LAST_READ_ERRORS_KEY: str(stats["error_rows"]),
            })
        self.config.set_many(
            values,
            updated_by="source_read",
        )
        self._record_event(
            "source_read_reservation_finalized",
            "Source read reservation finalized.",
            reservation.user_id,
            {
                "source_id": SOURCE_ID,
                "reservation_id": reservation.id,
                "reservation_status": final_status,
                "error_code": error_code,
            },
            severity="error" if final_status == "failed" else "info",
        )
        return self.read_policy_state(now=reservation.completed_at or datetime.utcnow())

    def _required_config(self, key: str) -> str:
        value = self.config.get(key)
        if not value:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Missing required setting: {key}")
        return value

    def _upsert_source_snapshot(
        self,
        *,
        file_path: str,
        content: bytes,
        file_meta: dict[str, str | None],
        sheet_names: list[str],
        row_count: int,
        duplicate_count: int,
        invalid_row_count: int,
    ) -> DlSourceSnapshot:
        now = datetime.utcnow()
        integrity_hash = hashlib.sha256(content).hexdigest()
        snapshot = (
            self.db.query(DlSourceSnapshot)
            .filter(DlSourceSnapshot.connector_id == SOURCE_ID)
            .filter(DlSourceSnapshot.file_path == file_path)
            .one_or_none()
        )
        if snapshot is None:
            snapshot = DlSourceSnapshot(
                connector_id=SOURCE_ID,
                file_path=file_path,
                version_seq=1,
                snapshotted_at=now,
            )
            self.db.add(snapshot)
        else:
            snapshot.version_seq = (snapshot.version_seq or 0) + 1
            snapshot.snapshotted_at = now
        snapshot.etag = file_meta.get("etag")
        snapshot.last_modified = file_meta.get("last_modified")
        snapshot.parsed_row_count = row_count
        snapshot.duplicate_count = duplicate_count
        snapshot.invalid_row_count = invalid_row_count
        snapshot.integrity_hash = integrity_hash
        snapshot.sheet_names = sheet_names
        self.db.commit()
        self.db.refresh(snapshot)
        return snapshot

    def _record_event(
        self,
        event_name: str,
        message: str,
        actor: str,
        metadata: dict,
        *,
        severity: str = "info",
    ) -> None:
        self.integration.record_event(
            connector_id=SOURCE_ID,
            event_name=event_name,
            message=message,
            severity=severity,
            metadata={**metadata, "actor": actor, "timestamp": _iso(datetime.utcnow())},
        )


def source_row_stats(rows: list[dict], duplicate_info: dict) -> dict:
    warnings: list[str] = []
    errors: list[str] = []
    error_details: list[dict[str, str]] = []
    for product_id in duplicate_info.get("duplicate_product_ids", []):
        errors.append(f"Duplicate product ID in spreadsheet: {product_id}")
    for sku in duplicate_info.get("duplicate_skus", []):
        errors.append(f"Duplicate SKU in spreadsheet: {sku}")
    for row in rows:
        for item in row.get("row_warnings") or []:
            if item not in warnings:
                warnings.append(str(item))
        for item in row.get("row_errors") or []:
            if item not in errors:
                errors.append(str(item))
        for detail in row.get("row_error_details") or []:
            if isinstance(detail, dict) and detail not in error_details:
                error_details.append({
                    "code": str(detail.get("code") or "SOURCE_ROW_INVALID"),
                    "message": str(detail.get("message") or "Source row is invalid."),
                })
    error_rows = sum(1 for row in rows if row.get("row_errors"))
    warning_rows = sum(1 for row in rows if not row.get("row_errors") and row.get("row_warnings"))
    valid_rows = len(rows) - error_rows - warning_rows
    duplicate_rows = sum(
        1 for row in rows if row.get("duplicate_product_id") or row.get("duplicate_sku")
    )
    return {
        "total_rows": len(rows),
        "valid_rows": valid_rows,
        "warning_rows": warning_rows,
        "error_rows": error_rows,
        "duplicate_rows": duplicate_rows,
        "duplicate_rows_are_error_subset": True,
        "warnings": warnings,
        "errors": errors,
        "error_details": error_details,
    }


def normalize_source_mapping(raw: object | None) -> dict[str, dict[str, object]]:
    data = raw if isinstance(raw, dict) else {}
    normalized: dict[str, dict[str, object]] = {}
    for field, defaults in DEFAULT_SOURCE_MAPPING.items():
        item = data.get(field) if isinstance(data.get(field), dict) else {}
        enabled = bool(item.get("enabled", defaults["enabled"]))
        column = str(item.get("column", defaults["column"]) or "").strip()
        if enabled and not column:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{field} column is required when enabled.")
        if column:
            column = normalize_column_reference(column)
        normalized[field] = {"enabled": enabled, "column": column}
    enabled_columns: dict[str, str] = {}
    for field, item in normalized.items():
        if not item["enabled"]:
            continue
        column_key = str(item["column"]).casefold()
        previous = enabled_columns.get(column_key)
        if previous:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Duplicate enabled source mapping column: {item['column']}.")
        enabled_columns[column_key] = field
    return normalized


def normalize_read_policy(raw: object | None) -> dict[str, object]:
    data = raw if isinstance(raw, dict) else {}
    enabled = bool(data.get("enabled", DEFAULT_READ_POLICY["enabled"]))
    manual_allowed = bool(data.get("manual_read_allowed", DEFAULT_READ_POLICY["manual_read_allowed"]))
    try:
        max_reads = int(data.get("max_reads_per_24h", DEFAULT_READ_POLICY["max_reads_per_24h"]))
    except (TypeError, ValueError):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "max_reads_per_24h must be a positive integer.",
        ) from None
    if max_reads < 1 or max_reads > 1000:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "max_reads_per_24h must be between 1 and 1000.")
    return {
        "enabled": enabled,
        "max_reads_per_24h": max_reads,
        "manual_read_allowed": manual_allowed,
    }


def normalize_column_reference(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if _COLUMN_REF_RE.fullmatch(text):
        return text.upper()
    if _HEADER_REF_RE.fullmatch(text):
        return " ".join(text.split())
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid column reference.")


def serialize_source_mapping(mapping: dict[str, dict[str, object]]) -> str:
    return json.dumps(mapping, sort_keys=True)


def serialize_read_policy(policy: dict[str, object]) -> str:
    return json.dumps(policy, sort_keys=True)


def _json_config(value: str | None) -> object | None:
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def _recent_history(value: str | None, now: datetime) -> list[datetime]:
    raw = _json_config(value)
    if not isinstance(raw, list):
        return []
    cutoff = now - timedelta(hours=24)
    history: list[datetime] = []
    for item in raw:
        try:
            parsed = datetime.fromisoformat(str(item).replace("Z", ""))
        except ValueError:
            continue
        if parsed >= cutoff:
            history.append(parsed)
    return sorted(history)


def _source_read_limit_exception(state: dict, *, now: datetime | None = None) -> HTTPException:
    current = now or datetime.utcnow()
    reset_at = str(state.get("reset_at") or "") or None
    retry_after = 0
    if reset_at:
        try:
            reset_time = datetime.fromisoformat(reset_at.replace("Z", ""))
            retry_after = max(1, math.ceil((reset_time - current).total_seconds()))
        except ValueError:
            retry_after = 0
    detail = {
        "code": "SOURCE_READ_LIMIT_REACHED",
        "message": "The source read allowance has been used.",
        "limit": int(state.get("max_reads_per_24h") or 0),
        "usage": int(state.get("reads_used_last_24h") or 0),
        "reset_at": reset_at,
        "retry_after_seconds": retry_after or None,
    }
    headers = {"Retry-After": str(retry_after)} if retry_after else None
    return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail, headers=headers)


def _iso(value: datetime) -> str:
    return value.isoformat() + "Z"


def _int_or_none(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _safe_error_message(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    return str(exc)[:200] or type(exc).__name__
