from pathlib import Path


def test_privileged_restore_validates_and_stages_before_live_file_swaps():
    source = Path("scripts/flowhub-helper").read_text(encoding="utf-8")
    assert "backup_manifest validate-archive --archive" in source
    assert "backup_manifest validate --root" in source
    assert "create_backup \"pre-restore\"" in source
    assert "-v ON_ERROR_STOP=1" in source
    assert "--single-transaction" in source
    restore_body = source[source.index("restore_backup() {"):]
    assert restore_body.index("restore_database_dump \"${staging_dir}/postgres.sql\"") < restore_body.index("apply_restored_files")
    assert "restore_database_from_archive \"$safety_archive\"" in restore_body
