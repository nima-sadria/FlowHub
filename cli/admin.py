"""FlowHub administrator account recovery commands.

These commands are intended for local server operators through the Docker-backed
`flowhub` wrapper. They do not expose an HTTP recovery endpoint and never print
passwords.
"""

from __future__ import annotations

import os
import getpass
import sys
import warnings
import re
from pathlib import Path
from typing import Optional

import typer

try:
    import termios
except ImportError:  # pragma: no cover - Windows fallback
    termios = None  # type: ignore[assignment]

app = typer.Typer(
    name="admin",
    help="Recover local FlowHub administrator accounts.",
    add_completion=False,
)


def _load_env(env_file: Optional[str]) -> None:
    env_path = Path(env_file or "/opt/FlowHub/.env.beta")
    if not env_path.exists():
        return

    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=True)
    except ImportError:
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ[key.strip()] = value.strip()


def _session(env_file: Optional[str]):
    _load_env(env_file)
    db_url = os.environ.get("BETA_DATABASE_URL", "")
    if not db_url:
        typer.echo(
            "ERROR: BETA_DATABASE_URL is not set. Use --env-file /path/to/.env.beta.",
            err=True,
        )
        raise typer.Exit(1)

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    kwargs: dict = {}
    if db_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}

    engine = create_engine(db_url, **kwargs)
    Session = sessionmaker(bind=engine)
    return engine, Session()


def _validate_password(password: str) -> None:
    if len(password) < 8:
        typer.echo("ERROR: Password must be at least 8 characters.", err=True)
        raise typer.Exit(1)


def _validate_email(email: str) -> None:
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        typer.echo("ERROR: Enter a valid email address.", err=True)
        raise typer.Exit(1)


SECURE_INPUT_ERROR = (
    "Secure password input is not available in this terminal. "
    "Run this command from an interactive TTY."
)


def _secure_password_input_available() -> bool:
    if os.name == "nt":
        return bool(getattr(sys.stdin, "isatty", lambda: False)())
    if termios is None:
        return False
    try:
        with open("/dev/tty", "r", encoding="utf-8") as tty:
            termios.tcgetattr(tty.fileno())
        return True
    except OSError:
        return False


def _prompt_secure_password(prompt: str = "New admin password") -> str:
    if not _secure_password_input_available():
        typer.echo(SECURE_INPUT_ERROR, err=True)
        raise typer.Exit(1)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", getpass.GetPassWarning)
        password = getpass.getpass(f"{prompt}: ")
        confirmation = getpass.getpass("Repeat for confirmation: ")

    if any(issubclass(item.category, getpass.GetPassWarning) for item in caught):
        typer.echo(SECURE_INPUT_ERROR, err=True)
        raise typer.Exit(1)
    if password != confirmation:
        typer.echo("ERROR: Password confirmation does not match.", err=True)
        raise typer.Exit(1)
    return password


@app.command("list")
def list_admins(
    env_file: Optional[str] = typer.Option(
        None,
        "--env-file",
        help="Path to .env.beta (default: /opt/FlowHub/.env.beta).",
    ),
) -> None:
    """List administrator accounts without exposing secrets."""
    engine, db = _session(env_file)
    try:
        from app.beta.auth.models import BetaUser

        admins = (
            db.query(BetaUser)
            .filter(BetaUser.role == "admin")
            .order_by(BetaUser.username.asc())
            .all()
        )
        if not admins:
            typer.echo("No administrator accounts found.")
            return
        for user in admins:
            status = "active" if user.is_active else "inactive"
            typer.echo(f"{user.username}\t{status}")
    finally:
        db.close()
        engine.dispose()


@app.command("create")
def create_admin(
    username: str = typer.Option(
        ...,
        "--username",
        "-u",
        prompt="Admin name",
        help="Username for the new administrator account.",
    ),
    email: str = typer.Option(
        ...,
        "--email",
        prompt="Admin email",
        help="Email address for operator confirmation. Current account storage uses username identity.",
    ),
    env_file: Optional[str] = typer.Option(
        None,
        "--env-file",
        help="Path to .env.beta (default: /opt/FlowHub/.env.beta).",
    ),
) -> None:
    """Create an emergency administrator account."""
    username = username.strip()
    if len(username) < 3:
        typer.echo("ERROR: Username must be at least 3 characters.", err=True)
        raise typer.Exit(1)
    email = email.strip()
    _validate_email(email)
    password = _prompt_secure_password("New admin password")
    _validate_password(password)
    if not typer.confirm(
        f"Create administrator '{username}'?",
        default=False,
    ):
        typer.echo("Admin creation cancelled. No changes made.")
        raise typer.Exit(1)

    engine, db = _session(env_file)
    try:
        from app.beta.auth.password import hash_password
        from app.beta.auth.repository import create_audit_event, create_user, get_user_by_username

        if get_user_by_username(db, username):
            typer.echo(f"ERROR: User '{username}' already exists.", err=True)
            raise typer.Exit(1)

        create_user(db, username=username, hashed_password=hash_password(password), role="admin")
        create_audit_event(db, username=username, event="admin_created_cli", ip_address="cli")
        typer.echo(f"Administrator '{username}' created.")
    finally:
        db.close()
        engine.dispose()


@app.command("delete")
def delete_admin(
    username: str = typer.Option(
        ...,
        "--username",
        "-u",
        prompt="Admin username to delete",
        help="Existing administrator username.",
    ),
    env_file: Optional[str] = typer.Option(
        None,
        "--env-file",
        help="Path to .env.beta (default: /opt/FlowHub/.env.beta).",
    ),
) -> None:
    """Delete an administrator account with last-admin protection."""
    username = username.strip()
    engine, db = _session(env_file)
    try:
        from app.beta.auth.models import BetaUser
        from app.beta.auth.repository import create_audit_event, get_user_by_username

        admins = (
            db.query(BetaUser)
            .filter(BetaUser.role == "admin")
            .order_by(BetaUser.username.asc())
            .all()
        )
        if not admins:
            typer.echo("ERROR: No administrator accounts found.", err=True)
            raise typer.Exit(1)

        typer.echo("Administrator accounts:")
        for user in admins:
            status = "active" if user.is_active else "inactive"
            typer.echo(f"  {user.username}\t{status}")

        user = get_user_by_username(db, username)
        if user is None or user.role != "admin":
            typer.echo(f"ERROR: Administrator '{username}' was not found.", err=True)
            raise typer.Exit(1)
        if len(admins) <= 1:
            typer.echo(
                "ERROR: Refusing to delete the last administrator account. "
                "Create another admin first.",
                err=True,
            )
            raise typer.Exit(1)
        if not typer.confirm(f"Delete administrator '{username}'?", default=False):
            typer.echo("Admin deletion cancelled. No changes made.")
            raise typer.Exit(1)

        create_audit_event(db, username=username, event="admin_deleted_cli", ip_address="cli")
        db.delete(user)
        db.commit()
        typer.echo(f"Administrator '{username}' deleted.")
    finally:
        db.close()
        engine.dispose()


@app.command("reset-password")
def reset_admin_password(
    username: str = typer.Option(
        ...,
        "--username",
        "-u",
        prompt="Admin username",
        help="Existing administrator username.",
    ),
    env_file: Optional[str] = typer.Option(
        None,
        "--env-file",
        help="Path to .env.beta (default: /opt/FlowHub/.env.beta).",
    ),
) -> None:
    """Reset an existing administrator password and revoke active sessions."""
    username = username.strip()
    password = _prompt_secure_password("New admin password")
    _validate_password(password)
    if not typer.confirm(
        f"Reset password for administrator '{username}' and revoke active sessions?",
        default=False,
    ):
        typer.echo("Password reset cancelled. No changes made.")
        raise typer.Exit(1)

    engine, db = _session(env_file)
    try:
        from app.beta.auth.password import hash_password
        from app.beta.auth.repository import (
            create_audit_event,
            get_user_by_username,
            revoke_all_user_tokens,
        )

        user = get_user_by_username(db, username)
        if user is None:
            typer.echo(f"ERROR: User '{username}' was not found.", err=True)
            raise typer.Exit(1)
        if user.role != "admin":
            typer.echo(
                f"ERROR: User '{username}' is not an administrator. "
                "Refusing to promote accounts through password reset.",
                err=True,
            )
            raise typer.Exit(1)

        user.hashed_password = hash_password(password)
        user.is_active = True
        db.commit()
        revoke_all_user_tokens(db, user.id)
        create_audit_event(db, username=username, event="admin_password_reset_cli", ip_address="cli")
        typer.echo(f"Password reset for administrator '{username}'. Active sessions revoked.")
    finally:
        db.close()
        engine.dispose()


@app.command("reset-username")
def reset_admin_username(
    username: str = typer.Option(
        ...,
        "--username",
        "-u",
        prompt="Current admin username",
        help="Existing administrator username.",
    ),
    new_username: str = typer.Option(
        ...,
        "--new-username",
        "-n",
        prompt="New admin username",
        help="New administrator username.",
    ),
    env_file: Optional[str] = typer.Option(
        None,
        "--env-file",
        help="Path to .env.beta (default: /opt/FlowHub/.env.beta).",
    ),
) -> None:
    """Rename an existing administrator account and revoke active sessions."""
    username = username.strip()
    new_username = new_username.strip()
    if len(new_username) < 3:
        typer.echo("ERROR: New username must be at least 3 characters.", err=True)
        raise typer.Exit(1)
    if username == new_username:
        typer.echo("No change requested.")
        return

    engine, db = _session(env_file)
    try:
        from app.beta.auth.repository import (
            create_audit_event,
            get_user_by_username,
            revoke_all_user_tokens,
        )

        user = get_user_by_username(db, username)
        if user is None:
            typer.echo(f"ERROR: User '{username}' was not found.", err=True)
            raise typer.Exit(1)
        if user.role != "admin":
            typer.echo(
                f"ERROR: User '{username}' is not an administrator. "
                "Refusing to rename non-admin accounts through recovery.",
                err=True,
            )
            raise typer.Exit(1)
        if get_user_by_username(db, new_username):
            typer.echo(f"ERROR: User '{new_username}' already exists.", err=True)
            raise typer.Exit(1)

        old_username = user.username
        user.username = new_username
        user.is_active = True
        db.commit()
        revoke_all_user_tokens(db, user.id)
        create_audit_event(db, username=new_username, event="admin_username_reset_cli", ip_address="cli")
        typer.echo(
            f"Administrator username changed from '{old_username}' to '{new_username}'. "
            "Active sessions revoked."
        )
    finally:
        db.close()
        engine.dispose()
