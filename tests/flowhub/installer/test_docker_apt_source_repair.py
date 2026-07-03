from __future__ import annotations

from pathlib import Path


INSTALL = Path("installer/install.sh")


def _src() -> str:
    return INSTALL.read_text(encoding="utf-8")


def test_bootstrap_system_package_update_repairs_stale_ubuntu26_docker_source():
    src = _src()
    body = src[src.index("_bs_install_system_deps()") : src.index("# -- Docker installation helpers")]
    assert "_apt_get_update_with_docker_source_repair" in body
    assert "apt-get update -qq" not in body


def test_non_bootstrap_docker_preflight_uses_same_apt_source_repair():
    src = _src()
    body = src[src.index("_ensure_docker_installed()") : src.index("# ---- Defaults ----")]
    assert "_apt_get_update_with_docker_source_repair" in body
    assert "apt-get update -qq" not in body


def test_stale_docker_source_repair_requires_existing_working_docker():
    src = _src()
    body = src[src.index("_apt_get_update_with_docker_source_repair()") : src.index("# Method 1: official Docker apt repository.")]
    assert "if _docker_runtime_available &&" in body
    assert "_has_active_ubuntu26_docker_source" in body
    assert "download\\.docker\\.com/linux/ubuntu|resolute|403|no longer signed" in body
    assert "_disable_ubuntu26_docker_sources" in body
    assert "return 1" in body


def test_docker_runtime_contract_checks_version_compose_and_daemon():
    src = _src()
    body = src[src.index("_docker_runtime_available()") : src.index("_has_active_ubuntu26_docker_source()")]
    assert "docker --version" in body
    assert "docker compose version" in body
    assert "docker info" in body


def test_stale_ubuntu26_docker_source_is_commented_not_deleted():
    src = _src()
    body = src[src.index("_disable_ubuntu26_docker_sources()") : src.index("_apt_get_update_with_docker_source_repair()")]
    assert "download\\.docker\\.com\\/linux\\/ubuntu" in body
    assert "resolute" in body
    assert "# FlowHub disabled unsupported Docker Ubuntu 26 source:" in body
    assert "rm -rf" not in body
    assert "docker system prune" not in body


def test_fresh_install_still_fails_if_docker_cannot_be_installed():
    src = _src()
    body = src[src.index("_ensure_docker_installed()") : src.index("# ---- Defaults ----")]
    assert "_docker_install_via_apt && return 0" in body
    assert "_docker_install_via_get_script && return 0" in body
    assert "_docker_install_report_failure" in body


def test_public_upgrade_refreshes_local_checkout_before_handoff():
    src = _src()
    assert "_FLOWHUB_BOOTSTRAP_REFRESH=0" in src
    assert "--upgrade|--repair|--reinstall" in src
    body = src[src.index("_bs_clone_or_pull()") : src.index("# Bootstrap detection")]
    assert 'if [[ "$_FLOWHUB_BOOTSTRAP_REFRESH" -eq 1 ]]' in body
    assert 'git -C "$_FLOWHUB_INSTALL_DIR" pull --ff-only origin "$_FLOWHUB_BRANCH"' in body
    assert body.index("Refreshing repository before installer handoff") < body.index("exec bash") if "exec bash" in body else True
