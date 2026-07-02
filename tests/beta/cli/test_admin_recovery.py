"""Tests for FlowHub admin recovery CLI commands."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


def _prepare_db(tmp_path):
    db_url = f"sqlite:///{tmp_path}/admin-recovery.db"
    env_file = tmp_path / ".env.beta"
    env_file.write_text(f"BETA_DATABASE_URL={db_url}\n", encoding="utf-8")

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.beta.auth import models  # noqa: F401
    from app.beta.database import BetaBase, _get_engine

    _get_engine.cache_clear()
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    BetaBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return engine, Session, env_file


def test_admin_create_creates_emergency_admin(tmp_path):
    engine, Session, env_file = _prepare_db(tmp_path)

    result = runner.invoke(
        app,
        [
            "admin",
            "create",
            "--username",
            "rescueadmin",
            "--password",
            "recovered-password",
            "--env-file",
            str(env_file),
        ],
    )

    assert result.exit_code == 0
    assert "rescueadmin" in result.output

    from app.beta.auth.repository import get_user_by_username

    db = Session()
    try:
        user = get_user_by_username(db, "rescueadmin")
        assert user is not None
        assert user.role == "admin"
        assert user.is_active is True
    finally:
        db.close()
        engine.dispose()


def test_admin_reset_password_updates_hash_and_revokes_sessions(tmp_path):
    engine, Session, env_file = _prepare_db(tmp_path)

    from app.beta.auth.password import hash_password, verify_password
    from app.beta.auth.repository import create_user, store_refresh_token

    db = Session()
    user = create_user(db, username="lockedadmin", hashed_password=hash_password("old-password"), role="admin")
    user.is_active = False
    db.commit()
    token = store_refresh_token(
        db,
        user_id=user.id,
        token_hash="a" * 64,
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1),
    )
    user_id = user.id
    token_id = token.id
    db.close()

    result = runner.invoke(
        app,
        [
            "admin",
            "reset-password",
            "--username",
            "lockedadmin",
            "--password",
            "new-password",
            "--env-file",
            str(env_file),
        ],
    )

    assert result.exit_code == 0
    assert "Active sessions revoked" in result.output

    db = Session()
    try:
        from app.beta.auth.models import BetaRefreshToken, BetaUser

        refreshed = db.get(BetaUser, user_id)
        assert refreshed is not None
        assert refreshed.is_active is True
        assert verify_password("new-password", refreshed.hashed_password) is True
        revoked = db.get(BetaRefreshToken, token_id)
        assert revoked is not None
        assert revoked.revoked_at is not None
    finally:
        db.close()
        engine.dispose()


def test_admin_reset_password_refuses_non_admin(tmp_path):
    engine, Session, env_file = _prepare_db(tmp_path)

    from app.beta.auth.password import hash_password
    from app.beta.auth.repository import create_user

    db = Session()
    create_user(db, username="viewer", hashed_password=hash_password("old-password"), role="viewer")
    db.close()

    result = runner.invoke(
        app,
        [
            "admin",
            "reset-password",
            "--username",
            "viewer",
            "--password",
            "new-password",
            "--env-file",
            str(env_file),
        ],
    )

    assert result.exit_code != 0
    assert "not an administrator" in result.output
    engine.dispose()


def test_admin_list_does_not_show_password_hashes(tmp_path):
    engine, Session, env_file = _prepare_db(tmp_path)

    from app.beta.auth.password import hash_password
    from app.beta.auth.repository import create_user

    db = Session()
    create_user(db, username="listedadmin", hashed_password=hash_password("hidden-password"), role="admin")
    db.close()

    result = runner.invoke(app, ["admin", "list", "--env-file", str(env_file)])

    assert result.exit_code == 0
    assert "listedadmin" in result.output
    assert "hidden-password" not in result.output
    assert "argon2" not in result.output
    engine.dispose()
