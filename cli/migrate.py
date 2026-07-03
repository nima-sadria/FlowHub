"""FlowHub - flowhub migrate command group."""

import typer

app = typer.Typer(help="Database migration management.")

_NOT_IMPLEMENTED = (
    "Not implemented in the local Python CLI. "
    "Use the installed Docker-backed repair or update command to run migrations."
)


@app.command("status")
def migrate_status() -> None:
    """Show current and pending migrations."""
    typer.echo(_NOT_IMPLEMENTED)


@app.command("up")
def migrate_up() -> None:
    """Run pending migrations."""
    typer.echo(_NOT_IMPLEMENTED)


@app.command("history")
def migrate_history() -> None:
    """Show migration history."""
    typer.echo(_NOT_IMPLEMENTED)
