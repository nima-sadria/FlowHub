"""Static checks for the installed flowhub shell wrapper."""

from __future__ import annotations

from pathlib import Path


WRAPPER = Path("scripts/flowhub")


def _src() -> str:
    return WRAPPER.read_text(encoding="utf-8")


def test_wrapper_no_args_opens_management_menu():
    src = _src()
    assert 'cmd="${1:-menu}"' in src
    assert "show_management_menu" in src


def test_management_menu_contains_all_numbered_options():
    src = _src()
    for number in range(0, 29):
        assert f"{number}." in src
    assert "FlowHub Management" in src
    assert "Please enter your selection [0-28]:" in src


def test_menu_footer_contains_required_status_fields():
    src = _src()
    for label in [
        "Panel state:",
        "Database:",
        "Safety mode:",
        "Install path:",
        "Public URL:",
        "Docker:",
        "Version / commit:",
    ]:
        assert label in src


def test_wrapper_documents_admin_recovery_commands():
    src = _src()
    assert "flowhub admin reset-username" in src
    assert "flowhub admin reset-password" in src
