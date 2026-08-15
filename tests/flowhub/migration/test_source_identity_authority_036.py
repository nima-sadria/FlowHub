from __future__ import annotations

import json
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
import sqlalchemy as sa


ROOT = Path(__file__).resolve().parents[3]
IDENTITY_TABLES = {
    "saq_observation_datasets",
    "saq_observation_worksheet_datasets",
    "sc_mapping_identity_assessments",
    "sc_source_product_identities",
}


def _config() -> Config:
    config = Config(str(ROOT / "alembic_flowhub.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic_flowhub"))
    return config


def test_flowhub_036_adds_provider_neutral_identity_evidence_without_inference(
    tmp_path: Path, monkeypatch
) -> None:
    url = f"sqlite:///{(tmp_path / 'source-identity-036.sqlite').as_posix()}"
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", url)
    command.upgrade(_config(), "FLOWHUB_035")
    engine = sa.create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO flowhub_users "
                    "(id,username,hashed_password,role,is_active,created_at) VALUES "
                    "(1,'owner','x','admin',true,CURRENT_TIMESTAMP)"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO sc_sources "
                    "(id,name,source_kind,external_source_id,worksheet_mode,worksheet_name,"
                    "data_start_row,status,version,owner_user_id,created_at,updated_at) VALUES "
                    "('source','Source','external','nextcloud:identity','selected','Products',"
                    "2,'active',1,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO sc_source_mapping_revisions "
                    "(id,source_id,version,checksum,worksheet_mode,worksheet_name,data_start_row,"
                    "value_policy_json,created_by_user_id,created_at) VALUES "
                    "('mapping','source',1,:checksum,'selected','Products',2,'{}',1,"
                    "CURRENT_TIMESTAMP)"
                ),
                {"checksum": "a" * 64},
            )
            connection.execute(
                sa.text(
                    "INSERT INTO sc_source_mapping_revisions "
                    "(id,source_id,version,checksum,worksheet_mode,worksheet_name,data_start_row,"
                    "value_policy_json,created_by_user_id,created_at) VALUES "
                    "('mapping-v2','source',2,:checksum,'selected','Products',2,'{}',1,"
                    "CURRENT_TIMESTAMP)"
                ),
                {"checksum": "b" * 64},
            )
            connection.execute(
                sa.text(
                    "INSERT INTO sc_source_field_mappings "
                    "(id,mapping_revision_id,field,reference_type,reference_value,required) "
                    "VALUES ('source-key-v2','mapping-v2','source_key','column_letter','B',true)"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO sc_source_mapping_revisions "
                    "(id,source_id,version,checksum,worksheet_mode,worksheet_name,data_start_row,"
                    "value_policy_json,created_by_user_id,created_at) VALUES "
                    "('mapping-mixed','source',3,:checksum,'all',NULL,2,'{}',1,"
                    "CURRENT_TIMESTAMP)"
                ),
                {"checksum": "c" * 64},
            )
            connection.execute(
                sa.text(
                    "INSERT INTO sc_source_worksheet_rule_sets "
                    "(id,mapping_revision_id,mode,duplicate_product_policy,sealed,created_at) "
                    "VALUES ('rules-mixed','mapping-mixed','per_worksheet','block',false,"
                    "CURRENT_TIMESTAMP)"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO sc_source_worksheet_rules "
                    "(id,rule_set_id,worksheet_name,enabled,data_start_row,value_policy_json) "
                    "VALUES ('rule-keyed','rules-mixed','Keyed',true,2,'{}'),"
                    "('rule-unkeyed','rules-mixed','Unkeyed',true,2,'{}')"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO sc_source_worksheet_fields "
                    "(id,worksheet_rule_id,field,reference_type,reference_value,required) "
                    "VALUES ('mixed-source-key','rule-keyed','source_key',"
                    "'column_letter','B',true)"
                )
            )
            connection.execute(
                sa.text(
                    "UPDATE sc_source_worksheet_rule_sets SET sealed=true "
                    "WHERE id='rules-mixed'"
                )
            )

        command.upgrade(_config(), "FLOWHUB_036")

        inspector = sa.inspect(engine)
        assert IDENTITY_TABLES <= set(inspector.get_table_names())
        mapping_checks = {
            item["name"]
            for item in inspector.get_check_constraints(
                "sc_source_mapping_revisions"
            )
        }
        assert "ck_sc_mapping_identity_policy_version" in mapping_checks
        assessment_checks = {
            item["name"]
            for item in inspector.get_check_constraints(
                "sc_mapping_identity_assessments"
            )
        }
        assert {
            "ck_sc_identity_assessment_revision_kind",
            "ck_sc_identity_assessment_status",
            "ck_sc_identity_assessment_counts",
            "ck_sc_identity_assessment_evidence",
        } <= assessment_checks
        assessment_unique = {
            item["name"]: item["column_names"]
            for item in inspector.get_unique_constraints(
                "sc_mapping_identity_assessments"
            )
        }
        assert assessment_unique["uq_sc_identity_assessment_revision"] == [
            "mapping_revision_id",
            "source_revision_kind",
            "source_revision_id",
            "identity_fingerprint",
            "binding_context_fingerprint",
            "algorithm_version",
        ]
        identity_unique = {
            item["name"]: item["column_names"]
            for item in inspector.get_unique_constraints(
                "sc_source_product_identities"
            )
        }
        assert identity_unique["uq_sc_source_product_identity_key"] == [
            "source_id",
            "normalization_version",
            "source_key_hash",
        ]
        identity_checks = {
            item["name"]
            for item in inspector.get_check_constraints(
                "sc_source_product_identities"
            )
        }
        assert {
            "ck_sc_source_product_identity_revision_kind",
            "ck_sc_source_product_identity_evidence",
        } <= identity_checks
        with engine.connect() as connection:
            assert connection.execute(
                sa.text("SELECT version_num FROM alembic_version")
            ).scalar_one() == "FLOWHUB_036"
            authority, policy_version = connection.execute(
                sa.text(
                    "SELECT identity_authority_json, identity_policy_version "
                    "FROM sc_source_mapping_revisions WHERE id='mapping'"
                )
            ).one()
            decoded_authority = (
                authority if isinstance(authority, dict) else json.loads(authority)
            )
            assert decoded_authority == {}
            assert policy_version == 1
            v2_authority, v2_policy_version = connection.execute(
                sa.text(
                    "SELECT identity_authority_json, identity_policy_version "
                    "FROM sc_source_mapping_revisions WHERE id='mapping-v2'"
                )
            ).one()
            decoded_v2_authority = (
                v2_authority
                if isinstance(v2_authority, dict)
                else json.loads(v2_authority)
            )
            assert decoded_v2_authority == {}
            assert v2_policy_version == 2
            assert connection.execute(
                sa.text(
                    "SELECT identity_policy_version "
                    "FROM sc_source_mapping_revisions WHERE id='mapping-mixed'"
                )
            ).scalar_one() == 1
            for table in IDENTITY_TABLES:
                assert connection.execute(
                    sa.text(f"SELECT COUNT(*) FROM {table}")
                ).scalar_one() == 0
            trigger_names = set(
                connection.execute(
                    sa.text(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='trigger' AND name LIKE '%_immutable_%'"
                    )
                ).scalars()
            )
            for table in IDENTITY_TABLES:
                assert f"{table}_immutable_update" in trigger_names
                assert f"{table}_immutable_delete" in trigger_names

        from app.flowhub.source_acquisition.models import (
            SourceObservationDataset,
            SourceObservationWorksheetDataset,
        )
        from app.flowhub.source_workspace.models import (
            SourceMappingIdentityAssessment,
            SourceProductIdentity,
        )

        for model in (
            SourceObservationDataset,
            SourceObservationWorksheetDataset,
            SourceMappingIdentityAssessment,
            SourceProductIdentity,
        ):
            migrated_columns = {
                item["name"] for item in inspector.get_columns(model.__tablename__)
            }
            assert migrated_columns == {column.name for column in model.__table__.columns}
            for foreign_key in inspector.get_foreign_keys(model.__tablename__):
                assert foreign_key.get("options", {}).get("ondelete") == "RESTRICT"
    finally:
        engine.dispose()


def test_flowhub_036_contract_is_forward_only_and_does_not_guess_authority() -> None:
    source = (
        ROOT
        / "alembic_flowhub/versions/flowhub_036_source_identity_authority.py"
    ).read_text(encoding="utf-8")
    assert 'revision = "FLOWHUB_036"' in source
    assert 'down_revision = "FLOWHUB_035"' in source
    assert "raise RuntimeError(" in source
    assert "woocommerce" not in source.lower()
    assert "snappshop" not in source.lower()
    assert "source_observation" in source
    assert "flowhub_sheet_revision" in source
    assert "status IN ('pass','blocked')" in source


def test_postgresql_manifest_requires_the_flowhub_036_migration_test() -> None:
    manifest = (ROOT / "scripts/assert_postgres_junit.py").read_text(
        encoding="utf-8"
    )
    workflow = (ROOT / ".github/workflows/flowhub-postgresql.yml").read_text(
        encoding="utf-8"
    )
    test_name = (
        "test_postgresql_035_to_036_preserves_mapping_and_enforces_identity_policy"
    )
    assert '"036": REQUIRED_036_TESTS' in manifest
    assert test_name in manifest
    assert test_name in workflow


@pytest.mark.postgres
def test_postgresql_035_to_036_preserves_mapping_and_enforces_identity_policy(
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
    try:
        with engine.begin() as connection:
            connection.execute(sa.text("DROP SCHEMA public CASCADE"))
            connection.execute(sa.text("CREATE SCHEMA public"))
        monkeypatch.setenv("FLOWHUB_DATABASE_URL", url)
        command.upgrade(_config(), "FLOWHUB_035")
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO flowhub_users "
                    "(id,username,hashed_password,role,is_active,created_at) VALUES "
                    "(1,'owner','x','admin',true,CURRENT_TIMESTAMP)"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO sc_sources "
                    "(id,name,source_kind,worksheet_mode,worksheet_name,data_start_row,status,"
                    "version,owner_user_id,created_at,updated_at) VALUES "
                    "('source','Source','external','all',NULL,2,'active',1,1,"
                    "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO sc_source_mapping_revisions "
                    "(id,source_id,version,checksum,worksheet_mode,worksheet_name,data_start_row,"
                    "value_policy_json,created_by_user_id,created_at) VALUES "
                    "('mapping','source',1,:checksum,'all',NULL,2,'{}',1,CURRENT_TIMESTAMP)"
                ),
                {"checksum": "d" * 64},
            )
            connection.execute(
                sa.text(
                    "INSERT INTO sc_source_field_mappings "
                    "(id,mapping_revision_id,field,reference_type,reference_value,required) "
                    "VALUES ('source-key','mapping','source_key','column_letter','B',true)"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO sc_source_mapping_revisions "
                    "(id,source_id,version,checksum,worksheet_mode,worksheet_name,"
                    "data_start_row,value_policy_json,created_by_user_id,created_at) "
                    "VALUES ('mapping-mixed','source',2,:checksum,'all',NULL,2,"
                    "'{}',1,CURRENT_TIMESTAMP)"
                ),
                {"checksum": "e" * 64},
            )
            connection.execute(
                sa.text(
                    "INSERT INTO sc_source_worksheet_rule_sets "
                    "(id,mapping_revision_id,mode,duplicate_product_policy,sealed,"
                    "created_at) VALUES "
                    "('rules-mixed','mapping-mixed','per_worksheet','block',false,"
                    "CURRENT_TIMESTAMP)"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO sc_source_worksheet_rules "
                    "(id,rule_set_id,worksheet_name,enabled,data_start_row,"
                    "value_policy_json) VALUES "
                    "('rule-keyed','rules-mixed','Keyed',true,2,'{}'),"
                    "('rule-unkeyed','rules-mixed','Unkeyed',true,2,'{}')"
                )
            )
            connection.execute(
                sa.text(
                    "INSERT INTO sc_source_worksheet_fields "
                    "(id,worksheet_rule_id,field,reference_type,reference_value,"
                    "required) VALUES "
                    "('mixed-source-key','rule-keyed','source_key','column_letter',"
                    "'B',true)"
                )
            )

        command.upgrade(_config(), "FLOWHUB_036")
        with engine.connect() as connection:
            authority, policy_version = connection.execute(
                sa.text(
                    "SELECT identity_authority_json, identity_policy_version "
                    "FROM sc_source_mapping_revisions WHERE id='mapping'"
                )
            ).one()
            assert authority == {}
            assert policy_version == 2
            assert connection.execute(
                sa.text(
                    "SELECT identity_policy_version "
                    "FROM sc_source_mapping_revisions WHERE id='mapping-mixed'"
                )
            ).scalar_one() == 1
            assert connection.execute(
                sa.text("SELECT COUNT(*) FROM sc_source_product_identities")
            ).scalar_one() == 0
            trigger_names = set(
                connection.execute(
                    sa.text(
                        "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal"
                    )
                ).scalars()
            )
            for table in IDENTITY_TABLES:
                assert f"{table}_immutable" in trigger_names
        with pytest.raises(sa.exc.IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    sa.text(
                        "UPDATE sc_source_mapping_revisions "
                        "SET identity_policy_version=3 WHERE id='mapping'"
                    )
                )
    finally:
        engine.dispose()
