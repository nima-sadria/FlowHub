from __future__ import annotations

from abc import ABC, abstractmethod

from .auth import AuthConfig
from .health import HealthResult
from .test_result import ConnectionTestResult
from .types import ConnectorCapabilities, ConnectorID, ConnectorType


class SourceConnector(ABC):
    """Abstract base for all FlowHub source connectors.

    Each concrete subclass isolates all provider-specific protocol knowledge
    (WebDAV, OCS, Sheets API, etc.) behind this interface. No FlowHub business
    logic outside app/connectors/sources/<provider>/ may call provider APIs
    directly.
    """

    connector_id: ConnectorID
    connector_type: ConnectorType = ConnectorType.SOURCE

    @abstractmethod
    def capabilities(self) -> ConnectorCapabilities:
        """Declare which optional methods this connector supports."""
        ...

    @abstractmethod
    async def connect(self, auth: AuthConfig) -> None:
        """Establish and verify a connection to the source."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Release any held connections or resources."""
        ...

    @abstractmethod
    async def health(self) -> HealthResult:
        """Return the current health of the connection."""
        ...

    @abstractmethod
    async def test_connection(self, auth: AuthConfig) -> ConnectionTestResult:
        """Perform a lightweight connectivity probe without storing state."""
        ...

    # -- Optional methods - raise NotImplementedError when cap is False ---------

    async def list_folders(self, path: str = "/") -> list[str]:
        raise NotImplementedError(f"{type(self).__name__} does not support list_folders")

    async def list_files(self, path: str = "/") -> list[str]:
        raise NotImplementedError(f"{type(self).__name__} does not support list_files")

    async def list_worksheets(self, file_path: str) -> list[str]:
        raise NotImplementedError(f"{type(self).__name__} does not support list_worksheets")

    async def read_worksheet(self, file_path: str, worksheet: str) -> list[dict]:
        raise NotImplementedError(f"{type(self).__name__} does not support read_worksheet")

    async def get_metadata(self, path: str) -> dict:
        raise NotImplementedError(f"{type(self).__name__} does not support get_metadata")

    async def watch_changes(self, path: str) -> None:
        raise NotImplementedError(f"{type(self).__name__} does not support watch_changes")


class DestinationConnector(ABC):
    """Abstract base for all FlowHub destination connectors.

    Each concrete subclass isolates all provider-specific protocol knowledge
    (WooCommerce REST, etc.) behind this interface. No FlowHub business logic
    outside app/connectors/destinations/<provider>/ may call provider APIs
    directly.

    All methods are READ-ONLY. No write path is permitted in FlowHub Beta.
    """

    connector_id: ConnectorID
    connector_type: ConnectorType = ConnectorType.DESTINATION

    @abstractmethod
    def capabilities(self) -> ConnectorCapabilities:
        """Declare which optional methods this connector supports."""
        ...

    @abstractmethod
    async def connect(self, auth: AuthConfig) -> None:
        """Establish and verify a connection to the destination."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Release any held connections or resources."""
        ...

    @abstractmethod
    async def health(self) -> HealthResult:
        """Return the current health of the connection."""
        ...

    @abstractmethod
    async def test_connection(self, auth: AuthConfig) -> ConnectionTestResult:
        """Perform a lightweight connectivity probe without storing state."""
        ...

    # -- Optional methods - raise NotImplementedError when cap is False ---------

    async def list_products(self, page: int = 1, per_page: int = 100) -> list[dict]:
        raise NotImplementedError(f"{type(self).__name__} does not support list_products")

    async def read_inventory(self, product_id: int) -> dict:
        raise NotImplementedError(f"{type(self).__name__} does not support read_inventory")
