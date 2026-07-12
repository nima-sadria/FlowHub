"""Channel-neutral Write Pipeline adapter contracts."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol


class WriteItemContract(Protocol):
    channel_product_id: str
    proposed_price: float
    pre_write_snapshot_json: dict[str, object]


@dataclass(frozen=True)
class ChannelWriteCapabilities:
    channel_type: str
    channel_ids: tuple[str, ...]
    operation_types: tuple[str, ...]
    stock_write_supported: bool = False
    scheduler_supported: bool = False
    automatic_apply_supported: bool = False


@dataclass(frozen=True)
class ChannelWriteContext:
    get_setting: Callable[[str], str | None]
    requested_by: str


class ChannelWriteAdapter(Protocol):
    def supports(self, channel_id: str, operation_type: str) -> bool:
        """Return True when this adapter can execute the channel operation."""

    def get_capabilities(self) -> ChannelWriteCapabilities:
        """Return adapter capabilities without exposing secrets."""

    def validate_item(self, item: Mapping[str, object]) -> None:
        """Validate provider-specific item requirements before a Dry Run is persisted."""

    async def execute_item(
        self, item: WriteItemContract, context: ChannelWriteContext
    ) -> dict[str, object]:
        """Execute one already-approved write item."""

    async def verify_item(
        self, item: WriteItemContract, context: ChannelWriteContext
    ) -> dict[str, object]:
        """Read back one updated item after a successful write."""
