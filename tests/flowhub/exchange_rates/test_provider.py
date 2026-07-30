from __future__ import annotations

import logging
import traceback
from decimal import Decimal

import httpx
import pytest

from app.connectors.common.safe_http import _SensitiveUrlFilter
from app.flowhub.exchange_rates.provider import ExchangeRateProviderError, NavasanExchangeRateProvider


class FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def test_latest_normalizes_string_decimal_and_timestamp(monkeypatch):
    monkeypatch.setattr(
        "httpx.get",
        lambda *args, **kwargs: FakeResponse(200, {"usd_sell": {"value": "12345.6700", "change": "-10", "timestamp": 1700000000}, "unknown": {"value": "1"}}),
    )
    rate = NavasanExchangeRateProvider("secret").fetch_latest_rates()[0]
    assert rate.value == Decimal("12345.6700")
    assert rate.change == Decimal("-10")
    assert rate.provider_timestamp is not None


@pytest.mark.parametrize("status,code", [(400, "bad_request"), (401, "authentication_failed"), (422, "invalid_request"), (429, "rate_limited"), (503, "provider_unavailable")])
def test_documented_http_errors_are_normalized(monkeypatch, status, code):
    monkeypatch.setattr("httpx.get", lambda *args, **kwargs: FakeResponse(status, {"message": "secret should not escape"}))
    with pytest.raises(ExchangeRateProviderError) as exc:
        NavasanExchangeRateProvider("secret").fetch_latest_rates()
    assert exc.value.code == code
    assert "secret" not in str(exc.value)


def test_invalid_value_and_malformed_json(monkeypatch):
    monkeypatch.setattr("httpx.get", lambda *args, **kwargs: FakeResponse(200, {"usd_sell": {"value": "NaN"}}))
    with pytest.raises(ExchangeRateProviderError, match="invalid"):
        NavasanExchangeRateProvider("secret").fetch_latest_rates()
    monkeypatch.setattr("httpx.get", lambda *args, **kwargs: FakeResponse(200, ValueError("bad json")))
    with pytest.raises(ExchangeRateProviderError) as exc:
        NavasanExchangeRateProvider("secret").fetch_latest_rates()
    assert exc.value.code == "malformed_json"


def test_only_official_https_origin_is_allowed():
    with pytest.raises(ExchangeRateProviderError, match="official"):
        NavasanExchangeRateProvider("secret", base_url="http://api.navasan.tech")


def test_timeout_and_network_failures_are_redacted(monkeypatch):
    credential = "must-" + "not-escape"
    request = httpx.Request(
        "GET", f"https://api.navasan.tech/latest/?api_key={credential}"
    )
    monkeypatch.setattr(
        "httpx.get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            httpx.TimeoutException("timed out", request=request)
        ),
    )
    with pytest.raises(ExchangeRateProviderError) as timeout:
        NavasanExchangeRateProvider(credential).fetch_latest_rates()
    assert timeout.value.code == "timeout"
    assert "must-not-escape" not in str(timeout.value)
    assert "must-not-escape" not in "".join(
        traceback.format_exception(timeout.value)
    )

    monkeypatch.setattr(
        "httpx.get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            httpx.ConnectError("dns failure", request=request)
        ),
    )
    with pytest.raises(ExchangeRateProviderError) as network:
        NavasanExchangeRateProvider(credential).fetch_latest_rates()
    assert network.value.code == "network_error"
    assert "must-not-escape" not in str(network.value)


def test_transport_logging_redacts_query_credentials():
    record = logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="HTTP Request: GET %s",
        args=("https://api.navasan.tech/latest/?api_key=must-not-escape",),
        exc_info=None,
    )
    _SensitiveUrlFilter().filter(record)
    rendered = record.getMessage()
    assert "must-not-escape" not in rendered
    assert "api_key=********" in rendered


def test_usage_requires_complete_non_negative_counters(monkeypatch):
    monkeypatch.setattr(
        "httpx.get",
        lambda *args, **kwargs: FakeResponse(
            200,
            {
                "daily_usage": "7",
                "hourly_usage": "2",
                "monthly_usage": "30",
                "last_use": "2026-01-01 12:00:00",
                "api_key": "must-be-discarded",
            },
        ),
    )
    usage = NavasanExchangeRateProvider("secret").fetch_usage()
    assert usage.daily_usage == 7
    assert not hasattr(usage, "api_key")

    monkeypatch.setattr(
        "httpx.get",
        lambda *args, **kwargs: FakeResponse(
            200, {"daily_usage": "bad", "hourly_usage": "2"}
        ),
    )
    with pytest.raises(ExchangeRateProviderError) as malformed:
        NavasanExchangeRateProvider("secret").fetch_usage()
    assert malformed.value.code == "malformed_usage"
