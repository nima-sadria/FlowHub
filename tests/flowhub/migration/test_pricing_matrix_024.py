from __future__ import annotations

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[3]
PRICING_TABLES = {
    "pm_policy_revisions",
    "pm_product_group_revisions",
    "pm_product_group_members",
    "pm_rule_entries",
    "pm_channel_config_revisions",
    "pm_policy_lifecycle_events",
    "pm_channel_policy_heads",
    "pm_workspace_bindings",
    "pm_attention_signals",
}


def _config() -> Config:
    config = Config(str(ROOT / "alembic_flowhub.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic_flowhub"))
    return config


def _upgrade_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, revision: str) -> tuple[str, sa.Engine]:
    database_url = f"sqlite:///{(tmp_path / f'{revision}.sqlite').as_posix()}"
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", database_url)
    command.upgrade(_config(), revision)
    return database_url, sa.create_engine(database_url)


def _pricing_metadata() -> dict[str, sa.Table]:
    from app.flowhub.database import FlowHubBase
    from app.flowhub.pricing_matrix import models as _pricing_matrix_models  # noqa: F401

    return {name: FlowHubBase.metadata.tables[name] for name in PRICING_TABLES}


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
    try:
        with engine.begin() as connection:
            connection.execute(sa.text("DROP SCHEMA public CASCADE"))
            connection.execute(sa.text("CREATE SCHEMA public"))
    finally:
        engine.dispose()


def test_clean_install_reaches_pricing_matrix_head_with_model_parity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, engine = _upgrade_database(tmp_path, monkeypatch, "FLOWHUB_024")
    try:
        with engine.connect() as connection:
            assert connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "FLOWHUB_024"
        inspector = sa.inspect(engine)
        assert PRICING_TABLES <= set(inspector.get_table_names())

        for table_name, table in _pricing_metadata().items():
            actual_columns = {column["name"]: column for column in inspector.get_columns(table_name)}
            assert set(actual_columns) == {column.name for column in table.columns}
            for expected in table.columns:
                assert actual_columns[expected.name]["nullable"] is expected.nullable

            actual_indexes = {tuple(index["column_names"]) for index in inspector.get_indexes(table_name)}
            expected_indexes = {tuple(index.columns.keys()) for index in table.indexes}
            assert expected_indexes <= actual_indexes

            actual_unique = {
                tuple(constraint["column_names"])
                for constraint in inspector.get_unique_constraints(table_name)
                if constraint["column_names"]
            }
            expected_unique = {
                tuple(constraint.columns.keys())
                for constraint in table.constraints
                if isinstance(constraint, sa.UniqueConstraint)
            }
            assert expected_unique <= actual_unique

            actual_checks = {
                constraint["name"] for constraint in inspector.get_check_constraints(table_name)
            }
            expected_checks = {
                constraint.name
                for constraint in table.constraints
                if isinstance(constraint, sa.CheckConstraint)
            }
            assert expected_checks <= actual_checks

            actual_foreign_keys = {
                (
                    tuple(constraint["constrained_columns"]),
                    constraint["referred_table"],
                    tuple(constraint["referred_columns"]),
                    constraint.get("options", {}).get("ondelete"),
                )
                for constraint in inspector.get_foreign_keys(table_name)
            }
            expected_foreign_keys = {
                (
                    tuple(element.parent.name for element in constraint.elements),
                    constraint.elements[0].column.table.name,
                    tuple(element.column.name for element in constraint.elements),
                    constraint.ondelete,
                )
                for constraint in table.foreign_key_constraints
            }
            assert expected_foreign_keys <= actual_foreign_keys

        head_column = next(
            column
            for column in inspector.get_columns("pm_channel_policy_heads")
            if column["name"] == "head_version"
        )
        assert str(head_column["default"]).strip("()'") == "0"

        with engine.connect() as connection:
            policy_sql = connection.execute(
                sa.text(
                    "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'pm_policy_revisions'"
                )
            ).scalar_one()
            assert "basis_strategy = 'min'" in policy_sql
            attention_sql = connection.execute(
                sa.text(
                    "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'pm_attention_signals'"
                )
            ).scalar_one()
            assert "status IN ('open','resolved','superseded')" in attention_sql
    finally:
        engine.dispose()


def test_upgrade_from_023_preserves_channels_and_seeds_heads_idempotently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_url, engine = _upgrade_database(tmp_path, monkeypatch, "FLOWHUB_023")
    channel_ids = ("woocommerce:legacy", "snappshop:legacy")
    try:
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

        command.upgrade(_config(), "FLOWHUB_024")
        command.upgrade(_config(), "head")

        with engine.connect() as connection:
            heads = connection.execute(
                sa.text(
                    "SELECT channel_id, head_version, current_event_id, effective_activation_id "
                    "FROM pm_channel_policy_heads ORDER BY channel_id"
                )
            ).all()
            preserved_channels = connection.execute(
                sa.text("SELECT id FROM uw_channels ORDER BY id")
            ).scalars().all()
            inferred_configs = connection.execute(
                sa.text(
                    "SELECT count(*) FROM pm_channel_config_revisions "
                    "WHERE channel_id IN ('woocommerce:legacy', 'snappshop:legacy')"
                )
            ).scalar_one()
            inferred_profiles = connection.execute(
                sa.text(
                    "SELECT count(*) FROM uw_currency_profiles "
                    "WHERE scope = 'channel' AND scope_reference IN "
                    "('woocommerce:legacy', 'snappshop:legacy')"
                )
            ).scalar_one()

        assert heads == [(channel_ids[1], 0, None, None), (channel_ids[0], 0, None, None)]
        assert set(channel_ids) <= set(preserved_channels)
        assert inferred_configs == 0
        assert inferred_profiles == 0
    finally:
        engine.dispose()

    assert database_url.endswith("FLOWHUB_023.sqlite")


def test_pricing_matrix_downgrade_is_explicitly_unsupported_and_non_destructive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, engine = _upgrade_database(tmp_path, monkeypatch, "FLOWHUB_024")
    try:
        with pytest.raises(NotImplementedError, match="forward-only"):
            command.downgrade(_config(), "FLOWHUB_023")

        inspector = sa.inspect(engine)
        assert PRICING_TABLES <= set(inspector.get_table_names())
        with engine.connect() as connection:
            assert connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "FLOWHUB_024"
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_postgresql_clean_install_reaches_024_with_pricing_matrix_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = _postgres_test_url()
    _reset_postgres(url)
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", url)
    command.upgrade(_config(), "FLOWHUB_024")
    engine = sa.create_engine(url)
    try:
        inspector = sa.inspect(engine)
        assert PRICING_TABLES <= set(inspector.get_table_names())
        with engine.connect() as connection:
            assert connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == "FLOWHUB_024"
    finally:
        engine.dispose()
