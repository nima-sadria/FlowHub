from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

INSTALL = Path("installer/install.sh")


def _src() -> str:
    return INSTALL.read_text(encoding="utf-8")


def test_installer_normalizes_legacy_env_and_compose_names_before_detection():
    src = _src()
    normalize_pos = src.index('normalize_legacy_release_files "$INSTALL_DIR"')
    detect_pos = src.index("if detect_existing_installation")
    assert normalize_pos < detect_pos
    assert ".env.beta" in src
    assert "docker-compose.beta.yml" in src


def test_legacy_env_migrates_only_when_new_env_is_absent_and_remains_protected():
    src = _src()
    body = src[src.index("normalize_legacy_release_files()") : src.index("migrate_legacy_installation_if_needed()")]
    assert '[[ ! -f "${dir}/.env" && -f "${dir}/.env.beta" ]]' in body
    assert 'mv "${dir}/.env.beta" "${dir}/.env"' in body
    assert '_normalize_legacy_env_keys "${dir}/.env"' in body
    assert 'chown root:root "${dir}/.env"' in body
    assert 'chmod 600 "${dir}/.env"' in body


def test_legacy_env_keys_are_translated_to_flowhub_names():
    src = _src()
    body = src[src.index("_normalize_legacy_env_keys()") : src.index("_ensure_docker_runtime_running()")]
    assert "grep -qE '^BETA_'" in body
    assert 'sub(/^BETA_/, "FLOWHUB_")' in body
    assert 'FLOWHUB_ENV=production' in body
    assert 'chmod 600 "$env_file"' in body


def test_legacy_compose_migrates_only_when_new_compose_is_absent():
    src = _src()
    body = src[src.index("normalize_legacy_release_files()") : src.index("migrate_legacy_installation_if_needed()")]
    assert '[[ ! -f "${dir}/docker-compose.yml" && -f "${dir}/docker-compose.beta.yml" ]]' in body
    assert 'mv "${dir}/docker-compose.beta.yml" "${dir}/docker-compose.yml"' in body


def test_legacy_path_migration_preserves_old_release_files_when_copying_missing_items():
    src = _src()
    assert "for item in .env .env.beta docker-compose.yml docker-compose.beta.yml storage backups logs; do" in src


def test_upgrade_resets_installed_checkout_to_configured_release_branch():
    src = _src()
    validation = src[src.index("_validate_flowhub_branch()") : src.index("_bs_clone_or_pull()")]
    bootstrap = src[src.index("_bs_clone_or_pull()") : src.index("# Bootstrap detection")]
    body = src[src.index("step_update_repository()") : src.index("# ---- Upgrade path")]
    assert '_FLOWHUB_BRANCH="${FLOWHUB_BRANCH:-main}"' in src
    assert 'normalized_branch="$(git check-ref-format --branch "$_FLOWHUB_BRANCH"' in validation
    assert '[[ "$normalized_branch" != "$_FLOWHUB_BRANCH" ]]' in validation
    assert bootstrap.index("_validate_flowhub_branch") < bootstrap.index("git -C")
    assert body.index("_validate_flowhub_branch") < body.index("git -C")
    assert 'git -C "$INSTALL_DIR" fetch origin "$_FLOWHUB_BRANCH"' in body
    assert 'git -C "$INSTALL_DIR" checkout -B "$_FLOWHUB_BRANCH" "origin/${_FLOWHUB_BRANCH}"' in body
    assert 'git -C "$INSTALL_DIR" reset --hard "origin/${_FLOWHUB_BRANCH}"' in body
    assert 'normalize_legacy_release_files "$INSTALL_DIR"' in body


@pytest.mark.parametrize("branch", ["main", "release/1.2", "feature/foo.bar", "hotfix-123"])
def test_configured_release_branch_validation_preserves_valid_names(branch: str):
    result = subprocess.run(
        ["git", "check-ref-format", "--branch", branch],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == branch


@pytest.mark.parametrize(
    "branch",
    [
        "-b",
        "--upload-pack=/tmp/pwn",
        "main:refs/heads/pwn",
        "+main:refs/heads/pwn",
        "feature name",
        "feature..name",
        "feature~1",
        "feature^{}",
        "@{-1}",
    ],
)
def test_configured_release_branch_validation_rejects_invalid_or_rewritten_names(branch: str):
    result = subprocess.run(
        ["git", "check-ref-format", "--branch", branch],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0 or result.stdout.strip() != branch


def test_runtime_contract_blocks_stale_beta_runtime_before_migration():
    src = _src()
    contract = src[src.index("assert_production_runtime_files()") : src.index("stop_stale_beta_runtime()")]
    assert "docker-compose.yml" in contract
    assert ".env" in contract
    assert "alembic_flowhub.ini" in contract
    assert "alembic_flowhub" in contract
    assert "image: flowhub:latest" in contract
    assert "app.flowhub.app:app" in contract
    assert "flowhub-beta:latest|app\\.beta\\.app|docker-compose\\.beta\\.yml|\\.env\\.beta" in contract


def test_launch_and_migration_verify_production_runtime_contract():
    src = _src()
    launch = src[src.index("step_docker_launch()") : src.index("step_database_init()")]
    migration = src[src.index("step_database_init()") : src.index("detect_flowhub_operator_user()")]
    assert 'assert_production_runtime_files "$INSTALL_DIR"' in launch
    assert 'stop_stale_beta_runtime "$INSTALL_DIR"' in launch
    assert 'assert_production_runtime_files "$INSTALL_DIR"' in migration


def test_deploy_recreates_services_and_removes_orphans():
    src = Path("installer/lib/docker_deploy.sh").read_text(encoding="utf-8")
    assert "up -d --build --force-recreate --remove-orphans" in src
