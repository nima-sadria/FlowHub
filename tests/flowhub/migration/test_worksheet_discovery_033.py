from __future__ import annotations

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command


ROOT = Path(__file__).resolve().parents[3]
NEW_TABLES = {
    "dl_source_discovery_locks",
    "dl_source_discovery_reservations",
    "dl_worksheet_discovery_cache",
    "dl_source_identity_validations",
}


def _config() -> Config:
    config = Config(str(ROOT / "alembic_flowhub.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic_flowhub"))
    return config


def _assert_upgrade_preserves_sentinel(url: str) -> None:
    command.upgrade(_config(), "FLOWHUB_032")
    engine = sa.create_engine(url)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO flowhub_app_config(key,value,updated_by) "
                "VALUES ('worksheet.discovery.sentinel','preserved','test')"
            )
        )

    command.upgrade(_config(), "FLOWHUB_033")
    with engine.begin() as connection:
        assert NEW_TABLES <= set(sa.inspect(connection).get_table_names())
        assert connection.execute(
            sa.text(
                "SELECT value FROM flowhub_app_config "
                "WHERE key='worksheet.discovery.sentinel'"
            )
        ).scalar_one() == "preserved"
    engine.dispose()


def test_flowhub_033_is_explicit_additive_and_forward_only() -> None:
    source = (
        ROOT / "alembic_flowhub/versions/flowhub_033_worksheet_discovery.py"
    ).read_text()
    assert 'revision = "FLOWHUB_033"' in source
    assert 'down_revision = "FLOWHUB_032"' in source
    assert "FlowHubBase" not in source
    assert "drop_table" not in source
    assert "forward-only" in source.lower()


def test_sqlite_032_to_033_is_additive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    url = f"sqlite:///{(tmp_path / 'worksheet-discovery-033.sqlite').as_posix()}"
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", url)
    _assert_upgrade_preserves_sentinel(url)


def _postgres_test_url() -> str:
    url = os.environ.get("FLOWHUB_TEST_POSTGRES_URL", "")
    if not url:
        pytest.skip("FLOWHUB_TEST_POSTGRES_URL is not configured")
    parsed = sa.engine.make_url(url)
    if parsed.host not in {"127.0.0.1", "localhost"} or "test" not in (
        parsed.database or ""
    ).lower():
        pytest.fail(
            "FLOWHUB_TEST_POSTGRES_URL must reference a local disposable test database"
        )
    return url


@pytest.mark.postgres
def test_postgresql_032_to_033_is_additive(monkeypatch: pytest.MonkeyPatch) -> None:
    url = _postgres_test_url()
    engine = sa.create_engine(url)
    with engine.begin() as connection:
        connection.execute(sa.text("DROP SCHEMA public CASCADE"))
        connection.execute(sa.text("CREATE SCHEMA public"))
    engine.dispose()
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", url)
    _assert_upgrade_preserves_sentinel(url)
