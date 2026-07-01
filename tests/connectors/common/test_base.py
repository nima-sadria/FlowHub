import asyncio

import pytest

from app.connectors.common.auth import AuthConfig
from app.connectors.common.base import DestinationConnector, SourceConnector
from app.connectors.common.health import HealthResult, HealthStatus
from app.connectors.common.test_result import ConnectionTestResult
from app.connectors.common.types import ConnectorCapabilities, ConnectorType


# -- Minimal concrete implementations for contract verification ----------------

class _MinimalSource(SourceConnector):
    connector_id = "test-source"

    def capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities()

    async def connect(self, auth: AuthConfig) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def health(self) -> HealthResult:
        return HealthResult(status=HealthStatus.HEALTHY)

    async def test_connection(self, auth: AuthConfig) -> ConnectionTestResult:
        return ConnectionTestResult(ok=True, message="ok")


class _MinimalDestination(DestinationConnector):
    connector_id = "test-dest"

    def capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities()

    async def connect(self, auth: AuthConfig) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def health(self) -> HealthResult:
        return HealthResult(status=HealthStatus.HEALTHY)

    async def test_connection(self, auth: AuthConfig) -> ConnectionTestResult:
        return ConnectionTestResult(ok=True, message="ok")


# -- ABC instantiation guard ---------------------------------------------------

def test_source_connector_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        SourceConnector()  # type: ignore[abstract]


def test_destination_connector_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        DestinationConnector()  # type: ignore[abstract]


# -- Concrete implementations satisfy the contract ----------------------------

def test_minimal_source_instantiates():
    s = _MinimalSource()
    assert s.connector_id == "test-source"
    assert s.connector_type == ConnectorType.SOURCE


def test_minimal_destination_instantiates():
    d = _MinimalDestination()
    assert d.connector_id == "test-dest"
    assert d.connector_type == ConnectorType.DESTINATION


def test_source_optional_methods_raise():
    s = _MinimalSource()
    with pytest.raises(NotImplementedError):
        asyncio.run(s.list_folders())
    with pytest.raises(NotImplementedError):
        asyncio.run(s.list_files("/"))
    with pytest.raises(NotImplementedError):
        asyncio.run(s.list_worksheets("/file.xlsx"))
    with pytest.raises(NotImplementedError):
        asyncio.run(s.read_worksheet("/file.xlsx", "Sheet1"))
    with pytest.raises(NotImplementedError):
        asyncio.run(s.get_metadata("/"))
    with pytest.raises(NotImplementedError):
        asyncio.run(s.watch_changes("/"))


def test_destination_optional_methods_raise():
    d = _MinimalDestination()
    with pytest.raises(NotImplementedError):
        asyncio.run(d.list_products())
    with pytest.raises(NotImplementedError):
        asyncio.run(d.read_inventory(1))


def test_source_connect_and_health():
    s = _MinimalSource()
    auth = AuthConfig(auth_type="none")
    asyncio.run(s.connect(auth))
    result = asyncio.run(s.health())
    assert result.status == HealthStatus.HEALTHY


def test_destination_test_connection():
    d = _MinimalDestination()
    auth = AuthConfig(auth_type="none")
    result = asyncio.run(d.test_connection(auth))
    assert result.ok is True
    assert result.message == "ok"


# -- Public __init__ re-exports ------------------------------------------------

def test_common_package_exports():
    from app.connectors.common import (  # noqa: F401
        AuthConfig,
        ConnectorCapabilities,
        ConnectorError,
        ConnectorErrorCode,
        ConnectorID,
        ConnectorType,
        ConnectionTestResult,
        DestinationConnector,
        HealthResult,
        HealthStatus,
        RateLimitConfig,
        RetryConfig,
        SourceConnector,
    )
    assert SourceConnector is not None
    assert DestinationConnector is not None
