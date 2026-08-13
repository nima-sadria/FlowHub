from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
import sqlalchemy as sa


ROOT = Path(__file__).resolve().parents[3]
ARCHIVED_AT = datetime(2026, 8, 13, 8, 30, 0)


def _config() -> Config:
    config = Config(str(ROOT / "alembic_flowhub.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic_flowhub"))
    return config


def _assert_lifecycle_upgrade(url: str) -> None:
    command.upgrade(_config(), "FLOWHUB_033")
    engine = sa.create_engine(url)
    metadata = sa.MetaData()
    metadata.reflect(engine, only=["flowhub_users", "sc_sources", "uw_audit_entries"])
    users = metadata.tables["flowhub_users"]
    sources = metadata.tables["sc_sources"]
    audits = metadata.tables["uw_audit_entries"]
    with engine.begin() as connection:
        connection.execute(
            users.insert().values(
                id=1,
                username="lifecycle-owner",
                hashed_password="not-a-real-password",
                role="admin",
                is_active=True,
                created_at=datetime(2026, 1, 1),
            )
        )
        base = {
            "source_kind": "external",
            "worksheet_mode": "selected",
            "worksheet_name": "Prices",
            "data_start_row": 2,
            "version": 3,
            "owner_user_id": 1,
            "created_at": datetime(2026, 1, 1),
            "updated_at": ARCHIVED_AT,
        }
        connection.execute(
            sources.insert(),
            [
                {**base, "id": "archived-source", "name": "Archived", "external_source_id": "nextcloud:primary", "status": "disabled"},
                {**base, "id": "paused-source", "name": "Paused", "external_source_id": "nextcloud:paused", "status": "disabled"},
                {**base, "id": "active-source", "name": "Active", "external_source_id": "nextcloud:active", "status": "active"},
            ],
        )
        connection.execute(
            audits.insert().values(
                id="archive-audit",
                correlation_id="lifecycle-test",
                event_type="source_archived",
                user_id=1,
                occurred_at=ARCHIVED_AT,
                reason="protected_source_history_preserved",
                request_metadata_json={},
                metadata_json={"sourceId": "archived-source"},
                metadata_checksum="a" * 64,
            )
        )

    command.upgrade(_config(), "FLOWHUB_034")
    with engine.begin() as connection:
        rows = connection.execute(
            sa.text("SELECT id, status, archived_at FROM sc_sources ORDER BY id")
        ).all()
        assert [(row.id, row.status) for row in rows] == [
            ("active-source", "active"),
            ("archived-source", "archived"),
            ("paused-source", "disabled"),
        ]
        assert rows[0].archived_at is None
        assert str(rows[1].archived_at).startswith("2026-08-13 08:30:00")
        assert rows[2].archived_at is None
        checks = sa.inspect(connection).get_check_constraints("sc_sources")
        lifecycle_check = next(item for item in checks if item["name"] == "ck_sc_source_status")
        assert "archived" in lifecycle_check["sqltext"]
    engine.dispose()


def test_flowhub_034_is_evidence_backed_and_forward_only() -> None:
    source = (
        ROOT / "alembic_flowhub/versions/flowhub_034_source_lifecycle_truth.py"
    ).read_text()
    assert 'revision = "FLOWHUB_034"' in source
    assert 'down_revision = "FLOWHUB_033"' in source
    assert "source_archived" in source
    assert "status = 'disabled'" in source
    assert "raise RuntimeError(" in source


def test_sqlite_033_to_034_preserves_disabled_and_backfills_archived(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = f"sqlite:///{(tmp_path / 'source-lifecycle-034.sqlite').as_posix()}"
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", url)
    _assert_lifecycle_upgrade(url)


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
def test_postgresql_033_to_034_preserves_disabled_and_backfills_archived(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = _postgres_test_url()
    engine = sa.create_engine(url)
    with engine.begin() as connection:
        connection.execute(sa.text("DROP SCHEMA public CASCADE"))
        connection.execute(sa.text("CREATE SCHEMA public"))
    engine.dispose()
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", url)
    _assert_lifecycle_upgrade(url)
