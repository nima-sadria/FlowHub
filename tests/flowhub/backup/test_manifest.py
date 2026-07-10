from __future__ import annotations

import tarfile

import pytest

from app.flowhub.backup.manifest import BackupValidationError, validate_archive, validate_manifest, write_manifest


def _backup_root(tmp_path):
    root = tmp_path / "backup"
    root.mkdir(parents=True)
    (root / "postgres.sql").write_text("BEGIN; SELECT 1; COMMIT;\n", encoding="utf-8")
    (root / ".env").write_text("FLOWHUB_JWT_SECRET=redacted\n", encoding="utf-8")
    storage = root / "storage"
    storage.mkdir()
    (storage / "state.json").write_text('{"ok": true}\n', encoding="utf-8")
    return root


def test_valid_manifest_validates_required_backup_contents(tmp_path):
    root = _backup_root(tmp_path)
    manifest = write_manifest(root, application_version="1.0.0", migration_head="FLOWHUB_011")

    payload = validate_manifest(root, manifest)

    assert payload["database"]["filename"] == "postgres.sql"
    assert payload["migration_head"] == "FLOWHUB_011"
    assert payload["archive_integrity"]["algorithm"] == "sha256"


def test_missing_dump_or_bad_checksum_is_rejected_before_restore(tmp_path):
    root = _backup_root(tmp_path)
    write_manifest(root, application_version="1.0.0", migration_head="FLOWHUB_011")
    (root / "postgres.sql").write_text("corrupt", encoding="utf-8")
    with pytest.raises(BackupValidationError, match="checksum"):
        validate_manifest(root)

    root = _backup_root(tmp_path / "missing")
    (root / "postgres.sql").unlink()
    with pytest.raises(BackupValidationError, match="missing required file"):
        write_manifest(root, application_version="1.0.0", migration_head="FLOWHUB_011")


def test_traversal_archive_is_rejected_before_extraction(tmp_path):
    archive = tmp_path / "unsafe.tar.gz"
    payload = tmp_path / "payload.txt"
    payload.write_text("unsafe", encoding="utf-8")
    with tarfile.open(archive, "w:gz") as handle:
        handle.add(payload, arcname="../outside.txt")

    with pytest.raises(BackupValidationError, match="unsafe path"):
        validate_archive(archive)
