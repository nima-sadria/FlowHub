from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[3]


def _config() -> Config:
    config = Config(str(ROOT / "alembic_flowhub.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic_flowhub"))
    return config


def test_existing_receipts_upgrade_with_backfilled_item_identity(tmp_path, monkeypatch):
    database_path = tmp_path / "from-022.sqlite"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", database_url)
    command.upgrade(_config(), "FLOWHUB_022")
    engine = sa.create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO webhook_receipts
                    (
                        channel_id, provider, provider_event_id, payload_hash,
                        payload_summary_json, normalized_event_json, received_at,
                        processing_state, attempt_count
                    )
                VALUES
                    (
                        'tapsishop:main', 'tapsishop', 'legacy-request-1',
                        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                        '{}', '{}', CURRENT_TIMESTAMP, 'processed', 1
                    )
                """
            )
        )

    command.upgrade(_config(), "head")

    inspector = sa.inspect(engine)
    assert "webhook_provider_event_identities" in inspector.get_table_names()
    with engine.connect() as connection:
        identity = connection.execute(
            sa.text(
                """
                SELECT channel_id, provider, provider_event_id
                FROM webhook_provider_event_identities
                """
            )
        ).one()
        revision = connection.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    assert identity == ("tapsishop:main", "tapsishop", "legacy-request-1")
    assert revision == "FLOWHUB_023"
    engine.dispose()


def test_webhook_identity_migration_downgrade_and_reupgrade(tmp_path, monkeypatch):
    database_path = tmp_path / "roundtrip-023.sqlite"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", database_url)
    command.upgrade(_config(), "head")
    command.downgrade(_config(), "FLOWHUB_022")
    engine = sa.create_engine(database_url)
    assert "webhook_provider_event_identities" not in sa.inspect(engine).get_table_names()

    command.upgrade(_config(), "head")

    assert "webhook_provider_event_identities" in sa.inspect(engine).get_table_names()
    engine.dispose()
