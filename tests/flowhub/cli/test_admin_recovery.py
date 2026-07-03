"""Tests for FlowHub admin recovery CLI commands."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import typer
from typer.testing import CliRunner

import cli.admin as admin_cli
from cli.main import app

runner = CliRunner()


def _prepare_db(tmp_path):
    db_url = f"sqlite:///{tmp_path}/admin-recovery.db"
    env_file = tmp_path / ".env"
    env_file.write_text(f"FLOWHUB_DATABASE_URL={db_url}\n", encoding="utf-8")

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.flowhub.auth import models  # noqa: F401
    from app.flowhub.database import FlowHubBase, _get_engine

    _get_engine.cache_clear()
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    FlowHubBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return engine, Session, env_file


def test_admin_create_creates_emergency_admin(tmp_path, monkeypatch):
    engine, Session, env_file = _prepare_db(tmp_path)
    monkeypatch.setattr(admin_cli, "_prompt_secure_password", lambda prompt="New admin password": "recovered-password")

    result = runner.invoke(
        app,
        [
            "admin",
            "create",
            "--username",
            "rescueadmin",
            "--email",
            "rescue@example.com",
            "--env-file",
            str(env_file),
        ],
        input="y\n",
    )

    assert result.exit_code == 0
    assert "rescueadmin" in result.output
    assert "recovered-password" not in result.output

    from app.flowhub.auth.repository import get_user_by_username

    db = Session()
    try:
        user = get_user_by_username(db, "rescueadmin")
        assert user is not None
        assert user.role == "admin"
        assert user.is_active is True
    finally:
        db.close()
        engine.dispose()


def test_admin_create_requires_valid_email(tmp_path, monkeypatch):
    engine, _Session, env_file = _prepare_db(tmp_path)
    monkeypatch.setattr(admin_cli, "_prompt_secure_password", lambda prompt="New admin password": "recovered-password")

    result = runner.invoke(
        app,
        [
            "admin",
            "create",
            "--username",
            "bademailadmin",
            "--email",
            "not-an-email",
            "--env-file",
            str(env_file),
        ],
    )

    assert result.exit_code != 0
    assert "Enter a valid email address" in result.output
    assert "recovered-password" not in result.output
    engine.dispose()


def test_admin_create_confirmation_makes_no_change(tmp_path, monkeypatch):
    engine, Session, env_file = _prepare_db(tmp_path)
    monkeypatch.setattr(admin_cli, "_prompt_secure_password", lambda prompt="New admin password": "recovered-password")

    result = runner.invoke(
        app,
        [
            "admin",
            "create",
            "--username",
            "cancelcreate",
            "--email",
            "cancel@example.com",
            "--env-file",
            str(env_file),
        ],
        input="n\n",
    )

    assert result.exit_code != 0
    assert "No changes made" in result.output

    from app.flowhub.auth.repository import get_user_by_username

    db = Session()
    try:
        assert get_user_by_username(db, "cancelcreate") is None
    finally:
        db.close()
        engine.dispose()


def test_admin_reset_password_updates_hash_and_revokes_sessions(tmp_path, monkeypatch):
    engine, Session, env_file = _prepare_db(tmp_path)
    monkeypatch.setattr(admin_cli, "_prompt_secure_password", lambda prompt="New admin password": "new-password")

    from app.flowhub.auth.password import hash_password, verify_password
    from app.flowhub.auth.repository import create_user, store_refresh_token

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
            "--env-file",
            str(env_file),
        ],
        input="y\n",
    )

    assert result.exit_code == 0
    assert "Active sessions revoked" in result.output
    assert "new-password" not in result.output

    db = Session()
    try:
        from app.flowhub.auth.models import FlowHubRefreshToken, FlowHubUser

        refreshed = db.get(FlowHubUser, user_id)
        assert refreshed is not None
        assert refreshed.is_active is True
        assert verify_password("new-password", refreshed.hashed_password) is True
        revoked = db.get(FlowHubRefreshToken, token_id)
        assert revoked is not None
        assert revoked.revoked_at is not None
    finally:
        db.close()
        engine.dispose()


def test_admin_reset_password_refuses_non_admin(tmp_path, monkeypatch):
    engine, Session, env_file = _prepare_db(tmp_path)
    monkeypatch.setattr(admin_cli, "_prompt_secure_password", lambda prompt="New admin password": "new-password")

    from app.flowhub.auth.password import hash_password
    from app.flowhub.auth.repository import create_user

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
            "--env-file",
            str(env_file),
        ],
        input="y\n",
    )

    assert result.exit_code != 0
    assert "not an administrator" in result.output
    engine.dispose()


def test_admin_reset_password_help_has_no_password_option():
    result = runner.invoke(app, ["admin", "reset-password", "--help"])

    assert result.exit_code == 0
    assert "--password" not in result.output
    assert " -p " not in result.output


def test_admin_create_help_has_no_password_option():
    result = runner.invoke(app, ["admin", "create", "--help"])

    assert result.exit_code == 0
    assert "--password" not in result.output
    assert " -p " not in result.output


def test_secure_password_prompt_rejects_confirmation_mismatch(monkeypatch):
    monkeypatch.setattr(admin_cli, "_secure_password_input_available", lambda: True)
    values = iter(["new-password", "mismatch-password"])
    monkeypatch.setattr(admin_cli.getpass, "getpass", lambda _prompt: next(values))

    with pytest.raises(typer.Exit):
        admin_cli._prompt_secure_password()


def test_admin_reset_password_aborts_without_secure_input(tmp_path, monkeypatch):
    engine, Session, env_file = _prepare_db(tmp_path)

    from app.flowhub.auth.password import hash_password, verify_password
    from app.flowhub.auth.repository import create_user

    db = Session()
    user = create_user(db, username="ttyadmin", hashed_password=hash_password("old-password"), role="admin")
    user_id = user.id
    db.close()

    monkeypatch.setattr(admin_cli, "_secure_password_input_available", lambda: False)

    result = runner.invoke(
        app,
        [
            "admin",
            "reset-password",
            "--username",
            "ttyadmin",
            "--env-file",
            str(env_file),
        ],
    )

    assert result.exit_code != 0
    assert admin_cli.SECURE_INPUT_ERROR in result.output

    db = Session()
    try:
        from app.flowhub.auth.models import FlowHubUser

        refreshed = db.get(FlowHubUser, user_id)
        assert refreshed is not None
        assert verify_password("old-password", refreshed.hashed_password) is True
    finally:
        db.close()
        engine.dispose()


def test_admin_reset_password_final_confirmation_makes_no_change(tmp_path, monkeypatch):
    engine, Session, env_file = _prepare_db(tmp_path)
    monkeypatch.setattr(admin_cli, "_prompt_secure_password", lambda prompt="New admin password": "new-password")

    from app.flowhub.auth.password import hash_password, verify_password
    from app.flowhub.auth.repository import create_user

    db = Session()
    user = create_user(db, username="canceladmin", hashed_password=hash_password("old-password"), role="admin")
    user_id = user.id
    db.close()

    result = runner.invoke(
        app,
        [
            "admin",
            "reset-password",
            "--username",
            "canceladmin",
            "--env-file",
            str(env_file),
        ],
        input="n\n",
    )

    assert result.exit_code != 0
    assert "No changes made" in result.output

    db = Session()
    try:
        from app.flowhub.auth.models import FlowHubUser

        refreshed = db.get(FlowHubUser, user_id)
        assert refreshed is not None
        assert verify_password("old-password", refreshed.hashed_password) is True
    finally:
        db.close()
        engine.dispose()


def test_admin_reset_username_renames_admin_and_revokes_sessions(tmp_path):
    engine, Session, env_file = _prepare_db(tmp_path)

    from app.flowhub.auth.password import hash_password
    from app.flowhub.auth.repository import create_user, store_refresh_token

    db = Session()
    user = create_user(db, username="oldadmin", hashed_password=hash_password("password"), role="admin")
    token = store_refresh_token(
        db,
        user_id=user.id,
        token_hash="b" * 64,
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1),
    )
    user_id = user.id
    token_id = token.id
    db.close()

    result = runner.invoke(
        app,
        [
            "admin",
            "reset-username",
            "--username",
            "oldadmin",
            "--new-username",
            "newadmin",
            "--env-file",
            str(env_file),
        ],
    )

    assert result.exit_code == 0
    assert "newadmin" in result.output
    assert "Active sessions revoked" in result.output

    db = Session()
    try:
        from app.flowhub.auth.models import FlowHubRefreshToken, FlowHubUser
        from app.flowhub.auth.repository import get_user_by_username

        assert get_user_by_username(db, "oldadmin") is None
        renamed = db.get(FlowHubUser, user_id)
        assert renamed is not None
        assert renamed.username == "newadmin"
        revoked = db.get(FlowHubRefreshToken, token_id)
        assert revoked is not None
        assert revoked.revoked_at is not None
    finally:
        db.close()
        engine.dispose()


def test_admin_reset_username_refuses_non_admin(tmp_path):
    engine, Session, env_file = _prepare_db(tmp_path)

    from app.flowhub.auth.password import hash_password
    from app.flowhub.auth.repository import create_user

    db = Session()
    create_user(db, username="viewer", hashed_password=hash_password("password"), role="viewer")
    db.close()

    result = runner.invoke(
        app,
        [
            "admin",
            "reset-username",
            "--username",
            "viewer",
            "--new-username",
            "renamedviewer",
            "--env-file",
            str(env_file),
        ],
    )

    assert result.exit_code != 0
    assert "not an administrator" in result.output
    engine.dispose()


def test_admin_reset_username_refuses_duplicate_username(tmp_path):
    engine, Session, env_file = _prepare_db(tmp_path)

    from app.flowhub.auth.password import hash_password
    from app.flowhub.auth.repository import create_user

    db = Session()
    create_user(db, username="firstadmin", hashed_password=hash_password("password"), role="admin")
    create_user(db, username="secondadmin", hashed_password=hash_password("password"), role="admin")
    db.close()

    result = runner.invoke(
        app,
        [
            "admin",
            "reset-username",
            "--username",
            "firstadmin",
            "--new-username",
            "secondadmin",
            "--env-file",
            str(env_file),
        ],
    )

    assert result.exit_code != 0
    assert "already exists" in result.output

    db = Session()
    try:
        from app.flowhub.auth.repository import get_user_by_username

        assert get_user_by_username(db, "firstadmin") is not None
        assert get_user_by_username(db, "secondadmin") is not None
    finally:
        db.close()
        engine.dispose()


def test_admin_list_does_not_show_password_hashes(tmp_path):
    engine, Session, env_file = _prepare_db(tmp_path)

    from app.flowhub.auth.password import hash_password
    from app.flowhub.auth.repository import create_user

    db = Session()
    create_user(db, username="listedadmin", hashed_password=hash_password("hidden-password"), role="admin")
    db.close()

    result = runner.invoke(app, ["admin", "list", "--env-file", str(env_file)])

    assert result.exit_code == 0
    assert "listedadmin" in result.output
    assert "hidden-password" not in result.output
    assert "argon2" not in result.output
    engine.dispose()


def test_admin_delete_removes_selected_admin(tmp_path):
    engine, Session, env_file = _prepare_db(tmp_path)

    from app.flowhub.auth.password import hash_password
    from app.flowhub.auth.repository import create_user, get_user_by_username

    db = Session()
    create_user(db, username="keepadmin", hashed_password=hash_password("password"), role="admin")
    create_user(db, username="deleteadmin", hashed_password=hash_password("password"), role="admin")
    db.close()

    result = runner.invoke(
        app,
        [
            "admin",
            "delete",
            "--username",
            "deleteadmin",
            "--env-file",
            str(env_file),
        ],
        input="y\n",
    )

    assert result.exit_code == 0
    assert "Administrator accounts:" in result.output
    assert "deleteadmin" in result.output

    db = Session()
    try:
        assert get_user_by_username(db, "deleteadmin") is None
        assert get_user_by_username(db, "keepadmin") is not None
    finally:
        db.close()
        engine.dispose()


def test_admin_delete_refuses_last_admin(tmp_path):
    engine, Session, env_file = _prepare_db(tmp_path)

    from app.flowhub.auth.password import hash_password
    from app.flowhub.auth.repository import create_user, get_user_by_username

    db = Session()
    create_user(db, username="onlyadmin", hashed_password=hash_password("password"), role="admin")
    db.close()

    result = runner.invoke(
        app,
        [
            "admin",
            "delete",
            "--username",
            "onlyadmin",
            "--env-file",
            str(env_file),
        ],
    )

    assert result.exit_code != 0
    assert "Refusing to delete the last administrator" in result.output

    db = Session()
    try:
        assert get_user_by_username(db, "onlyadmin") is not None
    finally:
        db.close()
        engine.dispose()


def test_admin_delete_confirmation_makes_no_change(tmp_path):
    engine, Session, env_file = _prepare_db(tmp_path)

    from app.flowhub.auth.password import hash_password
    from app.flowhub.auth.repository import create_user, get_user_by_username

    db = Session()
    create_user(db, username="keepadmin", hashed_password=hash_password("password"), role="admin")
    create_user(db, username="canceldelete", hashed_password=hash_password("password"), role="admin")
    db.close()

    result = runner.invoke(
        app,
        [
            "admin",
            "delete",
            "--username",
            "canceldelete",
            "--env-file",
            str(env_file),
        ],
        input="n\n",
    )

    assert result.exit_code != 0
    assert "No changes made" in result.output

    db = Session()
    try:
        assert get_user_by_username(db, "canceldelete") is not None
    finally:
        db.close()
        engine.dispose()
