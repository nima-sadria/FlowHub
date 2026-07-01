"""Direct-call audit tests.

Two independent checks that enforce connector isolation for the FlowHub Beta runtime.

------------------------------------------------------------------------------
TEST 1 - test_no_direct_httpx_in_beta_runtime()
  Scans the entire app/beta/ tree for any `import httpx` / `from httpx` statement.
  The only permitted file is app/beta/connections/adapters.py (generic transport
  adapter for the installer / diagnostics B6 layer - not a WC/NC API client).
  All other Beta files that need HTTP go through app/connectors/.

TEST 2 - test_legacy_services_not_imported_by_beta()
  Confirms that the Legacy Compatibility service layer (app/services/woocommerce.py,
  app/services/nextcloud.py, app/services/auth.py) is NOT imported by any file
  in app/beta/. These legacy files make direct WC/NC httpx calls and are used
  only by app/main.py (legacy compatibility app on legacy port 8000).

------------------------------------------------------------------------------
Out-of-scope (legitimately use httpx for non-Beta purposes):
  app/connectors/         - the connector layer itself (httpx is expected here)
  app/beta/connections/adapters.py - generic installer/B6 transport adapter
  app/a2/                 - A2 source adapter phase (separate migration phase)
  app/services/           - Legacy Compatibility layer (not used by Beta runtime)
  app/main.py             - Legacy Compatibility app bootstrap
"""
import ast
import pathlib

_REPO_ROOT = pathlib.Path(__file__).parents[2]
_BETA_DIR = _REPO_ROOT / "app" / "beta"

# Permitted Beta file that uses httpx for non-WC/NC transport (installer / B6 diagnostics)
_ADAPTERS_FILE = _BETA_DIR / "connections" / "adapters.py"

# Legacy Compatibility service modules that make direct WC/NC HTTP calls.
# These must remain isolated from app/beta/ - verified by TEST 2.
_LEGACY_SERVICES = [
    "app.services.woocommerce",
    "app.services.nextcloud",
    "app.services.auth",
]


def _collect_python_files(root: pathlib.Path) -> list[pathlib.Path]:
    return list(root.rglob("*.py"))


def _has_httpx_import(path: pathlib.Path) -> bool:
    """Return True if the file contains any httpx import at module or function level."""
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


def _imported_modules(path: pathlib.Path) -> set[str]:
    """Return all module names imported (absolute or relative) by a Python file."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return set()
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return set()
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name:
                    modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
    return modules


# -- TEST 1 --------------------------------------------------------------------

def test_no_direct_httpx_in_beta_runtime():
    """All of app/beta/ must be httpx-free, except the generic transport adapter.

    FlowHub Beta runtime uses app/connectors/ for all WC and Nextcloud HTTP.
    The one permitted exception is app/beta/connections/adapters.py which
    implements a generic installer/B6 network adapter unrelated to WC/NC APIs.
    """
    violations: list[str] = []

    for py_file in _collect_python_files(_BETA_DIR):
        # Permitted exception - generic transport adapter, not a WC/NC API client
        if py_file.resolve() == _ADAPTERS_FILE.resolve():
            continue
        if _has_httpx_import(py_file):
            rel = py_file.relative_to(_REPO_ROOT)
            violations.append(str(rel))

    assert violations == [], (
        "The following app/beta/ files import httpx directly.\n"
        "All WC/NC HTTP calls must go through app/connectors/.\n"
        "The only permitted Beta httpx user is app/beta/connections/adapters.py "
        "(generic installer transport - not a WC/NC client).\n"
        "Violations:\n"
        + "\n".join(f"  {v}" for v in sorted(violations))
    )


# -- TEST 2 --------------------------------------------------------------------

def test_legacy_services_not_imported_by_beta():
    """app/beta/ must not import any Legacy Compatibility service module.

    app/services/woocommerce.py, app/services/nextcloud.py, and app/services/auth.py
    make direct httpx WC/NC calls and are used only by the legacy app/main.py
    (FlowHub on legacy port 8000).  They must never be imported by the FlowHub Beta
    runtime (app/beta/app.py on port 8085).
    """
    violations: list[str] = []

    for py_file in _collect_python_files(_BETA_DIR):
        imported = _imported_modules(py_file)
        for legacy_module in _LEGACY_SERVICES:
            if legacy_module in imported:
                rel = py_file.relative_to(_REPO_ROOT)
                violations.append(f"{rel} imports {legacy_module}")

    assert violations == [], (
        "The following app/beta/ files import Legacy Compatibility service modules.\n"
        "These modules make direct httpx WC/NC calls and must remain isolated to app/main.py.\n"
        "FlowHub Beta must use app/connectors/ or app/beta/integrations/ instead.\n"
        "Violations:\n"
        + "\n".join(f"  {v}" for v in sorted(violations))
    )
