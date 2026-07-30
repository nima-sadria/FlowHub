"""Provider adapters.  No caller receives a raw Navasan response."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from app.connectors.common.safe_http import (
    SafeHttpNetworkError,
    SafeHttpTimeout,
    SafeJsonHttpClient,
)


class ExchangeRateProviderError(RuntimeError):
    def __init__(self, code: str, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class ProviderRate:
    external_symbol: str
    value: Decimal
    change: Decimal | None
    provider_timestamp: datetime | None


@dataclass(frozen=True)
class ProviderUsage:
    daily_usage: int | None
    hourly_usage: int | None
    monthly_usage: int | None
    last_use: str | None


class ExchangeRateProvider(Protocol):
    provider_id: str

    def list_supported_rates(self) -> list[str]: ...
    def fetch_latest_rates(self) -> list[ProviderRate]: ...
    def fetch_usage(self) -> ProviderUsage: ...
    def test_connection(self) -> None: ...


class NavasanExchangeRateProvider:
    provider_id = "navasan"
    OFFICIAL_BASE_URL = "https://api.navasan.tech"

    def __init__(self, api_key: str, *, base_url: str = OFFICIAL_BASE_URL, timeout: int = 10) -> None:
        if base_url.rstrip("/") != self.OFFICIAL_BASE_URL:
            raise ExchangeRateProviderError("invalid_provider_url", "Only the official Navasan HTTPS endpoint is allowed.")
        if not api_key.strip():
            raise ExchangeRateProviderError("missing_credentials", "Navasan API credentials are not configured.")
        self._api_key = api_key.strip()
        self._base_url = self.OFFICIAL_BASE_URL
        self._timeout = max(2, min(int(timeout), 30))

    def list_supported_rates(self) -> list[str]:
        return [
            "usd_sell", "usd_buy", "aed_sell", "eur", "gbp", "cad", "aud", "try",
            "sekkeh", "18ayar", "usdt", "btc", "eth",
        ]

    def _get(self, endpoint: str) -> Any:
        try:
            # Query parameters are never logged; callers only receive normalized data.
            response = SafeJsonHttpClient().get(
                f"{self._base_url}/{endpoint}/",
                params={"api_key": self._api_key},
                timeout=self._timeout,
            )
        except SafeHttpTimeout as exc:
            raise ExchangeRateProviderError("timeout", "Navasan request timed out.") from exc
        except SafeHttpNetworkError as exc:
            raise ExchangeRateProviderError("network_error", "Navasan could not be reached.") from exc
        if response.status_code in {400, 401, 422, 429, 503}:
            code = {400: "bad_request", 401: "authentication_failed", 422: "invalid_request", 429: "rate_limited", 503: "provider_unavailable"}[response.status_code]
            raise ExchangeRateProviderError(code, "Navasan rejected or could not serve the request.", status=response.status_code)
        if response.status_code != 200:
            raise ExchangeRateProviderError("provider_error", "Navasan returned an unexpected response.", status=response.status_code)
        try:
            return response.json()
        except ValueError as exc:
            raise ExchangeRateProviderError("malformed_json", "Navasan returned malformed JSON.") from exc

    @staticmethod
    def _decimal(value: Any, *, field: str) -> Decimal:
        if value in (None, "") or isinstance(value, bool):
            raise ExchangeRateProviderError("invalid_numeric_value", f"Navasan returned an invalid {field}.")
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ExchangeRateProviderError("invalid_numeric_value", f"Navasan returned an invalid {field}.") from exc
        if not parsed.is_finite():
            raise ExchangeRateProviderError("invalid_numeric_value", f"Navasan returned an invalid {field}.")
        return parsed

    def fetch_latest_rates(self) -> list[ProviderRate]:
        payload = self._get("latest")
        if not isinstance(payload, dict):
            raise ExchangeRateProviderError("malformed_response", "Navasan latest response was not an object.")
        result: list[ProviderRate] = []
        invalid_item = False
        for symbol, entry in payload.items():
            if symbol not in self.list_supported_rates() or not isinstance(entry, dict):
                continue
            try:
                value = self._decimal(entry.get("value"), field="value")
            except ExchangeRateProviderError:
                # Keep valid items from a partial provider response. A response
                # containing no valid configured item is rejected below.
                invalid_item = True
                continue
            timestamp = entry.get("timestamp")
            provider_timestamp = None
            if timestamp not in (None, ""):
                try:
                    provider_timestamp = datetime.fromtimestamp(int(timestamp), tz=timezone.utc).replace(tzinfo=None)
                except (TypeError, ValueError, OverflowError):
                    provider_timestamp = None
            change = None
            if entry.get("change") not in (None, ""):
                try:
                    change = self._decimal(entry.get("change"), field="change")
                except ExchangeRateProviderError:
                    change = None
            result.append(ProviderRate(symbol, value, change, provider_timestamp))
        if not result:
            code = "invalid_numeric_value" if invalid_item else "missing_rate_items"
            message = (
                "Navasan returned an invalid numeric value for every supported rate item."
                if invalid_item
                else "Navasan returned no valid supported rate items."
            )
            raise ExchangeRateProviderError(code, message)
        return result

    def fetch_usage(self) -> ProviderUsage:
        payload = self._get("usage")
        if not isinstance(payload, dict):
            raise ExchangeRateProviderError("malformed_response", "Navasan usage response was not an object.")

        def integer(name: str) -> int:
            try:
                value = int(payload[name])
            except (KeyError, TypeError, ValueError) as exc:
                raise ExchangeRateProviderError(
                    "malformed_usage",
                    "Navasan returned malformed usage counters.",
                ) from exc
            if value < 0:
                raise ExchangeRateProviderError(
                    "malformed_usage",
                    "Navasan returned malformed usage counters.",
                )
            return value

        return ProviderUsage(integer("daily_usage"), integer("hourly_usage"), integer("monthly_usage"), str(payload.get("last_use")) if payload.get("last_use") else None)

    def test_connection(self) -> None:
        self._get("latest")
