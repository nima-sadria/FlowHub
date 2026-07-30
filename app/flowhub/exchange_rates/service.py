"""Exchange-rate orchestration, scheduling, persistence, and safety controls."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, time, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.flowhub.setup.service import AppConfigService

from .budget import ExchangeRateBudgetService, utcnow
from .models import (
    ExchangeRateDefinition,
    ExchangeRateFetchRun,
    ExchangeRateProviderConfig,
    ExchangeRateSelection,
    ExchangeRateSnapshot,
)
from .provider import ExchangeRateProviderError, ProviderUsage
from .registry import ExchangeRateProviderRegistry, default_provider_registry


DEFAULT_DEFINITIONS = [
    ("usd_sell", "USD_TEHRAN_SELL", "USD Tehran Sell", "فروش دلار تهران", "market", "sell", "IRR"),
    ("usd_buy", "USD_TEHRAN_BUY", "USD Tehran Buy", "خرید دلار تهران", "market", "buy", "IRR"),
    ("aed_sell", "AED_DUBAI_SELL", "AED Dubai Sell", "فروش درهم دبی", "market", "sell", "IRR"),
    ("eur", "EUR_MARKET", "EUR Market", "یورو بازار", "market", None, "IRR"),
    ("gbp", "GBP_MARKET", "GBP Market", "پوند بازار", "market", None, "IRR"),
    ("cad", "CAD_MARKET", "CAD Market", "دلار کانادا", "market", None, "IRR"),
    ("aud", "AUD_MARKET", "AUD Market", "دلار استرالیا", "market", None, "IRR"),
    ("try", "TRY_MARKET", "TRY Market", "لیر ترکیه", "market", None, "IRR"),
    ("sekkeh", "GOLD_COIN_IMAMI", "Imami Coin", "سکه امامی", "gold", None, "IRR"),
    ("18ayar", "GOLD_18K", "18K Gold", "طلای ۱۸ عیار", "gold", None, "IRR"),
    ("usdt", "USDT", "USDT", "تتر", "crypto", None, "IRR"),
    ("btc", "BTC", "Bitcoin", "بیت‌کوین", "crypto", None, "IRR"),
    ("eth", "ETH", "Ethereum", "اتریوم", "crypto", None, "IRR"),
]

USAGE_SYNC_INTERVAL = timedelta(hours=24)
LOCK_TTL = timedelta(minutes=5)
STALE_AFTER = timedelta(hours=6)
DEFAULT_SELECTIONS = ("usd_sell", "eur", "aed_sell")


class ExchangeRateService:
    provider_id = "navasan"

    def __init__(
        self,
        db: Session,
        *,
        registry: ExchangeRateProviderRegistry | None = None,
    ) -> None:
        self.db = db
        self.config = AppConfigService(db)
        self.registry = registry or default_provider_registry
        self.budget = ExchangeRateBudgetService(db)

    def _configured_timezone(self) -> str:
        candidate = (
            self.config.get("server.timezone")
            or os.environ.get("FLOWHUB_TIMEZONE")
            or "UTC"
        )
        try:
            ZoneInfo(candidate)
        except ZoneInfoNotFoundError:
            return "UTC"
        return candidate

    def _api_key(self) -> str:
        # Environment is the canonical secret provider. The database-backed
        # connector configuration remains a compatibility fallback for the
        # existing Super Admin settings workflow.
        return (
            os.environ.get("FLOWHUB_NAVASAN_API_KEY")
            or self.config.get("exchange_rates.navasan.api_key")
            or ""
        ).strip()

    def has_credentials(self) -> bool:
        return bool(self._api_key())

    def ensure_provider(self) -> ExchangeRateProviderConfig:
        provider = self.db.get(ExchangeRateProviderConfig, self.provider_id)
        configured_timezone = self._configured_timezone()
        official_base_url = self.registry.official_base_url("navasan")
        if provider is None:
            provider = ExchangeRateProviderConfig(
                provider_id=self.provider_id,
                provider_type="navasan",
                display_name="Navasan",
                enabled=False,
                api_key_secret_reference="FLOWHUB_NAVASAN_API_KEY",
                base_url=official_base_url,
                request_timeout=10,
                refreshes_per_day=1,
                daily_request_limit=120,
                reserved_request_count=10,
                status="disabled",
                schedule_timezone=configured_timezone,
            )
            self.db.add(provider)
            self.db.flush()
        else:
            # Provider endpoints are registry-owned (not arbitrary user input),
            # and schedules always follow FlowHub's configured timezone.
            provider.base_url = official_base_url
            provider.schedule_timezone = configured_timezone
            provider.api_key_secret_reference = "FLOWHUB_NAVASAN_API_KEY"
        existing = {
            row.external_symbol
            for row in self.db.scalars(
                select(ExchangeRateDefinition).where(
                    ExchangeRateDefinition.provider_id == self.provider_id
                )
            )
        }
        for symbol, canonical, name, name_fa, classification, side, unit in DEFAULT_DEFINITIONS:
            if symbol not in existing:
                self.db.add(
                    ExchangeRateDefinition(
                        id=f"{self.provider_id}:{symbol}",
                        provider_id=self.provider_id,
                        external_symbol=symbol,
                        canonical_code=canonical,
                        display_name=name,
                        display_name_fa=name_fa,
                        classification=classification,
                        side=side,
                        unit=unit,
                    )
                )
        self.db.commit()
        return provider

    def _provider(self, provider: ExchangeRateProviderConfig):
        return self.registry.build(
            provider.provider_type,
            api_key=self._api_key(),
            base_url=provider.base_url,
            timeout=provider.request_timeout,
        )

    def definitions(self) -> list[ExchangeRateDefinition]:
        self.ensure_provider()
        return list(
            self.db.scalars(
                select(ExchangeRateDefinition)
                .where(
                    ExchangeRateDefinition.provider_id == self.provider_id,
                    ExchangeRateDefinition.active.is_(True),
                )
                .order_by(ExchangeRateDefinition.display_name)
            )
        )

    def selections(self, user_id: int) -> list[ExchangeRateSelection]:
        rows = list(
            self.db.scalars(
                select(ExchangeRateSelection)
                .where(ExchangeRateSelection.user_id == user_id)
                .order_by(ExchangeRateSelection.position)
            )
        )
        if (
            [row.position for row in rows] == [0, 1, 2]
            and len({(row.provider_id, row.external_symbol) for row in rows}) == 3
        ):
            return rows
        self.db.execute(
            delete(ExchangeRateSelection).where(
                ExchangeRateSelection.user_id == user_id
            )
        )
        definitions = {
            row.external_symbol: row for row in self.definitions()
        }
        rows = [
            ExchangeRateSelection(
                user_id=user_id,
                position=position,
                provider_id=self.provider_id,
                external_symbol=symbol,
                canonical_code=definitions[symbol].canonical_code,
            )
            for position, symbol in enumerate(DEFAULT_SELECTIONS)
        ]
        self.db.add_all(rows)
        self.db.commit()
        return rows

    def update_selections(
        self, user_id: int, symbols: list[str]
    ) -> list[ExchangeRateSelection]:
        normalized = [symbol.strip() for symbol in symbols]
        if len(normalized) != 3 or len(set(normalized)) != 3:
            raise ValueError("Exactly three distinct exchange rates must be selected.")
        supported = {row.external_symbol: row for row in self.definitions()}
        if any(symbol not in supported for symbol in normalized):
            raise ValueError("One or more selected exchange rates are not supported.")
        self.db.execute(
            delete(ExchangeRateSelection).where(
                ExchangeRateSelection.user_id == user_id
            )
        )
        rows = [
            ExchangeRateSelection(
                user_id=user_id,
                position=position,
                provider_id=self.provider_id,
                external_symbol=symbol,
                canonical_code=supported[symbol].canonical_code,
                updated_at=utcnow(),
            )
            for position, symbol in enumerate(normalized)
        ]
        self.db.add_all(rows)
        self.db.commit()
        return rows

    def _latest_by_canonical(
        self, canonical_codes: list[str]
    ) -> dict[str, ExchangeRateSnapshot]:
        result: dict[str, ExchangeRateSnapshot] = {}
        for canonical_code in canonical_codes:
            row = self.db.scalar(
                select(ExchangeRateSnapshot)
                .where(ExchangeRateSnapshot.canonical_code == canonical_code)
                .order_by(ExchangeRateSnapshot.fetched_at.desc())
            )
            if row is not None:
                result[canonical_code] = row
        return result

    def latest_for_user(self, user_id: int) -> list[dict]:
        provider = self.ensure_provider()
        selections = self.selections(user_id)
        definitions = {
            row.external_symbol: row for row in self.definitions()
        }
        canonical_codes = [
            selection.canonical_code
            or definitions[selection.external_symbol].canonical_code
            for selection in selections
        ]
        snapshots = self._latest_by_canonical(canonical_codes)
        return [
            self._serialize(
                snapshots.get(canonical_code),
                definitions.get(selection.external_symbol),
                selection.position,
                enabled=provider.enabled,
            )
            for selection, canonical_code in zip(selections, canonical_codes, strict=True)
        ]

    @staticmethod
    def _serialize(
        snapshot: ExchangeRateSnapshot | None,
        definition: ExchangeRateDefinition | None,
        position: int,
        *,
        enabled: bool,
    ) -> dict:
        status = "unavailable"
        if snapshot is not None:
            status = (
                "fresh"
                if utcnow() - snapshot.fetched_at <= STALE_AFTER
                else "stale"
            )
            if not enabled:
                status = "disabled"
        elif not enabled:
            status = "disabled"
        return {
            "position": position,
            "provider": snapshot.provider_id
            if snapshot
            else (definition.provider_id if definition else ""),
            "external_symbol": snapshot.external_symbol
            if snapshot
            else (definition.external_symbol if definition else ""),
            "canonical_code": snapshot.canonical_code
            if snapshot
            else (definition.canonical_code if definition else ""),
            "display_name": snapshot.display_name
            if snapshot
            else (definition.display_name if definition else ""),
            "display_name_fa": snapshot.display_name_fa
            if snapshot
            else (definition.display_name_fa if definition else ""),
            "classification": snapshot.classification
            if snapshot
            else (definition.classification if definition else "market"),
            "side": snapshot.side if snapshot else (definition.side if definition else None),
            "value": str(snapshot.value) if snapshot else None,
            "unit": snapshot.unit
            if snapshot
            else (definition.unit if definition else "IRR"),
            "change": str(snapshot.change)
            if snapshot and snapshot.change is not None
            else None,
            "provider_timestamp": snapshot.provider_timestamp.isoformat()
            if snapshot and snapshot.provider_timestamp
            else None,
            "fetched_at": snapshot.fetched_at.isoformat() if snapshot else None,
            "status": status,
            "snapshot_id": snapshot.id if snapshot else None,
        }

    def _acquire_refresh_lock(self, *, now: datetime) -> str | None:
        token = uuid4().hex
        result = self.db.execute(
            update(ExchangeRateProviderConfig)
            .where(
                ExchangeRateProviderConfig.provider_id == self.provider_id,
                or_(
                    ExchangeRateProviderConfig.refresh_lock_until.is_(None),
                    ExchangeRateProviderConfig.refresh_lock_until <= now,
                ),
            )
            .values(
                refresh_lock_until=now + LOCK_TTL,
                refresh_lock_token=token,
            )
        )
        self.db.commit()
        return token if result.rowcount == 1 else None

    def _release_refresh_lock(self, token: str) -> None:
        self.db.execute(
            update(ExchangeRateProviderConfig)
            .where(
                ExchangeRateProviderConfig.provider_id == self.provider_id,
                ExchangeRateProviderConfig.refresh_lock_token == token,
            )
            .values(refresh_lock_until=None, refresh_lock_token=None)
        )
        self.db.commit()

    @staticmethod
    def _interval(provider: ExchangeRateProviderConfig) -> timedelta:
        return timedelta(seconds=86400 / max(1, provider.refreshes_per_day))

    def _schedule_failure(
        self,
        provider: ExchangeRateProviderConfig,
        *,
        now: datetime,
        error_code: str,
    ) -> None:
        provider.consecutive_failures = int(provider.consecutive_failures or 0) + 1
        if error_code == "authentication_failed":
            provider.authentication_blocked = True
            provider.next_refresh_at = None
            return
        if error_code == "budget_exhausted":
            provider.next_refresh_at = self._next_budget_reset(provider)
            return
        interval = self._interval(provider)
        if provider.consecutive_failures <= 3:
            backoff = timedelta(
                minutes=min(60, 5 * (2 ** (provider.consecutive_failures - 1)))
            )
            provider.next_refresh_at = now + min(interval, backoff)
        else:
            provider.next_refresh_at = now + interval

    def refresh(self, *, trigger: str = "manual") -> dict:
        provider = self.ensure_provider()
        if not provider.enabled:
            return {"status": "disabled", "records": 0}
        if not self.has_credentials():
            return {"status": "unavailable", "error_code": "missing_credentials", "records": 0}
        if provider.authentication_blocked:
            return {
                "status": "blocked",
                "error_code": "authentication_failed",
                "records": 0,
            }
        now = utcnow()
        lock_token = self._acquire_refresh_lock(now=now)
        if lock_token is None:
            return {"status": "already_running", "records": 0}
        run = ExchangeRateFetchRun(
            provider_id=self.provider_id,
            status="running",
            started_at=now,
            request_count=0,
            diagnostics_json={"trigger": trigger},
        )
        self.db.add(run)
        self.db.commit()
        try:
            self.budget.reserve(self.provider_id, kind=f"{trigger}_refresh", now=now)
            run.request_count = 1
            adapter = self._provider(provider)
            data = adapter.fetch_latest_rates()
            self.budget.mark_completed(self.provider_id, now=now)
            definitions = {
                row.external_symbol: row for row in self.definitions()
            }
            normalized_count = 0
            inserted_count = 0
            fetched_at = utcnow()
            for item in data:
                definition = definitions.get(item.external_symbol)
                if definition is None:
                    continue
                normalized_count += 1
                fingerprint = hashlib.sha256(
                    "|".join(
                        (
                            self.provider_id,
                            item.external_symbol,
                            item.provider_timestamp.isoformat()
                            if item.provider_timestamp
                            else "",
                            str(item.value),
                            str(item.change) if item.change is not None else "",
                        )
                    ).encode("utf-8")
                ).hexdigest()
                if self.db.scalar(
                    select(ExchangeRateSnapshot.id).where(
                        ExchangeRateSnapshot.source_key == fingerprint
                    )
                ):
                    continue
                self.db.add(
                    ExchangeRateSnapshot(
                        id=str(uuid4()),
                        provider_id=self.provider_id,
                        external_symbol=item.external_symbol,
                        canonical_code=definition.canonical_code,
                        display_name=definition.display_name,
                        display_name_fa=definition.display_name_fa,
                        value=item.value,
                        unit=definition.unit,
                        classification=definition.classification,
                        side=definition.side,
                        change=item.change,
                        provider_timestamp=item.provider_timestamp,
                        fetched_at=fetched_at,
                        status="fresh",
                        raw_reference=None,
                        source_key=fingerprint,
                    )
                )
                inserted_count += 1
            if normalized_count == 0:
                raise ExchangeRateProviderError(
                    "partial_response",
                    "The provider returned no configured rate items.",
                )
            provider = self.db.get(ExchangeRateProviderConfig, self.provider_id)
            assert provider is not None
            missing = max(0, len(definitions) - normalized_count)
            provider.status = "degraded" if missing else "healthy"
            provider.last_success_at = fetched_at
            provider.last_error = "partial_response" if missing else None
            provider.consecutive_failures = 0
            provider.authentication_blocked = False
            provider.next_refresh_at = fetched_at + self._interval(provider)
            if trigger == "scheduled":
                provider.last_scheduled_refresh_at = fetched_at
            run.status = "partial" if missing else "success"
            run.records_fetched = normalized_count
            run.finished_at = fetched_at
            run.diagnostics_json = {
                "trigger": trigger,
                "inserted": inserted_count,
                "missing_configured_items": missing,
            }
            self.db.commit()
            return {
                "status": run.status,
                "records": normalized_count,
                "inserted": inserted_count,
                "trigger": trigger,
            }
        except ExchangeRateProviderError as exc:
            if exc.status is not None:
                self.budget.mark_completed(self.provider_id, now=now)
            provider = self.db.get(ExchangeRateProviderConfig, self.provider_id)
            assert provider is not None
            provider.status = "error"
            provider.last_failure_at = utcnow()
            provider.last_error = exc.code
            self._schedule_failure(
                provider, now=utcnow(), error_code=exc.code
            )
            run.status = "failed"
            run.error_code = exc.code
            run.error_message = str(exc)
            run.finished_at = utcnow()
            self.db.commit()
            return {"status": "failed", "error_code": exc.code, "records": 0}
        except Exception:
            # Persist a bounded, credential-free failure state even if local
            # normalization or persistence fails after the provider response.
            self.db.rollback()
            provider = self.db.get(ExchangeRateProviderConfig, self.provider_id)
            assert provider is not None
            provider.status = "error"
            provider.last_failure_at = utcnow()
            provider.last_error = "internal_refresh_error"
            self._schedule_failure(
                provider, now=utcnow(), error_code="internal_refresh_error"
            )
            run = self.db.get(ExchangeRateFetchRun, run.id)
            if run is not None:
                run.status = "failed"
                run.error_code = "internal_refresh_error"
                run.error_message = "Exchange-rate refresh failed during local processing."
                run.finished_at = utcnow()
            self.db.commit()
            return {
                "status": "failed",
                "error_code": "internal_refresh_error",
                "records": 0,
            }
        finally:
            self._release_refresh_lock(lock_token)

    def test_connection(self) -> dict:
        provider = self.ensure_provider()
        if not provider.enabled or not self.has_credentials():
            raise ExchangeRateProviderError(
                "provider_unavailable",
                "The exchange-rate provider is not enabled and configured.",
            )
        if provider.authentication_blocked:
            raise ExchangeRateProviderError(
                "authentication_failed",
                "Provider authentication must be reconfigured before retrying.",
            )
        now = utcnow()
        lock_token = self._acquire_refresh_lock(now=now)
        if lock_token is None:
            raise ExchangeRateProviderError(
                "already_running", "Another provider operation is already running."
            )
        try:
            self.budget.reserve(self.provider_id, kind="test_connection", now=now)
            self._provider(provider).test_connection()
            self.budget.mark_completed(self.provider_id, now=now)
            return {"ok": True, "status": "healthy"}
        except ExchangeRateProviderError as exc:
            if exc.status is not None:
                self.budget.mark_completed(self.provider_id, now=now)
            if exc.code == "authentication_failed":
                provider = self.db.get(ExchangeRateProviderConfig, self.provider_id)
                assert provider is not None
                provider.authentication_blocked = True
                provider.status = "error"
                provider.last_error = exc.code
                provider.next_refresh_at = None
                self.db.commit()
            raise
        finally:
            self._release_refresh_lock(lock_token)

    def sync_usage(self, *, force: bool = False) -> dict:
        provider = self.ensure_provider()
        now = utcnow()
        if not provider.enabled or not self.has_credentials():
            return {"status": "skipped", "reason": "provider_unavailable"}
        if provider.authentication_blocked:
            return {"status": "skipped", "reason": "authentication_failed"}
        if (
            not force
            and provider.usage_next_sync_at is not None
            and provider.usage_next_sync_at > now
        ):
            return {"status": "cached"}
        lock_token = self._acquire_refresh_lock(now=now)
        if lock_token is None:
            return {"status": "already_running"}
        try:
            self.budget.reserve(self.provider_id, kind="usage", now=now)
            usage: ProviderUsage = self._provider(provider).fetch_usage()
            self.budget.mark_completed(self.provider_id, now=now)
            provider = self.db.get(ExchangeRateProviderConfig, self.provider_id)
            assert provider is not None
            provider.provider_daily_usage = usage.daily_usage
            provider.provider_hourly_usage = usage.hourly_usage
            provider.provider_monthly_usage = usage.monthly_usage
            provider.provider_last_use = usage.last_use
            provider.usage_reconciled_at = utcnow()
            provider.usage_next_sync_at = utcnow() + USAGE_SYNC_INTERVAL
            provider.usage_status = "reconciled"
            provider.usage_error_code = None
            self.db.commit()
            return {"status": "reconciled"}
        except ExchangeRateProviderError as exc:
            if exc.status is not None:
                self.budget.mark_completed(self.provider_id, now=now)
            provider = self.db.get(ExchangeRateProviderConfig, self.provider_id)
            assert provider is not None
            provider.usage_status = "stale" if provider.usage_reconciled_at else "error"
            provider.usage_error_code = exc.code
            provider.usage_next_sync_at = (
                None
                if exc.code == "authentication_failed"
                else utcnow() + timedelta(hours=1)
            )
            if exc.code == "authentication_failed":
                provider.authentication_blocked = True
            self.db.commit()
            return {"status": provider.usage_status, "error_code": exc.code}
        finally:
            self._release_refresh_lock(lock_token)

    def scheduler_tick(self) -> dict:
        provider = self.ensure_provider()
        now = utcnow()
        if not provider.enabled:
            provider.next_refresh_at = None
            provider.status = "disabled"
            self.db.commit()
            return {"status": "disabled"}
        if not self.has_credentials():
            provider.next_refresh_at = None
            provider.status = "unavailable"
            provider.last_error = "missing_credentials"
            self.db.commit()
            return {"status": "unavailable"}
        if provider.authentication_blocked:
            provider.next_refresh_at = None
            self.db.commit()
            return {"status": "blocked"}
        usage_result = self.sync_usage(force=False)
        provider = self.db.get(ExchangeRateProviderConfig, self.provider_id)
        assert provider is not None
        if provider.next_refresh_at is None:
            provider.next_refresh_at = now
            self.db.commit()
        if provider.next_refresh_at > now:
            return {
                "status": "not_due",
                "next_refresh_at": provider.next_refresh_at.isoformat(),
                "usage": usage_result["status"],
            }
        result = self.refresh(trigger="scheduled")
        result["usage"] = usage_result["status"]
        return result

    def _next_budget_reset(self, provider: ExchangeRateProviderConfig) -> datetime:
        try:
            zone = ZoneInfo(provider.schedule_timezone)
        except ZoneInfoNotFoundError:
            zone = ZoneInfo("UTC")
        now_aware = datetime.now(timezone.utc)
        local_now = now_aware.astimezone(zone)
        next_day = local_now.date() + timedelta(days=1)
        return datetime.combine(next_day, time.min, tzinfo=zone).astimezone(
            timezone.utc
        ).replace(tzinfo=None)

    def diagnostics(self) -> dict:
        provider = self.ensure_provider()
        budget = self.budget.snapshot(self.provider_id)
        next_eligible = (
            self._next_budget_reset(provider)
            if budget.safe_remaining == 0
            else provider.next_refresh_at
        )
        return {
            **self.admin_config(),
            "status": provider.status,
            "estimated_scheduled_usage": provider.refreshes_per_day + 1,
            "safe_scheduled_limit": max(
                0, provider.daily_request_limit - provider.reserved_request_count - 1
            ),
            "internal_daily_usage": budget.attempted,
            "internal_completed_usage": budget.completed,
            "provider_usage": {
                "daily_usage": budget.provider_daily,
                "hourly_usage": budget.provider_hourly,
                "monthly_usage": budget.provider_monthly,
                "last_use": provider.provider_last_use,
            },
            "effective_usage": budget.effective_usage,
            "remaining_safe_requests": budget.safe_remaining,
            "usage_discrepancy": budget.discrepancy,
            "usage_reconciliation_status": provider.usage_status,
            "usage_reconciled_at": provider.usage_reconciled_at.isoformat()
            if provider.usage_reconciled_at
            else None,
            "usage_error_code": provider.usage_error_code,
            "last_success_at": provider.last_success_at.isoformat()
            if provider.last_success_at
            else None,
            "last_failure_at": provider.last_failure_at.isoformat()
            if provider.last_failure_at
            else None,
            "last_error": provider.last_error,
            "next_scheduled_refresh": provider.next_refresh_at.isoformat()
            if provider.next_refresh_at
            else None,
            "next_eligible_refresh": next_eligible.isoformat()
            if next_eligible
            else None,
            "runner_state": provider.runner_state,
            "runner_heartbeat_at": provider.runner_heartbeat_at.isoformat()
            if provider.runner_heartbeat_at
            else None,
        }

    def admin_config(self) -> dict:
        provider = self.ensure_provider()
        return {
            "provider_id": provider.provider_id,
            "provider_type": provider.provider_type,
            "display_name": provider.display_name,
            "enabled": provider.enabled,
            "base_url": provider.base_url,
            "request_timeout": provider.request_timeout,
            "refreshes_per_day": provider.refreshes_per_day,
            "daily_request_limit": provider.daily_request_limit,
            "reserved_request_count": provider.reserved_request_count,
            "schedule_timezone": provider.schedule_timezone,
            "api_key_configured": self.has_credentials(),
            "api_key_masked": "********" if self.has_credentials() else "",
        }

    def update_admin_config(self, values: dict, updated_by: str) -> dict:
        provider = self.ensure_provider()
        refreshes = int(values.get("refreshes_per_day", provider.refreshes_per_day))
        daily_limit = int(values.get("daily_request_limit", provider.daily_request_limit))
        reserve = int(values.get("reserved_request_count", provider.reserved_request_count))
        safe_refresh_limit = daily_limit - reserve - 1  # one budgeted usage reconciliation/day
        if (
            daily_limit < 2
            or reserve < 0
            or reserve >= daily_limit
            or refreshes < 1
            or refreshes > safe_refresh_limit
        ):
            raise ValueError(
                "Refresh frequency must fit within the safe daily budget after the usage reconciliation allowance."
            )
        provider.enabled = bool(values.get("enabled", provider.enabled))
        provider.refreshes_per_day = refreshes
        provider.daily_request_limit = daily_limit
        provider.reserved_request_count = reserve
        provider.request_timeout = max(
            2, min(int(values.get("request_timeout", provider.request_timeout)), 30)
        )
        provider.base_url = self.registry.official_base_url(provider.provider_type)
        provider.schedule_timezone = self._configured_timezone()
        submitted_key = str(values.get("api_key") or "").strip()
        if submitted_key:
            self.config.set(
                "exchange_rates.navasan.api_key",
                submitted_key,
                updated_by=updated_by,
            )
            provider.authentication_blocked = False
            provider.usage_next_sync_at = None
        provider.status = "configured" if provider.enabled else "disabled"
        provider.next_refresh_at = utcnow() if provider.enabled and self.has_credentials() else None
        provider.updated_at = utcnow()
        self.db.commit()
        return self.admin_config()
