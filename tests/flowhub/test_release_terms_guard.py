from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TERMS = [
    "be" + "ta",
    "mo" + "ck",
    "st" + "ub",
    "place" + "holder",
    "de" + "mo",
    "sam" + "ple",
    "fa" + "ke",
]
TEST_ONLY_ALLOWED = {"mo" + "ck"}
SKIP_PREFIXES = (
    "frontend/node_modules/",
)
SKIP_SUFFIXES = (
    "package-lock.json",
    ".ico",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".pdf",
    ".lock",
    ".pyc",
)
TEMPORARY_INTERNAL_REFERENCE_FILES = {
    "alembic_flowhub/env.py",
    "installer/install.sh",
    "tests/flowhub/migration/test_release_compatibility.py",
    "tests/flowhub/installer/test_legacy_release_files.py",
}


def _tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _skip_content_scan(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return (
        any(normalized.startswith(prefix) for prefix in SKIP_PREFIXES)
        or normalized.endswith(SKIP_SUFFIXES)
    )


def _is_test_path(path: str) -> bool:
    return (
        path.startswith("tests/")
        or ".test." in path
        or ".spec." in path
        or path.endswith("_test.py")
    )


def _read_text(path: Path) -> str | None:
    if not path.exists():
        return None
    data = path.read_bytes()
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def test_release_terms_do_not_appear_in_tracked_production_files() -> None:
    violations: list[str] = []

    for path in _tracked_files():
        normalized = path.replace("\\", "/")
        if any(normalized.startswith(prefix) for prefix in SKIP_PREFIXES):
            continue

        lower_path = normalized.lower()
        terms_for_path = TERMS if not _is_test_path(normalized) else [
            term for term in TERMS if term not in TEST_ONLY_ALLOWED
        ]
        for term in terms_for_path:
            if term in lower_path:
                violations.append(f"{normalized}: path contains {term!r}")

        if normalized in TEMPORARY_INTERNAL_REFERENCE_FILES:
            continue

        if _skip_content_scan(normalized):
            continue

        text = _read_text(ROOT / normalized)
        if text is None:
            continue
        lower_text = text.lower()
        terms_for_text = TERMS if not _is_test_path(normalized) else [
            term for term in TERMS if term not in TEST_ONLY_ALLOWED
        ]
        for term in terms_for_text:
            if term in lower_text:
                violations.append(f"{normalized}: content contains {term!r}")

    assert not violations, "\n".join(violations[:200])


def test_guard_scans_production_asset_paths_even_when_binary_content_is_skipped() -> None:
    forbidden = "place" + "holder"
    tracked_asset = f"static/icons/product-{forbidden}.webp"
    assert any(tracked_asset.startswith(prefix) for prefix in SKIP_PREFIXES) is False
    assert _skip_content_scan(tracked_asset) is True
    assert forbidden in tracked_asset
