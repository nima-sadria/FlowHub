"""FlowHub - flowhub logs command group."""

import typer

app = typer.Typer(help="Log streaming and export.")

_NOT_IMPLEMENTED = "Not implemented in the local Python CLI. Use the installed Docker-backed command: flowhub logs"


@app.command("tail")
def logs_tail() -> None:
    """Stream logs live."""
    typer.echo(_NOT_IMPLEMENTED)


@app.command("show")
def logs_show() -> None:
    """Show recent log lines."""
    typer.echo(_NOT_IMPLEMENTED)


@app.command("export")
def logs_export() -> None:
    """Export logs to a file."""
    typer.echo(_NOT_IMPLEMENTED)
