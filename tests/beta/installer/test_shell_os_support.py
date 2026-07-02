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
