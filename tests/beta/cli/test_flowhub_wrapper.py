"""Static checks for the installed flowhub shell wrapper."""

from __future__ import annotations

from pathlib import Path


WRAPPER = Path("scripts/flowhub")
HELPER = Path("scripts/flowhub-helper")


def _src() -> str:
    return WRAPPER.read_text(encoding="utf-8")


def test_wrapper_no_args_opens_management_menu():
    src = _src()
    assert 'cmd="${1:-menu}"' in src
    assert "show_management_menu" in src


def test_management_menu_contains_all_numbered_options():
    src = _src()
    for number in range(0, 29):
        assert f"{number}." in src
    assert "FlowHub Management" in src
    assert "Please enter your selection [0-28]:" in src


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
