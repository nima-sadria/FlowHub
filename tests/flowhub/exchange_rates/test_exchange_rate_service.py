from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.flowhub.auth.models import FlowHubUser
from app.flowhub.database import FlowHubBase
from app.flowhub.exchange_rates.models import ExchangeRateSelection
from app.flowhub.exchange_rates.service import ExchangeRateService
from app.flowhub.setup.models import FlowHubAppConfig


def make_db() -> Session:
    # Importing the models above registers the FK targets used by this focused
    # unit test; SQLite keeps the test deterministic and offline.
    engine = create_engine("sqlite:///:memory:")
    FlowHubBase.metadata.create_all(engine)
    return Session(engine)


def test_selections_are_per_user_ordered_and_exactly_three():
    db = make_db()
    first = FlowHubUser(username="one", hashed_password="x", role="viewer", is_active=True)
    second = FlowHubUser(username="two", hashed_password="x", role="viewer", is_active=True)
    db.add_all([first, second]); db.commit()
    service = ExchangeRateService(db)
    assert [row.external_symbol for row in service.selections(first.id)] == ["usd_sell", "eur", "aed_sell"]
    service.update_selections(first.id, ["eur", "usd_sell", "aed_sell"])
    assert [row.external_symbol for row in service.selections(first.id)] == ["eur", "usd_sell", "aed_sell"]
    assert [row.external_symbol for row in service.selections(second.id)] == ["usd_sell", "eur", "aed_sell"]
    try:
        service.update_selections(first.id, ["eur", "eur", "aed_sell"])
    except ValueError as exc:
        assert "three" in str(exc)
    else:
        raise AssertionError("duplicate selections must be rejected")
    assert db.query(ExchangeRateSelection).filter_by(user_id=first.id).count() == 3


def test_budget_respects_safety_reserve_and_secret_storage_is_configured():
    db = make_db()
    service = ExchangeRateService(db)
    provider = service.ensure_provider()
    provider.daily_request_limit = 5
    provider.reserved_request_count = 2
    db.commit()
    assert service.budget.reserve(provider.provider_id, kind="test").attempted == 1
    assert service.budget.reserve(provider.provider_id, kind="test").attempted == 2
    assert service.budget.reserve(provider.provider_id, kind="test").attempted == 3
    try:
        service.budget.reserve(provider.provider_id, kind="test")
    except Exception as exc:
        assert "budget" in str(exc)
    else:
        raise AssertionError("reserve must prevent consuming the final two requests")
    service.config.set("exchange_rates.navasan.api_key", "placeholder", updated_by="test")
    assert service.config.get_safe()["exchange_rates.navasan.api_key"] == "[REDACTED]"
