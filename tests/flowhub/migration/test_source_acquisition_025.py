from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[3]
RUN_TABLE = "saq_runs"


def _config() -> Config:
    config = Config(str(ROOT / "alembic_flowhub.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic_flowhub"))
    return config


def _upgrade_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, revision: str) -> sa.Engine:
    database_url = f"sqlite:///{(tmp_path / f'{revision}.sqlite').as_posix()}"
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", database_url)
    command.upgrade(_config(), revision)
    return sa.create_engine(database_url)


def test_clean_install_reaches_025_with_source_acquisition_run_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _upgrade_database(tmp_path, monkeypatch, "FLOWHUB_025")
    try:
        with engine.connect() as connection:
            assert connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "FLOWHUB_025"
        inspector = sa.inspect(engine)
        from app.flowhub.source_acquisition.models import AcquisitionRun

        columns = {column["name"]: column for column in inspector.get_columns(RUN_TABLE)}
        assert set(columns) == {column.name for column in AcquisitionRun.__table__.columns}
        assert {
            "id",
            "source_id",
            "resource_scope",
            "idempotency_key",
            "parent_run_id",
            "root_run_id",
            "status",
            "result",
            "lease_expires_at",
            "failure_code",
        } <= set(columns)
        assert columns["idempotency_key"]["nullable"] is True
        assert columns["status"]["nullable"] is False
        indexes = {item["name"] for item in inspector.get_indexes(RUN_TABLE)}
        assert {
            "uq_saq_runs_active_scope",
            "uq_saq_runs_idempotency_scope",
            "uq_saq_runs_root_attempt",
            "ix_saq_runs_lease_expiry",
        } <= indexes
        checks = {item["name"] for item in inspector.get_check_constraints(RUN_TABLE)}
        assert {
            "ck_saq_run_status",
            "ck_saq_run_result",
            "ck_saq_run_status_result",
            "ck_saq_run_terminal_timestamp",
        } <= checks
        actual_foreign_keys = {
            (tuple(item["constrained_columns"]), item["referred_table"])
            for item in inspector.get_foreign_keys(RUN_TABLE)
        }
        assert {
            (("source_id",), "sc_sources"),
            (("actor_user_id",), "flowhub_users"),
            (("parent_run_id",), RUN_TABLE),
            (("root_run_id",), RUN_TABLE),
            (("cancellation_requested_by_user_id",), "flowhub_users"),
        } <= actual_foreign_keys
    finally:
        engine.dispose()


def test_upgrade_from_024_preserves_source_records_and_downgrade_is_forward_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _upgrade_database(tmp_path, monkeypatch, "FLOWHUB_024")
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO flowhub_users(id,username,hashed_password,role,is_active,created_at) "
                    "VALUES (1,'owner','x','admin',1,CURRENT_TIMESTAMP)"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO sc_sources(id,name,source_kind,worksheet_mode,worksheet_name,data_start_row,"
                    "status,version,owner_user_id,created_at,updated_at) VALUES "
                    "('source','Source','external','selected','Products',2,'active',1,1,"
                    "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                )
            )
        command.upgrade(_config(), "FLOWHUB_025")
        with engine.connect() as connection:
            assert connection.execute(sa.text("SELECT name FROM sc_sources WHERE id='source'")).scalar_one() == "Source"
            assert connection.execute(sa.text("SELECT count(*) FROM saq_runs")).scalar_one() == 0
        with pytest.raises(NotImplementedError, match="forward-only"):
            command.downgrade(_config(), "FLOWHUB_024")
        assert RUN_TABLE in set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()
