"""Regression guard for deliberately unmounted target API routers.

These modules are roadmap placeholders, not partially active capabilities.  A
future implementation must update the architecture decision and this guard
before it exposes a route.
"""

from __future__ import annotations

from importlib import import_module

from app.flowhub.app import app


PLANNED_ROUTER_PREFIXES = {
    "ai": "/ai",
    "backup": "/backup",
    "changesets": "/changesets",
    "dryrun": "/dryrun",
    "execution": "/execution",
    "flags": "/flags",
    "plugins": "/plugins",
    "rules": "/rules",
    "safety": "/safety",
    "scheduler": "/scheduler",
}


def test_planned_router_modules_define_no_endpoints() -> None:
    """Target router files must not be mistaken for implemented API surfaces."""
    for module_name in PLANNED_ROUTER_PREFIXES:
        module = import_module(f"app.flowhub.api.v2.{module_name}")
        assert module.router.routes == [], module_name


def test_planned_router_prefixes_are_not_mounted() -> None:
    """Target routers remain unreachable until an Owner-approved implementation."""
    mounted_paths = {
        route.path
        for route in app.routes
        if hasattr(route, "path")
    }
    for prefix in PLANNED_ROUTER_PREFIXES.values():
        assert not any(path == prefix or path.startswith(f"{prefix}/") for path in mounted_paths)
