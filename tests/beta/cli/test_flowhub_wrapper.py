"""Static checks for the installed flowhub shell wrapper."""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest
from pathlib import Path


WRAPPER = Path("scripts/flowhub")
HELPER = Path("scripts/flowhub-helper")


def _src() -> str:
    return WRAPPER.read_text(encoding="utf-8")


def _bash() -> str:
    if os.name == "nt":
        git_bash = Path("C:/Program Files/Git/bin/bash.exe")
        if git_bash.exists():
            return str(git_bash)
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash is required for flowhub wrapper smoke tests")
    return bash


def test_wrapper_no_args_opens_management_menu():
    src = _src()
    assert 'cmd="${1:-menu}"' in src
    assert "show_management_menu" in src


def test_management_menu_contains_all_numbered_options():
    src = _src()
    for number in range(0, 28):
        assert f"{number}." in src
    assert "FlowHub Management" in src
    assert "Please enter your selection [0-27]:" in src
    assert "Please enter your selection [0-1]:" in src


def test_menu_footer_contains_required_status_fields():
    src = _src()
    for label in [
        "Panel state:",
        "Database:",
        "Safety mode:",
        "Install path:",
        "Public URL:",
        "Docker:",
        "Version / commit:",
    ]:
        assert label in src


def test_wrapper_documents_admin_recovery_commands():
    src = _src()
    assert "flowhub admin reset-username" in src
    assert "flowhub admin reset-password" in src


def test_wrapper_does_not_source_protected_env_file():
    src = _src()
    assert '. "$ENV_FILE"' not in src
    assert "source \"$ENV_FILE\"" not in src
    assert "sudo -n \"$HELPER\"" in src


def test_helper_requires_root_and_has_command_allowlist():
    src = HELPER.read_text(encoding="utf-8")
    assert "require_root" in src
    assert "Unsupported helper command" in src
    for command in ["status", "health", "restart", "backup", "app-cli", "state"]:
        assert f"{command})" in src
    assert "eval " not in src
    assert "bash -c" not in src


def test_helper_app_cli_allowlist_blocks_arbitrary_commands():
    src = HELPER.read_text(encoding="utf-8")
    assert "admin|diagnostics|configure|migrate|integrations" in src
    assert "Unsupported app CLI command" in src
    assert "update)" not in src


def test_helper_keeps_password_reset_interactive():
    src = HELPER.read_text(encoding="utf-8")
    assert "reset-password" in src
    assert "exec app python -m cli.main" in src
    assert "--password" not in src


def test_repair_has_narrow_existing_install_fallback():
    src = _src()
    assert "repair_with_fallback" in src
    assert src.count('sudo bash "${INSTALL_DIR}/installer/install.sh" --repair') == 1


def _run_wrapper(input_text: str, install_dir: Path) -> subprocess.CompletedProcess[str]:
    bash = _bash()
    env = os.environ.copy()
    env["FLOWHUB_INSTALL_DIR"] = str(install_dir)
    env["FLOWHUB_HELPER"] = str(install_dir / "missing-helper")
    return subprocess.run(
        [bash, str(WRAPPER)],
        input=input_text,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def test_menu_without_installation_shows_install_setup_only(tmp_path):
    install_dir = tmp_path / "FlowHub"
    result = _run_wrapper("0\n", install_dir)

    assert result.returncode == 0
    assert "Install / Setup" in result.stdout
    assert "1. Install FlowHub" in result.stdout
    assert "Maintenance" not in result.stdout
    assert "1. Upgrade" not in result.stdout


def test_menu_with_installation_shows_maintenance_not_install(tmp_path):
    install_dir = tmp_path / "FlowHub"
    install_dir.mkdir()
    result = _run_wrapper("0\n", install_dir)

    assert result.returncode == 0
    assert "Maintenance" in result.stdout
    assert "1. Upgrade" in result.stdout
    assert "2. Repair" in result.stdout
    assert "3. Reinstall" in result.stdout
    assert "4. Uninstall" in result.stdout
    assert "Install / Setup" not in result.stdout
    assert "1. Install" not in result.stdout


def test_install_command_on_existing_installation_does_not_run_installer(tmp_path):
    bash = _bash()
    install_dir = tmp_path / "FlowHub"
    install_dir.mkdir()
    env = os.environ.copy()
    env["FLOWHUB_INSTALL_DIR"] = str(install_dir)
    env["FLOWHUB_HELPER"] = str(install_dir / "missing-helper")

    result = subprocess.run(
        [bash, str(WRAPPER), "install"],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode != 0
    assert (
        f"FlowHub is already installed at {install_dir}. "
        "Use flowhub upgrade, flowhub repair, or flowhub reinstall."
    ) in result.stderr
    assert "helper is not installed" not in result.stderr
