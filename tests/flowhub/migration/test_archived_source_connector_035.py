from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
import sqlalchemy as sa


ROOT = Path(__file__).resolve().parents[3]


def _config() -> Config:
    config = Config(str(ROOT / "alembic_flowhub.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic_flowhub"))
    return config


def test_flowhub_035_retires_archived_binding_without_removing_history(
    tmp_path: Path, monkeypatch
) -> None:
    url = f"sqlite:///{(tmp_path / 'source-connector-035.sqlite').as_posix()}"
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", url)
    command.upgrade(_config(), "FLOWHUB_034")
    engine = sa.create_engine(url)
    now = datetime(2026, 8, 14, 9, 0, 0)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO flowhub_users "
                "(id, username, hashed_password, role, is_active, created_at) "
                "VALUES (1, 'owner', 'unused', 'admin', true, :now)"
            ),
            {"now": now},
        )
        for connector_id in ("nextcloud:archived", "nextcloud:active"):
            connection.execute(
                sa.text(
                    "INSERT INTO ip_connector_instances "
                    "(id, connector_type, name, version, enabled, read_only, status, created_at, updated_at) "
                    "VALUES (:id, 'nextcloud', :id, '1.0.0', true, true, 'healthy', :now, :now)"
                ),
                {"id": connector_id, "now": now},
            )
        connection.execute(
            sa.text(
                "INSERT INTO ip_connector_settings "
                "(connector_id, key, value_json, secret, configured, updated_at) "
                "VALUES ('nextcloud:archived', 'password', :secret, true, true, :now)"
            ),
            {"secret": '"preserved-secret"', "now": now},
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
            "archived_at": now,
        }
        connection.execute(
            sa.text(
                "INSERT INTO sc_sources "
                "(id, name, source_kind, external_source_id, worksheet_mode, worksheet_name, "
                "data_start_row, status, archived_at, version, owner_user_id, created_at, updated_at) "
                "VALUES ('historical', 'Historical', :source_kind, 'nextcloud:archived', "
                ":worksheet_mode, :worksheet_name, :data_start_row, 'archived', :archived_at, "
                ":version, :owner_user_id, :created_at, :updated_at)"
            ),
            base,
        )

    command.upgrade(_config(), "FLOWHUB_035")
    with engine.begin() as connection:
        connectors = connection.execute(
            sa.text(
                "SELECT id, enabled, status FROM ip_connector_instances ORDER BY id"
            )
        ).all()
        assert [(row.id, bool(row.enabled), row.status) for row in connectors] == [
            ("nextcloud:active", True, "healthy"),
            ("nextcloud:archived", False, "disabled"),
        ]
        assert connection.execute(
            sa.text("SELECT COUNT(*) FROM sc_sources WHERE id = 'historical'")
        ).scalar_one() == 1
        assert connection.execute(
            sa.text(
                "SELECT value_json FROM ip_connector_settings "
                "WHERE connector_id = 'nextcloud:archived' AND key = 'password'"
            )
        ).scalar_one() == '"preserved-secret"'
    engine.dispose()


def test_flowhub_035_is_forward_only() -> None:
    source = (
        ROOT
        / "alembic_flowhub/versions/flowhub_035_archived_source_connector_retirement.py"
    ).read_text(encoding="utf-8")
    assert 'revision = "FLOWHUB_035"' in source
    assert 'down_revision = "FLOWHUB_034"' in source
    assert "status = 'archived'" in source
    assert "raise RuntimeError(" in source


@pytest.mark.postgres
def test_postgresql_034_to_035_retires_only_archived_connector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    engine = sa.create_engine(url)
    with engine.begin() as connection:
        connection.execute(sa.text("DROP SCHEMA public CASCADE"))
        connection.execute(sa.text("CREATE SCHEMA public"))
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", url)
    command.upgrade(_config(), "FLOWHUB_034")
    now = datetime(2026, 8, 14, 9, 0, 0)
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
                "('nextcloud:archived', 'nextcloud', 'Archived', '1.0.0', true, true, 'healthy', :now, :now), "
                "('nextcloud:active', 'nextcloud', 'Active', '1.0.0', true, true, 'healthy', :now, :now)"
            ),
            {"now": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO sc_sources "
                "(id, name, source_kind, external_source_id, worksheet_mode, worksheet_name, "
                "data_start_row, status, archived_at, version, owner_user_id, created_at, updated_at) "
                "VALUES ('historical', 'Historical', 'external', 'nextcloud:archived', "
                "'all', NULL, 2, 'archived', :now, 1, 1, :now, :now)"
            ),
            {"now": now},
        )
    command.upgrade(_config(), "FLOWHUB_035")
    with engine.begin() as connection:
        rows = connection.execute(
            sa.text(
                "SELECT id, enabled, status FROM ip_connector_instances ORDER BY id"
            )
        ).all()
        assert [(row.id, row.enabled, row.status) for row in rows] == [
            ("nextcloud:active", True, "healthy"),
            ("nextcloud:archived", False, "disabled"),
        ]
        assert connection.execute(
            sa.text("SELECT COUNT(*) FROM sc_sources WHERE id = 'historical'")
        ).scalar_one() == 1
    engine.dispose()
