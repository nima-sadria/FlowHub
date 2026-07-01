"""Integration Platform ORM models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.beta.database import BetaBase


def _utcnow() -> datetime:
    return datetime.utcnow()


class IntegrationConnectorInstance(BetaBase):
    __tablename__ = "ip_connector_instances"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    connector_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="1.0.0")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    read_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="disabled")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)

    settings: Mapped[list[IntegrationConnectorSetting]] = relationship(
        "IntegrationConnectorSetting",
        back_populates="connector",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class IntegrationConnectorSetting(BetaBase):
    __tablename__ = "ip_connector_settings"
    __table_args__ = (UniqueConstraint("connector_id", "key", name="uq_ip_connector_setting"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector_id: Mapped[str] = mapped_column(
        String(120),
        ForeignKey("ip_connector_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    value_json: Mapped[object | None] = mapped_column(JSON, nullable=True)
    secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    configured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)

    connector: Mapped[IntegrationConnectorInstance] = relationship(
        "IntegrationConnectorInstance",
        back_populates="settings",
    )


class IntegrationConnectorHealthSnapshot(BetaBase):
    __tablename__ = "ip_connector_health_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    checked_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    details_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class IntegrationConnectorEvent(BetaBase):
    __tablename__ = "ip_connector_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    event_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(30), nullable=False, default="info")
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)


class IntegrationConnectorDiagnostic(BetaBase):
    __tablename__ = "ip_connector_diagnostics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    checks_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    warnings_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    errors_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    finished_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correlation_id: Mapped[str] = mapped_column(String(120), nullable=False, default="")


class IntegrationConnectorTelemetry(BetaBase):
    __tablename__ = "ip_connector_telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    connector_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    transport: Mapped[str] = mapped_column(String(60), nullable=False, default="internal")
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms_p50: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms_p95: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rate_limit_events: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    refresh_duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bucket_start: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)


class IntegrationWebhookEvent(BetaBase):
    __tablename__ = "ip_webhook_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connector_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    connector_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rejected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_summary_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    correlation_id: Mapped[str] = mapped_column(String(120), nullable=False, default="")


class IntegrationPollingPolicy(BetaBase):
    __tablename__ = "ip_polling_policies"

    connector_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=900)
    jitter_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
