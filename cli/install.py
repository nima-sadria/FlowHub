"""FlowHub - flowhub install command.

Wraps B4 Installer Foundation. In B5: dry-run mode only.
No Docker execution. No network calls. No production deployment.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(help="Installation management.")

_DEFAULT_INSTALL_DIR = Path("/opt/FlowHub")


def _env_file_to_installer_config(env_file: Path | None):  # type: ignore[return]
    """Load an InstallerConfig from a .env file, auto-generating missing secrets."""
    from installer.installer_core import InstallerConfig, generate_secrets, apply_secrets

    config = InstallerConfig()

    if env_file is not None and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip()
            # Map FLOWHUB_* env vars to InstallerConfig fields
            _MAP = {
                "FLOWHUB_DOMAIN": "domain",
                "FLOWHUB_ADMIN_EMAIL": "admin_email",
                "FLOWHUB_NEXTCLOUD_URL": "nextcloud_url",
                "FLOWHUB_NEXTCLOUD_FILE_PATH": "nextcloud_file_path",
                "FLOWHUB_NEXTCLOUD_USERNAME": "nextcloud_username",
                "FLOWHUB_NEXTCLOUD_PASSWORD": "nextcloud_password",
                "FLOWHUB_WOOCOMMERCE_URL": "woocommerce_url",
                "FLOWHUB_WOOCOMMERCE_KEY": "woocommerce_key",
                "FLOWHUB_WOOCOMMERCE_SECRET": "woocommerce_secret",
                "FLOWHUB_ENV": "env",
                "FLOWHUB_PORT": "port",
                "FLOWHUB_SSL_MODE": "ssl_mode",
                "FLOWHUB_POSTGRES_DB": "postgres_db",
                "FLOWHUB_POSTGRES_USER": "postgres_user",
                "FLOWHUB_POSTGRES_PASSWORD": "postgres_password",
                "FLOWHUB_JWT_SECRET": "jwt_secret",
                "FLOWHUB_REST_API_SECRET": "rest_api_secret",
                "FLOWHUB_TIMEZONE": "timezone",
                "FLOWHUB_CURRENCY": "currency",
                "FLOWHUB_STORAGE_PATH": "storage_path",
                "FLOWHUB_BACKUP_PATH": "backup_path",
                "FLOWHUB_LOG_LEVEL": "log_level",
            }
            field = _MAP.get(k)
            if field is not None:
                if field == "port":
                    try:
                        object.__setattr__(config, field, int(v))
                    except ValueError:
                        pass
                else:
                    object.__setattr__(config, field, v)

    # Auto-generate any missing secrets
    if config.needs_secret_generation():
        sec = generate_secrets()
        config = apply_secrets(config, sec)

    return config


@app.command("dry-run")
def install_dry_run(
    env_file: Annotated[
        Path | None,
        typer.Option("--env-file", help="Path to .env file to seed installer values"),
    ] = None,
    install_dir: Annotated[
        Path,
        typer.Option("--install-dir", help="Target installation directory"),
    ] = _DEFAULT_INSTALL_DIR,
) -> None:
    """Simulate a full installation without writing any files.

    Loads values from --env-file if provided; auto-generates secrets.
    Prints: planned files, planned directories, masked secrets summary,
    validation result. Writes nothing to disk.
    """
    from cli.shared.output import console, print_banner, print_section, print_success
    from cli.shared.config_reader import load_config
    from installer.installer_core import dry_run_install

    manager, profile = load_config(env_file)
    print_banner(profile)

    config = _env_file_to_installer_config(env_file)
    result = dry_run_install(config, install_dir)

    print_section("Prerequisite Checks")
    for pre in result.prerequisites:
        icon = "[green]OK[/green]" if pre.passed else "[red]X[/red]"
        console.print(f"  {icon}  {pre.name}: {pre.message}")
        if not pre.passed and pre.fix:
            console.print(f"     [dim]Fix: {pre.fix}[/dim]")

    print_section("Files That Would Be Written")
    for f in result.files_would_be_written:
        console.print(f"  [dim]{f}[/dim]")

    print_section("Directories That Would Be Created")
    for d in result.storage_dirs:
        console.print(f"  [dim]{d}[/dim]")

    print_section("Secrets")
    if result.secrets_would_be_generated:
        console.print("  [dim]Secrets would be auto-generated (masked below):[/dim]")
    # Show masked summary - never plain text
    from installer.installer_core import InstallerSecrets
    masked = InstallerSecrets(
        jwt_secret=config.jwt_secret,
        rest_api_secret=config.rest_api_secret,
        postgres_password=config.postgres_password,
    ).masked_summary()
    for k, v in masked.items():
        console.print(f"  {k:<24} {v}")

    print_section("Validation Result")
    from installer.installer_core import validate_generated_config
    validation = validate_generated_config(env_content=result.env_content)
    if validation.is_valid:
        print_success("Generated configuration is valid.")
    else:
        console.print(f"  [bold red]X {len(validation.errors)} validation error(s):[/bold red]")
        from app.flowhub.config import SECRET_FIELDS
        for err in validation.errors:
            display = "[REDACTED]" if err.field in SECRET_FIELDS else repr(err.value)
            console.print(f"    [red]X[/red] {err.field}={display}: {err.message}")

    console.print()
    console.print("[bold cyan]  Dry-run complete. Nothing was written to disk.[/bold cyan]\n")
