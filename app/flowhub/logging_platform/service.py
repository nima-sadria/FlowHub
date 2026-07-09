"""Unified Logging Platform service.

The service stores structured application logs only. It redacts sensitive
fields before persistence and never triggers product, connector, scheduler, or
write execution.
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.flowhub.logging_platform.models import (
    LoggingCorrelation,
    LoggingEntry,
    LoggingExportEvent,
    LoggingRedactionPolicyVersion,
    LoggingRequestTrace,
    LoggingRetentionPolicy,
)
from app.flowhub.security.redaction import is_sensitive_key

SEVERITIES = {"debug", "info", "warning", "error", "critical"}
FRONTEND_CATEGORIES = {
    "UI Events",
    "API Errors",
    "Page Errors",
    "Unexpected Exceptions",
    "Performance Warnings",
    "Network Errors",
    "Component Errors",
}
SECRET_MARKERS = {
    "secret",
    "password",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "signature",
    "consumer_key",
    "consumer_secret",
    "webhook_secret",
    "bearer",
}


class LoggingPlatformService:
    def __init__(self, db: Session):
        self.db = db

    def summary(self, filters: dict[str, Any]) -> dict:
        q = self._filtered_query(filters)
        rows = q.all()
        top_components = self._top_counts(rows, "component")
        top_connectors = self._top_counts(rows, "connector")
        recent_errors = [
            self._entry_to_item(row)
            for row in sorted(
                [item for item in rows if item.severity in {"error", "critical"}],
                key=lambda item: item.timestamp,
                reverse=True,
            )[:5]
        ]
        return {
            "total_logs": len(rows),
            "error_count": sum(1 for item in rows if item.severity == "error"),
            "warning_count": sum(1 for item in rows if item.severity == "warning"),
            "critical_count": sum(1 for item in rows if item.severity == "critical"),
            "top_components": top_components,
            "top_connectors": top_connectors,
            "recent_errors": recent_errors,
            "time_range": {"from": filters.get("from"), "to": filters.get("to")},
            "correlation_id": self._correlation_id(),
        }

    def search(self, filters: dict[str, Any]) -> dict:
        page = max(int(filters.get("page") or 1), 1)
        page_size = min(max(int(filters.get("page_size") or 50), 1), 500)
        q = self._filtered_query(filters)
        total = q.count()
        sort_desc = str(filters.get("sort") or "-timestamp").startswith("-")
        order_col = LoggingEntry.timestamp.desc() if sort_desc else LoggingEntry.timestamp.asc()
        rows = q.order_by(order_col).offset((page - 1) * page_size).limit(page_size).all()
        return {
            "items": [self._entry_to_item(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "correlation_id": self._correlation_id(),
        }

    def detail(self, log_id: str) -> dict:
        row = self.db.get(LoggingEntry, log_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Log entry not found.")
        related = (
            self.db.query(LoggingEntry)
            .filter(LoggingEntry.correlation_id == row.correlation_id)
            .order_by(LoggingEntry.timestamp.asc())
            .limit(20)
            .all()
        )
        return {
            "item": {
                **self._entry_to_item(row),
                "structured": row.structured_json or {},
                "exception": {
                    "type": None,
                    "summary": row.exception_summary,
                    "stacktrace": None,
                },
                "payload": row.payload_json or {},
                "related_correlation_entries": [self._entry_to_item(item) for item in related],
            },
            "correlation_id": row.correlation_id,
        }

    def correlation(self, correlation_id: str, page: int = 1, page_size: int = 50) -> dict:
        return self.search({"correlation_id": correlation_id, "page": page, "page_size": page_size, "sort": "timestamp"})

    def request_trace(self, request_id: str) -> dict:
        rows = (
            self.db.query(LoggingEntry)
            .filter(LoggingEntry.request_id == request_id)
            .order_by(LoggingEntry.timestamp.asc())
            .all()
        )
        if not rows:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Request trace not found.")
        trace = self.db.get(LoggingRequestTrace, request_id)
        return {
            "request": {
                "request_id": request_id,
                "correlation_id": rows[0].correlation_id,
                "route": trace.route if trace else "",
                "status_code": trace.status_code if trace else None,
                "user": trace.user if trace else rows[0].user,
                "duration_ms": trace.duration_ms if trace else None,
                "result": trace.result if trace else rows[-1].result,
            },
            "items": [self._entry_to_item(row) for row in rows],
            "correlation_id": rows[0].correlation_id,
        }

    def ingest_frontend(self, body: dict, username: str = "") -> dict:
        logs = body.get("logs") if isinstance(body, dict) else None
        if not isinstance(logs, list):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "logs must be a list.")
        accepted = 0
        rejections: list[dict] = []
        for index, item in enumerate(logs):
            if not isinstance(item, dict):
                rejections.append({"index": index, "reason": "invalid_log"})
                continue
            if item.get("category") not in FRONTEND_CATEGORIES:
                rejections.append({"index": index, "reason": "category_not_allowed"})
                continue
            self._store_entry({**item, "component": item.get("component") or "frontend", "user": username})
            accepted += 1
        self.db.commit()
        return {
            "accepted": accepted,
            "rejected": len(rejections),
            "rejections": rejections,
            "correlation_id": self._correlation_id(),
        }

    def ingest_backend(self, body: dict, username: str = "internal") -> dict:
        logs = body.get("logs") if isinstance(body, dict) else None
        if not isinstance(logs, list):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "logs must be a list.")
        accepted = 0
        for item in logs:
            if isinstance(item, dict):
                self._store_entry({**item, "user": item.get("user") or username})
                accepted += 1
        self.db.commit()
        return {"accepted": accepted, "rejected": len(logs) - accepted, "rejections": [], "correlation_id": self._correlation_id()}

    def export(self, filters: dict[str, Any], requested_by: str) -> tuple[str, str]:
        fmt = str(filters.get("format") or "json").lower()
        if fmt not in {"json", "csv"}:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unsupported export format.")
        result = self.search({**filters, "page": 1, "page_size": min(int(filters.get("page_size") or 10000), 10000)})
        self.db.add(
            LoggingExportEvent(
                requested_by=requested_by,
                filters_json=self._redact(filters),
                format=fmt,
                correlation_id=result["correlation_id"],
            )
        )
        self.db.commit()
        if fmt == "json":
            import json

            return "application/json", json.dumps(result["items"])
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(result["items"][0].keys()) if result["items"] else ["id"])
        writer.writeheader()
        writer.writerows(result["items"])
        return "text/csv", output.getvalue()

    def retention(self) -> dict:
        self._ensure_retention_defaults()
        rows = self.db.query(LoggingRetentionPolicy).order_by(LoggingRetentionPolicy.category.asc()).all()
        return {
            "policies": [{"category": row.category, "retention_days": row.retention_days} for row in rows],
            "correlation_id": self._correlation_id(),
        }

    def update_retention(self, body: dict, username: str) -> dict:
        policies = body.get("policies") if isinstance(body, dict) else None
        if not isinstance(policies, list):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "policies must be a list.")
        now = datetime.utcnow()
        for policy in policies:
            if not isinstance(policy, dict):
                continue
            category = str(policy.get("category") or "")
            days = int(policy.get("retention_days") or 0)
            if not category or days < 1:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid retention policy.")
            row = self.db.get(LoggingRetentionPolicy, category)
            if row is None:
                row = LoggingRetentionPolicy(category=category, retention_days=days)
                self.db.add(row)
            row.retention_days = days
            row.updated_at = now
            row.updated_by = username
        self.db.commit()
        return self.retention()

    def redaction_policy(self) -> dict:
        row = self.db.query(LoggingRedactionPolicyVersion).order_by(LoggingRedactionPolicyVersion.id.desc()).first()
        if row is None:
            row = LoggingRedactionPolicyVersion(version="1.0", rules_json=self._policy_rules())
            self.db.add(row)
            self.db.commit()
        return {
            **self._policy_rules(),
            "correlation_id": self._correlation_id(),
        }

    def live_contract(self) -> dict:
        return {
            "implemented": False,
            "future_ready": True,
            "message": "Live Tail is future-ready and not required in the first implementation.",
            "correlation_id": self._correlation_id(),
        }

    def _filtered_query(self, filters: dict[str, Any]):
        q = self.db.query(LoggingEntry)
        for key in ["severity", "component", "module", "operation", "category", "connector", "channel", "user", "correlation_id", "request_id", "result"]:
            value = filters.get(key)
            if value:
                q = q.filter(getattr(LoggingEntry, key) == str(value))
        if filters.get("from"):
            q = q.filter(LoggingEntry.timestamp >= _parse_datetime(str(filters["from"])))
        if filters.get("to"):
            q = q.filter(LoggingEntry.timestamp <= _parse_datetime(str(filters["to"])))
        search = filters.get("search")
        if search:
            pattern = f"%{search}%"
            q = q.filter(or_(LoggingEntry.message.ilike(pattern), LoggingEntry.exception_summary.ilike(pattern)))
        return q

    def _store_entry(self, item: dict[str, Any]) -> LoggingEntry:
        severity = str(item.get("severity") or "info").lower()
        if severity not in SEVERITIES:
            severity = "info"
        timestamp = _parse_datetime(str(item.get("timestamp"))) if item.get("timestamp") else datetime.utcnow()
        correlation_id = str(item.get("correlation_id") or self._correlation_id())
        request_id = str(item.get("request_id") or "")
        row = LoggingEntry(
            id=str(item.get("id") or f"log_{uuid.uuid4().hex}"),
            timestamp=timestamp,
            severity=severity,
            component=str(item.get("component") or "backend"),
            module=str(item.get("module") or ""),
            operation=str(item.get("operation") or ""),
            category=str(item.get("category") or ""),
            message=str(self._redact_value(item.get("message") or "")),
            correlation_id=correlation_id,
            request_id=request_id,
            user=str(item.get("user") or ""),
            connector=str(item.get("connector") or ""),
            channel=str(item.get("channel") or ""),
            duration_ms=item.get("duration_ms"),
            result=str(item.get("result") or ""),
            exception_summary=self._redact_value(item.get("exception_summary")),
            structured_json=self._redact(item.get("structured") or item.get("details") or {}),
            payload_json=self._redact(item.get("payload") or {}),
        )
        self.db.add(row)
        self._touch_correlation(correlation_id, timestamp)
        if request_id:
            self._touch_request(request_id, correlation_id, row)
        return row

    def _entry_to_item(self, row: LoggingEntry) -> dict:
        return {
            "id": row.id,
            "timestamp": _iso(row.timestamp),
            "severity": row.severity,
            "component": row.component,
            "module": row.module,
            "operation": row.operation,
            "category": row.category,
            "message": row.message,
            "correlation_id": row.correlation_id,
            "request_id": row.request_id,
            "user": row.user,
            "connector": row.connector,
            "channel": row.channel,
            "duration_ms": row.duration_ms,
            "result": row.result,
            "exception_summary": row.exception_summary,
        }

    def _touch_correlation(self, correlation_id: str, timestamp: datetime) -> None:
        row = self.db.get(LoggingCorrelation, correlation_id)
        if row is None:
            self.db.add(LoggingCorrelation(correlation_id=correlation_id, first_seen_at=timestamp, last_seen_at=timestamp, entry_count=1))
        else:
            row.last_seen_at = max(row.last_seen_at, timestamp)
            row.entry_count += 1

    def _touch_request(self, request_id: str, correlation_id: str, entry: LoggingEntry) -> None:
        row = self.db.get(LoggingRequestTrace, request_id)
        if row is None:
            self.db.add(
                LoggingRequestTrace(
                    request_id=request_id,
                    correlation_id=correlation_id,
                    user=entry.user,
                    started_at=entry.timestamp,
                    result=entry.result,
                )
            )
        else:
            row.finished_at = entry.timestamp
            row.result = entry.result
            if row.started_at:
                row.duration_ms = int((entry.timestamp - row.started_at).total_seconds() * 1000)

    def _ensure_retention_defaults(self) -> None:
        defaults = {"operational": 30, "connector_telemetry": 90, "audit_security": 365}
        changed = False
        for category, days in defaults.items():
            if self.db.get(LoggingRetentionPolicy, category) is None:
                self.db.add(LoggingRetentionPolicy(category=category, retention_days=days))
                changed = True
        if changed:
            self.db.commit()

    def _top_counts(self, rows: list[LoggingEntry], field: str) -> list[dict]:
        counts: dict[str, int] = {}
        for row in rows:
            value = str(getattr(row, field) or "")
            if not value:
                continue
            counts[value] = counts.get(value, 0) + 1
        return [{field: key, "count": value} for key, value in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:5]]

    def _redact(self, value: Any) -> Any:
        if isinstance(value, dict):
            result: dict[str, Any] = {}
            for key, item in value.items():
                key_lower = str(key).lower()
                result[key] = "[REDACTED]" if is_sensitive_key(key_lower) else self._redact(item)
            return result
        if isinstance(value, list):
            return [self._redact(item) for item in value]
        return self._redact_value(value)

    def _redact_value(self, value: Any) -> Any:
        if value is None:
            return None
        text = str(value)
        if any(marker in text.lower() for marker in SECRET_MARKERS):
            return "[REDACTED]"
        return value

    def _policy_rules(self) -> dict:
        return {
            "categories": [
                {"name": "secrets", "examples": ["api_key", "token", "password", "authorization_header"], "action": "redact"},
                {"name": "personal_data", "examples": ["email", "phone"], "action": "mask_or_hash"},
            ],
            "never_exposed": ["secret_values", "authorization_headers", "cookies", "webhook_signatures"],
        }

    def _correlation_id(self) -> str:
        return f"corr_{uuid.uuid4().hex[:12]}"


def _parse_datetime(value: str) -> datetime:
    if not value or value == "None":
        return datetime.utcnow()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return datetime.utcnow()


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat() + "Z"
