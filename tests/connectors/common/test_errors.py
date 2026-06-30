import pytest

from app.connectors.common.errors import ConnectorError, ConnectorErrorCode


def test_error_code_values():
    assert ConnectorErrorCode.AUTH_FAILED.value == "auth_failed"
    assert ConnectorErrorCode.RATE_LIMITED.value == "rate_limited"
    assert ConnectorErrorCode.TIMEOUT.value == "timeout"
    assert ConnectorErrorCode.NETWORK.value == "network"
    assert ConnectorErrorCode.NOT_FOUND.value == "not_found"
    assert ConnectorErrorCode.PERMISSION.value == "permission"
    assert ConnectorErrorCode.PROVIDER_ERROR.value == "provider_error"
    assert ConnectorErrorCode.UNKNOWN.value == "unknown"


def test_connector_error_is_exception():
    err = ConnectorError(
        code=ConnectorErrorCode.AUTH_FAILED,
        message="invalid credentials",
        provider="nextcloud",
    )
    assert isinstance(err, Exception)


def test_connector_error_str():
    err = ConnectorError(
        code=ConnectorErrorCode.AUTH_FAILED,
        message="invalid credentials",
        provider="nextcloud",
        http_status=401,
    )
    s = str(err)
    assert "nextcloud" in s
    assert "auth_failed" in s
    assert "401" in s


def test_connector_error_retryable_default():
    err = ConnectorError(code=ConnectorErrorCode.NETWORK, message="reset", provider="nc")
    assert err.retryable is False


def test_connector_error_retryable_set():
    err = ConnectorError(
        code=ConnectorErrorCode.TIMEOUT,
        message="timed out",
        provider="nc",
        retryable=True,
    )
    assert err.retryable is True


def test_connector_error_can_be_raised_and_caught():
    with pytest.raises(ConnectorError) as exc_info:
        raise ConnectorError(
            code=ConnectorErrorCode.NOT_FOUND,
            message="file not found",
            provider="nextcloud",
            http_status=404,
        )
    assert exc_info.value.code == ConnectorErrorCode.NOT_FOUND
    assert exc_info.value.http_status == 404


def test_connector_error_no_http_status():
    err = ConnectorError(code=ConnectorErrorCode.NETWORK, message="refused", provider="nc")
    s = str(err)
    assert "HTTP" not in s
