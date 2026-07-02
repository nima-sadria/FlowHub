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
    assert "Cmnd_Alias FLOWHUB_HELPER" in src
    assert "NOPASSWD: FLOWHUB_HELPER" in src
    assert "visudo -cf" in src


def test_installer_keeps_env_beta_protected():
    src = INSTALL.read_text(encoding="utf-8")
    assert 'chown root:root "${REPO_DIR}/.env.beta"' in src
    assert 'chmod 600 "${REPO_DIR}/.env.beta"' in src
