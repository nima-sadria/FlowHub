"""Static and smoke checks for the installed flowhub shell wrapper."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


WRAPPER = Path("scripts/flowhub")
HELPER = Path("scripts/flowhub-helper")


def _src() -> str:
    return WRAPPER.read_text(encoding="utf-8")


def _helper_src() -> str:
    return HELPER.read_text(encoding="utf-8")


def _bash() -> str:
    if os.name == "nt":
        git_bash = Path("C:/Program Files/Git/bin/bash.exe")
        if git_bash.exists():
            return str(git_bash)
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash is required for flowhub wrapper smoke tests")
    return bash


def _run_wrapper(input_text: str, install_dir: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["FLOWHUB_INSTALL_DIR"] = str(install_dir)
    env["FLOWHUB_HELPER"] = str(install_dir / "missing-helper")
    return subprocess.run(
        [_bash(), str(WRAPPER)],
        input=input_text,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def test_wrapper_no_args_opens_canonical_management_menu():
    src = _src()
    assert 'cmd="${1:-menu}"' in src
    assert "show_management_menu" in src
    assert "FlowHub Management" in src
    assert "Please enter your selection [0-13]:" in src


def test_management_menu_contains_new_operator_labels_only():
    src = _src()
    for label in [
        "1. Install",
        "2. Update",
        "3. Uninstall",
        "4. Domain + SSL Setup",
        "5. IP + Port Setup",
        "6. Admin Setup",
        "7. Show Base URL",
        "8. Show Admin Users",
        "9. Add Admin User",
        "10. Delete Admin User",
        "11. Status Overview",
        "12. Logs",
        "13. Errors & Warnings",
        "0. Exit",
    ]:
        assert label in src

    menu_block = "FlowHub Management" + src.split("FlowHub Management", 1)[1].split("EOF", 1)[0]
    for removed in [
        "Repair",
        "Reinstall",
        "Reset Administrator Username",
        "Reset Administrator Password",
        "View Current Settings",
        "Change Port",
        "Rotate Secrets",
        "Check Secret Exposure",
        "View Safety Status",
        "Docker Compose Status",
        "Database Status",
        "Migration Status",
        "Shell into App Container",
        "Restore",
        "Start",
        "Stop",
        "Restart",
    ]:
        assert removed not in menu_block


def test_menu_number_to_handler_mapping_is_complete():
    src = _src()
    expected_handlers = {
        "1)": "Use Update instead",
        "2)": '"$0" update',
        "3)": '"$0" uninstall',
        "4)": "helper config set-domain-ssl",
        "5)": "helper config set-ip-port",
        "6)": '"$0" admin create',
        "7)": "helper base-url",
        "8)": '"$0" admin list',
        "9)": '"$0" admin create',
        "10)": '"$0" admin delete',
        "11)": "helper overview",
        "12)": "helper logs recent",
        "13)": "helper logs errors",
    }
    for choice, handler in expected_handlers.items():
        assert choice in src
        assert handler in src


def test_menu_exits_and_handles_invalid_input(tmp_path):
    install_dir = tmp_path / "FlowHub"
    install_dir.mkdir()

    result = _run_wrapper("bad\n\n0\n", install_dir)

    assert result.returncode == 0
    assert "Invalid selection: bad" in result.stdout
    assert "Exiting." in result.stdout


def test_install_option_on_existing_host_is_disabled(tmp_path):
    install_dir = tmp_path / "FlowHub"
    install_dir.mkdir()

    result = _run_wrapper("1\n\n0\n", install_dir)

    assert result.returncode == 0
    assert "FlowHub is already installed. Use Update instead." in result.stdout
    assert "ERROR: FlowHub helper is not installed" not in result.stdout
    assert "ERROR: FlowHub helper is not installed" not in result.stderr


def test_install_command_on_existing_installation_does_not_run_installer(tmp_path):
    install_dir = tmp_path / "FlowHub"
    install_dir.mkdir()
    env = os.environ.copy()
    env["FLOWHUB_INSTALL_DIR"] = str(install_dir)
    env["FLOWHUB_HELPER"] = str(install_dir / "missing-helper")

    result = subprocess.run(
        [_bash(), str(WRAPPER), "install"],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )

    assert result.returncode != 0
    assert "FlowHub is already installed. Use Update instead." in result.stderr
    assert "helper is not installed" not in result.stderr


def test_domain_and_ip_setup_flows_use_strict_helper_commands():
    src = _src()
    assert "Domain host:" in src
    assert "Public panel port:" in src
    assert 'helper config set-domain-ssl "$domain" "$port"' in src
    assert "Listen IP:" in src
    assert 'helper config set-ip-port "$ip" "$port"' in src
    assert "configure set app.domain" not in src


def test_wrapper_documents_direct_commands_without_password_argument():
    src = _src()
    for command in [
        "flowhub base-url",
        "flowhub overview",
        "flowhub errors",
        "flowhub admin create",
        "flowhub admin delete",
        "flowhub admin reset-username",
        "flowhub admin reset-password",
    ]:
        assert command in src
    assert "--password" not in src
    assert '"-p"' not in src
    assert "'-p'" not in src


def test_wrapper_does_not_source_protected_env_file():
    src = _src()
    assert '. "$ENV_FILE"' not in src
    assert "source \"$ENV_FILE\"" not in src
    assert "sudo -n \"$HELPER\"" in src


def test_helper_requires_root_and_has_strict_command_allowlist():
    src = _helper_src()
    assert "require_root" in src
    assert "Unsupported helper command" in src
    for command in [
        "status",
        "health",
        "restart",
        "backup",
        "config",
        "tls",
        "app-cli",
        "state",
        "base-url",
        "overview",
        "logs",
    ]:
        assert f"{command})" in src
    assert "eval " not in src
    assert "bash -c" not in src


def test_helper_app_cli_allowlist_blocks_arbitrary_commands():
    src = _helper_src()
    assert "admin|diagnostics|configure|migrate|integrations" in src
    assert "Unsupported app CLI command" in src
    assert "update)" not in src
    assert "shell)" not in src
    assert "exec app bash" not in src


def test_helper_supports_menu_actions_without_arbitrary_shell():
    src = _helper_src()
    for symbol in [
        "set_domain_ssl",
        "set_ip_port",
        "status_overview",
        "recent_logs",
        "recent_errors",
        "validate_domain",
        "validate_ip",
        "validate_port",
    ]:
        assert symbol in src
    assert "eval " not in src
    assert "bash -c" not in src


def test_helper_uses_port_in_domain_ssl_url_contract():
    src = _helper_src()
    assert 'echo "Base URL: https://${domain}:${port}/"' in src
    assert 'echo "Public URL: https://${domain}:${port}/"' in src
    assert 'echo "Public URL: https://${domain}"' not in src


def test_status_overview_output_is_concise():
    src = _helper_src()
    assert 'echo "Database: $(database_state)"' in src
    assert 'echo "Panel: $(panel_state)"' in src
    assert 'echo "API: $(api_state)"' in src


def test_helper_start_and_restart_wait_for_readiness():
    src = _helper_src()
    assert "run_compose up -d" in src
    assert "run_compose restart" in src
    assert src.count("wait_for_app_health 60") >= 2


def test_migration_head_verification_has_no_hardcoded_revision():
    src = _helper_src()
    # A hard-coded revision (e.g. "FLOWHUB_031") makes the check permanently
    # stale the moment a new migration ships. The verification must compare
    # two values discovered live from the running app container instead.
    assert "FLOWHUB_031" not in src
    assert "FLOWHUB_036" not in src
    assert "current_migration_applied" in src
    assert "current_migration_head" in src
    assert 'expected="$(current_migration_head)"' in src
    assert 'applied="$(current_migration_applied)"' in src
    assert '[[ "$applied" == "$expected" ]]' in src


def test_current_migration_applied_reads_db_state_not_code_head():
    src = _helper_src()
    assert "alembic -c alembic_flowhub.ini current" in src
    assert "alembic -c alembic_flowhub.ini heads" in src


def test_safe_upgrade_refuses_on_dirty_tree_wrong_branch_or_divergence():
    src = _helper_src()
    assert "safe_upgrade" in src
    assert 'refusing update: tracked source changes are present.' in src
    assert 'refusing update: expected branch main' in src
    assert 'refusing update: local main diverges from origin/main' in src
    assert "--ff-only" in src


def test_deploy_current_migrates_before_swapping_runtime_containers():
    src = _helper_src()
    assert "deploy_current" in src
    build_idx = src.index("run_compose build app")
    migrate_idx = src.index("run_compose run --rm flowhub-migrate")
    swap_idx = src.index("--force-recreate app order-sync-runner exchange-rate-runner")
    assert build_idx < migrate_idx < swap_idx, "must build, then migrate, before replacing running containers"
    assert "flowhub-owner-review-current" in src


def test_run_installer_upgrade_uses_safe_upgrade_not_install_sh_reset_hard():
    src = _helper_src()
    assert "upgrade) safe_upgrade ;;" in src
    assert 'upgrade) bash "${INSTALL_DIR}/installer/install.sh" --upgrade ;;' not in src
    assert "deploy-current) deploy_current ;;" in src


def test_git_and_docker_operations_run_as_the_checkout_owner_not_root():
    src = _helper_src()
    assert "run_as_operator" in src
    assert "operator_user" in src
    # run_compose must route through the operator, not invoke docker/docker
    # compose directly as root.
    assert 'run_as_operator ${dc} --project-directory' in src
