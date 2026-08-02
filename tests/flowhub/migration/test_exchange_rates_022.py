from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[3]


def config() -> Config:
    cfg = Config(str(ROOT / "alembic_flowhub.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic_flowhub"))
    return cfg


def test_previous_revision_upgrades_to_hardened_exchange_rates(tmp_path, monkeypatch):
    db_path = tmp_path / "from-021.sqlite"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", db_url)
    command.upgrade(config(), "FLOWHUB_021")
    engine = sa.create_engine(db_url)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO flowhub_users
                    (username, hashed_password, role, is_active, created_at)
                VALUES ('existing-user', 'hash', 'viewer', 1, CURRENT_TIMESTAMP)
                """
            )
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO fh_exchange_rate_selections
                    (user_id, position, provider_id, external_symbol, updated_at)
                VALUES (1, 0, 'navasan', 'usd_sell', CURRENT_TIMESTAMP)
                """
            )
        )
    command.upgrade(config(), "head")
    inspector = sa.inspect(engine)
    provider_columns = {
        column["name"]
        for column in inspector.get_columns("fh_exchange_rate_providers")
    }
    assert {
        "request_completed_count",
        "provider_daily_usage",
        "next_refresh_at",
        "refresh_lock_token",
        "runner_heartbeat_at",
    } <= provider_columns
    with engine.connect() as connection:
        canonical = connection.execute(
            sa.text(
                "SELECT canonical_code FROM fh_exchange_rate_selections WHERE user_id = 1"
            )
        ).scalar_one()
    assert canonical == "USD_TEHRAN_SELL"
    engine.dispose()


def test_exchange_rate_hardening_downgrade_and_reupgrade(tmp_path, monkeypatch):
    db_path = tmp_path / "roundtrip-022.sqlite"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", db_url)
    command.upgrade(config(), "head")
    command.downgrade(config(), "FLOWHUB_021")
    engine = sa.create_engine(db_url)
    assert "request_completed_count" not in {
        column["name"]
        for column in sa.inspect(engine).get_columns("fh_exchange_rate_providers")
    }
    command.upgrade(config(), "head")
    with engine.connect() as connection:
        assert connection.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar_one() == "FLOWHUB_023"
    engine.dispose()
