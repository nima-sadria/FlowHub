"""Tests for the legacy Python menu delegation.

The installed shell wrapper at scripts/flowhub is the canonical interactive
operator menu. The Python CLI no-args path stays as a safe pointer for local
developer usage and must not drift into a second menu contract.
"""

from __future__ import annotations

from unittest.mock import patch


def test_python_menu_delegates_to_installed_wrapper(capsys):
    from cli.menu import show_menu

    show_menu()
    out = capsys.readouterr().out

    assert "canonical interactive menu" in out
    assert "Run: flowhub" in out


def test_python_menu_does_not_expose_legacy_options(capsys):
    from cli.menu import show_menu

    show_menu()
    out = capsys.readouterr().out

    assert "Configure" not in out
    assert "Restart Services" not in out
    assert "Enter choice [1-7]" not in out


def test_main_no_args_calls_show_menu():
    from typer.testing import CliRunner
    from cli.main import app

    runner = CliRunner()
    with patch("cli.menu.show_menu") as mock_menu:
        result = runner.invoke(app, [])

    assert result.exit_code == 0
    mock_menu.assert_called_once()


def test_help_still_works():
    from typer.testing import CliRunner
    from cli.main import app

    runner = CliRunner()
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
