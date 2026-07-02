"""Static checks for shell installer OS support policy."""

from __future__ import annotations

from pathlib import Path


INSTALL = Path("installer/install.sh")
CHECKS = Path("installer/lib/checks.sh")


def test_bootstrap_supports_ubuntu_2404_and_2604():
    src = INSTALL.read_text(encoding="utf-8")
    assert '"24.04"' in src
    assert '"26.04"' in src
    assert "Ubuntu Core is not supported" in src


def test_preflight_supports_ubuntu_2404_and_2604():
    src = CHECKS.read_text(encoding="utf-8")
    assert '"24.04"' in src
    assert '"26.04"' in src
    assert "Ubuntu Core is not supported" in src


def test_preflight_requires_x86_64_and_apt_download_tooling():
    src = CHECKS.read_text(encoding="utf-8")
    assert "x86_64" in src
    assert "apt-get" in src
    assert "curl" in src
    assert "wget" in src


def test_installer_installs_privileged_helper_and_sudoers_allowlist():
    src = INSTALL.read_text(encoding="utf-8")
    assert "/usr/local/lib/flowhub/flowhub-helper" in src
    assert "/etc/sudoers.d/flowhub" in src
    assert "Cmnd_Alias FLOWHUB_HELPER = ${helper_dst}" in src
    assert "Cmnd_Alias FLOWHUB_HELPER = ${helper_dst} *" not in src
    assert "NOPASSWD: FLOWHUB_HELPER" in src
    assert "visudo -cf" in src
    assert "docker" not in src[src.index('sudoers_tmp="$(mktemp)"') : src.index('install -o root -g root -m 0440 "$sudoers_tmp"')]


def test_installer_configures_operator_group_membership():
    src = INSTALL.read_text(encoding="utf-8")
    assert "groupadd --system flowhub" in src
    assert 'usermod -aG flowhub "$operator_user"' in src
    assert "detect_flowhub_operator_user" in src
    assert "FLOWHUB_OPERATOR_USER" in src
    assert 'id -nG "$candidate"' in src


def test_sudoers_scope_is_helper_only():
    src = INSTALL.read_text(encoding="utf-8")
    sudoers = src[src.index('sudoers_tmp="$(mktemp)"') : src.index('install -o root -g root -m 0440 "$sudoers_tmp"')]
    assert "%flowhub ALL=(root) NOPASSWD: FLOWHUB_HELPER" in sudoers
    assert "${operator_user} ALL=(root) NOPASSWD: FLOWHUB_HELPER" in sudoers
    assert "ALL=(ALL)" not in sudoers
    assert "NOPASSWD: ALL" not in sudoers


def test_installer_keeps_env_beta_protected():
    src = INSTALL.read_text(encoding="utf-8")
    assert 'chown root:root "${REPO_DIR}/.env.beta"' in src
    assert 'chmod 600 "${REPO_DIR}/.env.beta"' in src


def test_upgrade_and_repair_refresh_installed_cli_wrapper():
    src = INSTALL.read_text(encoding="utf-8")
    upgrade = src[src.index("step_upgrade()") : src.index("# ---- Repair path")]
    repair = src[src.index("step_repair()") : src.index("# ---- Reconfigure path")]
    reconfigure = src[src.index("step_reconfigure()") : src.index("# Load .env.beta")]

    assert "step_update_repository" in upgrade
    assert "step_install_cli" in upgrade
    assert "step_install_cli" in repair
    assert "step_install_cli" in reconfigure
