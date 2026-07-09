"""Read-only spreadsheet Source mapping, read policy, and import helpers."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.flowhub.data_layer.models import DlSourceSnapshot
from app.flowhub.integration_platform.service import IntegrationPlatformService
from app.flowhub.integrations.errors import IntegrationError
from app.flowhub.integrations.nextcloud import NextcloudClient
from app.flowhub.integrations.spreadsheet import load_workbook_bytes, parse_source_price_rows
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


class SpreadsheetSourceReadService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.config = AppConfigService(db)
        self.integration = IntegrationPlatformService(db)

    async def read_nextcloud_spreadsheet(
        self,
        *,
        triggered_by: str,
        manual: bool,
        consume_quota: bool = True,
    ) -> SourceImportResult:
        spreadsheet_path = self._required_config("nextcloud.spreadsheet_path")
        policy_state = self.check_read_allowed(manual=manual)
        mapping = self.mapping()
        worksheet = self.worksheet_selection()
        client = NextcloudClient.from_config(self.config)
        if client is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Nextcloud source credentials are incomplete.")

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
                "read_only": True,
                "source_write": False,
            },
        )
        try:
            content, file_meta = await client.download_file(spreadsheet_path)
            workbook = load_workbook_bytes(content)
            rows, duplicate_info = parse_source_price_rows(
                workbook,
                mapping=mapping,
                worksheet_mode=worksheet["mode"],
                worksheet_name=worksheet["name"],
            )
            if not rows:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Spreadsheet contains no importable source rows.")
            stats = source_row_stats(rows, duplicate_info)
            snapshot = self._upsert_source_snapshot(
                file_path=spreadsheet_path,
                content=content,
                file_meta=file_meta,
                sheet_names=list(workbook.sheetnames),
                row_count=len(rows),
                duplicate_count=len(duplicate_info["duplicate_product_ids"]) + len(duplicate_info["duplicate_skus"]),
                invalid_row_count=stats["error_rows"],
            )
            if consume_quota:
                policy_state = self.record_read(stats)
            self._record_event(
                "source_read_completed",
                "Source read completed.",
                triggered_by,
                {
                    "source_id": SOURCE_ID,
                    "source_type": SOURCE_TYPE,
                    "spreadsheet_path": spreadsheet_path,
                    "worksheets": list(workbook.sheetnames),
                    "row_count": len(rows),
                    "valid_rows": stats["valid_rows"],
                    "warning_rows": stats["warning_rows"],
                    "error_rows": stats["error_rows"],
                    "read_only": True,
                    "source_write": False,
                },
            )
            return SourceImportResult(
                source_id=SOURCE_ID,
                source_type=SOURCE_TYPE,
                spreadsheet_path=spreadsheet_path,
                rows=rows,
                duplicate_info=duplicate_info,
                snapshot=snapshot,
                read_policy=policy_state,
                stats=stats,
            )
        except IntegrationError as exc:
            safe_message = str(getattr(exc, "detail", "") or getattr(exc, "message", "") or "Source read failed.")
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
                    "error": safe_message[:200],
                    "read_only": True,
                    "source_write": False,
                },
                severity="error",
            )
            raise HTTPException(exc.status_code or status.HTTP_502_BAD_GATEWAY, safe_message[:200]) from exc
        except ValueError as exc:
            safe_message = str(exc)
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
                    "read_only": True,
                    "source_write": False,
                },
                severity="error",
            )
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, safe_message) from exc
        except Exception as exc:
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
            "last_read_at": result.read_policy["last_read_at"],
            "remaining_reads_today": result.read_policy["reads_remaining"],
            "reads_used_last_24h": result.read_policy["reads_used_last_24h"],
            "reads_remaining": result.read_policy["reads_remaining"],
            "reset_at": result.read_policy["reset_at"],
            "warnings": result.stats["warnings"],
            "errors": result.stats["errors"],
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
        history = _recent_history(self.config.get(_HISTORY_KEY), now)
        max_reads = int(policy["max_reads_per_24h"])
        used = len(history) if policy["enabled"] else 0
        reset_at = None
        if history:
            reset_at = _iso(min(history) + timedelta(hours=24))
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
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Source read limit exceeded.")
        return state

    def record_read(self, stats: dict) -> dict:
        now = datetime.utcnow()
        history = _recent_history(self.config.get(_HISTORY_KEY), now)
        history.append(now)
        self.config.set_many(
            {
                _HISTORY_KEY: json.dumps([_iso(item) for item in history]),
                _LAST_READ_AT_KEY: _iso(now),
                _LAST_READ_STATUS_KEY: "completed" if stats["error_rows"] == 0 else "completed_with_errors",
                _LAST_READ_ROWS_KEY: str(stats["total_rows"]),
                _LAST_READ_WARNINGS_KEY: str(stats["warning_rows"]),
                _LAST_READ_ERRORS_KEY: str(stats["error_rows"]),
            },
            updated_by="source_read",
        )
        return self.read_policy_state(now=now)

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
    return {
        "total_rows": len(rows),
        "valid_rows": sum(1 for row in rows if not row.get("row_errors")),
        "warning_rows": sum(1 for row in rows if row.get("row_warnings")),
        "error_rows": sum(1 for row in rows if row.get("row_errors")),
        "warnings": warnings,
        "errors": errors,
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
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "max_reads_per_24h must be a positive integer.")
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
