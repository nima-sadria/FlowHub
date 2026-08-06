from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[3]
AUTHORITY_TABLES = {
    "pm_channel_pricing_authority_events",
    "pm_channel_pricing_authority_heads",
    "pm_pricing_authority_write_rejections",
}


def _config() -> Config:
    config = Config(str(ROOT / "alembic_flowhub.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic_flowhub"))
    return config


def _upgrade_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, revision: str) -> sa.Engine:
    database_url = f"sqlite:///{(tmp_path / f'{revision}.sqlite').as_posix()}"
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", database_url)
    command.upgrade(_config(), revision)
    return sa.create_engine(database_url)


def test_clean_install_has_authority_schema_and_model_parity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _upgrade_database(tmp_path, monkeypatch, "FLOWHUB_028")
    try:
        from app.flowhub.database import FlowHubBase
        from app.flowhub.pricing_authority import models as _authority_models  # noqa: F401

        inspector = sa.inspect(engine)
        assert AUTHORITY_TABLES <= set(inspector.get_table_names())
        for table_name in AUTHORITY_TABLES:
            expected = FlowHubBase.metadata.tables[table_name]
            actual_columns = {column["name"]: column for column in inspector.get_columns(table_name)}
            assert set(actual_columns) == {column.name for column in expected.columns}
            assert all(
                actual_columns[column.name]["nullable"] is column.nullable
                for column in expected.columns
            )

        event_indexes = {tuple(index["column_names"]) for index in inspector.get_indexes("pm_channel_pricing_authority_events")}
        assert {("channel_id",), ("new_authority",)} <= event_indexes
        rejection_indexes = {
            tuple(index["column_names"])
            for index in inspector.get_indexes("pm_pricing_authority_write_rejections")
        }
        assert {("channel_id",), ("listing_id",), ("operation_id",), ("reason_code",)} <= rejection_indexes
        attempt_columns = {column["name"] for column in inspector.get_columns("flowhub_provider_write_attempts")}
        assert {
            "pricing_origin",
            "pricing_authority_event_id",
            "pricing_authority_head_version",
        } <= attempt_columns
        binding_columns = {column["name"] for column in inspector.get_columns("pm_workspace_bindings")}
        assert {
            "pricing_authority_event_id",
            "pricing_authority_head_version",
            "expected_pricing_authority",
        } <= binding_columns
    finally:
        engine.dispose()


def test_upgrade_from_027_preserves_channels_and_deterministically_seeds_legacy_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _upgrade_database(tmp_path, monkeypatch, "FLOWHUB_027")
    try:
        channel_ids = ("woocommerce:legacy", "snappshop:legacy")
        with engine.begin() as connection:
            for channel_id in channel_ids:
                connection.execute(
                    sa.text(
                        """
                        INSERT INTO uw_channels (
                            id, connector_type, name, implementation_state, capabilities_json,
                            capability_version, enabled, created_at, updated_at
                        ) VALUES (
                            :id, 'woocommerce', :name, 'available', '{}', 'v1', 1,
                            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        )
                        """
                    ),
                    {"id": channel_id, "name": channel_id},
                )
        command.upgrade(_config(), "FLOWHUB_028")
        command.upgrade(_config(), "head")
        with engine.connect() as connection:
            heads = connection.execute(
                sa.text(
                    "SELECT channel_id, current_authority, head_version, effective_event_id "
                    "FROM pm_channel_pricing_authority_heads WHERE channel_id IN "
                    "('woocommerce:legacy', 'snappshop:legacy') ORDER BY channel_id"
                )
            ).all()
            events = connection.execute(
                sa.text(
                    "SELECT channel_id, previous_authority, new_authority, expected_head_version "
                    "FROM pm_channel_pricing_authority_events WHERE channel_id IN "
                    "('woocommerce:legacy', 'snappshop:legacy') ORDER BY channel_id"
                )
            ).all()
        assert [(row[0], row[1], row[2]) for row in heads] == [
            ("snappshop:legacy", "legacy_formula_engine", 0),
            ("woocommerce:legacy", "legacy_formula_engine", 0),
        ]
        assert all(row[3].startswith("pae_") for row in heads)
        assert events == [
            ("snappshop:legacy", None, "legacy_formula_engine", 0),
            ("woocommerce:legacy", None, "legacy_formula_engine", 0),
        ]
    finally:
        engine.dispose()


def test_downgrade_is_explicitly_forward_only_and_preserves_authority_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _upgrade_database(tmp_path, monkeypatch, "FLOWHUB_028")
    try:
        with pytest.raises(NotImplementedError, match="forward-only"):
            command.downgrade(_config(), "FLOWHUB_027")
        assert AUTHORITY_TABLES <= set(sa.inspect(engine).get_table_names())
        with engine.connect() as connection:
            assert connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "FLOWHUB_028"
    finally:
        engine.dispose()
