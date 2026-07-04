from __future__ import annotations

from pathlib import Path


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


def test_upgrade_resets_installed_checkout_to_current_main_release():
    src = _src()
    body = src[src.index("step_update_repository()") : src.index("# ---- Upgrade path")]
    assert 'git -C "$INSTALL_DIR" fetch origin main' in body
    assert "git -C \"$INSTALL_DIR\" checkout -B main origin/main" in body
    assert "git -C \"$INSTALL_DIR\" reset --hard origin/main" in body
    assert 'normalize_legacy_release_files "$INSTALL_DIR"' in body


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
    migration = src[src.index("step_database_init()") : src.index("step_create_admin()")]
    assert 'assert_production_runtime_files "$INSTALL_DIR"' in launch
    assert 'stop_stale_beta_runtime "$INSTALL_DIR"' in launch
    assert 'assert_production_runtime_files "$INSTALL_DIR"' in migration


def test_deploy_recreates_services_and_removes_orphans():
    src = Path("installer/lib/docker_deploy.sh").read_text(encoding="utf-8")
    assert "up -d --build --force-recreate --remove-orphans" in src
