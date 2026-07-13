from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor
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


def test_migration_is_frozen_and_does_not_import_live_workspace_metadata() -> None:
    migration = (ROOT / "alembic_flowhub/versions/flowhub_016_unified_workspace.py").read_text()
    frozen = (ROOT / "alembic_flowhub/flowhub_016_frozen_schema.py").read_text()
    assert "FlowHubBase" not in migration
    assert "unified_workspace.models" not in migration
    assert "SCHEMA_FINGERPRINT" in frozen
    assert "POSTGRESQL_DDL" in frozen
    assert "SQLITE_DDL" in frozen


def test_upgrade_from_015_preserves_data_and_enforces_semantic_immutability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "upgrade-015.db"
    url = f"sqlite:///{path}"
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", url)
    config = _config()
    command.upgrade(config, "FLOWHUB_015")
    engine = sa.create_engine(url)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO flowhub_app_config (key,value,updated_by) "
                "VALUES ('migration.sentinel','preserved','test')"
            )
        )
    command.upgrade(config, "FLOWHUB_016")
    with engine.begin() as connection:
        assert connection.execute(
            sa.text("SELECT value FROM flowhub_app_config WHERE key='migration.sentinel'")
        ).scalar_one() == "preserved"
        connection.execute(
            sa.text(
                "INSERT INTO uw_currency_profiles "
                "(id,scope,scope_reference,currency,unit,normalization_currency,"
                "normalization_unit,conversion_factor,conversion_rule,version,enabled,created_at) "
                "VALUES ('currency-1','global','default','IRR','TOMAN','IRR','RIAL',10,"
                "'explicit-v1',1,1,CURRENT_TIMESTAMP)"
            )
        )
    for statement in (
        "UPDATE uw_currency_profiles SET unit='RIAL' WHERE id='currency-1'",
        "DELETE FROM uw_currency_profiles WHERE id='currency-1'",
    ):
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as connection:
            connection.execute(sa.text(statement))
    engine.dispose()


def test_sqlite_foreign_keys_and_global_lock_constraint_are_declared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "fresh-016.db"
    url = f"sqlite:///{path}"
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", url)
    command.upgrade(_config(), "head")
    engine = sa.create_engine(url)
    inspector = sa.inspect(engine)
    draft_fks = {column for fk in inspector.get_foreign_keys("uw_drafts") for column in fk["constrained_columns"]}
    attempt_tables = {"uw_apply_attempts", "uw_apply_attempt_events"}
    assert "current_revision_id" in draft_fks
    assert attempt_tables <= set(inspector.get_table_names())
    lock_uniques = {
        tuple(item["column_names"])
        for item in inspector.get_unique_constraints("uw_workspace_locks")
    }
    assert ("channel_id", "listing_id") in lock_uniques
    engine.dispose()


def test_postgresql_frozen_ddl_contains_effective_triggers_and_foreign_keys() -> None:
    from alembic_flowhub.flowhub_016_frozen_schema import POSTGRESQL_DDL

    ddl = "\n".join(POSTGRESQL_DDL)
    assert "CONSTRAINT uq_uw_lock_scope UNIQUE (channel_id, listing_id)" in ddl
    assert "FOREIGN KEY(current_revision_id) REFERENCES uw_draft_revisions" in ddl
    assert "FOREIGN KEY(snapshot_id) REFERENCES uw_workspace_snapshots" in ddl
    assert "CREATE TABLE uw_apply_attempts" in ddl


def _postgres_test_url() -> str:
    url = os.environ.get("FLOWHUB_TEST_POSTGRES_URL", "")
    if not url:
        pytest.skip("FLOWHUB_TEST_POSTGRES_URL is not configured")
    database = sa.engine.make_url(url).database or ""
    if "test" not in database.lower():
        pytest.fail("FLOWHUB_TEST_POSTGRES_URL must reference an isolated test database")
    return url


def _reset_postgres(url: str) -> None:
    engine = sa.create_engine(url)
    with engine.begin() as connection:
        connection.execute(sa.text("DROP SCHEMA public CASCADE"))
        connection.execute(sa.text("CREATE SCHEMA public"))
    engine.dispose()


@pytest.mark.postgres
def test_postgresql_immutability_and_foreign_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    url = _postgres_test_url()
    _reset_postgres(url)
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", url)
    command.upgrade(_config(), "head")
    engine = sa.create_engine(url)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO uw_currency_profiles "
                "(id,scope,scope_reference,currency,unit,normalization_currency,"
                "normalization_unit,conversion_factor,conversion_rule,version,enabled,checksum,created_at) "
                "VALUES ('pg-currency','global','default','IRR','TOMAN','IRR','RIAL',10,"
                "'explicit-v1',1,true,'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',"
                "CURRENT_TIMESTAMP)"
            )
        )
    for statement in (
        "UPDATE uw_currency_profiles SET unit='RIAL' WHERE id='pg-currency'",
        "DELETE FROM uw_currency_profiles WHERE id='pg-currency'",
    ):
        with pytest.raises(sa.exc.DBAPIError), engine.begin() as connection:
            connection.execute(sa.text(statement))
    with pytest.raises(sa.exc.IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO uw_drafts "
                "(id,workspace_id,snapshot_id,owner_user_id,current_revision_id,version,status,created_at,updated_at) "
                "VALUES ('bad-draft','missing-workspace','missing-snapshot',999,NULL,0,'draft',"
                "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
            )
        )
    engine.dispose()


@pytest.mark.postgres
def test_postgresql_upgrade_from_015_preserves_sentinel(monkeypatch: pytest.MonkeyPatch) -> None:
    url = _postgres_test_url()
    _reset_postgres(url)
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", url)
    config = _config()
    command.upgrade(config, "FLOWHUB_015")
    engine = sa.create_engine(url)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO flowhub_app_config (key,value,updated_by) "
                "VALUES ('migration.pg.sentinel','preserved','test')"
            )
        )
    command.upgrade(config, "FLOWHUB_016")
    with engine.begin() as connection:
        assert connection.execute(
            sa.text(
                "SELECT value FROM flowhub_app_config WHERE key='migration.pg.sentinel'"
            )
        ).scalar_one() == "preserved"
        assert "uw_apply_attempts" in sa.inspect(connection).get_table_names()
    engine.dispose()


@pytest.mark.postgres
def test_postgresql_global_lock_uniqueness_under_concurrency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = _postgres_test_url()
    _reset_postgres(url)
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", url)
    command.upgrade(_config(), "head")
    engine = sa.create_engine(url)
    barrier = threading.Barrier(2)

    def contender(lock_id: str) -> str:
        connection = engine.connect()
        transaction = connection.begin()
        try:
            # This test isolates the global unique index; referenced business rows are
            # exercised separately by the live foreign-key rejection test above.
            connection.execute(sa.text("SET LOCAL session_replication_role = replica"))
            barrier.wait(timeout=5)
            connection.execute(
                sa.text(
                    "INSERT INTO uw_workspace_locks "
                    "(id,workspace_id,channel_id,listing_id,apply_job_id,acquired_at,expires_at) "
                    "VALUES (:id,'workspace','woocommerce:primary','listing','job',"
                    "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP + INTERVAL '15 minutes')"
                ),
                {"id": lock_id},
            )
            transaction.commit()
            return "acquired"
        except sa.exc.IntegrityError:
            transaction.rollback()
            return "conflict"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(contender, ("lock-a", "lock-b")))
    assert sorted(outcomes) == ["acquired", "conflict"]
    engine.dispose()
