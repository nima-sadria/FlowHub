"""Unified Logging Platform ORM models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.flowhub.database import FlowHubBase


def _utcnow() -> datetime:
    return datetime.utcnow()


class LoggingEntry(FlowHubBase):
    __tablename__ = "logging_entries"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow, index=True)
    severity: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    component: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(120), nullable=False, default="", index=True)
    operation: Mapped[str] = mapped_column(String(120), nullable=False, default="", index=True)
    category: Mapped[str] = mapped_column(String(120), nullable=False, default="", index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(120), nullable=False, default="", index=True)
    request_id: Mapped[str] = mapped_column(String(120), nullable=False, default="", index=True)
    user: Mapped[str] = mapped_column(String(160), nullable=False, default="", index=True)
    connector: Mapped[str] = mapped_column(String(120), nullable=False, default="", index=True)
    channel: Mapped[str] = mapped_column(String(80), nullable=False, default="", index=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result: Mapped[str] = mapped_column(String(80), nullable=False, default="", index=True)
    exception_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class LoggingCorrelation(FlowHubBase):
    __tablename__ = "logging_correlations"

    correlation_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    entry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class LoggingRequestTrace(FlowHubBase):
    __tablename__ = "logging_request_traces"

    request_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    correlation_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    route: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result: Mapped[str] = mapped_column(String(80), nullable=False, default="")


class LoggingRetentionPolicy(FlowHubBase):
    __tablename__ = "logging_retention_policies"

    category: Mapped[str] = mapped_column(String(80), primary_key=True)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    updated_by: Mapped[str] = mapped_column(String(160), nullable=False, default="")


class LoggingExportEvent(FlowHubBase):
    __tablename__ = "logging_export_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    requested_by: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    filters_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    format: Mapped[str] = mapped_column(String(20), nullable=False, default="json")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    correlation_id: Mapped[str] = mapped_column(String(120), nullable=False, default="")


class LoggingRedactionPolicyVersion(FlowHubBase):
    __tablename__ = "logging_redaction_policy_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    rules_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
