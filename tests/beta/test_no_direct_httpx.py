"""Direct-call audit test.

Asserts that no Python module in the scoped BU5 integration directories
imports httpx. All WC/NC HTTP calls must go through app/connectors/.

Scoped directories (where WC/NC calls used to live and must now be clean):
  - app/beta/integrations/  — integration client wrappers
  - app/beta/api/v2/        — BU5 FastAPI route handlers

Out-of-scope directories (legitimately use httpx for other purposes):
  - app/connectors/         — allowed; this IS the connector layer
  - app/a2/                 — different phase (A2 adapter migration)
  - app/services/           — legacy layer (pre-Beta architecture)
  - app/beta/connections/   — generic transport adapter (not WC/NC specific)
  - app/main.py             — app bootstrap
"""
import ast
import pathlib

_REPO_ROOT = pathlib.Path(__file__).parents[2]

# Directories to audit — WC/NC API calls must NOT appear here
_AUDIT_DIRS = [
    _REPO_ROOT / "app" / "beta" / "integrations",
    _REPO_ROOT / "app" / "beta" / "api" / "v2",
]


def _collect_python_files(root: pathlib.Path) -> list[pathlib.Path]:
    return list(root.rglob("*.py"))


def _has_httpx_import(path: pathlib.Path) -> bool:
    """Return True if the file contains any httpx import at module level."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "httpx" in (alias.name or ""):
                    return True
        elif isinstance(node, ast.ImportFrom):
            if "httpx" in (node.module or ""):
                return True
    return False


def test_no_direct_httpx_in_beta_integrations_and_routes():
    """BU5 integration clients and route handlers must not import httpx directly."""
    violations: list[str] = []

    for audit_dir in _AUDIT_DIRS:
        for py_file in _collect_python_files(audit_dir):
            if _has_httpx_import(py_file):
                rel = py_file.relative_to(_REPO_ROOT)
                violations.append(str(rel))

    assert violations == [], (
        "The following BU5 files import httpx directly — "
        "all WC/NC HTTP calls must go through app/connectors/:\n"
        + "\n".join(f"  {v}" for v in sorted(violations))
    )
