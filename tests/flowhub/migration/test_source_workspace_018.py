from __future__ import annotations

import os
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


def test_flowhub_018_is_explicit_additive_and_forward_only() -> None:
    source = (ROOT / "alembic_flowhub/versions/flowhub_018_source_centric_workspace.py").read_text()
    assert 'revision = "FLOWHUB_018"' in source
    assert 'down_revision = "FLOWHUB_017"' in source
    assert "FlowHubBase" not in source
    assert "drop_table" not in source
    assert "forward-only" in source


def test_flowhub_017_to_018_preserves_v12_and_enforces_revision_immutability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = f"sqlite:///{(tmp_path / 'source-018.sqlite').as_posix()}"
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", url)
    command.upgrade(_config(), "FLOWHUB_017")
    engine = sa.create_engine(url)
    with engine.begin() as connection:
        connection.execute(
            sa.text("INSERT INTO flowhub_app_config(key,value,updated_by) VALUES ('v12.sentinel','preserved','test')")
        )
    command.upgrade(_config(), "FLOWHUB_018")
    inspector = sa.inspect(engine)
    assert {"sc_sources", "sc_source_mapping_revisions", "sc_sheets", "sc_sheet_revisions", "sc_sheet_cells", "sc_data_quality_issues"} <= set(inspector.get_table_names())
    with engine.begin() as connection:
        assert connection.execute(sa.text("SELECT value FROM flowhub_app_config WHERE key='v12.sentinel'")).scalar_one() == "preserved"
        connection.execute(sa.text("INSERT INTO flowhub_users(id,username,hashed_password,role,is_active,created_at) VALUES (1,'owner','x','admin',1,CURRENT_TIMESTAMP)"))
        connection.execute(sa.text("INSERT INTO sc_sources(id,name,source_kind,external_source_id,worksheet_mode,worksheet_name,data_start_row,status,version,owner_user_id,created_at,updated_at) VALUES ('source','Source','flowhub_sheet',NULL,'selected','Sheet1',1,'active',1,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
        connection.execute(sa.text("INSERT INTO sc_source_mapping_revisions(id,source_id,version,checksum,worksheet_mode,worksheet_name,data_start_row,value_policy_json,created_by_user_id,created_at) VALUES ('mapping','source',1,'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','selected','Sheet1',1,'{}',1,CURRENT_TIMESTAMP)"))
    for statement in (
        "UPDATE sc_source_mapping_revisions SET version=2 WHERE id='mapping'",
        "DELETE FROM sc_source_mapping_revisions WHERE id='mapping'",
    ):
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as connection:
            connection.execute(sa.text(statement))


def _postgres_test_url() -> str:
    url = os.environ.get("FLOWHUB_TEST_POSTGRES_URL", "")
    if not url:
        pytest.skip("FLOWHUB_TEST_POSTGRES_URL is not configured")
    parsed = sa.engine.make_url(url)
    if parsed.host not in {"127.0.0.1", "localhost"} or "test" not in (parsed.database or "").lower():
        pytest.fail("FLOWHUB_TEST_POSTGRES_URL must reference a local disposable test database")
    return url


def _reset_postgres(url: str) -> None:
    engine = sa.create_engine(url)
    with engine.begin() as connection:
        connection.execute(sa.text("DROP SCHEMA public CASCADE"))
        connection.execute(sa.text("CREATE SCHEMA public"))
    engine.dispose()


@pytest.mark.postgres
def test_postgresql_018_fresh_schema_foreign_keys_and_immutability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = _postgres_test_url()
    _reset_postgres(url)
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", url)
    command.upgrade(_config(), "FLOWHUB_018")
    engine = sa.create_engine(url)
    inspector = sa.inspect(engine)
    assert {"sc_sources", "sc_source_mapping_revisions", "sc_sheet_revisions", "sc_sheet_cells"} <= set(inspector.get_table_names())
    source_fks = inspector.get_foreign_keys("sc_sources")
    assert any(item["constrained_columns"] == ["owner_user_id"] and item["referred_table"] == "flowhub_users" for item in source_fks)
    with pytest.raises(sa.exc.IntegrityError), engine.begin() as connection:
        connection.execute(sa.text("INSERT INTO sc_sources(id,name,source_kind,worksheet_mode,data_start_row,status,version,owner_user_id,created_at,updated_at) VALUES ('bad','Bad','flowhub_sheet','selected',1,'active',1,999,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
    with engine.begin() as connection:
        connection.execute(sa.text("INSERT INTO flowhub_users(id,username,hashed_password,role,is_active,created_at) VALUES (1,'source-owner','x','admin',true,CURRENT_TIMESTAMP)"))
        connection.execute(sa.text("INSERT INTO sc_sources(id,name,source_kind,worksheet_mode,worksheet_name,data_start_row,status,version,owner_user_id,created_at,updated_at) VALUES ('source','Source','flowhub_sheet','selected','Sheet1',1,'active',1,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
        connection.execute(sa.text("INSERT INTO sc_source_mapping_revisions(id,source_id,version,checksum,worksheet_mode,worksheet_name,data_start_row,value_policy_json,created_by_user_id,created_at) VALUES ('mapping','source',1,'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','selected','Sheet1',1,CAST('{}' AS jsonb),1,CURRENT_TIMESTAMP)"))
    for statement in (
        "UPDATE sc_source_mapping_revisions SET version=2 WHERE id='mapping'",
        "DELETE FROM sc_source_mapping_revisions WHERE id='mapping'",
    ):
        with pytest.raises(sa.exc.DBAPIError), engine.begin() as connection:
            connection.execute(sa.text(statement))
    engine.dispose()


@pytest.mark.postgres
def test_postgresql_017_to_018_preserves_v12_sentinel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = _postgres_test_url()
    _reset_postgres(url)
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", url)
    command.upgrade(_config(), "FLOWHUB_017")
    engine = sa.create_engine(url)
    with engine.begin() as connection:
        connection.execute(sa.text("INSERT INTO flowhub_app_config(key,value,updated_by) VALUES ('v13.pg.sentinel','preserved','test')"))
    command.upgrade(_config(), "FLOWHUB_018")
    with engine.begin() as connection:
        assert connection.execute(sa.text("SELECT value FROM flowhub_app_config WHERE key='v13.pg.sentinel'")).scalar_one() == "preserved"
        assert "sc_sheet_import_jobs" in sa.inspect(connection).get_table_names()
    engine.dispose()
