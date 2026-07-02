"""FlowHub administrator account recovery commands.

These commands are intended for local server operators through the Docker-backed
`flowhub` wrapper. They do not expose an HTTP recovery endpoint and never print
passwords.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import typer

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
        prompt="Admin username",
        help="Username for the new administrator account.",
    ),
    password: str = typer.Option(
        ...,
        "--password",
        "-p",
        prompt="New admin password",
        hide_input=True,
        confirmation_prompt=True,
        help="Password for the new administrator account.",
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
    _validate_password(password)

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


@app.command("reset-password")
def reset_admin_password(
    username: str = typer.Option(
        ...,
        "--username",
        "-u",
        prompt="Admin username",
        help="Existing administrator username.",
    ),
    password: str = typer.Option(
        ...,
        "--password",
        "-p",
        prompt="New admin password",
        hide_input=True,
        confirmation_prompt=True,
        help="New password for the administrator account.",
    ),
    env_file: Optional[str] = typer.Option(
        None,
        "--env-file",
        help="Path to .env.beta (default: /opt/FlowHub/.env.beta).",
    ),
) -> None:
    """Reset an existing administrator password and revoke active sessions."""
    username = username.strip()
    _validate_password(password)

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
