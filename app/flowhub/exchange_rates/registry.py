"""Provider registry; business logic depends on this contract, not Navasan."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .provider import ExchangeRateProvider, NavasanExchangeRateProvider


@dataclass(frozen=True)
class ProviderRegistration:
    provider_type: str
    official_base_url: str
    factory: Callable[[str, str, int], ExchangeRateProvider]


class ExchangeRateProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, ProviderRegistration] = {}

    def register(self, registration: ProviderRegistration) -> None:
        self._providers[registration.provider_type] = registration

    def build(
        self,
        provider_type: str,
        *,
        api_key: str,
        base_url: str,
        timeout: int,
    ) -> ExchangeRateProvider:
        registration = self._providers.get(provider_type)
        if registration is None:
            raise ValueError(f"Unknown exchange-rate provider type: {provider_type}")
        return registration.factory(api_key, base_url, timeout)

    def official_base_url(self, provider_type: str) -> str:
        registration = self._providers.get(provider_type)
        if registration is None:
            raise ValueError(f"Unknown exchange-rate provider type: {provider_type}")
        return registration.official_base_url


default_provider_registry = ExchangeRateProviderRegistry()
default_provider_registry.register(
    ProviderRegistration(
        provider_type="navasan",
        official_base_url=NavasanExchangeRateProvider.OFFICIAL_BASE_URL,
        factory=lambda key, url, timeout: NavasanExchangeRateProvider(
            key, base_url=url, timeout=timeout
        ),
    )
)
