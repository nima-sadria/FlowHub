from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[3]
OBSERVATION_TABLES = {
    "saq_observation_version_heads",
    "saq_observations",
    "saq_observation_evidence",
    "saq_observation_snapshot_references",
}


def _config() -> Config:
    config = Config(str(ROOT / "alembic_flowhub.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic_flowhub"))
    return config


def _upgrade_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, revision: str) -> sa.Engine:
    url = f"sqlite:///{(tmp_path / f'{revision}.sqlite').as_posix()}"
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", url)
    command.upgrade(_config(), revision)
    return sa.create_engine(url)


def test_clean_install_reaches_026_with_observation_model_parity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _upgrade_database(tmp_path, monkeypatch, "FLOWHUB_026")
    try:
        from app.flowhub.source_acquisition.models import (
            SourceObservation,
            SourceObservationEvidence,
            SourceObservationSnapshotReference,
            SourceObservationVersionHead,
        )

        with engine.connect() as connection:
            assert connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "FLOWHUB_026"
        inspector = sa.inspect(engine)
        assert OBSERVATION_TABLES <= set(inspector.get_table_names())
        for model in (
            SourceObservationVersionHead,
            SourceObservation,
            SourceObservationEvidence,
            SourceObservationSnapshotReference,
        ):
            columns = {item["name"]: item for item in inspector.get_columns(model.__tablename__)}
            assert set(columns) == {column.name for column in model.__table__.columns}
            assert {tuple(index["column_names"]) for index in inspector.get_indexes(model.__tablename__)} >= {
                tuple(index.columns.keys()) for index in model.__table__.indexes
            }
    finally:
        engine.dispose()


def test_upgrade_from_025_preserves_runs_and_observation_downgrade_is_forward_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _upgrade_database(tmp_path, monkeypatch, "FLOWHUB_025")
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
            connection.execute(
                sa.text(
                    "INSERT INTO saq_runs(id,source_id,resource_scope,trigger_kind,request_fingerprint,"
                    "correlation_id,root_run_id,attempt_number,status,result,queued_at,terminal_at,"
                    "created_at,updated_at) VALUES "
                    "('run','source','source','manual',:checksum,'run','run',1,'succeeded','observed',"
                    "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                ),
                {"checksum": "a" * 64},
            )
        command.upgrade(_config(), "FLOWHUB_026")
        with engine.connect() as connection:
            assert connection.execute(sa.text("SELECT status,result FROM saq_runs WHERE id='run'")).one() == (
                "succeeded",
                "observed",
            )
            assert connection.execute(sa.text("SELECT count(*) FROM saq_observations")).scalar_one() == 0
        with pytest.raises(NotImplementedError, match="forward-only"):
            command.downgrade(_config(), "FLOWHUB_025")
        assert OBSERVATION_TABLES <= set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()
