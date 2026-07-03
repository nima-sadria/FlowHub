"""Tests for flowhub integrations command group (CP1.3)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest
from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


def _test_double_runner_pass(adapter, config=None):
    """A DiagnosticRunner that returns PASS for all integration checks."""
    from tests.flowhub.connections.conftest import TestDoubleNetworkAdapter
    from app.flowhub.diagnostics.runner import DiagnosticRunner

    test_double = TestDoubleNetworkAdapter()
    return DiagnosticRunner(adapter=test_double, config=config or {})


def _test_double_runner_fail(adapter, config=None):
    from tests.flowhub.connections.conftest import TestDoubleNetworkAdapter
    from app.flowhub.connections.adapters import DNSResolutionError
    from app.flowhub.diagnostics.runner import DiagnosticRunner

    test_double = TestDoubleNetworkAdapter()
    test_double.dns_default = DNSResolutionError("NXDOMAIN")
    return DiagnosticRunner(adapter=test_double, config=config or {})


class TestIntegrationsList:
    def test_list_exits_zero(self):
        result = runner.invoke(app, ["integrations", "list"])
        assert result.exit_code == 0

    def test_list_shows_known_services(self):
        result = runner.invoke(app, ["integrations", "list"])
        assert "nextcloud" in result.output
        assert "woocommerce" in result.output
        assert "currency_api" in result.output

    def test_list_shows_help_hint(self):
        result = runner.invoke(app, ["integrations", "list"])
        assert "test" in result.output.lower() or "flowhub" in result.output


class TestIntegrationsTest:
    def _patch_runner(self, test_double_pass: bool = True):
        from tests.flowhub.connections.conftest import TestDoubleNetworkAdapter
        from app.flowhub.connections.adapters import DNSResolutionError
        from app.flowhub.diagnostics.runner import DiagnosticRunner

        test_double = TestDoubleNetworkAdapter()
        if not test_double_pass:
            test_double.dns_default = DNSResolutionError("NXDOMAIN")
        _runner = DiagnosticRunner(adapter=test_double, config={})

        return mock.patch("cli.integrations._make_adapter", return_value=test_double), \
               mock.patch("cli.integrations.DiagnosticRunner", return_value=_runner)

    def test_test_help_exits_zero(self):
        result = runner.invoke(app, ["integrations", "test", "--help"])
        assert result.exit_code == 0

    def test_test_unknown_service_exits_nonzero(self):
        result = runner.invoke(app, ["integrations", "test", "unknown_service"])
        assert result.exit_code != 0

    def test_test_error_message_for_unknown_service(self):
        result = runner.invoke(app, ["integrations", "test", "unknown_service"])
        assert "unknown" in result.output.lower() or "unknown" in (result.stderr or "").lower()

    def test_test_pass_exits_zero(self):
        from tests.flowhub.connections.conftest import TestDoubleNetworkAdapter
        from app.flowhub.diagnostics.runner import DiagnosticRunner
        test_double = TestDoubleNetworkAdapter()
        _runner = DiagnosticRunner(adapter=test_double, config={})

        with mock.patch("cli.integrations._make_adapter", return_value=test_double), \
             mock.patch("cli.integrations.DiagnosticRunner", return_value=_runner):
            result = runner.invoke(app, ["integrations", "test", "nextcloud"])
        assert result.exit_code == 0

    def test_test_fail_exits_nonzero(self):
        from tests.flowhub.connections.conftest import TestDoubleNetworkAdapter
        from app.flowhub.connections.adapters import DNSResolutionError
        from app.flowhub.diagnostics.runner import DiagnosticRunner
        test_double = TestDoubleNetworkAdapter()
        test_double.dns_default = DNSResolutionError("NXDOMAIN")
        _runner = DiagnosticRunner(adapter=test_double, config={})

        with mock.patch("cli.integrations._make_adapter", return_value=test_double), \
             mock.patch("cli.integrations.DiagnosticRunner", return_value=_runner):
            result = runner.invoke(app, ["integrations", "test", "nextcloud"])
        assert result.exit_code != 0

    def test_test_json_output(self):
        from tests.flowhub.connections.conftest import TestDoubleNetworkAdapter
        from app.flowhub.diagnostics.runner import DiagnosticRunner
        test_double = TestDoubleNetworkAdapter()
        _runner = DiagnosticRunner(adapter=test_double, config={})

        with mock.patch("cli.integrations._make_adapter", return_value=test_double), \
             mock.patch("cli.integrations.DiagnosticRunner", return_value=_runner):
            result = runner.invoke(app, ["integrations", "test", "nextcloud", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "overall_status" in data
        assert "checks" in data

    def test_test_no_secrets_in_output(self):
        from tests.flowhub.connections.conftest import TestDoubleNetworkAdapter
        from app.flowhub.diagnostics.runner import DiagnosticRunner
        test_double = TestDoubleNetworkAdapter()
        _runner = DiagnosticRunner(adapter=test_double, config={"FLOWHUB_NEXTCLOUD_PASSWORD": "supersecret"})

        with mock.patch("cli.integrations._make_adapter", return_value=test_double), \
             mock.patch("cli.integrations.DiagnosticRunner", return_value=_runner):
            result = runner.invoke(app, ["integrations", "test", "nextcloud"])
        assert "supersecret" not in result.output

    def test_test_shows_check_results(self):
        from tests.flowhub.connections.conftest import TestDoubleNetworkAdapter
        from app.flowhub.diagnostics.runner import DiagnosticRunner
        test_double = TestDoubleNetworkAdapter()
        _runner = DiagnosticRunner(adapter=test_double, config={})

        with mock.patch("cli.integrations._make_adapter", return_value=test_double), \
             mock.patch("cli.integrations.DiagnosticRunner", return_value=_runner):
            result = runner.invoke(app, ["integrations", "test", "nextcloud"])
        assert result.exit_code == 0
        assert "PASS" in result.output or "pass" in result.output.lower()


class TestIntegrationsStatus:
    def test_status_exits_zero(self):
        from tests.flowhub.connections.conftest import TestDoubleNetworkAdapter
        from app.flowhub.diagnostics.runner import DiagnosticRunner
        test_double = TestDoubleNetworkAdapter()
        _runner = DiagnosticRunner(adapter=test_double, config={})

        with mock.patch("cli.integrations._make_adapter", return_value=test_double), \
             mock.patch("cli.integrations.DiagnosticRunner", return_value=_runner):
            result = runner.invoke(app, ["integrations", "status"])
        assert result.exit_code == 0

    def test_status_json_output(self):
        from tests.flowhub.connections.conftest import TestDoubleNetworkAdapter
        from app.flowhub.diagnostics.runner import DiagnosticRunner
        test_double = TestDoubleNetworkAdapter()
        _runner = DiagnosticRunner(adapter=test_double, config={})

        with mock.patch("cli.integrations._make_adapter", return_value=test_double), \
             mock.patch("cli.integrations.DiagnosticRunner", return_value=_runner):
            result = runner.invoke(app, ["integrations", "status", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "overall_status" in data

    def test_status_no_secrets_in_output(self):
        from tests.flowhub.connections.conftest import TestDoubleNetworkAdapter
        from app.flowhub.diagnostics.runner import DiagnosticRunner
        test_double = TestDoubleNetworkAdapter()
        _runner = DiagnosticRunner(adapter=test_double, config={"FLOWHUB_WOOCOMMERCE_SECRET": "mysecret"})

        with mock.patch("cli.integrations._make_adapter", return_value=test_double), \
             mock.patch("cli.integrations.DiagnosticRunner", return_value=_runner):
            result = runner.invoke(app, ["integrations", "status"])
        assert "mysecret" not in result.output
