"""Authoritative, timezone-aware provider request budgeting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from .models import ExchangeRateProviderConfig
from .provider import ExchangeRateProviderError


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def local_budget_date(now: datetime, timezone_name: str) -> date:
    aware = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    return aware.astimezone(zone).date()


@dataclass(frozen=True)
class BudgetSnapshot:
    budget_date: date
    attempted: int
    completed: int
    provider_daily: int | None
    provider_hourly: int | None
    provider_monthly: int | None
    effective_usage: int
    configured_limit: int
    reserve: int
    safe_limit: int
    safe_remaining: int
    discrepancy: int | None


class ExchangeRateBudgetService:
    """Atomically reserves every Navasan request before external I/O."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _reset_if_needed(self, provider_id: str, *, now: datetime) -> date:
        provider = self.db.get(ExchangeRateProviderConfig, provider_id)
        if provider is None:
            raise ExchangeRateProviderError("provider_not_configured", "Exchange-rate provider is not configured.")
        today = local_budget_date(now, provider.schedule_timezone)
        self.db.execute(
            update(ExchangeRateProviderConfig)
            .where(
                ExchangeRateProviderConfig.provider_id == provider_id,
                or_(
                    ExchangeRateProviderConfig.request_count_date.is_(None),
                    ExchangeRateProviderConfig.request_count_date != today,
                ),
            )
            .values(
                request_count_date=today,
                request_count=0,
                request_completed_count=0,
                provider_daily_usage=None,
                provider_hourly_usage=None,
                provider_monthly_usage=None,
                provider_last_use=None,
                usage_reconciled_at=None,
                usage_status="unknown",
                usage_error_code=None,
            )
        )
        self.db.commit()
        return today

    def snapshot(self, provider_id: str, *, now: datetime | None = None) -> BudgetSnapshot:
        current = now or utcnow()
        today = self._reset_if_needed(provider_id, now=current)
        provider = self.db.get(ExchangeRateProviderConfig, provider_id)
        assert provider is not None
        internal = int(provider.request_count or 0)
        provider_daily = provider.provider_daily_usage
        effective = max(internal, int(provider_daily or 0))
        safe_limit = max(0, provider.daily_request_limit - provider.reserved_request_count)
        return BudgetSnapshot(
            budget_date=today,
            attempted=internal,
            completed=int(provider.request_completed_count or 0),
            provider_daily=provider_daily,
            provider_hourly=provider.provider_hourly_usage,
            provider_monthly=provider.provider_monthly_usage,
            effective_usage=effective,
            configured_limit=provider.daily_request_limit,
            reserve=provider.reserved_request_count,
            safe_limit=safe_limit,
            safe_remaining=max(0, safe_limit - effective),
            discrepancy=(abs(internal - provider_daily) if provider_daily is not None else None),
        )

    def reserve(self, provider_id: str, *, kind: str, now: datetime | None = None) -> BudgetSnapshot:
        del kind  # The kind is intentionally not persisted with credentials or URLs.
        current = now or utcnow()
        self._reset_if_needed(provider_id, now=current)
        for _ in range(5):
            provider = self.db.get(ExchangeRateProviderConfig, provider_id)
            assert provider is not None
            internal = int(provider.request_count or 0)
            provider_daily = provider.provider_daily_usage
            effective = max(internal, int(provider_daily or 0))
            safe_limit = max(0, provider.daily_request_limit - provider.reserved_request_count)
            if safe_limit < 1 or effective >= safe_limit:
                raise ExchangeRateProviderError(
                    "budget_exhausted",
                    "The configured safe provider request budget has been reached.",
                )
            daily_clause = (
                ExchangeRateProviderConfig.provider_daily_usage.is_(None)
                if provider_daily is None
                else ExchangeRateProviderConfig.provider_daily_usage == provider_daily
            )
            result = self.db.execute(
                update(ExchangeRateProviderConfig)
                .where(
                    ExchangeRateProviderConfig.provider_id == provider_id,
                    ExchangeRateProviderConfig.request_count_date == provider.request_count_date,
                    ExchangeRateProviderConfig.request_count == internal,
                    daily_clause,
                )
                .values(request_count=internal + 1)
            )
            if result.rowcount == 1:
                self.db.commit()
                return self.snapshot(provider_id, now=current)
            self.db.rollback()
            self.db.expire_all()
        raise ExchangeRateProviderError("budget_contention", "Provider request budget is busy; try again shortly.")

    def mark_completed(self, provider_id: str, *, now: datetime | None = None) -> None:
        current = now or utcnow()
        today = self._reset_if_needed(provider_id, now=current)
        self.db.execute(
            update(ExchangeRateProviderConfig)
            .where(
                ExchangeRateProviderConfig.provider_id == provider_id,
                ExchangeRateProviderConfig.request_count_date == today,
            )
            .values(
                request_completed_count=ExchangeRateProviderConfig.request_completed_count + 1
            )
        )
        self.db.commit()
