from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory

from alembic import command

ROOT = Path(__file__).resolve().parents[3]


def _alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic_flowhub.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic_flowhub"))
    return cfg


def _head_revision() -> str:
    return ScriptDirectory.from_config(_alembic_config()).get_current_head()


def test_legacy_revision_and_core_tables_upgrade_without_data_loss(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy.db"
    db_url = f"sqlite:///{db_path}"
    engine = sa.create_engine(db_url)

    from app.flowhub.auth import models as _auth_models  # noqa: F401
    from app.flowhub.data_layer import models as _data_layer_models  # noqa: F401
    from app.flowhub.database import FlowHubBase
    from app.flowhub.integration_platform import models as _integration_models  # noqa: F401
    from app.flowhub.logging_platform import models as _logging_models  # noqa: F401
    from app.flowhub.orders import models as _order_models  # noqa: F401
    from app.flowhub.setup import models as _setup_models  # noqa: F401
    from app.flowhub.webhooks import models as _webhook_models  # noqa: F401

    # A legacy beta_007 database cannot contain future Unified Workspace or
    # Source-Centric Workspace tables.
    # Test collection imports current models globally, so exclude those tables from
    # this historical fixture instead of accidentally pre-creating the migration target.
    legacy_tables = [
        table
        for table in FlowHubBase.metadata.sorted_tables
        if not table.name.startswith(("uw_", "sc_"))
    ]
    FlowHubBase.metadata.create_all(engine, tables=legacy_tables)
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        conn.execute(sa.text("INSERT INTO alembic_version (version_num) VALUES ('beta_007')"))
        conn.execute(sa.text("ALTER TABLE flowhub_users RENAME TO beta_users"))
        conn.execute(sa.text("ALTER TABLE flowhub_refresh_tokens RENAME TO beta_refresh_tokens"))
        conn.execute(sa.text("ALTER TABLE flowhub_login_audit RENAME TO beta_login_audit"))
        conn.execute(sa.text("ALTER TABLE flowhub_app_config RENAME TO beta_app_config"))
        conn.execute(
            sa.text(
                """
                INSERT INTO beta_users (id, username, hashed_password, role, is_active, created_at)
                VALUES (1, 'admin', 'hashed-secret', 'admin', 1, CURRENT_TIMESTAMP)
                """
            )
        )
        conn.execute(
            sa.text(
                """
                INSERT INTO beta_app_config (key, value, updated_by)
                VALUES ('setup.completed', 'true', 'fixture')
                """
            )
        )

    monkeypatch.setenv("FLOWHUB_DATABASE_URL", db_url)
    command.upgrade(_alembic_config(), "head")

    inspector = sa.inspect(engine)
    tables = set(inspector.get_table_names())
    assert "flowhub_users" in tables
    assert "flowhub_refresh_tokens" in tables
    assert "flowhub_login_audit" in tables
    assert "flowhub_app_config" in tables
    assert "beta_users" not in tables
    assert "beta_app_config" not in tables

    with engine.connect() as conn:
        revision = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
        admin_count = conn.execute(sa.text("SELECT COUNT(*) FROM flowhub_users WHERE username = 'admin'")).scalar_one()
        setup_value = conn.execute(
            sa.text("SELECT value FROM flowhub_app_config WHERE key = 'setup.completed'")
        ).scalar_one()

    assert revision == _head_revision()
    assert admin_count == 1
    assert setup_value == "true"
    engine.dispose()


def test_fresh_database_still_upgrades_to_head(tmp_path, monkeypatch):
    db_path = tmp_path / "fresh.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", db_url)

    command.upgrade(_alembic_config(), "head")

    engine = sa.create_engine(db_url)
    with engine.connect() as conn:
        revision = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert revision == _head_revision()
    tables = set(sa.inspect(engine).get_table_names())
    assert {
        "dl_workspace_previews",
        "dl_source_read_locks",
        "dl_source_read_reservations",
        "flowhub_login_rate_limits",
        "webhook_receipts",
        "webhook_processing_attempts",
        "webhook_dead_letters",
        "channel_orders",
        "channel_order_items",
        "channel_shipments",
        "channel_invoices",
        "channel_order_events",
        "channel_inventory_effects",
        "channel_order_sync_checkpoints",
        "channel_order_sync_audit",
    } <= tables
    checkpoint_columns = {column["name"] for column in sa.inspect(engine).get_columns("channel_order_sync_checkpoints")}
    assert {
        "lease_expires_at",
        "lease_heartbeat_at",
        "last_success_at",
        "last_failure_at",
        "last_failure_category",
        "last_run_id",
    } <= checkpoint_columns
    engine.dispose()
