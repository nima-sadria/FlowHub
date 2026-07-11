"""FlowHub - Alembic migration environment.

Reads FLOWHUB_DATABASE_URL from the environment (set in .env).
target_metadata is wired to FlowHubBase so that `alembic --autogenerate`
detects model changes from FLOWHUB_001 onward.

Usage:
  alembic -c alembic_flowhub.ini upgrade head
  alembic -c alembic_flowhub.ini current
  alembic -c alembic_flowhub.ini history
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, inspect, pool, text

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = os.environ.get("FLOWHUB_DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)

# Import models so their tables are registered on FlowHubBase.metadata before
# Alembic inspects it.  The import chain is: models -> database (FlowHubBase).
# The database module is safe to import without a live connection.
from app.flowhub.database import FlowHubBase  # noqa: E402
from app.flowhub.auth import models as _auth_models  # noqa: E402, F401
from app.flowhub.setup import models as _setup_models  # noqa: E402, F401
from app.flowhub.data_layer import models as _data_layer_models  # noqa: E402, F401
from app.flowhub.integration_platform import models as _integration_platform_models  # noqa: E402, F401
from app.flowhub.write_pipeline import models as _write_pipeline_models  # noqa: E402, F401
from app.flowhub.webhooks import models as _webhook_models  # noqa: E402, F401
from app.flowhub.orders import models as _order_models  # noqa: E402, F401

target_metadata = FlowHubBase.metadata


_LEGACY_REVISION_MAP = {
    "beta_001": "FLOWHUB_001",
    "beta_002": "FLOWHUB_002",
    "beta_003": "FLOWHUB_003",
    "beta_004": "FLOWHUB_004",
    "beta_005": "FLOWHUB_005",
    "beta_006": "FLOWHUB_006",
    "beta_007": "FLOWHUB_007",
}

_LEGACY_TABLE_RENAMES = (
    ("beta_users", "flowhub_users"),
    ("beta_refresh_tokens", "flowhub_refresh_tokens"),
    ("beta_login_audit", "flowhub_login_audit"),
    ("beta_app_config", "flowhub_app_config"),
)


def _quote_identifier(dialect_name: str, name: str) -> str:
    escaped = name.replace('"', '""')
    if dialect_name == "mysql":
        return f"`{name.replace('`', '``')}`"
    return f'"{escaped}"'


def _rename_table(connection, old_name: str, new_name: str) -> None:
    old = _quote_identifier(connection.dialect.name, old_name)
    new = _quote_identifier(connection.dialect.name, new_name)
    connection.execute(text(f"ALTER TABLE {old} RENAME TO {new}"))


def _normalize_legacy_revision_state(connection) -> None:
    """Bridge one release of old internal revision/table names.

    This runs before Alembic resolves the current revision, so installations
    stamped with the old revision IDs can continue upgrading without data loss.
    """

    inspector = inspect(connection)
    table_names = set(inspector.get_table_names())
    if "alembic_version" not in table_names:
        return

    row = connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).fetchone()
    if not row:
        return

    current = row[0]
    mapped = _LEGACY_REVISION_MAP.get(current)
    if not mapped:
        return

    for old_name, new_name in _LEGACY_TABLE_RENAMES:
        if old_name in table_names and new_name not in table_names:
            _rename_table(connection, old_name, new_name)
            table_names.remove(old_name)
            table_names.add(new_name)

    connection.execute(
        text("UPDATE alembic_version SET version_num = :version"),
        {"version": mapped},
    )


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        with connection.begin():
            _normalize_legacy_revision_state(connection)
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
