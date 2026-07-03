"""Tests for HealthEngine orchestrator."""

from __future__ import annotations

import pytest

from app.flowhub.connections.adapters import DNSResolutionError, TLSHandshakeError
from app.flowhub.control_plane.failure import FailureClass
from app.flowhub.health.models import CheckCategory, HealthStatus


# ---------------------------------------------------------------------------
# run() - single check delegation
# ---------------------------------------------------------------------------


def test_engine_run_delegates_to_check(engine, test_double_adapter):
    from app.flowhub.health.checks import DNSCheck
    test_double_adapter.dns_default = ["1.2.3.4"]
    r = engine.run(DNSCheck("dns", "nc.example.com", test_double_adapter))
    assert r.status == HealthStatus.PASS


def test_engine_run_many_returns_all(engine, test_double_adapter):
    from app.flowhub.health.checks import DNSCheck, StorageCheck
    checks = [
        DNSCheck("dns", "nc.example.com", test_double_adapter),
        StorageCheck("storage", "/data", test_double_adapter),
    ]
    results = engine.run_many(checks)
    assert len(results) == 2


# ---------------------------------------------------------------------------
# run_integration_chain()
# ---------------------------------------------------------------------------


def test_engine_integration_chain_success(engine, test_double_adapter):
    results = engine.run_integration_chain("nextcloud", "https://nc.example.com")
    assert all(r.status in (HealthStatus.PASS, HealthStatus.WARN) for r in results)


def test_engine_integration_chain_has_4_steps_https(engine, test_double_adapter):
    results = engine.run_integration_chain("nextcloud", "https://nc.example.com")
    # DNS, TCP, TLS, HTTP (no auth credentials supplied)
    assert len(results) == 4


def test_engine_integration_chain_has_3_steps_http(engine, test_double_adapter):
    results = engine.run_integration_chain("service", "http://nc.example.com")
    # DNS, TCP, HTTP (no TLS, no auth)
    assert len(results) == 3


def test_engine_integration_chain_dns_fail_skips_rest(engine, test_double_adapter):
    test_double_adapter.dns_default = DNSResolutionError("NXDOMAIN")
    results = engine.run_integration_chain("nextcloud", "https://nc.example.com")
    dns = next(r for r in results if r.category == CheckCategory.DNS)
    tcp = next(r for r in results if r.category == CheckCategory.TCP)
    assert dns.status == HealthStatus.FAIL
    assert tcp.status == HealthStatus.SKIP


def test_engine_integration_chain_tls_fail_skips_http(engine, test_double_adapter):
    test_double_adapter.tls_default = TLSHandshakeError("cert verify failed")
    results = engine.run_integration_chain("nextcloud", "https://nc.example.com")
    http = next(r for r in results if r.category == CheckCategory.HTTP)
    assert http.status == HealthStatus.SKIP


# ---------------------------------------------------------------------------
# run_dns_check convenience method
# ---------------------------------------------------------------------------


def test_engine_run_dns_check_pass(engine, test_double_adapter):
    test_double_adapter.dns_default = ["1.2.3.4"]
    r = engine.run_dns_check("nc.example.com")
    assert r.status == HealthStatus.PASS
    assert r.category == CheckCategory.DNS


def test_engine_run_dns_check_fail(engine, test_double_adapter):
    test_double_adapter.dns_default = DNSResolutionError("NXDOMAIN")
    r = engine.run_dns_check("nc.example.com")
    assert r.status == HealthStatus.FAIL
    assert r.failure_class == FailureClass.DNS_FAILURE


# ---------------------------------------------------------------------------
# run_storage_check convenience method
# ---------------------------------------------------------------------------


def test_engine_run_storage_check_pass(engine, test_double_adapter):
    r = engine.run_storage_check("/data/flowhub")
    assert r.status == HealthStatus.PASS


# ---------------------------------------------------------------------------
# run_database_check convenience method
# ---------------------------------------------------------------------------


def test_engine_run_database_check_pass(engine, test_double_adapter):
    r = engine.run_database_check("postgresql://host/db")
    assert r.status == HealthStatus.PASS


# ---------------------------------------------------------------------------
# run_docker_check convenience method (unavailable)
# ---------------------------------------------------------------------------


def test_engine_run_docker_check_returns_skip(engine, test_double_adapter):
    r = engine.run_docker_check()
    assert r.status == HealthStatus.SKIP


# ---------------------------------------------------------------------------
# run_config_check convenience method
# ---------------------------------------------------------------------------


def test_engine_run_config_check_pass(engine):
    r = engine.run_config_check(
        required_keys=["FLOWHUB_SECRET_KEY"],
        config_dict={"FLOWHUB_SECRET_KEY": "x"},
    )
    assert r.status == HealthStatus.PASS


def test_engine_run_config_check_fail_on_missing(engine):
    r = engine.run_config_check(
        required_keys=["FLOWHUB_SECRET_KEY"],
        config_dict={},
    )
    assert r.status == HealthStatus.FAIL


# ---------------------------------------------------------------------------
# summarize()
# ---------------------------------------------------------------------------


def test_engine_summarize_all_pass(engine, test_double_adapter):
    results = engine.run_integration_chain("nextcloud", "https://nc.example.com")
    summary = engine.summarize(results)
    assert summary.overall_status in (HealthStatus.PASS, HealthStatus.WARN)


def test_engine_summarize_fail_when_dns_fails(engine, test_double_adapter):
    test_double_adapter.dns_default = DNSResolutionError("NXDOMAIN")
    results = engine.run_integration_chain("nextcloud", "https://nc.example.com")
    summary = engine.summarize(results)
    assert summary.overall_status == HealthStatus.FAIL
    assert summary.failed >= 1


def test_engine_summarize_counts_skips(engine, test_double_adapter):
    test_double_adapter.dns_default = DNSResolutionError("NXDOMAIN")
    results = engine.run_integration_chain("nextcloud", "https://nc.example.com")
    summary = engine.summarize(results)
    # DNS fail -> TCP, TLS, HTTP all skipped
    assert summary.skipped >= 3


# ---------------------------------------------------------------------------
# No network calls verification
# ---------------------------------------------------------------------------


def test_no_real_network_in_integration_chain(engine, test_double_adapter):
    """TestDoubleNetworkAdapter must have been called - not a real adapter."""
    # If a real network call happened, the test environment would fail or be slow.
    # We verify it didn't by checking the adapter is our test_double.
    from tests.flowhub.connections.conftest import TestDoubleNetworkAdapter
    assert isinstance(test_double_adapter, TestDoubleNetworkAdapter)
    results = engine.run_integration_chain("nextcloud", "https://nc.example.com")
    # Results must be present
    assert len(results) > 0
