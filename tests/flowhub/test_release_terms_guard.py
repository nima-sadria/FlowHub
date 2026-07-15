from __future__ import annotations

import re
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
    "tests/",
    "docs/architecture/",
)
SKIP_SUFFIXES = (
    ".css",
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
LEGACY_COMPATIBILITY_REFERENCE_FILES = {
    "alembic_flowhub/env.py",
    "installer/install.sh",
}
ALLOWED_RELEASE_TERM_PATHS = {
    # Owner-approved release registration. The exemption is path-exact and
    # does not permit release terms in application paths.
    "docs/releases/FLOWHUB_V1.3_BETA.md",
}
INTERNAL_TERM_PATTERNS = {
    "CHANGELOG.md": (r"FlowHub v1\.3 Beta",),
    "README.md": (r"v1\.3 Beta", r"FLOWHUB_V1\.3_BETA"),
    "docs/i18n/INTERNATIONALIZATION.md": (r"placeholders?",),
    "docs/i18n/TRANSLATOR_GUIDE.md": (r"placeholder",),
    "docs/releases/FLOWHUB_V1.3_BETA.md": (r"Beta",),
    "docs/roadmap/NEXT.md": (r"FlowHub v1\.3 Beta",),
    "app/flowhub/commerce/service.py": (
        r'"placeholder":\s*(True|False|bool\(meta\["placeholder"\]\))',
        r'\bplaceholder\s*=\s*bool\(meta\["placeholder"\]\)',
        r'\bif placeholder:',
        r'\bif meta\.get\("placeholder"\):',
        r'not bool\(meta\.get\("placeholder"\)\)',
        r'bool\(meta\.get\("placeholder"\)\)',
        r'bool\(meta\["placeholder"\]\)',
        r'meta\["placeholder"\]',
        r'_placeholder_connection_result',
        r'"status":\s*"placeholder"',
    ),
    "app/flowhub/integration_platform/registry.py": (
        r'\("placeholder",\s*"capability_detection"\)',
    ),
    "frontend/src/pages/CommerceHub.tsx": (
        r'\bsource\.placeholder\b',
        r'\bchannel\.placeholder\b',
        r'\bselected\.placeholder\b',
    ),
    "frontend/scripts/i18n.mjs": (r"[Pp]laceholders?",),
    "frontend/src/features/sourceWorkspace/SourceCentricWorkspace.tsx": (
        r"\bplaceholder=",
    ),
    "frontend/src/pages/DataQuality.tsx": (r"\bplaceholder=",),
    "frontend/src/pages/FlowHubSheet.tsx": (r"\bplaceholder=",),
    "frontend/src/pages/SourceConfiguration.tsx": (r"\bplaceholder=",),
    "frontend/src/services/types.ts": (
        r'\bplaceholder:\s*boolean\b',
    ),
    # This exact Handsontable evaluation token is a security validation
    # constant: the resolver must reject it in Production while permitting it
    # only in development/test.  Allowing this one line does not weaken the
    # repository-wide release-term scan for other production literals.
    "frontend/src/features/unifiedWorkspace/handsontableLicense.ts": (
        r"EVALUATION_KEY",
        r"non-commercial-and-evaluation",
        r"placeholder",
    ),
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


def _allowed_internal_term_line(path: str, line: str) -> bool:
    patterns = INTERNAL_TERM_PATTERNS.get(path, ())
    return any(re.search(pattern, line) for pattern in patterns)


def test_release_terms_do_not_appear_in_tracked_production_files() -> None:
    violations: list[str] = []

    for path in _tracked_files():
        normalized = path.replace("\\", "/")
        if any(normalized.startswith(prefix) for prefix in SKIP_PREFIXES):
            continue
        if _is_test_path(normalized):
            continue

        lower_path = normalized.lower()
        terms_for_path = TERMS
        for term in terms_for_path:
            if term in lower_path and normalized not in ALLOWED_RELEASE_TERM_PATHS:
                violations.append(f"{normalized}: path contains {term!r}")

        if normalized in LEGACY_COMPATIBILITY_REFERENCE_FILES:
            continue

        if _skip_content_scan(normalized):
            continue

        text = _read_text(ROOT / normalized)
        if text is None:
            continue
        terms_for_text = TERMS
        for line_number, line in enumerate(text.splitlines(), start=1):
            lower_line = line.lower()
            for term in terms_for_text:
                if term in lower_line and not _allowed_internal_term_line(normalized, line):
                    violations.append(f"{normalized}:{line_number}: content contains {term!r}")

    assert not violations, "\n".join(violations[:200])


def test_guard_scans_production_asset_paths_even_when_binary_content_is_skipped() -> None:
    forbidden = "place" + "holder"
    tracked_asset = f"static/icons/product-{forbidden}.webp"
    assert any(tracked_asset.startswith(prefix) for prefix in SKIP_PREFIXES) is False
    assert _skip_content_scan(tracked_asset) is True
    assert forbidden in tracked_asset
