from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal
from threading import Event

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.flowhub.database import FlowHubBase
from app.flowhub.exchange_rates.budget import ExchangeRateBudgetService, local_budget_date
from app.flowhub.exchange_rates.models import (
    ExchangeRateProviderConfig,
    ExchangeRateSnapshot,
)
from app.flowhub.exchange_rates.provider import (
    ExchangeRateProviderError,
    ProviderRate,
    ProviderUsage,
)
from app.flowhub.exchange_rates.registry import (
    ExchangeRateProviderRegistry,
    ProviderRegistration,
)
from app.flowhub.exchange_rates.runner import ExchangeRateRunner
from app.flowhub.exchange_rates.service import ExchangeRateService


class FakeProvider:
    provider_id = "fake"

    def __init__(
        self,
        *,
        rates: list[ProviderRate] | None = None,
        usage: ProviderUsage | None = None,
        error: ExchangeRateProviderError | None = None,
    ) -> None:
        self.rates = rates or [
            ProviderRate("usd_sell", Decimal("123.45"), Decimal("1.25"), datetime(2026, 1, 1))
        ]
        self.usage = usage or ProviderUsage(2, 1, 9, "2026-01-01 10:00:00")
        self.error = error
        self.latest_calls = 0
        self.usage_calls = 0

    def list_supported_rates(self) -> list[str]:
        return [rate.external_symbol for rate in self.rates]

    def fetch_latest_rates(self) -> list[ProviderRate]:
        self.latest_calls += 1
        if self.error:
            raise self.error
        return self.rates

    def fetch_usage(self) -> ProviderUsage:
        self.usage_calls += 1
        if self.error:
            raise self.error
        return self.usage

    def test_connection(self) -> None:
        if self.error:
            raise self.error


def make_db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    FlowHubBase.metadata.create_all(engine)
    return Session(engine)


def registry_for(fake: FakeProvider) -> ExchangeRateProviderRegistry:
    registry = ExchangeRateProviderRegistry()
    registry.register(
        ProviderRegistration(
            provider_type="navasan",
            official_base_url="https://api.navasan.tech",
            factory=lambda _key, _url, _timeout: fake,
        )
    )
    return registry


def configured_service(
    db: Session,
    fake: FakeProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> ExchangeRateService:
    monkeypatch.setenv("FLOWHUB_NAVASAN_API_KEY", "mock-only")
    service = ExchangeRateService(db, registry=registry_for(fake))
    provider = service.ensure_provider()
    provider.enabled = True
    provider.status = "configured"
    db.commit()
    return service


def test_effective_budget_uses_safer_higher_provider_count():
    db = make_db()
    service = ExchangeRateService(db)
    provider = service.ensure_provider()
    provider.daily_request_limit = 12
    provider.reserved_request_count = 2
    provider.request_count = 3
    provider.provider_daily_usage = 8
    provider.request_count_date = local_budget_date(datetime.utcnow(), provider.schedule_timezone)
    db.commit()
    snapshot = service.budget.snapshot(provider.provider_id)
    assert snapshot.effective_usage == 8
    assert snapshot.safe_remaining == 2
    assert snapshot.discrepancy == 5

    provider.request_count = 9
    provider.provider_daily_usage = 4
    db.commit()
    snapshot = service.budget.snapshot(provider.provider_id)
    assert snapshot.effective_usage == 9
    assert snapshot.safe_remaining == 1


def test_budget_day_reset_uses_configured_timezone():
    assert local_budget_date(
        datetime(2026, 1, 1, 20, 31), "Asia/Tehran"
    ).isoformat() == "2026-01-02"
    db = make_db()
    service = ExchangeRateService(db)
    provider = service.ensure_provider()
    provider.schedule_timezone = "Asia/Tehran"
    provider.request_count_date = datetime(2026, 1, 1).date()
    provider.request_count = 7
    provider.request_completed_count = 5
    provider.provider_daily_usage = 9
    db.commit()
    snapshot = service.budget.snapshot(
        provider.provider_id, now=datetime(2026, 1, 1, 20, 31)
    )
    assert snapshot.budget_date.isoformat() == "2026-01-02"
    assert snapshot.attempted == 0
    assert snapshot.completed == 0
    assert snapshot.provider_daily is None


def test_usage_reconciliation_is_cached_and_preserves_discrepancy(monkeypatch):
    db = make_db()
    fake = FakeProvider(usage=ProviderUsage(7, 2, 30, "2026-01-01 11:00:00"))
    service = configured_service(db, fake, monkeypatch)
    assert service.sync_usage()["status"] == "reconciled"
    assert service.sync_usage()["status"] == "cached"
    assert fake.usage_calls == 1
    diagnostics = service.diagnostics()
    assert diagnostics["provider_usage"]["daily_usage"] == 7
    assert diagnostics["effective_usage"] == 7
    assert diagnostics["usage_reconciled_at"] is not None


@pytest.mark.parametrize(
    "error,expected_status",
    [
        (ExchangeRateProviderError("rate_limited", "limited", status=429), "error"),
        (ExchangeRateProviderError("provider_unavailable", "down", status=503), "error"),
    ],
)
def test_usage_failure_is_bounded_and_cached(
    monkeypatch, error: ExchangeRateProviderError, expected_status: str
):
    db = make_db()
    fake = FakeProvider(error=error)
    service = configured_service(db, fake, monkeypatch)
    result = service.sync_usage()
    assert result["status"] == expected_status
    provider = service.ensure_provider()
    assert provider.usage_next_sync_at is not None
    assert fake.usage_calls == 1


def test_partial_refresh_preserves_last_known_good(monkeypatch):
    db = make_db()
    fake = FakeProvider(
        rates=[
            ProviderRate("usd_sell", Decimal("100"), Decimal("1"), datetime(2026, 1, 1)),
            ProviderRate("eur", Decimal("200"), None, datetime(2026, 1, 1)),
        ]
    )
    service = configured_service(db, fake, monkeypatch)
    first = service.refresh(trigger="manual")
    assert first["records"] == 2
    fake.rates = [
        ProviderRate("usd_sell", Decimal("110"), Decimal("10"), datetime(2026, 1, 2))
    ]
    second = service.refresh(trigger="scheduled")
    assert second["status"] == "partial"
    eur = db.query(ExchangeRateSnapshot).filter_by(external_symbol="eur").order_by(
        ExchangeRateSnapshot.fetched_at.desc()
    ).first()
    assert eur is not None
    assert eur.value == Decimal("200")


def test_authentication_failure_blocks_scheduler_retries(monkeypatch):
    db = make_db()
    fake = FakeProvider(
        error=ExchangeRateProviderError(
            "authentication_failed", "invalid key", status=401
        )
    )
    service = configured_service(db, fake, monkeypatch)
    provider = service.ensure_provider()
    provider.usage_next_sync_at = datetime.utcnow() + timedelta(days=1)
    provider.next_refresh_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    first = service.scheduler_tick()
    second = service.scheduler_tick()
    assert first["error_code"] == "authentication_failed"
    assert second["status"] == "blocked"
    assert fake.latest_calls == 1


def test_scheduler_restart_executes_once_without_catch_up(monkeypatch):
    db = make_db()
    fake = FakeProvider()
    service = configured_service(db, fake, monkeypatch)
    provider = service.ensure_provider()
    provider.usage_next_sync_at = datetime.utcnow() + timedelta(days=1)
    provider.next_refresh_at = datetime.utcnow() - timedelta(days=3)
    db.commit()
    result = service.scheduler_tick()
    assert result["status"] in {"success", "partial"}
    provider = service.ensure_provider()
    assert provider.next_refresh_at is not None
    assert provider.next_refresh_at > datetime.utcnow()
    assert service.scheduler_tick()["status"] == "not_due"
    assert fake.latest_calls == 1


def test_refresh_lock_is_shared_across_sessions(tmp_path, monkeypatch):
    db_path = tmp_path / "lock.sqlite"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    FlowHubBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    started = Event()
    release = Event()

    class BlockingProvider(FakeProvider):
        def fetch_latest_rates(self) -> list[ProviderRate]:
            self.latest_calls += 1
            started.set()
            assert release.wait(timeout=5)
            return self.rates

    fake = BlockingProvider()
    registry = registry_for(fake)
    monkeypatch.setenv("FLOWHUB_NAVASAN_API_KEY", "mock-only")
    with factory() as setup_db:
        service = ExchangeRateService(setup_db, registry=registry)
        provider = service.ensure_provider()
        provider.enabled = True
        setup_db.commit()

    def refresh() -> dict:
        with factory() as db:
            return ExchangeRateService(db, registry=registry).refresh(trigger="manual")

    with ThreadPoolExecutor(max_workers=2) as pool:
        first_future = pool.submit(refresh)
        assert started.wait(timeout=5)
        second = refresh()
        release.set()
        first = first_future.result(timeout=5)
    assert second["status"] == "already_running"
    assert first["status"] in {"success", "partial"}
    assert fake.latest_calls == 1


def test_provider_registry_substitution_does_not_change_service(monkeypatch):
    db = make_db()
    fake = FakeProvider()
    service = configured_service(db, fake, monkeypatch)
    assert service._provider(service.ensure_provider()) is fake
    assert [row.canonical_code for row in service.definitions()]


def test_dedicated_runner_owns_scheduler_tick(tmp_path, monkeypatch):
    db_path = tmp_path / "runner.sqlite"
    engine = create_engine(f"sqlite:///{db_path}")
    FlowHubBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    calls: list[str] = []

    def fake_tick(self: ExchangeRateService) -> dict:
        calls.append(self.provider_id)
        return {"status": "not_due"}

    monkeypatch.setattr(ExchangeRateService, "scheduler_tick", fake_tick)
    runner = ExchangeRateRunner(
        factory, enabled=True, poll_seconds=5, runner_id="test-runner"
    )
    assert runner.run_once()["status"] == "not_due"
    with factory() as db:
        provider = db.get(ExchangeRateProviderConfig, "navasan")
        assert provider is not None
        assert provider.runner_id == "test-runner"
        assert provider.runner_state == "idle"
        assert provider.runner_heartbeat_at is not None
    assert calls == ["navasan"]
