from __future__ import annotations

import asyncio
import io
import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

from alembic import command

ROOT = Path(__file__).resolve().parents[3]


def _config() -> Config:
    config = Config(str(ROOT / "alembic_flowhub.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic_flowhub"))
    return config


def test_flowhub_019_is_explicit_additive_and_forward_only() -> None:
    source = (ROOT / "alembic_flowhub/versions/flowhub_019_worksheet_rules.py").read_text()
    assert 'revision = "FLOWHUB_019"' in source
    assert 'down_revision = "FLOWHUB_018"' in source
    assert "FlowHubBase" not in source
    assert "drop_table" not in source
    assert "forward-only" in source


@pytest.mark.parametrize(
    ("url", "required_sql"),
    (
        (
            "sqlite:///flowhub-019-offline.sqlite",
            "CREATE TRIGGER sc_data_quality_scans_state_update",
        ),
        (
            "postgresql+psycopg://flowhub:flowhub@localhost/flowhub_test",
            "CREATE OR REPLACE FUNCTION sc_guard_data_quality_scan_mutation",
        ),
    ),
)
def test_flowhub_019_offline_sql_contains_complete_trigger_ddl(
    url: str,
    required_sql: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = io.StringIO()
    config = _config()
    config.output_buffer = output
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", url)

    command.upgrade(config, "FLOWHUB_018:FLOWHUB_019", sql=True)

    sql = output.getvalue()
    assert "CREATE TABLE sc_data_quality_scans" in sql
    assert "CREATE TABLE sc_data_quality_scan_sources" in sql
    assert "sc_source_worksheet_rule_sets" in sql
    assert "sc_data_quality_scan_sources_scan_insert_guard" in sql
    assert "sc_data_quality_issues_scan_insert_guard" in sql
    assert "VARCHAR(512)" in sql
    assert required_sql in sql
    assert "UPDATE alembic_version" in sql


def test_runtime_sqlite_engine_enables_declared_foreign_keys(tmp_path: Path) -> None:
    from app.flowhub.database import _get_engine

    url = f"sqlite:///{(tmp_path / 'runtime-fks.sqlite').as_posix()}"
    _get_engine.cache_clear()
    engine = _get_engine(url)
    try:
        with engine.begin() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            connection.exec_driver_sql("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
            connection.exec_driver_sql(
                "CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER NOT NULL, "
                "FOREIGN KEY(parent_id) REFERENCES parent(id))"
            )
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO child(id,parent_id) VALUES (1,999)")
    finally:
        engine.dispose()
        _get_engine.cache_clear()


def test_sqlite_018_to_019_preserves_mapping_and_enforces_rule_immutability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = f"sqlite:///{(tmp_path / 'source-019.sqlite').as_posix()}"
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", url)
    command.upgrade(_config(), "FLOWHUB_018")
    engine = sa.create_engine(url)
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.execute(
            sa.text(
                "INSERT INTO flowhub_users(id,username,hashed_password,role,is_active,created_at) "
                "VALUES (1,'owner','x','admin',1,CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO sc_sources(id,name,source_kind,worksheet_mode,worksheet_name,"
                "data_start_row,status,version,owner_user_id,created_at,updated_at) "
                "VALUES ('source','Source','external','all',NULL,2,'active',1,1,"
                "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO sc_sources(id,name,source_kind,worksheet_mode,worksheet_name,"
                "data_start_row,status,version,owner_user_id,created_at,updated_at) "
                "VALUES ('source-two','Source Two','external','all',NULL,2,'active',1,1,"
                "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO sc_source_mapping_revisions(id,source_id,version,checksum,"
                "worksheet_mode,worksheet_name,data_start_row,value_policy_json,"
                "created_by_user_id,created_at) VALUES ('mapping','source',1,:checksum,"
                "'all',NULL,2,'{}',1,CURRENT_TIMESTAMP)"
            ),
            {"checksum": "a" * 64},
        )
        for channel_id in ("channel-one", "channel-two"):
            connection.execute(
                sa.text(
                    "INSERT INTO uw_channels(id,connector_type,name,implementation_state,"
                    "capabilities_json,capability_version,enabled,created_at,updated_at) "
                    "VALUES (:id,'test',:id,'implemented','{}','1',1,"
                    "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                ),
                {"id": channel_id},
            )
        connection.execute(
            sa.text(
                "INSERT INTO sc_data_quality_issues(id,source_id,category,severity,code,"
                "summary,recommended_action,technical_details_json,created_at) VALUES "
                "('legacy-issue','source','legacy','warning','LEGACY','Legacy issue',"
                "'Preserve this row','{}',CURRENT_TIMESTAMP)"
            )
        )
    command.upgrade(_config(), "FLOWHUB_019")
    inspector = sa.inspect(engine)
    assert {
        "sc_data_quality_scans",
        "sc_data_quality_scan_sources",
        "sc_source_worksheet_rule_sets",
        "sc_source_worksheet_rules",
        "sc_source_worksheet_fields",
        "sc_source_worksheet_channels",
        "sc_source_worksheet_channel_fields",
    } <= set(inspector.get_table_names())
    issue_fks = inspector.get_foreign_keys("sc_data_quality_issues")
    issue_columns = {
        str(item["name"]): item for item in inspector.get_columns("sc_data_quality_issues")
    }
    assert issue_columns["source_row_key"]["type"].length == 512
    assert any(
        item["constrained_columns"] == ["scan_id"]
        and item["referred_table"] == "sc_data_quality_scans"
        for item in issue_fks
    )
    scan_source_fks = inspector.get_foreign_keys("sc_data_quality_scan_sources")
    assert {
        (tuple(item["constrained_columns"]), item["referred_table"])
        for item in scan_source_fks
    } == {
        (("scan_id",), "sc_data_quality_scans"),
        (("source_id",), "sc_sources"),
    }
    with engine.begin() as connection:
        assert connection.execute(
            sa.text("SELECT checksum FROM sc_source_mapping_revisions WHERE id='mapping'")
        ).scalar_one() == "a" * 64
        assert connection.execute(
            sa.text(
                "SELECT scan_id,summary FROM sc_data_quality_issues "
                "WHERE id='legacy-issue'"
            )
        ).one() == (None, "Legacy issue")
        connection.execute(
            sa.text(
                "INSERT INTO sc_source_worksheet_rule_sets(id,mapping_revision_id,mode,"
                "duplicate_product_policy,sealed,created_at) VALUES "
                "('rules','mapping','shared','block',0,CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO sc_source_worksheet_rules(id,rule_set_id,worksheet_name,enabled,"
                "data_start_row,value_policy_json) VALUES "
                "('rule','rules','*',1,2,'{}')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO sc_source_worksheet_fields(id,worksheet_rule_id,field,"
                "reference_type,reference_value,required) VALUES "
                "('field','rule','name','column_letter','A',1)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO sc_source_worksheet_channels(id,worksheet_rule_id,channel_id,"
                "worksheet_name,enabled) VALUES "
                "('channel-map','rule','channel-one',NULL,1)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO sc_source_worksheet_channel_fields(id,"
                "worksheet_channel_mapping_id,field,reference_type,reference_value) VALUES "
                "('channel-field','channel-map','external_id','column_letter','B')"
            )
        )
        connection.execute(
            sa.text("UPDATE sc_source_worksheet_rule_sets SET sealed=1 WHERE id='rules'")
        )
        connection.execute(
            sa.text(
                "INSERT INTO sc_data_quality_scans(id,owner_user_id,source_id,"
                "source_ids_json,source_results_json,status,sources_checked,products_checked,"
                "issue_count,blocking_issue_count,warning_count,affected_product_count,"
                "affected_channel_count,affected_source_count,previous_issue_count,"
                "resolved_since_previous,error_code,created_at,checked_at) VALUES "
                "('scan',1,'source','[\"source\"]','{}','checking',0,0,0,0,0,0,0,0,"
                "NULL,0,NULL,CURRENT_TIMESTAMP,NULL)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO sc_data_quality_scan_sources(scan_id,source_id) "
                "VALUES ('scan','source')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO sc_data_quality_issues(id,scan_id,source_id,snapshot_id,"
                "worksheet_name,source_row_key,source_product_name,mapping_state,channel_id,"
                "canonical_product_id,category,severity,code,summary,recommended_action,"
                "technical_details_json,created_at) VALUES "
                "('issue','scan','source',NULL,'Sheet1','row-1','Product','unmapped',NULL,"
                "NULL,'missing_id','blocked','MISSING_ID','Missing ID','Choose the ID column',"
                "'{}',CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            sa.text(
                "UPDATE sc_data_quality_scans SET status='completed',sources_checked=1,"
                "products_checked=1,issue_count=1,blocking_issue_count=1,"
                "affected_product_count=1,affected_source_count=1,"
                "checked_at=CURRENT_TIMESTAMP WHERE id='scan'"
            )
        )
    with pytest.raises(sa.exc.IntegrityError), engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.execute(
            sa.text(
                "INSERT INTO sc_source_worksheet_rule_sets(id,mapping_revision_id,mode,"
                "duplicate_product_policy,sealed,created_at) VALUES "
                "('bad','missing','shared','block',0,CURRENT_TIMESTAMP)"
            )
        )
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO sc_data_quality_scans(id,owner_user_id,source_id,"
                "source_ids_json,source_results_json,status,sources_checked,products_checked,"
                "issue_count,blocking_issue_count,warning_count,affected_product_count,"
                "affected_channel_count,affected_source_count,previous_issue_count,"
                "resolved_since_previous,error_code,created_at,checked_at) VALUES "
                "('fk-scan',1,'source','[\"source\"]','{}','checking',0,0,0,0,0,0,0,0,"
                "NULL,0,NULL,CURRENT_TIMESTAMP,NULL)"
            )
        )
    with pytest.raises(sa.exc.IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO sc_data_quality_scan_sources(scan_id,source_id) "
                "VALUES ('fk-scan','missing')"
            )
        )
    with pytest.raises(sa.exc.IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO sc_data_quality_scan_sources(scan_id,source_id) "
                "VALUES ('scan','source-two')"
            )
        )
    late_inserts = (
        "INSERT INTO sc_source_worksheet_rules(id,rule_set_id,worksheet_name,enabled,"
        "data_start_row,value_policy_json) VALUES ('late-rule','rules','Late',1,2,'{}')",
        "INSERT INTO sc_source_worksheet_fields(id,worksheet_rule_id,field,reference_type,"
        "reference_value,required) VALUES "
        "('late-field','rule','category','column_letter','C',0)",
        "INSERT INTO sc_source_worksheet_channels(id,worksheet_rule_id,channel_id,"
        "worksheet_name,enabled) VALUES "
        "('late-channel','rule','channel-two',NULL,1)",
        "INSERT INTO sc_source_worksheet_channel_fields(id,worksheet_channel_mapping_id,"
        "field,reference_type,reference_value) VALUES "
        "('late-channel-field','channel-map','price','column_letter','C')",
    )
    for statement in late_inserts:
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as connection:
            connection.execute(sa.text(statement))
    for statement in (
        "UPDATE sc_source_worksheet_rule_sets SET mode='per_worksheet' WHERE id='rules'",
        "DELETE FROM sc_source_worksheet_rule_sets WHERE id='rules'",
        "UPDATE sc_source_worksheet_rules SET enabled=0 WHERE id='rule'",
        "DELETE FROM sc_source_worksheet_rules WHERE id='rule'",
        "UPDATE sc_source_worksheet_fields SET required=0 WHERE id='field'",
        "DELETE FROM sc_source_worksheet_fields WHERE id='field'",
        "UPDATE sc_source_worksheet_channels SET enabled=0 WHERE id='channel-map'",
        "DELETE FROM sc_source_worksheet_channels WHERE id='channel-map'",
        "UPDATE sc_source_worksheet_channel_fields SET reference_value='Z' "
        "WHERE id='channel-field'",
        "DELETE FROM sc_source_worksheet_channel_fields WHERE id='channel-field'",
    ):
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as connection:
            connection.execute(sa.text(statement))
    with pytest.raises(sa.exc.IntegrityError), engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.execute(
            sa.text(
                "INSERT INTO sc_data_quality_issues(id,scan_id,source_id,category,severity,"
                "code,summary,recommended_action,technical_details_json,created_at) VALUES "
                "('late-issue','scan','source','missing_id','blocked','MISSING_ID',"
                "'Missing ID','Choose the ID column','{}',CURRENT_TIMESTAMP)"
            )
        )
    for statement in (
        "UPDATE sc_data_quality_issues SET summary='changed' WHERE id='issue'",
        "DELETE FROM sc_data_quality_issues WHERE id='issue'",
        "UPDATE sc_data_quality_scan_sources SET source_id='source-two' "
        "WHERE scan_id='scan' AND source_id='source'",
        "DELETE FROM sc_data_quality_scan_sources "
        "WHERE scan_id='scan' AND source_id='source'",
        "UPDATE sc_data_quality_scans SET issue_count=99 WHERE id='scan'",
        "DELETE FROM sc_data_quality_scans WHERE id='scan'",
    ):
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as connection:
            connection.execute(sa.text(statement))
    engine.dispose()


def test_sqlite_migrated_schema_allows_service_to_finalize_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy.orm import Session

    from app.flowhub.auth.models import FlowHubUser
    from app.flowhub.database import _get_engine
    from app.flowhub.source_workspace.models import (
        SourceDataQualityIssue,
        SourceDataQualityScan,
    )
    from app.flowhub.source_workspace.service import SourceWorkspaceService

    url = f"sqlite:///{(tmp_path / 'service-scan-019.sqlite').as_posix()}"
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", url)
    command.upgrade(_config(), "FLOWHUB_019")
    _get_engine.cache_clear()
    engine = _get_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO flowhub_users(id,username,hashed_password,role,is_active,"
                    "created_at) VALUES (1,'service-owner','x','admin',1,CURRENT_TIMESTAMP)"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO sc_sources(id,name,source_kind,worksheet_mode,worksheet_name,"
                    "data_start_row,status,version,owner_user_id,created_at,updated_at) "
                    "VALUES ('source','Source','external','all',NULL,2,'active',1,1,"
                    "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                )
            )
        with Session(engine) as db:
            user = db.get(FlowHubUser, 1)
            assert user is not None
            service = SourceWorkspaceService(db)

            async def evaluate(_source_id: str, _user: FlowHubUser) -> dict[str, object]:
                return {
                    "candidates": [{"sourceRowKey": "row-1"}],
                    "issues": [
                        {
                            "sourceRowKey": "row-1",
                            "sourceRowNumber": 2,
                            "worksheetName": "Sheet1",
                            "channelId": None,
                            "sourceProductName": "Product",
                            "mappingState": "unmapped",
                            "category": "missing_id",
                            "severity": "blocked",
                            "code": "MISSING_ID",
                            "summary": "Missing ID",
                            "recommendedAction": "Choose the ID column",
                            "technicalDetails": {},
                        }
                    ],
                }

            monkeypatch.setattr(service, "snapshot_candidates", evaluate)
            result = asyncio.run(
                service.scan_data_quality(user=user, source_id="source")
            )
            scan = db.query(SourceDataQualityScan).one()
            assert result["summary"]["scanId"] == scan.id
            assert scan.status == "completed"
            assert scan.issue_count == 1
            assert db.query(SourceDataQualityIssue).filter_by(scan_id=scan.id).count() == 1
    finally:
        engine.dispose()
        _get_engine.cache_clear()


def test_sqlite_019_tables_match_source_workspace_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.flowhub.database import FlowHubBase

    url = f"sqlite:///{(tmp_path / 'schema-parity-019.sqlite').as_posix()}"
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", url)
    command.upgrade(_config(), "FLOWHUB_019")
    engine = sa.create_engine(url)

    def include_object(
        obj: object,
        name: str | None,
        type_: str,
        _reflected: bool,
        _compare_to: object | None,
    ) -> bool:
        table = getattr(obj, "table", None)
        table_name = getattr(table, "name", name if type_ == "table" else "")
        return str(table_name).startswith(("sc_source_worksheet", "sc_data_quality"))

    try:
        with engine.connect() as connection:
            differences = compare_metadata(
                MigrationContext.configure(
                    connection,
                    opts={"include_object": include_object},
                ),
                FlowHubBase.metadata,
            )
        assert differences == []
    finally:
        engine.dispose()


def _postgres_test_url() -> str:
    url = os.environ.get("FLOWHUB_TEST_POSTGRES_URL", "")
    if not url:
        pytest.skip("FLOWHUB_TEST_POSTGRES_URL is not configured")
    parsed = sa.engine.make_url(url)
    if parsed.host not in {"127.0.0.1", "localhost"} or "test" not in (
        parsed.database or ""
    ).lower():
        pytest.fail("FLOWHUB_TEST_POSTGRES_URL must reference a local disposable test database")
    return url


@pytest.mark.postgres
def test_postgresql_019_foreign_keys_immutability_and_018_preservation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = _postgres_test_url()
    engine = sa.create_engine(url)
    with engine.begin() as connection:
        connection.execute(sa.text("DROP SCHEMA public CASCADE"))
        connection.execute(sa.text("CREATE SCHEMA public"))
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", url)
    command.upgrade(_config(), "FLOWHUB_018")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO flowhub_users(id,username,hashed_password,role,is_active,created_at) "
                "VALUES (1,'owner-019','x','admin',true,CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO sc_sources(id,name,source_kind,worksheet_mode,worksheet_name,"
                "data_start_row,status,version,owner_user_id,created_at,updated_at) "
                "VALUES ('source','Source','external','all',NULL,2,'active',1,1,"
                "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO sc_sources(id,name,source_kind,worksheet_mode,worksheet_name,"
                "data_start_row,status,version,owner_user_id,created_at,updated_at) "
                "VALUES ('source-two','Source Two','external','all',NULL,2,'active',1,1,"
                "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO sc_source_mapping_revisions(id,source_id,version,checksum,"
                "worksheet_mode,worksheet_name,data_start_row,value_policy_json,"
                "created_by_user_id,created_at) VALUES ('mapping','source',1,:checksum,"
                "'all',NULL,2,CAST('{}' AS jsonb),1,CURRENT_TIMESTAMP)"
            ),
            {"checksum": "b" * 64},
        )
        for channel_id in ("channel-one", "channel-two"):
            connection.execute(
                sa.text(
                    "INSERT INTO uw_channels(id,connector_type,name,implementation_state,"
                    "capabilities_json,capability_version,enabled,created_at,updated_at) "
                    "VALUES (:id,'test',:id,'implemented',CAST('{}' AS jsonb),'1',true,"
                    "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                ),
                {"id": channel_id},
            )
        connection.execute(
            sa.text(
                "INSERT INTO sc_data_quality_issues(id,source_id,category,severity,code,"
                "summary,recommended_action,technical_details_json,created_at) VALUES "
                "('legacy-issue','source','legacy','warning','LEGACY','Legacy issue',"
                "'Preserve this row',CAST('{}' AS jsonb),CURRENT_TIMESTAMP)"
            )
        )
    command.upgrade(_config(), "FLOWHUB_019")
    inspector = sa.inspect(engine)
    assert {
        "sc_data_quality_scans",
        "sc_data_quality_scan_sources",
        "sc_source_worksheet_rule_sets",
    } <= set(inspector.get_table_names())
    fks = inspector.get_foreign_keys("sc_source_worksheet_rule_sets")
    assert any(
        item["constrained_columns"] == ["mapping_revision_id"]
        and item["referred_table"] == "sc_source_mapping_revisions"
        for item in fks
    )
    issue_fks = inspector.get_foreign_keys("sc_data_quality_issues")
    assert any(
        item["constrained_columns"] == ["scan_id"]
        and item["referred_table"] == "sc_data_quality_scans"
        for item in issue_fks
    )
    scan_source_fks = inspector.get_foreign_keys("sc_data_quality_scan_sources")
    assert {
        (tuple(item["constrained_columns"]), item["referred_table"])
        for item in scan_source_fks
    } == {
        (("scan_id",), "sc_data_quality_scans"),
        (("source_id",), "sc_sources"),
    }
    with engine.begin() as connection:
        assert connection.execute(
            sa.text("SELECT checksum FROM sc_source_mapping_revisions WHERE id='mapping'")
        ).scalar_one() == "b" * 64
        assert connection.execute(
            sa.text(
                "SELECT scan_id,summary FROM sc_data_quality_issues "
                "WHERE id='legacy-issue'"
            )
        ).one() == (None, "Legacy issue")
        connection.execute(
            sa.text(
                "INSERT INTO sc_source_worksheet_rule_sets(id,mapping_revision_id,mode,"
                "duplicate_product_policy,sealed,created_at) VALUES "
                "('rules','mapping','shared','block',false,CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO sc_source_worksheet_rules(id,rule_set_id,worksheet_name,enabled,"
                "data_start_row,value_policy_json) VALUES "
                "('rule','rules','*',true,2,CAST('{}' AS jsonb))"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO sc_source_worksheet_fields(id,worksheet_rule_id,field,"
                "reference_type,reference_value,required) VALUES "
                "('field','rule','name','column_letter','A',true)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO sc_source_worksheet_channels(id,worksheet_rule_id,channel_id,"
                "worksheet_name,enabled) VALUES "
                "('channel-map','rule','channel-one',NULL,true)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO sc_source_worksheet_channel_fields(id,"
                "worksheet_channel_mapping_id,field,reference_type,reference_value) VALUES "
                "('channel-field','channel-map','external_id','column_letter','B')"
            )
        )
        connection.execute(
            sa.text("UPDATE sc_source_worksheet_rule_sets SET sealed=true WHERE id='rules'")
        )
        connection.execute(
            sa.text(
                "INSERT INTO sc_data_quality_scans(id,owner_user_id,source_id,"
                "source_ids_json,source_results_json,status,sources_checked,products_checked,"
                "issue_count,blocking_issue_count,warning_count,affected_product_count,"
                "affected_channel_count,affected_source_count,previous_issue_count,"
                "resolved_since_previous,error_code,created_at,checked_at) VALUES "
                "('scan',1,'source',CAST('[\"source\"]' AS jsonb),CAST('{}' AS jsonb),"
                "'checking',0,0,0,0,0,0,0,0,NULL,0,NULL,CURRENT_TIMESTAMP,NULL)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO sc_data_quality_scan_sources(scan_id,source_id) "
                "VALUES ('scan','source')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO sc_data_quality_issues(id,scan_id,source_id,category,severity,"
                "code,summary,recommended_action,technical_details_json,created_at) VALUES "
                "('issue','scan','source','missing_id','blocked','MISSING_ID','Missing ID',"
                "'Choose the ID column',CAST('{}' AS jsonb),CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            sa.text(
                "UPDATE sc_data_quality_scans SET status='completed',sources_checked=1,"
                "products_checked=1,issue_count=1,blocking_issue_count=1,"
                "affected_product_count=1,affected_source_count=1,"
                "checked_at=CURRENT_TIMESTAMP WHERE id='scan'"
            )
        )
    with pytest.raises(sa.exc.DBAPIError), engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO sc_source_worksheet_rule_sets(id,mapping_revision_id,mode,"
                "duplicate_product_policy,sealed,created_at) VALUES "
                "('bad','missing','shared','block',false,CURRENT_TIMESTAMP)"
            )
        )
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO sc_data_quality_scans(id,owner_user_id,source_id,"
                "source_ids_json,source_results_json,status,sources_checked,products_checked,"
                "issue_count,blocking_issue_count,warning_count,affected_product_count,"
                "affected_channel_count,affected_source_count,previous_issue_count,"
                "resolved_since_previous,error_code,created_at,checked_at) VALUES "
                "('fk-scan',1,'source',CAST('[\"source\"]' AS jsonb),CAST('{}' AS jsonb),"
                "'checking',0,0,0,0,0,0,0,0,NULL,0,NULL,CURRENT_TIMESTAMP,NULL)"
            )
        )
    with pytest.raises(sa.exc.DBAPIError), engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO sc_data_quality_scan_sources(scan_id,source_id) "
                "VALUES ('fk-scan','missing')"
            )
        )
    with pytest.raises(sa.exc.DBAPIError), engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO sc_data_quality_scan_sources(scan_id,source_id) "
                "VALUES ('scan','source-two')"
            )
        )
    late_inserts = (
        "INSERT INTO sc_source_worksheet_rules(id,rule_set_id,worksheet_name,enabled,"
        "data_start_row,value_policy_json) VALUES "
        "('late-rule','rules','Late',true,2,CAST('{}' AS jsonb))",
        "INSERT INTO sc_source_worksheet_fields(id,worksheet_rule_id,field,reference_type,"
        "reference_value,required) VALUES "
        "('late-field','rule','category','column_letter','C',false)",
        "INSERT INTO sc_source_worksheet_channels(id,worksheet_rule_id,channel_id,"
        "worksheet_name,enabled) VALUES "
        "('late-channel','rule','channel-two',NULL,true)",
        "INSERT INTO sc_source_worksheet_channel_fields(id,worksheet_channel_mapping_id,"
        "field,reference_type,reference_value) VALUES "
        "('late-channel-field','channel-map','price','column_letter','C')",
    )
    for statement in late_inserts:
        with pytest.raises(sa.exc.DBAPIError), engine.begin() as connection:
            connection.execute(sa.text(statement))
    for statement in (
        "UPDATE sc_source_worksheet_rule_sets SET mode='per_worksheet' WHERE id='rules'",
        "DELETE FROM sc_source_worksheet_rule_sets WHERE id='rules'",
        "UPDATE sc_source_worksheet_rules SET enabled=false WHERE id='rule'",
        "DELETE FROM sc_source_worksheet_rules WHERE id='rule'",
        "UPDATE sc_source_worksheet_fields SET required=false WHERE id='field'",
        "DELETE FROM sc_source_worksheet_fields WHERE id='field'",
        "UPDATE sc_source_worksheet_channels SET enabled=false WHERE id='channel-map'",
        "DELETE FROM sc_source_worksheet_channels WHERE id='channel-map'",
        "UPDATE sc_source_worksheet_channel_fields SET reference_value='Z' "
        "WHERE id='channel-field'",
        "DELETE FROM sc_source_worksheet_channel_fields WHERE id='channel-field'",
    ):
        with pytest.raises(sa.exc.DBAPIError), engine.begin() as connection:
            connection.execute(sa.text(statement))
    with pytest.raises(sa.exc.DBAPIError), engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO sc_data_quality_issues(id,scan_id,source_id,category,severity,"
                "code,summary,recommended_action,technical_details_json,created_at) VALUES "
                "('late-issue','scan','source','missing_id','blocked','MISSING_ID',"
                "'Missing ID','Choose the ID column',CAST('{}' AS jsonb),CURRENT_TIMESTAMP)"
            )
        )
    for statement in (
        "UPDATE sc_data_quality_issues SET summary='changed' WHERE id='issue'",
        "DELETE FROM sc_data_quality_issues WHERE id='issue'",
        "UPDATE sc_data_quality_scan_sources SET source_id='source-two' "
        "WHERE scan_id='scan' AND source_id='source'",
        "DELETE FROM sc_data_quality_scan_sources "
        "WHERE scan_id='scan' AND source_id='source'",
        "UPDATE sc_data_quality_scans SET issue_count=99 WHERE id='scan'",
        "DELETE FROM sc_data_quality_scans WHERE id='scan'",
    ):
        with pytest.raises(sa.exc.DBAPIError), engine.begin() as connection:
            connection.execute(sa.text(statement))
    engine.dispose()
