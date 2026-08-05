from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config


ROOT = Path(__file__).resolve().parents[3]
ASSESSMENT_TABLES = {
    "saq_mapping_schema_expectations",
    "saq_schema_assessments",
    "saq_schema_drift_records",
    "saq_schema_diagnostics",
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


def test_clean_install_reaches_027_with_schema_assessment_model_parity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _upgrade_database(tmp_path, monkeypatch, "FLOWHUB_027")
    try:
        from app.flowhub.source_acquisition.models import (
            SourceMappingSchemaExpectation,
            SourceSchemaAssessment,
            SourceSchemaDiagnostic,
            SourceSchemaDriftRecord,
        )

        with engine.connect() as connection:
            assert connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "FLOWHUB_027"
        inspector = sa.inspect(engine)
        assert ASSESSMENT_TABLES <= set(inspector.get_table_names())
        for model in (
            SourceMappingSchemaExpectation,
            SourceSchemaAssessment,
            SourceSchemaDriftRecord,
            SourceSchemaDiagnostic,
        ):
            columns = {item["name"] for item in inspector.get_columns(model.__tablename__)}
            assert columns == {column.name for column in model.__table__.columns}
            indexes = {tuple(item["column_names"]) for item in inspector.get_indexes(model.__tablename__)}
            assert {tuple(index.columns.keys()) for index in model.__table__.indexes} <= indexes
    finally:
        engine.dispose()


def test_upgrade_from_026_preserves_observations_and_refuses_destructive_downgrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _upgrade_database(tmp_path, monkeypatch, "FLOWHUB_026")
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
            connection.execute(
                sa.text(
                    "INSERT INTO saq_observation_version_heads(source_id,resource_scope,next_version,updated_at) "
                    "VALUES ('source','source',2,CURRENT_TIMESTAMP)"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO saq_observations(id,acquisition_run_id,source_id,resource_scope,resource_identity,"
                    "resource_identity_hash,observation_version,observed_at,provenance_json,checksum,created_at) "
                    "VALUES ('observation','run','source','source','upload:one',:identity,1,CURRENT_TIMESTAMP,'{}',:checksum,CURRENT_TIMESTAMP)"
                ),
                {"identity": "b" * 64, "checksum": "c" * 64},
            )
        command.upgrade(_config(), "FLOWHUB_027")
        with engine.connect() as connection:
            assert connection.execute(sa.text("SELECT count(*) FROM saq_observations")).scalar_one() == 1
            assert connection.execute(sa.text("SELECT count(*) FROM saq_schema_assessments")).scalar_one() == 0
        with pytest.raises(NotImplementedError, match="forward-only"):
            command.downgrade(_config(), "FLOWHUB_026")
        assert ASSESSMENT_TABLES <= set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()
