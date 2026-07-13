from __future__ import annotations

import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command

ROOT = Path(__file__).resolve().parents[3]
LEGACY_016_COMMIT = "b56ff5c129e03bbd3337603b5becd674407b11c9"


def _config(root: Path = ROOT) -> Config:
    config = Config(str(root / "alembic_flowhub.ini"))
    config.set_main_option("script_location", str(root / "alembic_flowhub"))
    return config


def _url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def test_flowhub_017_is_additive_frozen_and_forward_only() -> None:
    source = (
        ROOT / "alembic_flowhub/versions/flowhub_017_production_safety.py"
    ).read_text(encoding="utf-8")
    assert 'revision = "FLOWHUB_017"' in source
    assert 'down_revision = "FLOWHUB_016"' in source
    assert "FlowHubBase" not in source
    assert "unified_workspace.models" not in source
    assert "drop_table" not in source
    assert "def downgrade()" in source


def test_flowhub_017_backfills_profiles_preserves_sentinel_and_enforces_immutability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = _url(tmp_path / "upgrade-017.sqlite")
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", url)
    config = _config()
    command.upgrade(config, "FLOWHUB_016")
    engine = sa.create_engine(url)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO flowhub_app_config(key,value,updated_by) "
                "VALUES ('migration.017.sentinel','preserved','test')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO uw_currency_profiles "
                "(id,scope,scope_reference,currency,unit,normalization_currency,"
                "normalization_unit,conversion_factor,conversion_rule,version,enabled,created_at) "
                "VALUES ('currency-017','global','default','IRR','TOMAN','IRR','RIAL',"
                "10,'explicit-v1',1,1,CURRENT_TIMESTAMP)"
            )
        )
    command.upgrade(config, "FLOWHUB_017")
    inspector = sa.inspect(engine)
    assert {
        "uw_apply_attempts",
        "uw_apply_attempt_events",
        "flowhub_provider_write_attempts",
        "flowhub_provider_write_attempt_events",
    } <= set(inspector.get_table_names())
    with engine.begin() as connection:
        assert (
            connection.execute(
                sa.text(
                    "SELECT value FROM flowhub_app_config "
                    "WHERE key='migration.017.sentinel'"
                )
            ).scalar_one()
            == "preserved"
        )
        profile_checksum = connection.execute(
            sa.text(
                "SELECT checksum FROM uw_currency_profiles WHERE id='currency-017'"
            )
        ).scalar_one()
        assert len(profile_checksum) == 64
        connection.execute(
            sa.text(
                "INSERT INTO flowhub_provider_write_attempts "
                "(id,source_workflow,operation_id,logical_item_id,workspace_id,"
                "apply_job_id,apply_job_item_id,listing_id,channel_id,external_identity,"
                "normalized_payload_json,payload_hash,provider_idempotency_key,"
                "attempt_number,correlation_id,created_at) VALUES "
                "('attempt-017','test','operation-017','item-017',NULL,NULL,NULL,"
                "'listing-017','test:channel','external-017','{}',"
                "'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',"
                "'provider-key-017',1,'correlation-017',CURRENT_TIMESTAMP)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO flowhub_provider_write_attempt_events "
                "(id,attempt_id,outcome,provider_response_json,error_category,"
                "error_message,occurred_at) VALUES "
                "('event-017','attempt-017','dispatch_intent_recorded','{}',"
                "NULL,NULL,CURRENT_TIMESTAMP)"
            )
        )
    for statement in (
        "UPDATE uw_currency_profiles SET unit='RIAL' WHERE id='currency-017'",
        "DELETE FROM uw_currency_profiles WHERE id='currency-017'",
        "UPDATE flowhub_provider_write_attempts SET channel_id='other' WHERE id='attempt-017'",
        "DELETE FROM flowhub_provider_write_attempt_events WHERE id='event-017'",
    ):
        with pytest.raises(sa.exc.IntegrityError), engine.begin() as connection:
            connection.execute(sa.text(statement))
    engine.dispose()


def test_flowhub_017_repairs_legacy_016(tmp_path: Path) -> None:
    archive = tmp_path / "legacy.zip"
    legacy_root = tmp_path / "legacy"
    result = subprocess.run(
        [
            "git",
            "archive",
            "--format=zip",
            f"--output={archive}",
            LEGACY_016_COMMIT,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"legacy commit unavailable: {result.stderr.strip()}")
    with zipfile.ZipFile(archive) as payload:
        payload.extractall(legacy_root)
    database = tmp_path / "legacy-016.sqlite"
    env = {**os.environ, "FLOWHUB_DATABASE_URL": _url(database)}
    legacy = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic_flowhub.ini", "upgrade", "FLOWHUB_016"],
        cwd=legacy_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert legacy.returncode == 0, legacy.stderr
    current = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic_flowhub.ini", "upgrade", "FLOWHUB_017"],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert current.returncode == 0, current.stderr
    engine = sa.create_engine(_url(database))
    inspector = sa.inspect(engine)
    assert {
        "uw_apply_attempts",
        "uw_apply_attempt_events",
        "flowhub_provider_write_attempts",
        "flowhub_provider_write_attempt_events",
    } <= set(inspector.get_table_names())
    assert {
        "logical_operation_key",
        "heartbeat_at",
        "worker_id",
        "operation_checksum",
    } <= {column["name"] for column in inspector.get_columns("uw_apply_jobs")}
    assert "channel_id" in {
        column["name"] for column in inspector.get_columns("uw_workspace_locks")
    }
    engine.dispose()
