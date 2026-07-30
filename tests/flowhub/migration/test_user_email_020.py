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


def test_flowhub_020_backfills_setup_owner_email(tmp_path, monkeypatch):
    db_path = tmp_path / "email-login.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("FLOWHUB_DATABASE_URL", db_url)

    command.upgrade(_config(), "FLOWHUB_019")
    engine = sa.create_engine(db_url)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO flowhub_users
                    (username, hashed_password, role, is_active, created_at)
                VALUES
                    ('admin', 'hash', 'owner', 1, CURRENT_TIMESTAMP)
                """
            )
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO flowhub_app_config (key, value, updated_by)
                VALUES ('admin.email', ' Owner@Example.COM ', 'test')
                """
            )
        )

    command.upgrade(_config(), "FLOWHUB_020")

    inspector = sa.inspect(engine)
    assert "email" in {column["name"] for column in inspector.get_columns("flowhub_users")}
    with engine.connect() as connection:
        email = connection.execute(
            sa.text("SELECT email FROM flowhub_users WHERE username = 'admin'")
        ).scalar_one()
    assert email == "owner@example.com"
    engine.dispose()
