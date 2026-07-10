from __future__ import annotations

import os
import shlex
import subprocess
import tarfile
from pathlib import Path

import pytest

from app.flowhub.backup.manifest import write_manifest


ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "scripts" / "flowhub-helper"
GIT_BASH = Path(r"C:\Program Files\Git\bin\bash.exe")


def _bash_path(path: Path) -> str:
    value = path.resolve().as_posix()
    if len(value) > 2 and value[1] == ":":
        return f"/{value[0].lower()}{value[2:]}"
    return value


def _archive(tmp_path: Path) -> Path:
    payload = tmp_path / "payload"
    payload.mkdir()
    (payload / ".env").write_text("FLOWHUB_ENV=restored\n", encoding="utf-8")
    (payload / "postgres.sql").write_text("BEGIN; SELECT 1; COMMIT;\n", encoding="utf-8")
    storage = payload / "storage"
    storage.mkdir()
    (storage / "state.json").write_text('{"state":"restored"}\n', encoding="utf-8")
    write_manifest(payload, application_version="1.0.0", migration_head="FLOWHUB_011")

    archive = tmp_path / "backup.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        for item in payload.iterdir():
            handle.add(item, arcname=item.name)
    return archive


def _harness(tmp_path: Path) -> Path:
    source = HELPER.read_text(encoding="utf-8")
    harness = tmp_path / "helper-functions.sh"
    harness.write_text(source.split("\nrequire_root\n", 1)[0], encoding="utf-8")
    return harness


def _run_restore(tmp_path: Path, *, database_succeeds: bool) -> subprocess.CompletedProcess[str]:
    if not GIT_BASH.is_file():
        pytest.skip("Git Bash is required for the isolated restore execution test.")

    install = tmp_path / "install"
    (install / "storage").mkdir(parents=True)
    (install / "backups").mkdir()
    (install / ".env").write_text("FLOWHUB_ENV=live\n", encoding="utf-8")
    (install / "storage" / "state.json").write_text('{"state":"live"}\n', encoding="utf-8")
    archive = _archive(tmp_path)
    harness = _harness(tmp_path)
    marker = tmp_path / "restored.sql"
    safety_archive = tmp_path / "safety.tar.gz"
    database_body = f"cp \"$1\" {shlex.quote(_bash_path(marker))}" if database_succeeds else "return 1"

    script = f"""
source {shlex.quote(_bash_path(harness))}
INSTALL_DIR={shlex.quote(_bash_path(install))}
ENV_FILE=\"$INSTALL_DIR/.env\"
COMPOSE_FILE=\"$INSTALL_DIR/docker-compose.yml\"
backup_manifest() {{ python3 {shlex.quote(_bash_path(ROOT / 'app' / 'flowhub' / 'backup' / 'manifest.py'))} \"$@\"; }}
create_backup() {{ BACKUP_ARCHIVE={shlex.quote(_bash_path(safety_archive))}; cp {shlex.quote(_bash_path(archive))} \"$BACKUP_ARCHIVE\"; }}
restore_database_dump() {{ {database_body}; }}
restore_database_from_archive() {{ return 0; }}
restore_backup {shlex.quote(_bash_path(archive))}
"""
    env = {**os.environ, "FLOWHUB_INSTALL_DIR": _bash_path(install)}
    return subprocess.run(
        [str(GIT_BASH), "-lc", script],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_restore_stages_database_before_replacing_runtime_files(tmp_path):
    result = _run_restore(tmp_path, database_succeeds=True)

    assert result.returncode == 0, result.stderr
    install = tmp_path / "install"
    assert (install / ".env").read_text(encoding="utf-8") == "FLOWHUB_ENV=restored\n"
    assert (install / "storage" / "state.json").read_text(encoding="utf-8") == '{"state":"restored"}\n'
    assert (tmp_path / "restored.sql").read_text(encoding="utf-8").startswith("BEGIN;")


def test_database_restore_failure_leaves_live_runtime_files_unchanged(tmp_path):
    result = _run_restore(tmp_path, database_succeeds=False)

    assert result.returncode != 0
    install = tmp_path / "install"
    assert (install / ".env").read_text(encoding="utf-8") == "FLOWHUB_ENV=live\n"
    assert (install / "storage" / "state.json").read_text(encoding="utf-8") == '{"state":"live"}\n'
