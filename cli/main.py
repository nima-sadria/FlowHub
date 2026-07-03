"""FlowHub CLI entry point.

Registers all command groups. Invoked with no arguments: points operators to
the installed Docker-backed `flowhub` shell menu. Invoked with a subcommand:
runs it.

Local invocation:
    python -m cli.main [command] [options]

System-installed (after install.sh):
    flowhub [command] [options]

Available commands:
    install dry-run       -- dry-run smoke path (writes nothing)
    configure show        -- show config (secrets redacted)
    configure verify      -- validate config using B3
    configure get <field> -- show a single field value (CP1.3)
    configure set <f> <v> -- update an editable runtime field (CP1.3)
    status                -- local env/config status
    health                -- local-only health checks
    diagnostics           -- config + prerequisites diagnostic report
    diagnostics run       -- full integration health check (CP1.3)
    integrations list     -- list registered integrations (CP1.3)
    integrations test     -- run live check for a service (CP1.3)
    integrations status   -- show status for all services (CP1.3)
    admin list            -- list local administrator accounts
    admin create          -- create an emergency administrator account
    admin reset-username  -- rename an administrator account
    admin reset-password  -- reset an administrator password
    migrate *             -- unavailable (B6)
    backup *              -- unavailable (B15)
    logs *                -- unavailable (B6)
    update *              -- unavailable (B15)
    adapters *            -- unavailable (B14)
    channels *            -- unavailable (B8)
    sources *             -- unavailable (B8)
    users *               -- unavailable (B7)
    scheduler *           -- unavailable (B11)
    ai *                  -- unavailable (B12)
"""

import typer

from cli.install import app as install_app
from cli.configure import app as configure_app
from cli.create_admin import app as create_admin_app
from cli.status import app as status_app
from cli.health import app as health_app
from cli.diagnostics import app as diagnostics_app
from cli.integrations import app as integrations_app
from cli.admin import app as admin_app
from cli.migrate import app as migrate_app
from cli.backup import app as backup_app
from cli.logs import app as logs_app
from cli.update import app as update_app
from cli.adapters import app as adapters_app
from cli.channels import app as channels_app
from cli.sources import app as sources_app
from cli.users import app as users_app
from cli.scheduler import app as scheduler_app
from cli.ai import app as ai_app

app = typer.Typer(
    name="flowhub",
    help="FlowHub management CLI.",
    no_args_is_help=False,
    invoke_without_command=True,
    add_completion=False,
)


@app.callback()
def _main_callback(ctx: typer.Context) -> None:
    """Point no-argument local runs to the installed management menu."""
    if ctx.invoked_subcommand is None:
        from cli.menu import show_menu
        show_menu()

app.add_typer(install_app, name="install")
app.add_typer(configure_app, name="configure")
app.add_typer(create_admin_app, name="create-admin")
app.add_typer(status_app, name="status")
app.add_typer(health_app, name="health")
app.add_typer(diagnostics_app, name="diagnostics")
app.add_typer(integrations_app, name="integrations")
app.add_typer(admin_app, name="admin")
app.add_typer(migrate_app, name="migrate")
app.add_typer(backup_app, name="backup")
app.add_typer(logs_app, name="logs")
app.add_typer(update_app, name="update")
app.add_typer(adapters_app, name="adapters")
app.add_typer(channels_app, name="channels")
app.add_typer(sources_app, name="sources")
app.add_typer(users_app, name="users")
app.add_typer(scheduler_app, name="scheduler")
app.add_typer(ai_app, name="ai")


if __name__ == "__main__":
    app()
