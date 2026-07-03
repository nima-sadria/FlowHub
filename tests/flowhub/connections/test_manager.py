"""Tests for ConnectionManager.

All tests use TestDoubleNetworkAdapter - no real network calls.
"""

from __future__ import annotations

import pytest

from app.flowhub.connections.adapters import (
    ConnectionTimeoutError,
    ConnectionUnreachableError,
    DNSResolutionError,
    InvalidResponseError,
    TLSHandshakeError,
)
from app.flowhub.connections.cache import ConnectionCache
from app.flowhub.connections.circuit_breaker import CircuitBreakerConfig
from app.flowhub.connections.manager import ConnectionManager
from app.flowhub.connections.models import (
    CircuitState,
    ConnectionDefinition,
    ConnectionStatus,
    ConnectionType,
)
from app.flowhub.control_plane.failure import FailureClass

from .conftest import TestDoubleNetworkAdapter


def _make_manager(
    adapter: TestDoubleNetworkAdapter,
    failure_threshold: int = 3,
    recovery_window_s: float = 30.0,
) -> ConnectionManager:
    config = CircuitBreakerConfig(
        failure_threshold=failure_threshold,
        recovery_window_s=recovery_window_s,
    )
    return ConnectionManager(
        adapter=adapter,
        circuit_config=config,
        sleep_fn=lambda _: None,  # no real sleep in tests
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_and_list(test_double_adapter, nextcloud_def):
    manager = _make_manager(test_double_adapter)
    manager.register(nextcloud_def)
    defs = manager.list_connections()
    assert len(defs) == 1
    assert defs[0].name == "nextcloud"


def test_register_multiple(test_double_adapter, nextcloud_def, woo_def):
    manager = _make_manager(test_double_adapter)
    manager.register(nextcloud_def)
    manager.register(woo_def)
    assert len(manager.list_connections()) == 2


def test_get_definition_returns_registered(test_double_adapter, nextcloud_def):
    manager = _make_manager(test_double_adapter)
    manager.register(nextcloud_def)
    assert manager.get_definition("nextcloud") is nextcloud_def


def test_get_definition_missing_returns_none(test_double_adapter):
    manager = _make_manager(test_double_adapter)
    assert manager.get_definition("ghost") is None


def test_check_unregistered_raises(test_double_adapter):
    manager = _make_manager(test_double_adapter)
    with pytest.raises(KeyError, match="nextcloud"):
        manager.check("nextcloud")


# ---------------------------------------------------------------------------
# Disabled connection
# ---------------------------------------------------------------------------


def test_disabled_connection_returns_disabled_status(test_double_adapter, disabled_def):
    manager = _make_manager(test_double_adapter)
    manager.register(disabled_def)
    result = manager.check("smtp")
    assert result.status == ConnectionStatus.DISABLED


def test_disabled_connection_has_none_failure_class(test_double_adapter, disabled_def):
    manager = _make_manager(test_double_adapter)
    manager.register(disabled_def)
    result = manager.check("smtp")
    assert result.failure_class == FailureClass.NONE


# ---------------------------------------------------------------------------
# Successful check
# ---------------------------------------------------------------------------


def test_healthy_result_on_success(test_double_adapter, nextcloud_def):
    manager = _make_manager(test_double_adapter)
    manager.register(nextcloud_def)
    result = manager.check("nextcloud")
    assert result.status == ConnectionStatus.HEALTHY


def test_healthy_result_has_none_failure_class(test_double_adapter, nextcloud_def):
    manager = _make_manager(test_double_adapter)
    manager.register(nextcloud_def)
    result = manager.check("nextcloud")
    assert result.failure_class == FailureClass.NONE


def test_healthy_result_reachable_is_true(test_double_adapter, nextcloud_def):
    manager = _make_manager(test_double_adapter)
    manager.register(nextcloud_def)
    result = manager.check("nextcloud")
    assert result.reachable is True


# ---------------------------------------------------------------------------
# DNS failure
# ---------------------------------------------------------------------------


def test_dns_failure_classification(test_double_adapter, nextcloud_def):
    test_double_adapter.dns_default = DNSResolutionError("NXDOMAIN")
    manager = _make_manager(test_double_adapter)
    manager.register(nextcloud_def)
    result = manager.check("nextcloud")
    assert result.failure_class == FailureClass.DNS_FAILURE
    assert result.status == ConnectionStatus.FAILED


def test_dns_failure_reachable_is_false(test_double_adapter, nextcloud_def):
    test_double_adapter.dns_default = DNSResolutionError("NXDOMAIN")
    manager = _make_manager(test_double_adapter)
    manager.register(nextcloud_def)
    result = manager.check("nextcloud")
    assert result.reachable is False


def test_dns_failure_not_retryable(test_double_adapter, nextcloud_def):
    test_double_adapter.dns_default = DNSResolutionError("NXDOMAIN")
    nextcloud_def.retry_attempts = 3
    manager = _make_manager(test_double_adapter)
    manager.register(nextcloud_def)
    result = manager.check("nextcloud")
    # DNS failure is non-retryable - attempt_number stays at 1
    assert result.attempt_number == 1


# ---------------------------------------------------------------------------
# TLS failure
# ---------------------------------------------------------------------------


def test_tls_failure_classification(test_double_adapter, nextcloud_def):
    test_double_adapter.tls_default = TLSHandshakeError("cert verify failed")
    manager = _make_manager(test_double_adapter)
    manager.register(nextcloud_def)
    result = manager.check("nextcloud")
    assert result.failure_class == FailureClass.TLS_FAILURE
    assert result.status == ConnectionStatus.FAILED


# ---------------------------------------------------------------------------
# Timeout failure
# ---------------------------------------------------------------------------


def test_timeout_failure_classification(test_double_adapter, nextcloud_def):
    test_double_adapter.dns_default = ConnectionTimeoutError("timeout")
    manager = _make_manager(test_double_adapter)
    manager.register(nextcloud_def)
    result = manager.check("nextcloud")
    assert result.failure_class == FailureClass.TIMEOUT
    assert result.retryable is True


def test_timeout_triggers_retry(test_double_adapter, nextcloud_def):
    """A retryable timeout should be retried up to retry_attempts times."""
    nextcloud_def.retry_attempts = 2
    call_count = [0]
    original_dns = test_double_adapter.resolve_dns

    def counting_dns(hostname):
        call_count[0] += 1
        raise ConnectionTimeoutError("timeout")

    test_double_adapter.resolve_dns = counting_dns
    manager = _make_manager(test_double_adapter)
    manager.register(nextcloud_def)
    manager.check("nextcloud")
    assert call_count[0] == 2  # 1 initial + 1 retry


# ---------------------------------------------------------------------------
# Unauthorized failure
# ---------------------------------------------------------------------------


def test_unauthorized_classification(test_double_adapter, nextcloud_def):
    test_double_adapter.http_default = (401, b"Unauthorized")
    manager = _make_manager(test_double_adapter)
    manager.register(nextcloud_def)
    result = manager.check("nextcloud")
    assert result.failure_class == FailureClass.UNAUTHORIZED


def test_forbidden_classification(test_double_adapter, nextcloud_def):
    test_double_adapter.http_default = (403, b"Forbidden")
    manager = _make_manager(test_double_adapter)
    manager.register(nextcloud_def)
    result = manager.check("nextcloud")
    assert result.failure_class == FailureClass.FORBIDDEN


# ---------------------------------------------------------------------------
# Invalid response
# ---------------------------------------------------------------------------


def test_invalid_response_classification(test_double_adapter, nextcloud_def):
    test_double_adapter.http_default = (500, b"Internal Server Error")
    manager = _make_manager(test_double_adapter)
    manager.register(nextcloud_def)
    result = manager.check("nextcloud")
    assert result.failure_class == FailureClass.INVALID_RESPONSE


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def test_cache_hit_returns_from_cache(test_double_adapter, nextcloud_def):
    manager = _make_manager(test_double_adapter)
    manager.register(nextcloud_def)
    r1 = manager.check("nextcloud")
    r2 = manager.check("nextcloud")
    assert r2.from_cache is True


def test_cache_invalidate_forces_live_check(test_double_adapter, nextcloud_def):
    manager = _make_manager(test_double_adapter)
    manager.register(nextcloud_def)
    manager.check("nextcloud")
    manager.invalidate("nextcloud")
    r = manager.check("nextcloud")
    assert r.from_cache is False


def test_get_cached_before_check_returns_none(test_double_adapter, nextcloud_def):
    manager = _make_manager(test_double_adapter)
    manager.register(nextcloud_def)
    assert manager.get_cached("nextcloud") is None


def test_get_cached_after_check_returns_result(test_double_adapter, nextcloud_def):
    manager = _make_manager(test_double_adapter)
    manager.register(nextcloud_def)
    manager.check("nextcloud")
    assert manager.get_cached("nextcloud") is not None


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------


def test_circuit_opens_after_failures(test_double_adapter, nextcloud_def):
    test_double_adapter.dns_default = DNSResolutionError("NXDOMAIN")
    nextcloud_def.retry_attempts = 1
    manager = _make_manager(test_double_adapter, failure_threshold=3)
    manager.register(nextcloud_def)
    for _ in range(3):
        manager.check("nextcloud")
    result = manager.check("nextcloud")
    assert result.circuit_state == CircuitState.OPEN


def test_circuit_open_returns_failed_without_network_call(test_double_adapter, nextcloud_def):
    test_double_adapter.dns_default = DNSResolutionError("NXDOMAIN")
    nextcloud_def.retry_attempts = 1
    manager = _make_manager(test_double_adapter, failure_threshold=2)
    manager.register(nextcloud_def)
    manager.check("nextcloud")
    manager.check("nextcloud")
    # Reset adapter to success - circuit should block it
    test_double_adapter.dns_default = ["127.0.0.1"]
    result = manager.check("nextcloud")
    # Circuit still OPEN from prior failures
    assert result.circuit_state == CircuitState.OPEN
    assert result.status == ConnectionStatus.FAILED


def test_bypass_circuit_ignores_open_state(test_double_adapter, nextcloud_def):
    test_double_adapter.dns_default = DNSResolutionError("NXDOMAIN")
    nextcloud_def.retry_attempts = 1
    manager = _make_manager(test_double_adapter, failure_threshold=2)
    manager.register(nextcloud_def)
    manager.check("nextcloud")
    manager.check("nextcloud")
    # Now circuit is open; bypass should still make the call
    test_double_adapter.dns_default = ["127.0.0.1"]
    result = manager.check_bypass_circuit("nextcloud")
    assert result.status == ConnectionStatus.HEALTHY


# ---------------------------------------------------------------------------
# check_all
# ---------------------------------------------------------------------------


def test_check_all_returns_all_names(test_double_adapter, nextcloud_def, woo_def):
    manager = _make_manager(test_double_adapter)
    manager.register(nextcloud_def)
    manager.register(woo_def)
    results = manager.check_all()
    assert set(results.keys()) == {"nextcloud", "woocommerce"}


# ---------------------------------------------------------------------------
# Secret safety
# ---------------------------------------------------------------------------


def test_no_secrets_in_connection_result_dict(test_double_adapter, nextcloud_def):
    manager = _make_manager(test_double_adapter)
    manager.register(nextcloud_def)
    result = manager.check("nextcloud")
    d = result.to_dict()
    # No field should contain literal credential values
    for key in d:
        assert "password" not in key.lower()
        assert "secret" not in key.lower()
        assert "token" not in key.lower()


def test_connection_result_round_trip(test_double_adapter, nextcloud_def):
    manager = _make_manager(test_double_adapter)
    manager.register(nextcloud_def)
    result = manager.check("nextcloud")
    d = result.to_dict()
    restored = type(result).from_dict(d)
    assert restored.name == result.name
    assert restored.status == result.status
    assert restored.failure_class == result.failure_class


# ---------------------------------------------------------------------------
# ConnectionDefinition validation
# ---------------------------------------------------------------------------


def test_timeout_exceeding_60s_raises():
    with pytest.raises(ValueError, match="60"):
        ConnectionDefinition(
            name="x",
            connection_type=ConnectionType.GENERIC_HTTP,
            enabled=True,
            required=False,
            endpoint="http://example.com",
            timeout_seconds=61.0,
        )


def test_negative_timeout_raises():
    with pytest.raises(ValueError):
        ConnectionDefinition(
            name="x",
            connection_type=ConnectionType.GENERIC_HTTP,
            enabled=True,
            required=False,
            endpoint="http://example.com",
            timeout_seconds=-1.0,
        )
