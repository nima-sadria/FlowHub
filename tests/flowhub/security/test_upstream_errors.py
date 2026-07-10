from __future__ import annotations

from app.connectors.common.errors import ConnectorError, ConnectorErrorCode
from app.flowhub.integrations.errors import IntegrationError
from app.flowhub.security.upstream_errors import is_unsafe_upstream_content, normalize_upstream_error, upstream_http_status


def test_connector_error_maps_to_safe_source_auth_contract():
    error = ConnectorError(
        code=ConnectorErrorCode.AUTH_FAILED,
        message="password=private-value",
        provider="nextcloud",
        http_status=401,
    )

    assert normalize_upstream_error(error) == {
        "code": "SOURCE_AUTH_FAILED",
        "message": "Authentication failed.",
        "source": "nextcloud",
        "http_status": 401,
    }


def test_timeout_dns_tls_and_rate_limit_codes_remain_safe():
    timeout = ConnectorError(ConnectorErrorCode.TIMEOUT, "request timeout", "woocommerce")
    dns = ConnectorError(ConnectorErrorCode.NETWORK, "dns resolution failed", "nextcloud")
    tls = ConnectorError(ConnectorErrorCode.NETWORK, "TLS certificate failed", "nextcloud")
    rate = ConnectorError(ConnectorErrorCode.RATE_LIMITED, "429", "woocommerce", http_status=429)

    assert normalize_upstream_error(timeout)["code"] == "CHANNEL_TIMEOUT"
    assert normalize_upstream_error(dns)["code"] == "SOURCE_DNS_ERROR"
    assert normalize_upstream_error(tls)["code"] == "SOURCE_TLS_ERROR"
    assert normalize_upstream_error(rate)["code"] == "CHANNEL_RATE_LIMITED"


def test_html_and_oversized_upstream_bodies_are_detected_and_never_returned():
    html = "<!DOCTYPE html><html><body>proxy password=private-value</body></html>"
    error = IntegrationError("nextcloud", "/remote.php/dav/files/woo/", html, status_code=502)

    assert is_unsafe_upstream_content(html) is True
    assert is_unsafe_upstream_content("x" * 513) is True
    assert normalize_upstream_error(error)["message"] == "The external service returned an invalid or unavailable response."
    assert upstream_http_status(error) == 502
