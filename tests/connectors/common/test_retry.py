from app.connectors.common.errors import ConnectorErrorCode
from app.connectors.common.retry import RetryConfig


def test_retry_defaults():
    r = RetryConfig()
    assert r.max_attempts == 3
    assert r.base_delay_s == 1.0
    assert r.max_delay_s == 30.0
    assert r.backoff_factor == 2.0


def test_retry_default_retryable_codes():
    r = RetryConfig()
    assert ConnectorErrorCode.RATE_LIMITED in r.retryable_codes
    assert ConnectorErrorCode.TIMEOUT in r.retryable_codes
    assert ConnectorErrorCode.NETWORK in r.retryable_codes
    assert ConnectorErrorCode.AUTH_FAILED not in r.retryable_codes
    assert ConnectorErrorCode.NOT_FOUND not in r.retryable_codes


def test_retry_frozen():
    import pytest
    r = RetryConfig()
    with pytest.raises(Exception):
        r.max_attempts = 10  # type: ignore[misc]


def test_retry_custom():
    r = RetryConfig(max_attempts=5, base_delay_s=0.5)
    assert r.max_attempts == 5
    assert r.base_delay_s == 0.5


def test_retry_custom_codes():
    codes = frozenset({ConnectorErrorCode.AUTH_FAILED})
    r = RetryConfig(retryable_codes=codes)
    assert ConnectorErrorCode.AUTH_FAILED in r.retryable_codes
    assert ConnectorErrorCode.TIMEOUT not in r.retryable_codes
