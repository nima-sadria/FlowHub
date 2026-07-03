"""Tests for individual health check implementations.

No real network calls - TestDoubleNetworkAdapter is used throughout.
"""

from __future__ import annotations

import pytest

from app.flowhub.connections.adapters import (
    AccessForbiddenError,
    AuthenticationError,
    ConnectionTimeoutError,
    ConnectionUnreachableError,
    DatabaseAdapterError,
    DNSResolutionError,
    StorageAdapterError,
    TCPConnectionError,
    TLSHandshakeError,
)
from app.flowhub.control_plane.failure import FailureClass
from app.flowhub.health.checks import (
    AuthCheck,
    ConfigCheck,
    DatabaseCheck,
    DNSCheck,
    DockerCheck,
    HTTPCheck,
    IntegrationCheck,
    StorageCheck,
    TCPCheck,
    TLSCheck,
)
from app.flowhub.health.models import CheckCategory, HealthStatus


# ============================================================
# 1. DNS Check
# ============================================================


def test_dns_check_pass(test_double_adapter):
    test_double_adapter.dns_default = ["1.2.3.4"]
    r = DNSCheck("dns", "nextcloud.example.com", test_double_adapter).run()
    assert r.status == HealthStatus.PASS


def test_dns_check_includes_resolved_ips(test_double_adapter):
    test_double_adapter.dns_default = ["1.2.3.4", "5.6.7.8"]
    r = DNSCheck("dns", "nextcloud.example.com", test_double_adapter).run()
    assert "1.2.3.4" in r.details.get("resolved_ips", [])


def test_dns_check_fail_on_resolution_error(test_double_adapter):
    test_double_adapter.dns_default = DNSResolutionError("NXDOMAIN")
    r = DNSCheck("dns", "nextcloud.example.com", test_double_adapter).run()
    assert r.status == HealthStatus.FAIL
    assert r.failure_class == FailureClass.DNS_FAILURE


def test_dns_check_hostname_in_target(test_double_adapter):
    r = DNSCheck("dns", "nc.example.com", test_double_adapter).run()
    assert r.target == "nc.example.com"


def test_dns_check_category(test_double_adapter):
    r = DNSCheck("dns", "nc.example.com", test_double_adapter).run()
    assert r.category == CheckCategory.DNS


# ============================================================
# 2. TCP Check
# ============================================================


def test_tcp_check_pass(test_double_adapter):
    test_double_adapter.tcp_default = 5.0
    r = TCPCheck("tcp", "host", 443, 10.0, test_double_adapter).run()
    assert r.status == HealthStatus.PASS


def test_tcp_check_fail_on_connection_error(test_double_adapter):
    test_double_adapter.tcp_default = TCPConnectionError("refused")
    r = TCPCheck("tcp", "host", 443, 10.0, test_double_adapter).run()
    assert r.status == HealthStatus.FAIL
    assert r.failure_class == FailureClass.UNREACHABLE


def test_tcp_check_fail_on_timeout(test_double_adapter):
    test_double_adapter.tcp_default = ConnectionTimeoutError("timeout")
    r = TCPCheck("tcp", "host", 443, 10.0, test_double_adapter).run()
    assert r.status == HealthStatus.FAIL
    assert r.failure_class == FailureClass.TIMEOUT


def test_tcp_check_skips_when_prereq_failed(test_double_adapter):
    from app.flowhub.health.models import HealthCheckResult
    dns_fail = HealthCheckResult.fail(
        "dns", CheckCategory.DNS, "host", FailureClass.DNS_FAILURE, "nxdomain"
    )
    r = TCPCheck("tcp", "host", 443, 10.0, test_double_adapter, prerequisite_result=dns_fail).run()
    assert r.status == HealthStatus.SKIP
    assert r.skipped_because == "dns"


def test_tcp_check_does_not_skip_when_prereq_passed(test_double_adapter):
    from app.flowhub.health.models import HealthCheckResult
    dns_ok = HealthCheckResult.ok("dns", CheckCategory.DNS, "host", "ok")
    r = TCPCheck("tcp", "host", 443, 10.0, test_double_adapter, prerequisite_result=dns_ok).run()
    assert r.status == HealthStatus.PASS


def test_tcp_check_category(test_double_adapter):
    r = TCPCheck("tcp", "host", 443, 10.0, test_double_adapter).run()
    assert r.category == CheckCategory.TCP


# ============================================================
# 3. TLS Check
# ============================================================


def test_tls_check_pass(test_double_adapter):
    test_double_adapter.tls_default = {
        "cert_subject": "nextcloud.example.com",
        "cert_expiry": "2030-01-01",
        "days_until_expiry": 999,
        "chain_valid": True,
        "latency_ms": 3.0,
    }
    r = TLSCheck("tls", "nextcloud.example.com", 443, 10.0, test_double_adapter).run()
    assert r.status == HealthStatus.PASS


def test_tls_check_warn_when_cert_expiring_soon(test_double_adapter):
    test_double_adapter.tls_default = {
        "cert_subject": "nextcloud.example.com",
        "cert_expiry": "2026-07-01",
        "days_until_expiry": 3,
        "chain_valid": True,
        "latency_ms": 3.0,
    }
    r = TLSCheck("tls", "nextcloud.example.com", 443, 10.0, test_double_adapter).run()
    assert r.status == HealthStatus.WARN


def test_tls_check_fail_on_handshake_error(test_double_adapter):
    test_double_adapter.tls_default = TLSHandshakeError("CERTIFICATE_VERIFY_FAILED")
    r = TLSCheck("tls", "nextcloud.example.com", 443, 10.0, test_double_adapter).run()
    assert r.status == HealthStatus.FAIL
    assert r.failure_class == FailureClass.TLS_FAILURE


def test_tls_check_skips_when_prereq_failed(test_double_adapter):
    from app.flowhub.health.models import HealthCheckResult
    tcp_fail = HealthCheckResult.fail(
        "tcp", CheckCategory.TCP, "host:443", FailureClass.UNREACHABLE, "refused"
    )
    r = TLSCheck("tls", "host", 443, 10.0, test_double_adapter, prerequisite_result=tcp_fail).run()
    assert r.status == HealthStatus.SKIP


def test_tls_check_cert_info_in_details(test_double_adapter):
    test_double_adapter.tls_default = {
        "cert_subject": "nextcloud.example.com",
        "cert_expiry": "2030-01-01",
        "days_until_expiry": 999,
        "chain_valid": True,
        "latency_ms": 3.0,
    }
    r = TLSCheck("tls", "nextcloud.example.com", 443, 10.0, test_double_adapter).run()
    assert "days_until_expiry" in r.details
    assert "cert_expiry" in r.details


def test_tls_check_category(test_double_adapter):
    r = TLSCheck("tls", "host", 443, 10.0, test_double_adapter).run()
    assert r.category == CheckCategory.TLS


# ============================================================
# 4. HTTP Check
# ============================================================


def test_http_check_pass_on_expected_status(test_double_adapter):
    test_double_adapter.http_default = (200, b"ok")
    r = HTTPCheck("http", "https://host/status", "GET", 200, 10.0, test_double_adapter).run()
    assert r.status == HealthStatus.PASS


def test_http_check_fail_on_wrong_status(test_double_adapter):
    test_double_adapter.http_default = (500, b"error")
    r = HTTPCheck("http", "https://host/status", "GET", 200, 10.0, test_double_adapter).run()
    assert r.status == HealthStatus.FAIL
    assert r.failure_class == FailureClass.INVALID_RESPONSE


def test_http_check_fail_on_timeout(test_double_adapter):
    test_double_adapter.http_default = ConnectionTimeoutError("timeout")
    r = HTTPCheck("http", "https://host/status", "GET", 200, 10.0, test_double_adapter).run()
    assert r.status == HealthStatus.FAIL
    assert r.failure_class == FailureClass.TIMEOUT


def test_http_check_401_is_unauthorized(test_double_adapter):
    test_double_adapter.http_default = (401, b"Unauthorized")
    r = HTTPCheck("http", "https://host/api", "GET", 200, 10.0, test_double_adapter).run()
    assert r.failure_class == FailureClass.UNAUTHORIZED


def test_http_check_403_is_forbidden(test_double_adapter):
    test_double_adapter.http_default = (403, b"Forbidden")
    r = HTTPCheck("http", "https://host/api", "GET", 200, 10.0, test_double_adapter).run()
    assert r.failure_class == FailureClass.FORBIDDEN


def test_http_check_skips_when_prereq_failed(test_double_adapter):
    from app.flowhub.health.models import HealthCheckResult
    tls_fail = HealthCheckResult.fail(
        "tls", CheckCategory.TLS, "host:443", FailureClass.TLS_FAILURE, "tls failed"
    )
    r = HTTPCheck(
        "http", "https://host/", "GET", 200, 10.0, test_double_adapter,
        prerequisite_result=tls_fail
    ).run()
    assert r.status == HealthStatus.SKIP


def test_http_check_status_code_in_details(test_double_adapter):
    test_double_adapter.http_default = (200, b"ok")
    r = HTTPCheck("http", "https://host/", "GET", 200, 10.0, test_double_adapter).run()
    assert r.details.get("status_code") == 200


def test_http_check_category(test_double_adapter):
    r = HTTPCheck("http", "https://host/", "GET", 200, 10.0, test_double_adapter).run()
    assert r.category == CheckCategory.HTTP


# ============================================================
# 5. Auth Check
# ============================================================


def test_auth_check_pass(test_double_adapter):
    test_double_adapter.auth_default = (True, 200)
    r = AuthCheck("auth", "https://host/api", "user", "pass", 10.0, test_double_adapter).run()
    assert r.status == HealthStatus.PASS


def test_auth_check_fail_on_unauthorized(test_double_adapter):
    test_double_adapter.auth_default = AuthenticationError("401")
    r = AuthCheck("auth", "https://host/api", "user", "pass", 10.0, test_double_adapter).run()
    assert r.status == HealthStatus.FAIL
    assert r.failure_class == FailureClass.UNAUTHORIZED


def test_auth_check_fail_on_forbidden(test_double_adapter):
    test_double_adapter.auth_default = AccessForbiddenError("403")
    r = AuthCheck("auth", "https://host/api", "user", "pass", 10.0, test_double_adapter).run()
    assert r.status == HealthStatus.FAIL
    assert r.failure_class == FailureClass.FORBIDDEN


def test_auth_check_maps_non_auth_errors_to_invalid_response(test_double_adapter):
    """Auth check must never return DNS/TLS/timeout - maps to INVALID_RESPONSE."""
    test_double_adapter.auth_default = DNSResolutionError("unexpected")
    r = AuthCheck("auth", "https://host/api", "user", "pass", 10.0, test_double_adapter).run()
    assert r.failure_class == FailureClass.INVALID_RESPONSE


def test_auth_check_detail_does_not_contain_password(test_double_adapter):
    test_double_adapter.auth_default = (True, 200)
    r = AuthCheck("auth", "https://host/api", "user", "pass", 10.0, test_double_adapter).run()
    for key in r.details:
        assert "password" not in key.lower()
    for value in r.details.values():
        assert str(value) != "pass"


def test_auth_check_skips_when_prereq_failed(test_double_adapter):
    from app.flowhub.health.models import HealthCheckResult
    http_fail = HealthCheckResult.fail(
        "http", CheckCategory.HTTP, "url", FailureClass.TIMEOUT, "timeout"
    )
    r = AuthCheck(
        "auth", "https://host/api", "user", "pass", 10.0, test_double_adapter,
        prerequisite_result=http_fail
    ).run()
    assert r.status == HealthStatus.SKIP


def test_auth_check_category(test_double_adapter):
    r = AuthCheck("auth", "https://host/api", "user", "pass", 10.0, test_double_adapter).run()
    assert r.category == CheckCategory.AUTH


# ============================================================
# 6. Config Check
# ============================================================


def test_config_check_pass_when_all_keys_present():
    config = {"FLOWHUB_SECRET_KEY": "x", "FLOWHUB_DATABASE_URL": "postgresql://..."}
    r = ConfigCheck("config", ["FLOWHUB_SECRET_KEY", "FLOWHUB_DATABASE_URL"], [], config).run()
    assert r.status == HealthStatus.PASS


def test_config_check_fail_when_required_key_missing():
    r = ConfigCheck("config", ["FLOWHUB_SECRET_KEY"], [], {}).run()
    assert r.status == HealthStatus.FAIL
    assert r.failure_class == FailureClass.CONFIGURATION_ERROR


def test_config_check_warn_when_optional_key_missing():
    config = {"FLOWHUB_SECRET_KEY": "x"}
    r = ConfigCheck("config", ["FLOWHUB_SECRET_KEY"], ["FLOWHUB_SMTP_HOST"], config).run()
    assert r.status == HealthStatus.WARN


def test_config_check_lists_missing_required_in_message():
    r = ConfigCheck("config", ["FLOWHUB_MISSING_KEY"], [], {}).run()
    assert "FLOWHUB_MISSING_KEY" in r.message


def test_config_check_category():
    r = ConfigCheck("config", [], [], {}).run()
    assert r.category == CheckCategory.CONFIG


# ============================================================
# 7. Storage Check
# ============================================================


def test_storage_check_pass_when_readable_writable(test_double_adapter):
    test_double_adapter.path_default = {
        "exists": True, "readable": True, "writable": True,
        "free_gb": 50.0, "total_gb": 100.0
    }
    r = StorageCheck("storage", "/data/flowhub", test_double_adapter).run()
    assert r.status == HealthStatus.PASS


def test_storage_check_fail_when_path_missing(test_double_adapter):
    test_double_adapter.path_default = {
        "exists": False, "readable": False, "writable": False,
        "free_gb": 0.0, "total_gb": 0.0
    }
    r = StorageCheck("storage", "/data/flowhub", test_double_adapter).run()
    assert r.status == HealthStatus.FAIL
    assert r.failure_class == FailureClass.STORAGE_ERROR


def test_storage_check_warn_when_not_writable(test_double_adapter):
    test_double_adapter.path_default = {
        "exists": True, "readable": True, "writable": False,
        "free_gb": 50.0, "total_gb": 100.0
    }
    r = StorageCheck("storage", "/data/flowhub", test_double_adapter).run()
    assert r.status == HealthStatus.WARN


def test_storage_check_warn_when_low_disk_space(test_double_adapter):
    test_double_adapter.path_default = {
        "exists": True, "readable": True, "writable": True,
        "free_gb": 0.5, "total_gb": 100.0
    }
    r = StorageCheck("storage", "/data/flowhub", test_double_adapter).run()
    assert r.status == HealthStatus.WARN


def test_storage_check_fail_when_critically_low_disk(test_double_adapter):
    test_double_adapter.path_default = {
        "exists": True, "readable": True, "writable": True,
        "free_gb": 0.05, "total_gb": 100.0
    }
    r = StorageCheck("storage", "/data/flowhub", test_double_adapter).run()
    assert r.status == HealthStatus.FAIL


def test_storage_check_fail_on_adapter_error(test_double_adapter):
    test_double_adapter.path_default = StorageAdapterError("OS error")
    r = StorageCheck("storage", "/data/flowhub", test_double_adapter).run()
    assert r.status == HealthStatus.FAIL
    assert r.failure_class == FailureClass.STORAGE_ERROR


def test_storage_check_category(test_double_adapter):
    r = StorageCheck("storage", "/data/flowhub", test_double_adapter).run()
    assert r.category == CheckCategory.STORAGE


# ============================================================
# 8. Database Check
# ============================================================


def test_database_check_pass_when_connected(test_double_adapter):
    test_double_adapter.db_default = {
        "connected": True, "latency_ms": 3.0, "pending_migrations": False
    }
    r = DatabaseCheck("db", "postgresql://host/db", 5.0, test_double_adapter).run()
    assert r.status == HealthStatus.PASS


def test_database_check_fail_when_not_connected(test_double_adapter):
    test_double_adapter.db_default = {
        "connected": False, "latency_ms": 0.0, "pending_migrations": False
    }
    r = DatabaseCheck("db", "postgresql://host/db", 5.0, test_double_adapter).run()
    assert r.status == HealthStatus.FAIL
    assert r.failure_class == FailureClass.DATABASE_ERROR


def test_database_check_warn_when_pending_migrations(test_double_adapter):
    test_double_adapter.db_default = {
        "connected": True, "latency_ms": 3.0, "pending_migrations": True
    }
    r = DatabaseCheck("db", "postgresql://host/db", 5.0, test_double_adapter).run()
    assert r.status == HealthStatus.WARN


def test_database_check_fail_on_adapter_error(test_double_adapter):
    test_double_adapter.db_default = DatabaseAdapterError("pg down")
    r = DatabaseCheck("db", "postgresql://host/db", 5.0, test_double_adapter).run()
    assert r.status == HealthStatus.FAIL


def test_database_check_url_redacted_from_target(test_double_adapter):
    """DB URL credentials must not appear in the result target."""
    r = DatabaseCheck(
        "db", "postgresql://admin:secret@host:5432/db", 5.0, test_double_adapter
    ).run()
    assert "secret" not in r.target
    assert "admin" not in r.target


def test_database_check_category(test_double_adapter):
    r = DatabaseCheck("db", "postgresql://host/db", 5.0, test_double_adapter).run()
    assert r.category == CheckCategory.DATABASE


# ============================================================
# 9. Docker Check (unavailable in CP1)
# ============================================================


def test_docker_check_returns_skip(test_double_adapter):
    r = DockerCheck("docker", test_double_adapter).run()
    assert r.status == HealthStatus.SKIP


def test_docker_check_skipped_because_not_implemented(test_double_adapter):
    r = DockerCheck("docker", test_double_adapter).run()
    assert r.skipped_because == "not_implemented"


def test_docker_check_category(test_double_adapter):
    r = DockerCheck("docker", test_double_adapter).run()
    assert r.category == CheckCategory.DOCKER


# ============================================================
# 10. Integration Check (chain DNS -> TCP -> TLS -> HTTP -> Auth)
# ============================================================


def test_integration_check_all_pass(test_double_adapter):
    r = IntegrationCheck(
        "nc:integration", "nextcloud", "https://nextcloud.example.com", 10.0, test_double_adapter
    ).run()
    assert r.status == HealthStatus.PASS


def test_integration_check_chain_length_without_auth(test_double_adapter):
    chain = IntegrationCheck(
        "nc:integration", "nextcloud", "https://nextcloud.example.com", 10.0, test_double_adapter
    ).run_chain()
    # DNS, TCP, TLS, HTTP (no auth - credentials not provided)
    assert len(chain) == 4


def test_integration_check_chain_length_with_auth(test_double_adapter):
    chain = IntegrationCheck(
        "nc:integration", "nextcloud", "https://nextcloud.example.com", 10.0, test_double_adapter,
        auth_username="admin", auth_password="pass"
    ).run_chain()
    # DNS, TCP, TLS, HTTP, Auth
    assert len(chain) == 5


def test_integration_check_fails_on_dns_failure(test_double_adapter):
    test_double_adapter.dns_default = DNSResolutionError("NXDOMAIN")
    r = IntegrationCheck(
        "nc:integration", "nextcloud", "https://nextcloud.example.com", 10.0, test_double_adapter
    ).run()
    assert r.status == HealthStatus.FAIL
    assert r.failure_class == FailureClass.DNS_FAILURE


def test_integration_chain_skips_downstream_on_dns_failure(test_double_adapter):
    test_double_adapter.dns_default = DNSResolutionError("NXDOMAIN")
    chain = IntegrationCheck(
        "nc:integration", "nextcloud", "https://nextcloud.example.com", 10.0, test_double_adapter
    ).run_chain()
    # DNS fails -> TCP, TLS, HTTP are all SKIP
    tcp = next(r for r in chain if "tcp" in r.check_name)
    tls = next(r for r in chain if "tls" in r.check_name)
    http = next(r for r in chain if "http" in r.check_name)
    assert tcp.status == HealthStatus.SKIP
    assert tls.status == HealthStatus.SKIP
    assert http.status == HealthStatus.SKIP


def test_integration_check_http_no_tls_for_plain_http(test_double_adapter):
    chain = IntegrationCheck(
        "nc:integration", "nextcloud", "http://nextcloud.example.com", 10.0, test_double_adapter
    ).run_chain()
    # DNS, TCP, HTTP (no TLS for plain http)
    categories = [r.category for r in chain]
    from app.flowhub.health.models import CheckCategory
    assert CheckCategory.TLS not in categories


def test_integration_check_category(test_double_adapter):
    r = IntegrationCheck(
        "nc:integration", "nextcloud", "https://nextcloud.example.com", 10.0, test_double_adapter
    ).run()
    assert r.category == CheckCategory.INTEGRATION
