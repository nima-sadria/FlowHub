from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.flowhub.data_layer.models import DlSourceReadReservation
from app.flowhub.database import FlowHubBase
from app.flowhub.rate_limit.service import RateLimitService
from app.flowhub.setup.service import AppConfigService
from app.flowhub.sources.spreadsheet_source import SpreadsheetSourceReadService


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    FlowHubBase.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _configure(db: Session, *, limit: int, policy_limit: int = 10) -> None:
    AppConfigService(db).set_many(
        {
            "rate_limit.read_requests_per_minute": str(limit),
            "rate_limit.write_requests_per_minute": "30",
            "nextcloud.source_read_policy": (
                '{"enabled": true, "manual_read_allowed": true, '
                f'"max_reads_per_24h": {policy_limit}'
                "}"
            ),
        }
    )


def _reservation(db: Session, source_id: str, index: int) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=index)
    db.add(
        DlSourceReadReservation(
            id=f"reservation-{source_id}-{index}",
            source_id=source_id,
            user_id="owner",
            reserved_at=now,
            completed_at=now,
            status="succeeded",
        )
    )
    db.commit()


def test_default_limit_10_is_reported_from_canonical_setting(db: Session):
    _configure(db, limit=10, policy_limit=999)

    quota = SpreadsheetSourceReadService(db).read_quota_contract(source_id="source-a")

    assert quota["limit"] == 10
    assert quota["usage"] == 0
    assert quota["reset_at"] is None


def test_changing_limit_updates_existing_window_and_allows_existing_usage(db: Session):
    _configure(db, limit=10)
    for index in range(10):
        _reservation(db, "source-a", index)

    before = SpreadsheetSourceReadService(db).read_quota_contract(source_id="source-a")
    assert before["limit"] == 10
    assert before["exhausted"] is True

    RateLimitService(db).update_settings(50, 30, updated_by="owner")
    after = SpreadsheetSourceReadService(db).read_quota_contract(source_id="source-a")

    assert after["limit"] == 50
    assert after["usage"] == 10
    assert after["remaining"] == 40
    assert after["exhausted"] is False
    assert after["reset_at"] is not None


def test_lowering_limit_is_deterministic_and_error_reports_effective_state(db: Session):
    _configure(db, limit=50)
    for index in range(10):
        _reservation(db, "source-a", index)

    RateLimitService(db).update_settings(5, 30, updated_by="owner")
    service = SpreadsheetSourceReadService(db)
    quota = service.read_quota_contract(source_id="source-a")

    assert quota["limit"] == 5
    assert quota["usage"] == 10
    assert quota["remaining"] == 0
    with pytest.raises(Exception) as raised:
        service.check_read_allowed(manual=True, source_id="source-a")
    detail = raised.value.detail
    assert detail["code"] == "SOURCE_READ_LIMIT_REACHED"
    assert detail["limit"] == 5
    assert detail["usage"] == 10
    assert detail["reset_at"] == quota["reset_at"]


def test_restart_reads_same_persisted_canonical_setting_and_scopes_usage_by_source(db: Session):
    _configure(db, limit=50, policy_limit=10)
    _reservation(db, "source-a", 1)
    _reservation(db, "source-b", 2)

    restarted = SpreadsheetSourceReadService(db)

    assert restarted.read_quota_contract(source_id="source-a")["usage"] == 1
    assert restarted.read_quota_contract(source_id="source-b")["usage"] == 1
    assert restarted.read_quota_contract(source_id="source-a")["limit"] == 50
