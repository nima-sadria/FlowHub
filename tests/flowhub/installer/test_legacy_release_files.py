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
    assert 'chown root:root "${dir}/.env"' in body
    assert 'chmod 600 "${dir}/.env"' in body


def test_legacy_compose_migrates_only_when_new_compose_is_absent():
    src = _src()
    body = src[src.index("normalize_legacy_release_files()") : src.index("migrate_legacy_installation_if_needed()")]
    assert '[[ ! -f "${dir}/docker-compose.yml" && -f "${dir}/docker-compose.beta.yml" ]]' in body
    assert 'mv "${dir}/docker-compose.beta.yml" "${dir}/docker-compose.yml"' in body


def test_legacy_path_migration_preserves_old_release_files_when_copying_missing_items():
    src = _src()
    assert "for item in .env .env.beta docker-compose.yml docker-compose.beta.yml storage backups logs; do" in src
