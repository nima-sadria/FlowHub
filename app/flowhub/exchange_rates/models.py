"""Durable normalized exchange-rate domain models.

Snapshots are immutable historical inputs for the future pricing engine.  The
provider-specific API response never leaves the provider adapter.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.flowhub.database import FlowHubBase


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ExchangeRateProviderConfig(FlowHubBase):
    __tablename__ = "fh_exchange_rate_providers"

    provider_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    provider_type: Mapped[str] = mapped_column(String(80), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    api_key_secret_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    base_url: Mapped[str] = mapped_column(String(255), nullable=False)
    request_timeout: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    refreshes_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    daily_request_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    reserved_request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="disabled")
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_count_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    request_completed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provider_daily_usage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_hourly_usage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_monthly_usage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_last_use: Mapped[str | None] = mapped_column(String(80), nullable=True)
    usage_reconciled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    usage_next_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    usage_status: Mapped[str] = mapped_column(String(30), nullable=False, default="unknown")
    usage_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    next_refresh_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_scheduled_refresh_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    authentication_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    schedule_timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    refresh_lock_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    refresh_lock_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    runner_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    runner_state: Mapped[str | None] = mapped_column(String(30), nullable=True)
    runner_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)


class ExchangeRateDefinition(FlowHubBase):
    __tablename__ = "fh_exchange_rate_definitions"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    provider_id: Mapped[str] = mapped_column(ForeignKey("fh_exchange_rate_providers.provider_id"), nullable=False, index=True)
    external_symbol: Mapped[str] = mapped_column(String(80), nullable=False)
    canonical_code: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[str] = mapped_column(String(180), nullable=False)
    display_name_fa: Mapped[str] = mapped_column(String(180), nullable=False)
    classification: Mapped[str] = mapped_column(String(80), nullable=False, default="market")
    side: Mapped[str | None] = mapped_column(String(20), nullable=True)
    unit: Mapped[str] = mapped_column(String(30), nullable=False, default="IRR")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    __table_args__ = (UniqueConstraint("provider_id", "external_symbol", name="uq_fh_rate_provider_symbol"),)


class ExchangeRateSnapshot(FlowHubBase):
    __tablename__ = "fh_exchange_rate_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    provider_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    external_symbol: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    canonical_code: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[str] = mapped_column(String(180), nullable=False)
    display_name_fa: Mapped[str] = mapped_column(String(180), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(28, 8), nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    classification: Mapped[str] = mapped_column(String(80), nullable=False, default="market")
    side: Mapped[str | None] = mapped_column(String(20), nullable=True)
    change: Mapped[Decimal | None] = mapped_column(Numeric(28, 8), nullable=True)
    provider_timestamp: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="fresh")
    raw_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_key: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    __table_args__ = (UniqueConstraint("provider_id", "external_symbol", "provider_timestamp", name="uq_fh_rate_snapshot_version"),)


class ExchangeRateSelection(FlowHubBase):
    __tablename__ = "fh_exchange_rate_selections"

    user_id: Mapped[int] = mapped_column(ForeignKey("flowhub_users.id", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_id: Mapped[str] = mapped_column(String(80), nullable=False)
    external_symbol: Mapped[str] = mapped_column(String(80), nullable=False)
    canonical_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    __table_args__ = (
        UniqueConstraint("user_id", "provider_id", "external_symbol", name="uq_fh_rate_selection_item"),
    )


class ExchangeRateFetchRun(FlowHubBase):
    __tablename__ = "fh_exchange_rate_fetch_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    provider_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    diagnostics_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
