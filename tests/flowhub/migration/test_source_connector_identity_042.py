from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command

ROOT = Path(__file__).resolve().parents[3]


def _config() -> Config:
    config = Config(str(ROOT / "alembic_flowhub.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic_flowhub"))
    return config


def _seed(url: str, monkeypatch: pytest.MonkeyPatch) -> sa.Engine:
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", url)
    command.upgrade(_config(), "FLOWHUB_041")
    return sa.create_engine(url)


def _insert_fixture(engine: sa.Engine) -> None:
    now = datetime(2026, 8, 20, 9, 0, 0)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO flowhub_users "
                "(id, username, hashed_password, role, is_active, created_at) "
                "VALUES (1, 'owner', 'unused', 'admin', true, :now)"
            ),
            {"now": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO ip_connector_instances "
                "(id, connector_type, name, version, enabled, read_only, status, created_at, updated_at) "
                "VALUES "
                "('nextcloud:primary', 'nextcloud', 'Legacy', '1.0.0', false, true, 'disabled', :now, :now), "
                "('nextcloud:replacement', 'nextcloud', 'Replacement', '1.0.0', true, true, 'configured', :now, :now), "
                "('nextcloud:ambiguous', 'nextcloud', 'Ambiguous', '1.0.0', false, true, 'disabled', :now, :now)"
            ),
            {"now": now},
        )
        base = {
            "source_kind": "external",
            "worksheet_mode": "all",
            "worksheet_name": None,
            "data_start_row": 2,
            "version": 1,
            "owner_user_id": 1,
            "created_at": now,
            "updated_at": now,
        }
        connection.execute(
            sa.text(
                "INSERT INTO sc_sources "
                "(id, name, source_kind, external_source_id, worksheet_mode, worksheet_name, "
                "data_start_row, status, version, owner_user_id, created_at, updated_at) "
                "VALUES ('legacy', 'Legacy', 'external', 'nextcloud', :worksheet_mode, "
                ":worksheet_name, :data_start_row, 'active', :version, :owner_user_id, "
                ":created_at, :updated_at)"
            ),
            base,
        )
        connection.execute(
            sa.text(
                "INSERT INTO sc_sources "
                "(id, name, source_kind, external_source_id, worksheet_mode, worksheet_name, "
                "data_start_row, status, version, owner_user_id, created_at, updated_at) "
                "VALUES ('historical', 'Historical', 'external', 'nextcloud:primary', :worksheet_mode, "
                ":worksheet_name, :data_start_row, 'archived', :version, :owner_user_id, "
                ":created_at, :updated_at)"
            ),
            base,
        )


def test_flowhub_042_maps_one_legacy_profile_and_preserves_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = f"sqlite:///{(tmp_path / 'source-connector-042.sqlite').as_posix()}"
    engine = _seed(url, monkeypatch)
    _insert_fixture(engine)

    command.upgrade(_config(), "FLOWHUB_042")
    with engine.connect() as connection:
        assert connection.execute(
            sa.text("SELECT external_source_id FROM sc_sources WHERE id = 'legacy'")
        ).scalar_one() == "nextcloud:replacement"
        assert connection.execute(
            sa.text("SELECT external_source_id FROM sc_sources WHERE id = 'historical'")
        ).scalar_one() == "nextcloud:primary"
        assert connection.execute(
            sa.text("SELECT enabled FROM ip_connector_instances WHERE id = 'nextcloud:primary'")
        ).scalar_one() in (False, 0)
    engine.dispose()


@pytest.mark.postgres
def test_postgresql_041_to_042_canonicalizes_only_unambiguous_active_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = os.environ.get("FLOWHUB_TEST_POSTGRES_URL", "")
    if not url:
        pytest.skip("FLOWHUB_TEST_POSTGRES_URL is not configured")
    parsed = sa.engine.make_url(url)
    if parsed.host not in {"127.0.0.1", "localhost"} or "test" not in (
        parsed.database or ""
    ).lower():
        pytest.fail("FLOWHUB_TEST_POSTGRES_URL must reference a local disposable test database")
    engine = sa.create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(sa.text("DROP SCHEMA public CASCADE"))
            connection.execute(sa.text("CREATE SCHEMA public"))
        _seed(url, monkeypatch).dispose()
        _insert_fixture(engine)
        command.upgrade(_config(), "FLOWHUB_042")
        with engine.connect() as connection:
            assert connection.execute(
                sa.text("SELECT external_source_id FROM sc_sources WHERE id = 'legacy'")
            ).scalar_one() == "nextcloud:replacement"
            assert connection.execute(
                sa.text("SELECT external_source_id FROM sc_sources WHERE id = 'historical'")
            ).scalar_one() == "nextcloud:primary"
            assert connection.execute(
                sa.text("SELECT COUNT(*) FROM sc_sources WHERE external_source_id = 'nextcloud:replacement'")
            ).scalar_one() == 1
    finally:
        engine.dispose()
