"""Write Pipeline adapter registry."""

from __future__ import annotations

from app.flowhub.write_pipeline.adapters import ChannelWriteAdapter


class ChannelWriteAdapterRegistry:
    def __init__(self) -> None:
        self._adapters: list[ChannelWriteAdapter] = []

    def register(self, adapter: ChannelWriteAdapter) -> None:
        self._adapters.append(adapter)

    def get(self, channel_id: str, operation_type: str) -> ChannelWriteAdapter | None:
        for adapter in self._adapters:
            if adapter.supports(channel_id, operation_type):
                return adapter
        return None

    def adapters(self) -> tuple[ChannelWriteAdapter, ...]:
        return tuple(self._adapters)


_DEFAULT_REGISTRY: ChannelWriteAdapterRegistry | None = None


def default_write_adapter_registry() -> ChannelWriteAdapterRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        from app.connectors.destinations.woocommerce.write_adapter import WooCommercePriceWriteAdapter

        registry = ChannelWriteAdapterRegistry()
        registry.register(WooCommercePriceWriteAdapter())
        _DEFAULT_REGISTRY = registry
    return _DEFAULT_REGISTRY
