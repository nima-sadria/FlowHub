from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# Stable string identifier for a connector, e.g. "nextcloud", "woocommerce".
ConnectorID = str


class ConnectorType(Enum):
    SOURCE = "source"
    DESTINATION = "destination"


@dataclass(frozen=True)
class ConnectorCapabilities:
    # Source capabilities
    can_list_folders: bool = False
    can_list_files: bool = False
    can_list_worksheets: bool = False
    can_read_worksheet: bool = False
    can_get_metadata: bool = False
    can_watch_changes: bool = False
    # Destination capabilities
    can_list_products: bool = False
    can_read_inventory: bool = False
    # Escape hatch for provider-specific extensions
    extra: dict[str, bool] = field(default_factory=dict)
