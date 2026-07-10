"""Backup manifest creation and validation used by the privileged restore helper."""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


FORMAT_VERSION = 1
MANIFEST_NAME = "backup_manifest.json"
REQUIRED_FILES = frozenset({"postgres.sql", ".env"})
REQUIRED_DIRECTORIES = frozenset({"storage"})


class BackupValidationError(ValueError):
    """Raised when an archive or staging directory is unsafe or incomplete."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(value: str) -> str:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or str(path) in {"", "."}:
        raise BackupValidationError("Backup contains an unsafe path.")
    return str(path)


def _files(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == MANIFEST_NAME:
            continue
        relative = _safe_relative(path.relative_to(root).as_posix())
        result[relative] = _sha256(path)
    return result


def build_manifest(root: Path, *, application_version: str, migration_head: str) -> dict[str, Any]:
    root = root.resolve()
    for required in REQUIRED_FILES:
        if not (root / required).is_file():
            raise BackupValidationError(f"Backup is missing required file: {required}")
    for required in REQUIRED_DIRECTORIES:
        if not (root / required).is_dir():
            raise BackupValidationError(f"Backup is missing required directory: {required}")
    files = _files(root)
    return {
        "format_version": FORMAT_VERSION,
        "application_version": application_version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "migration_head": migration_head,
        "database": {"filename": "postgres.sql", "sha256": files["postgres.sql"]},
        "included_paths": files,
        "archive_integrity": {"algorithm": "sha256", "file_count": len(files)},
    }


def write_manifest(root: Path, *, application_version: str, migration_head: str) -> Path:
    manifest = build_manifest(root, application_version=application_version, migration_head=migration_head)
    path = root / MANIFEST_NAME
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def validate_manifest(root: Path, manifest_path: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    manifest_path = manifest_path or root / MANIFEST_NAME
    if not manifest_path.is_file():
        raise BackupValidationError("Backup archive does not contain a manifest.")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BackupValidationError("Backup manifest is invalid.") from exc
    if not isinstance(payload, dict) or payload.get("format_version") != FORMAT_VERSION:
        raise BackupValidationError("Backup manifest format is not supported.")
    files = payload.get("included_paths")
    database = payload.get("database")
    if not isinstance(files, dict) or not isinstance(database, dict):
        raise BackupValidationError("Backup manifest is incomplete.")
    for required in REQUIRED_FILES:
        if required not in files or not (root / required).is_file():
            raise BackupValidationError(f"Backup is missing required file: {required}")
    for required in REQUIRED_DIRECTORIES:
        if not (root / required).is_dir():
            raise BackupValidationError(f"Backup is missing required directory: {required}")
    if database.get("filename") != "postgres.sql" or database.get("sha256") != files.get("postgres.sql"):
        raise BackupValidationError("Database dump manifest entry is invalid.")
    actual = _files(root)
    normalized_files: dict[str, str] = {}
    for name, checksum in files.items():
        if not isinstance(name, str) or not isinstance(checksum, str):
            raise BackupValidationError("Backup manifest checksum entry is invalid.")
        normalized_files[_safe_relative(name)] = checksum
    if actual != normalized_files:
        raise BackupValidationError("Backup checksum validation failed.")
    return payload


def validate_archive(archive_path: Path) -> None:
    """Reject traversal, links, devices, and malformed archive members before extraction."""
    try:
        with tarfile.open(archive_path, "r:gz") as archive:
            members = archive.getmembers()
    except (OSError, tarfile.TarError) as exc:
        raise BackupValidationError("Backup archive is unreadable.") from exc
    if not members:
        raise BackupValidationError("Backup archive is empty.")
    for member in members:
        name = member.name.replace("\\", "/")
        while name.startswith("./"):
            name = name[2:]
        if name not in {"", "."}:
            _safe_relative(name)
        if member.issym() or member.islnk() or member.isdev():
            raise BackupValidationError("Backup archive contains unsupported link or device entries.")


def _main() -> int:
    parser = argparse.ArgumentParser(description="FlowHub backup manifest helper")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--root", type=Path, required=True)
    create.add_argument("--application-version", required=True)
    create.add_argument("--migration-head", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--root", type=Path, required=True)
    validate_archive_parser = subparsers.add_parser("validate-archive")
    validate_archive_parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "create":
            write_manifest(args.root, application_version=args.application_version, migration_head=args.migration_head)
        elif args.command == "validate":
            validate_manifest(args.root)
        else:
            validate_archive(args.archive)
    except BackupValidationError as exc:
        print(f"ERROR: {exc}")
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through the helper CLI
    raise SystemExit(_main())
