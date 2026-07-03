"""FlowHub - create-admin CLI subcommand.

Creates the initial admin user in the FLOWHUB database.

Usage (after install.sh):
  flowhub create-admin
  flowhub create-admin --username admin --env-file /opt/FlowHub/.env

Run once; re-running with an existing username fails safely with an error
message. Passwords are accepted only through hidden interactive input or the
internal stdin channel used by the installer.
"""

from __future__ import annotations

import sys
from typing import Optional

import typer

app = typer.Typer(
    name="create-admin",
    help="Create the initial FlowHub admin user (required post-install step).",
    add_completion=False,
)


@app.callback(invoke_without_command=True)
def create_admin(
    username: str = typer.Option(
        "admin",
        "--username",
        "-u",
        prompt="Admin username",
        help="Username for the new admin account.",
    ),
    env_file: Optional[str] = typer.Option(
        None,
        "--env-file",
        help="Path to .env (default: /opt/FlowHub/.env).",
    ),
    secret_stdin: bool = typer.Option(
        False,
        "--secret-stdin",
        help="Internal installer use only: read the new admin secret from stdin.",
    ),
) -> None:
    """Create the initial FlowHub admin user.

    Run once after install.sh to create the admin account used to log in.
    """
    import os
    from pathlib import Path

    if secret_stdin:
        password = sys.stdin.readline().rstrip("\n")
        if not password:
            typer.echo("ERROR: admin secret was not provided on stdin.", err=True)
            raise typer.Exit(1)
    else:
        from cli.admin import _prompt_secure_password
        password = _prompt_secure_password("Admin password")

    from cli.admin import _validate_password
    try:
        _validate_password(password)
    except typer.BadParameter as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1)

    # Load .env so FLOWHUB_DATABASE_URL and FLOWHUB_JWT_SECRET are set
    env_path = Path(env_file or "/opt/FlowHub/.env")
    if env_path.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path)
        except ImportError:
            # Fall back to manual parsing if python-dotenv not available
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())

    db_url = os.environ.get("FLOWHUB_DATABASE_URL", "")
    if not db_url:
        typer.echo(
            "ERROR: FLOWHUB_DATABASE_URL is not set.\n"
            "  Use --env-file /path/to/.env or export FLOWHUB_DATABASE_URL.",
            err=True,
        )
        raise typer.Exit(1)

    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from app.flowhub.auth.password import hash_password
        from app.flowhub.auth.repository import create_user, get_user_by_username

        kwargs: dict = {}
        if db_url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}

        engine = create_engine(db_url, **kwargs)
        Session = sessionmaker(bind=engine)
        db = Session()

        try:
            existing = get_user_by_username(db, username)
            if existing:
                typer.echo(
                    f"ERROR: User '{username}' already exists. "
                    "Use a different username or delete the existing account first.",
                    err=True,
                )
                raise typer.Exit(1)

            hashed = hash_password(password)
            create_user(db, username=username, hashed_password=hashed, role="admin")

            typer.echo(f"  Admin user '{username}' created successfully.")
            typer.echo("  You can now log in at /login")
        finally:
            db.close()
            engine.dispose()

    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1)
